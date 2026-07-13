"""Bounded canonical-JSONL artifact storage for persona full-profile inputs.

This module is deliberately a storage envelope, not a logical manifest.  It
does not accept or assert a logical schema or logical-manifest digest.  A
caller that gives the rows meaning must bind that separate logical receipt to
``storage_envelope_sha256`` returned here.

Rows are consumed exactly once and are never collected or joined.  A complete
artifact is built in a fresh sibling directory, read back, and then published
as one directory with an atomic no-replace rename.  ``READY.json`` is written
last.  Existing complete artifacts are strict no-ops only after two bounded
readbacks surrounding a streaming recomputation of the expected envelope.
Partial or conflicting artifacts are neither adopted nor deleted.

No supported portable rename primitive binds the already-verified source
directory inode as an atomic precondition of the rename.  Every receipt is
therefore explicitly marked ``formal_publication_attested=False`` with the
``source_directory_inode_not_bound_by_rename`` blocker.  Formal full-scale
composition must refuse that receipt; the no-replace operation remains useful
only as a non-authorizing planning-artifact publication boundary.

The iterator APIs yield data before final whole-artifact verification.  Their
result is trustworthy only after normal exhaustion; callers must stage any
derived publication until that point.  ``verify_jsonl_artifact`` performs the
complete read without exposing provisional rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable, Iterator

try:  # Support both package imports and the repository's direct-import style.
    from . import persona_storage as storage
except ImportError:  # pragma: no cover
    import persona_storage as storage


STORAGE_ENVELOPE_SCHEMA = "kcs.persona.streaming-jsonl-storage-envelope/v1"
READY_SCHEMA = "kcs.persona.streaming-jsonl-ready/v1"
SCHEMA_VERSION = 1
CANONICALIZATION = "utf8-json-sort-keys-compact-no-floats-lf/v1"
FORMAL_PUBLICATION_BLOCKER = "source_directory_inode_not_bound_by_rename"
FORMAL_PUBLICATION_BLOCKERS = (FORMAL_PUBLICATION_BLOCKER,)

STORAGE_ENVELOPE_NAME = "storage-envelope.json"
READY_NAME = "READY.json"
SHARDS_DIRECTORY_NAME = "shards"
SHARD_NAME_TEMPLATE = "shard-{ordinal:06d}.jsonl"

MAX_ENVELOPE_BYTES = 8 * 1024 * 1024
ABSOLUTE_MAX_ROW_BYTES = 8 * 1024 * 1024
ABSOLUTE_MAX_ROWS_PER_SHARD = 65_536
ABSOLUTE_MAX_SHARD_BYTES = 32 * 1024 * 1024
ABSOLUTE_MAX_SHARDS = 4_096
ABSOLUTE_MAX_TOTAL_ROWS = 2_000_000
ABSOLUTE_MAX_TOTAL_BYTES = 128 * 1024 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_INTEGER = 2**63 - 1

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class PersonaStreamingStorageError(RuntimeError):
    """Raised when a streaming artifact violates its storage contract."""


def _strict_positive_integer(value: object, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PersonaStreamingStorageError(f"{label} must be an integer")
    if value < 1 or value > maximum:
        raise PersonaStreamingStorageError(
            f"{label} must be between 1 and {maximum}"
        )
    return value


@dataclass(frozen=True)
class ArtifactLimits:
    """Exact persisted bounds for one artifact.

    The defaults cover the current per-person full event/schedule envelope.
    Formal consumers should pass a narrower instance where their logical
    contract has lower row or total bounds.
    """

    max_row_bytes: int = 2 * 1024 * 1024
    max_rows_per_shard: int = 512
    max_shard_bytes: int = 32 * 1024 * 1024
    max_shards: int = 256
    max_total_rows: int = 1_000_000
    max_total_bytes: int = 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        _strict_positive_integer(
            self.max_row_bytes, "max_row_bytes", ABSOLUTE_MAX_ROW_BYTES
        )
        _strict_positive_integer(
            self.max_rows_per_shard,
            "max_rows_per_shard",
            ABSOLUTE_MAX_ROWS_PER_SHARD,
        )
        _strict_positive_integer(
            self.max_shard_bytes,
            "max_shard_bytes",
            ABSOLUTE_MAX_SHARD_BYTES,
        )
        _strict_positive_integer(self.max_shards, "max_shards", ABSOLUTE_MAX_SHARDS)
        _strict_positive_integer(
            self.max_total_rows, "max_total_rows", ABSOLUTE_MAX_TOTAL_ROWS
        )
        _strict_positive_integer(
            self.max_total_bytes, "max_total_bytes", ABSOLUTE_MAX_TOTAL_BYTES
        )
        if self.max_row_bytes > self.max_shard_bytes:
            raise PersonaStreamingStorageError(
                "max_row_bytes must not exceed max_shard_bytes"
            )
        if self.max_shard_bytes > self.max_total_bytes:
            raise PersonaStreamingStorageError(
                "max_shard_bytes must not exceed max_total_bytes"
            )
        if self.max_rows_per_shard > self.max_total_rows:
            raise PersonaStreamingStorageError(
                "max_rows_per_shard must not exceed max_total_rows"
            )

    def as_dict(self) -> dict[str, int]:
        return {
            "max_row_bytes": self.max_row_bytes,
            "max_rows_per_shard": self.max_rows_per_shard,
            "max_shard_bytes": self.max_shard_bytes,
            "max_shards": self.max_shards,
            "max_total_rows": self.max_total_rows,
            "max_total_bytes": self.max_total_bytes,
        }


DEFAULT_LIMITS = ArtifactLimits()


@dataclass(frozen=True)
class ShardDescriptor:
    ordinal: int
    file: str
    rows: int
    bytes: int
    sha256: str


@dataclass(frozen=True)
class ArtifactReceipt:
    root: Path
    storage_envelope_sha256: str
    canonical_rows_sha256: str
    rows: int
    bytes: int
    shards: tuple[ShardDescriptor, ...]
    # Atomic no-replace protects the destination name, but the supported
    # rename APIs cannot atomically assert that the source name still denotes
    # the directory inode that was verified immediately beforehand.  Keep the
    # generic storage receipt explicitly non-formal until a stronger,
    # platform-proven publication boundary exists.
    formal_publication_attested: bool = field(default=False, init=False)
    formal_publication_blockers: tuple[str, ...] = field(
        default=FORMAL_PUBLICATION_BLOCKERS, init=False
    )


@dataclass(frozen=True)
class PublishResult:
    artifact: ArtifactReceipt
    published: bool
    formal_publication_attested: bool = field(default=False, init=False)
    formal_publication_blockers: tuple[str, ...] = field(
        default=FORMAL_PUBLICATION_BLOCKERS, init=False
    )


@dataclass(frozen=True)
class JsonlRecord:
    """One provisionally yielded canonical row and its physical locator."""

    shard_ordinal: int
    byte_offset: int
    byte_length: int
    row_sha256: str
    value: dict[str, object]


def _validate_json_value(value: object, *, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise PersonaStreamingStorageError("JSON value exceeds its depth bound")
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if value < -MAX_JSON_INTEGER or value > MAX_JSON_INTEGER:
            raise PersonaStreamingStorageError("JSON integer exceeds signed 64-bit bound")
        return
    if type(value) is list:
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise PersonaStreamingStorageError("JSON object keys must be strings")
            _validate_json_value(item, depth=depth + 1)
        return
    raise PersonaStreamingStorageError(
        f"unsupported JSON value type: {type(value).__name__}"
    )


def canonical_json_bytes(value: object) -> bytes:
    """Return the module's canonical JSON bytes, without the trailing LF."""
    _validate_json_value(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeEncodeError, ValueError, TypeError) as exc:
        raise PersonaStreamingStorageError("value cannot be canonicalized") from exc


def _canonical_file_bytes(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PersonaStreamingStorageError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_noninteger_number(value):
    raise PersonaStreamingStorageError(f"non-integer JSON number is forbidden: {value}")


def _decode_canonical_json(raw: bytes, label: str) -> object:
    if not raw.endswith(b"\n"):
        raise PersonaStreamingStorageError(f"{label} must end in exactly one LF")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_noninteger_number,
            parse_constant=_reject_noninteger_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonaStreamingStorageError(f"{label} is invalid JSON") from exc
    _validate_json_value(value)
    if _canonical_file_bytes(value) != raw:
        raise PersonaStreamingStorageError(f"{label} is not canonical JSON")
    return value


def _require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise PersonaStreamingStorageError(f"{label} must be a lowercase SHA-256")
    return value


def _absolute_lexical(path: os.PathLike[str] | str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _require_supported_platform() -> None:
    # The verifier depends on directory-relative, O_NOFOLLOW opens.  Silently
    # degrading to path checks on Windows would turn the safety property into
    # a race, so Windows remains explicitly fail-closed for now.
    if os.name == "nt":  # pragma: no cover - exercised by simulated test
        raise PersonaStreamingStorageError(
            "Windows streaming publication is unavailable without safe dir-fd primitives"
        )
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NONBLOCK")
    ):
        raise PersonaStreamingStorageError(
            "platform lacks no-follow nonblocking directory-relative file primitives"
        )
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        raise PersonaStreamingStorageError(
            "platform lacks required directory-fd open/stat support"
        )
    if os.scandir not in os.supports_fd:
        raise PersonaStreamingStorageError(
            "platform lacks required bounded directory-fd scan support"
        )
    try:
        storage._require_noreplace_directory_support()
    except storage.PersonaStorageError as exc:
        raise PersonaStreamingStorageError(str(exc)) from exc


def _is_plain_directory(metadata: os.stat_result) -> bool:
    return storage.is_plain_directory_metadata(metadata)


def _is_plain_file(metadata: os.stat_result) -> bool:
    return storage.is_plain_regular_file_metadata(metadata)


def _stable_fingerprint(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _open_directory_path(path: Path, label: str) -> tuple[int, os.stat_result]:
    """Open an absolute directory without following any path component.

    ``O_NOFOLLOW`` protects only the final component of one ``open`` call.  To
    cover every ancestor, start from a root-directory descriptor and perform
    one identity-bound, directory-relative open per normalized component.
    """
    if not path.is_absolute():
        raise PersonaStreamingStorageError(f"{label} path must be absolute: {path}")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = -1
    try:
        try:
            descriptor = os.open(path.anchor, flags)
        except OSError as exc:
            raise PersonaStreamingStorageError(
                f"cannot safely open filesystem anchor for {label}: {path.anchor}"
            ) from exc
        opened = os.fstat(descriptor)
        if not _is_plain_directory(opened):
            raise PersonaStreamingStorageError(
                f"filesystem anchor for {label} is not a plain directory"
            )
        traversed = Path(path.anchor)
        for component in path.parts[1:]:
            if component in ("", ".", ".."):
                raise PersonaStreamingStorageError(
                    f"{label} has a non-canonical path component: {path}"
                )
            try:
                apparent = os.stat(
                    component, dir_fd=descriptor, follow_symlinks=False
                )
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as exc:
                raise PersonaStreamingStorageError(
                    f"cannot safely traverse {label} component: {traversed / component}"
                ) from exc
            try:
                child_opened = os.fstat(child)
                if (
                    not _is_plain_directory(apparent)
                    or not _is_plain_directory(child_opened)
                    or (apparent.st_dev, apparent.st_ino)
                    != (child_opened.st_dev, child_opened.st_ino)
                ):
                    raise PersonaStreamingStorageError(
                        f"{label} component changed while opening: {traversed / component}"
                    )
            except BaseException:
                os.close(child)
                raise
            previous = descriptor
            descriptor = child
            opened = child_opened
            traversed = traversed / component
            os.close(previous)
        return descriptor, opened
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        raise


def _require_exact_directory_entries(
    directory_fd: int,
    expected_names: frozenset[str] | set[str],
    *,
    maximum_entries: int,
    label: str,
) -> None:
    """Compare entry names without materializing an unbounded directory."""
    expected = frozenset(expected_names)
    if len(expected) > maximum_entries:
        raise PersonaStreamingStorageError(
            f"{label} expected entry set exceeds its bound"
        )
    seen: set[str] = set()
    count = 0
    try:
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                count += 1
                if count > maximum_entries:
                    raise PersonaStreamingStorageError(
                        f"{label} exceeds its physical entry bound"
                    )
                name = entry.name
                if name not in expected or name in seen:
                    raise PersonaStreamingStorageError(
                        f"{label} has an unexpected entry set"
                    )
                seen.add(name)
    except PersonaStreamingStorageError:
        raise
    except OSError as exc:
        raise PersonaStreamingStorageError(f"cannot safely scan {label}") from exc
    if seen != expected:
        raise PersonaStreamingStorageError(f"{label} has an unexpected entry set")


def _open_directory_at(
    parent_fd: int, name: str, label: str
) -> tuple[int, os.stat_result]:
    try:
        apparent = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise PersonaStreamingStorageError(f"cannot safely open {label}") from exc
    try:
        opened = os.fstat(descriptor)
        if not _is_plain_directory(apparent) or not _is_plain_directory(opened):
            raise PersonaStreamingStorageError(f"{label} must be a plain directory")
        if (apparent.st_dev, apparent.st_ino) != (opened.st_dev, opened.st_ino):
            raise PersonaStreamingStorageError(f"{label} changed while opening")
        return descriptor, opened
    except BaseException:
        os.close(descriptor)
        raise


def _read_plain_file_at(
    parent_fd: int, name: str, maximum: int, label: str
) -> tuple[bytes, tuple[int, ...]]:
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PersonaStreamingStorageError(f"{label} is missing") from exc
    if not _is_plain_file(before) or before.st_nlink != 1:
        raise PersonaStreamingStorageError(
            f"{label} must be a single-link plain regular file"
        )
    if before.st_size > maximum:
        raise PersonaStreamingStorageError(f"{label} exceeds {maximum} bytes")
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise PersonaStreamingStorageError(f"cannot safely open {label}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not _is_plain_file(opened)
            or opened.st_nlink != 1
            or _stable_fingerprint(opened) != _stable_fingerprint(before)
        ):
            raise PersonaStreamingStorageError(f"{label} changed while opening")
        pieces = []
        remaining = maximum + 1
        while remaining:
            piece = os.read(descriptor, min(64 * 1024, remaining))
            if not piece:
                break
            pieces.append(piece)
            remaining -= len(piece)
        raw = b"".join(pieces)
        after_open = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PersonaStreamingStorageError(f"{label} disappeared while reading") from exc
    if len(raw) > maximum:
        raise PersonaStreamingStorageError(f"{label} exceeds {maximum} bytes")
    if (
        not _is_plain_file(after)
        or after.st_nlink != 1
        or _stable_fingerprint(after_open) != _stable_fingerprint(opened)
        or _stable_fingerprint(after) != _stable_fingerprint(opened)
    ):
        raise PersonaStreamingStorageError(f"{label} changed while reading")
    return raw, _stable_fingerprint(opened)


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise PersonaStreamingStorageError("short write while streaming shard")
        view = view[written:]


def _descriptor_as_dict(descriptor: ShardDescriptor) -> dict[str, object]:
    return {
        "ordinal": descriptor.ordinal,
        "file": descriptor.file,
        "rows": descriptor.rows,
        "bytes": descriptor.bytes,
        "sha256": descriptor.sha256,
    }


def _build_envelope(
    descriptors: tuple[ShardDescriptor, ...],
    *,
    limits: ArtifactLimits,
    total_rows: int,
    total_bytes: int,
    canonical_rows_sha256: str,
) -> dict[str, object]:
    return {
        "schema": STORAGE_ENVELOPE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "canonicalization": CANONICALIZATION,
        "limits": limits.as_dict(),
        "shards": [_descriptor_as_dict(item) for item in descriptors],
        "totals": {
            "rows": total_rows,
            "bytes": total_bytes,
            "shards": len(descriptors),
        },
        "canonical_rows_sha256": canonical_rows_sha256,
    }


def _receipt_from_envelope(
    root: Path, envelope: dict[str, object], envelope_sha256: str
) -> ArtifactReceipt:
    descriptors = tuple(
        ShardDescriptor(
            ordinal=row["ordinal"],
            file=row["file"],
            rows=row["rows"],
            bytes=row["bytes"],
            sha256=row["sha256"],
        )
        for row in envelope["shards"]
    )
    return ArtifactReceipt(
        root=root,
        storage_envelope_sha256=envelope_sha256,
        canonical_rows_sha256=envelope["canonical_rows_sha256"],
        rows=envelope["totals"]["rows"],
        bytes=envelope["totals"]["bytes"],
        shards=descriptors,
    )


def _validate_envelope(
    value: object, limits: ArtifactLimits
) -> dict[str, object]:
    if type(value) is not dict or set(value) != {
        "schema",
        "schema_version",
        "canonicalization",
        "limits",
        "shards",
        "totals",
        "canonical_rows_sha256",
    }:
        raise PersonaStreamingStorageError("storage envelope has an invalid field set")
    if (
        value["schema"] != STORAGE_ENVELOPE_SCHEMA
        or type(value["schema_version"]) is not int
        or value["schema_version"] != SCHEMA_VERSION
        or value["canonicalization"] != CANONICALIZATION
    ):
        raise PersonaStreamingStorageError("storage envelope schema mismatch")
    expected_limits = limits.as_dict()
    persisted_limits = value["limits"]
    if (
        type(persisted_limits) is not dict
        or set(persisted_limits) != set(expected_limits)
        or any(
            type(persisted_limits[key]) is not int
            or persisted_limits[key] != expected_limits[key]
            for key in expected_limits
        )
    ):
        raise PersonaStreamingStorageError("storage envelope limits differ from expected")
    rows = value["shards"]
    if type(rows) is not list or len(rows) > limits.max_shards:
        raise PersonaStreamingStorageError("storage envelope shard count is invalid")
    validated = []
    for ordinal, row in enumerate(rows):
        if type(row) is not dict or set(row) != {
            "ordinal", "file", "rows", "bytes", "sha256"
        }:
            raise PersonaStreamingStorageError("shard descriptor has an invalid field set")
        expected_file = f"{SHARDS_DIRECTORY_NAME}/{SHARD_NAME_TEMPLATE.format(ordinal=ordinal)}"
        if (
            type(row["ordinal"]) is not int
            or row["ordinal"] != ordinal
            or type(row["file"]) is not str
            or row["file"] != expected_file
        ):
            raise PersonaStreamingStorageError("shard descriptor order/name mismatch")
        _strict_positive_integer(
            row["rows"], "shard rows", limits.max_rows_per_shard
        )
        _strict_positive_integer(
            row["bytes"], "shard bytes", limits.max_shard_bytes
        )
        _require_digest(row["sha256"], "shard sha256")
        validated.append(dict(row))
    totals = value["totals"]
    if type(totals) is not dict or set(totals) != {"rows", "bytes", "shards"}:
        raise PersonaStreamingStorageError("storage envelope totals are invalid")
    total_rows = totals["rows"]
    total_bytes = totals["bytes"]
    total_shards = totals["shards"]
    if isinstance(total_rows, bool) or not isinstance(total_rows, int):
        raise PersonaStreamingStorageError("total rows must be an integer")
    if isinstance(total_bytes, bool) or not isinstance(total_bytes, int):
        raise PersonaStreamingStorageError("total bytes must be an integer")
    if isinstance(total_shards, bool) or not isinstance(total_shards, int):
        raise PersonaStreamingStorageError("total shards must be an integer")
    if not (0 <= total_rows <= limits.max_total_rows):
        raise PersonaStreamingStorageError("total rows exceed their bound")
    if not (0 <= total_bytes <= limits.max_total_bytes):
        raise PersonaStreamingStorageError("total bytes exceed their bound")
    if total_shards != len(validated):
        raise PersonaStreamingStorageError("total shard count disagrees")
    if total_rows != sum(row["rows"] for row in validated):
        raise PersonaStreamingStorageError("total row count disagrees")
    if total_bytes != sum(row["bytes"] for row in validated):
        raise PersonaStreamingStorageError("total byte count disagrees")
    if (total_rows == 0) != (len(validated) == 0) or (
        total_bytes == 0
    ) != (len(validated) == 0):
        raise PersonaStreamingStorageError("empty artifact totals/shards disagree")
    _require_digest(value["canonical_rows_sha256"], "canonical rows sha256")
    detached = dict(value)
    detached["limits"] = dict(value["limits"])
    detached["shards"] = validated
    detached["totals"] = dict(totals)
    return detached


def _consume_rows(
    rows: Iterable[dict[str, object]],
    *,
    limits: ArtifactLimits,
    shards_fd: int | None,
) -> tuple[dict[str, object], bytes]:
    """Consume rows once, optionally writing them into an unpublished stage."""
    descriptors: list[ShardDescriptor] = []
    total_digest = hashlib.sha256()
    total_rows = 0
    total_bytes = 0
    shard_fd = -1
    shard_metadata = None
    shard_rows = 0
    shard_bytes = 0
    shard_digest = hashlib.sha256()

    def open_shard() -> None:
        nonlocal shard_fd, shard_metadata, shard_rows, shard_bytes, shard_digest
        if len(descriptors) >= limits.max_shards:
            raise PersonaStreamingStorageError("artifact exceeds max_shards")
        shard_rows = 0
        shard_bytes = 0
        shard_digest = hashlib.sha256()
        if shards_fd is None:
            shard_fd = -1
            shard_metadata = None
            return
        name = SHARD_NAME_TEMPLATE.format(ordinal=len(descriptors))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            shard_fd = os.open(name, flags, 0o600, dir_fd=shards_fd)
        except OSError as exc:
            raise PersonaStreamingStorageError(
                f"cannot create unpublished shard {name}"
            ) from exc
        shard_metadata = os.fstat(shard_fd)
        if not _is_plain_file(shard_metadata) or shard_metadata.st_nlink != 1:
            raise PersonaStreamingStorageError("created shard is not a single-link file")

    def finish_shard() -> None:
        nonlocal shard_fd, shard_metadata
        if shard_rows == 0:
            return
        ordinal = len(descriptors)
        name = SHARD_NAME_TEMPLATE.format(ordinal=ordinal)
        if shard_fd >= 0:
            try:
                os.fsync(shard_fd)
                opened_after = os.fstat(shard_fd)
            finally:
                os.close(shard_fd)
                shard_fd = -1
            apparent = os.stat(name, dir_fd=shards_fd, follow_symlinks=False)
            if (
                not _is_plain_file(apparent)
                or apparent.st_nlink != 1
                or opened_after.st_size != shard_bytes
                or _stable_fingerprint(opened_after)
                != _stable_fingerprint(apparent)
                or (shard_metadata.st_dev, shard_metadata.st_ino)
                != (apparent.st_dev, apparent.st_ino)
            ):
                raise PersonaStreamingStorageError(
                    f"unpublished shard changed while writing: {name}"
                )
        descriptors.append(
            ShardDescriptor(
                ordinal=ordinal,
                file=f"{SHARDS_DIRECTORY_NAME}/{name}",
                rows=shard_rows,
                bytes=shard_bytes,
                sha256=shard_digest.hexdigest(),
            )
        )

    try:
        for row in iter(rows):
            if type(row) is not dict:
                raise PersonaStreamingStorageError("every JSONL row must be a plain dict")
            line = _canonical_file_bytes(row)
            if len(line) > limits.max_row_bytes:
                raise PersonaStreamingStorageError("canonical JSONL row exceeds max_row_bytes")
            if total_rows >= limits.max_total_rows:
                raise PersonaStreamingStorageError("artifact exceeds max_total_rows")
            if total_bytes + len(line) > limits.max_total_bytes:
                raise PersonaStreamingStorageError("artifact exceeds max_total_bytes")
            if shard_rows == 0 and (not descriptors or shard_fd < 0):
                open_shard()
            elif (
                shard_rows >= limits.max_rows_per_shard
                or shard_bytes + len(line) > limits.max_shard_bytes
            ):
                finish_shard()
                open_shard()
            if shards_fd is not None:
                _write_all(shard_fd, line)
            shard_rows += 1
            shard_bytes += len(line)
            shard_digest.update(line)
            total_rows += 1
            total_bytes += len(line)
            total_digest.update(line)
        finish_shard()
        if shards_fd is not None:
            os.fsync(shards_fd)
    except BaseException:
        if shard_fd >= 0:
            os.close(shard_fd)
        raise
    envelope = _build_envelope(
        tuple(descriptors),
        limits=limits,
        total_rows=total_rows,
        total_bytes=total_bytes,
        canonical_rows_sha256=total_digest.hexdigest(),
    )
    raw = _canonical_file_bytes(envelope)
    if len(raw) > MAX_ENVELOPE_BYTES:
        raise PersonaStreamingStorageError("storage envelope exceeds its byte bound")
    return envelope, raw


def _open_artifact(
    root: Path,
    *,
    limits: ArtifactLimits,
    expected_envelope_sha256: str | None,
):
    root_fd, root_metadata = _open_directory_path(root, "streaming artifact root")
    shards_fd = -1
    try:
        _require_exact_directory_entries(
            root_fd,
            frozenset(
                (STORAGE_ENVELOPE_NAME, READY_NAME, SHARDS_DIRECTORY_NAME)
            ),
            maximum_entries=4,
            label="artifact root",
        )
        envelope_raw, envelope_fingerprint = _read_plain_file_at(
            root_fd,
            STORAGE_ENVELOPE_NAME,
            MAX_ENVELOPE_BYTES,
            "storage envelope",
        )
        envelope_sha256 = hashlib.sha256(envelope_raw).hexdigest()
        if expected_envelope_sha256 is not None:
            _require_digest(expected_envelope_sha256, "expected envelope sha256")
            if envelope_sha256 != expected_envelope_sha256:
                raise PersonaStreamingStorageError("storage envelope digest mismatch")
        envelope_value = _decode_canonical_json(envelope_raw, "storage envelope")
        envelope = _validate_envelope(envelope_value, limits)
        ready_raw, ready_fingerprint = _read_plain_file_at(
            root_fd, READY_NAME, MAX_ENVELOPE_BYTES, "READY marker"
        )
        ready = _decode_canonical_json(ready_raw, "READY marker")
        expected_ready = {
            "schema": READY_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "storage_envelope_sha256": envelope_sha256,
        }
        if (
            type(ready) is not dict
            or set(ready) != set(expected_ready)
            or type(ready.get("schema_version")) is not int
            or ready != expected_ready
        ):
            raise PersonaStreamingStorageError("READY marker does not bind the envelope")
        shards_fd, shards_metadata = _open_directory_at(
            root_fd, SHARDS_DIRECTORY_NAME, "shards directory"
        )
        expected_shards = {
            Path(row["file"]).name for row in envelope["shards"]
        }
        _require_exact_directory_entries(
            shards_fd,
            expected_shards,
            maximum_entries=limits.max_shards + 1,
            label="shards directory",
        )
        return (
            root_fd,
            root_metadata,
            shards_fd,
            shards_metadata,
            envelope,
            envelope_sha256,
            envelope_raw,
            envelope_fingerprint,
            ready_raw,
            ready_fingerprint,
        )
    except BaseException:
        if shards_fd >= 0:
            os.close(shards_fd)
        os.close(root_fd)
        raise


def _stream_records(
    destination: os.PathLike[str] | str,
    *,
    limits: ArtifactLimits,
    expected_envelope_sha256: str | None,
) -> Iterator[JsonlRecord]:
    _require_supported_platform()
    if not isinstance(limits, ArtifactLimits):
        raise TypeError("limits must be ArtifactLimits")
    root = _absolute_lexical(destination)
    (
        root_fd,
        root_metadata,
        shards_fd,
        shards_metadata,
        envelope,
        envelope_sha256,
        envelope_raw,
        envelope_fingerprint,
        ready_raw,
        ready_fingerprint,
    ) = _open_artifact(
        root,
        limits=limits,
        expected_envelope_sha256=expected_envelope_sha256,
    )
    total_digest = hashlib.sha256()
    total_rows = 0
    total_bytes = 0
    prior_descriptor = None
    shard_fingerprints: dict[str, tuple[int, ...]] = {}
    try:
        for descriptor in envelope["shards"]:
            name = Path(descriptor["file"]).name
            try:
                before = os.stat(name, dir_fd=shards_fd, follow_symlinks=False)
                shard_fd = os.open(
                    name,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=shards_fd,
                )
            except OSError as exc:
                raise PersonaStreamingStorageError(
                    f"cannot safely open shard {name}"
                ) from exc
            try:
                opened = os.fstat(shard_fd)
                if (
                    not _is_plain_file(before)
                    or not _is_plain_file(opened)
                    or before.st_nlink != 1
                    or opened.st_nlink != 1
                    or _stable_fingerprint(before) != _stable_fingerprint(opened)
                ):
                    raise PersonaStreamingStorageError(
                        f"shard {name} changed while opening"
                    )
                if opened.st_size > limits.max_shard_bytes:
                    raise PersonaStreamingStorageError(
                        f"shard {name} exceeds max_shard_bytes"
                    )
                handle = os.fdopen(shard_fd, "rb", closefd=False)
                shard_digest = hashlib.sha256()
                shard_rows = 0
                shard_bytes = 0
                offset = 0
                first_length = None
                try:
                    while True:
                        line = handle.readline(limits.max_row_bytes + 1)
                        if not line:
                            break
                        if len(line) > limits.max_row_bytes or not line.endswith(b"\n"):
                            raise PersonaStreamingStorageError(
                                f"shard {name} contains an overlong or unterminated row"
                            )
                        value = _decode_canonical_json(line, f"row in {name}")
                        if type(value) is not dict:
                            raise PersonaStreamingStorageError(
                                f"shard {name} row must be a plain object"
                            )
                        if first_length is None:
                            first_length = len(line)
                            if prior_descriptor is not None and (
                                prior_descriptor["rows"]
                                < limits.max_rows_per_shard
                                and prior_descriptor["bytes"] + first_length
                                <= limits.max_shard_bytes
                            ):
                                raise PersonaStreamingStorageError(
                                    "JSONL shards were split before either deterministic cap"
                                )
                        shard_rows += 1
                        shard_bytes += len(line)
                        total_rows += 1
                        total_bytes += len(line)
                        if shard_rows > limits.max_rows_per_shard:
                            raise PersonaStreamingStorageError(
                                f"shard {name} exceeds max_rows_per_shard"
                            )
                        if shard_bytes > limits.max_shard_bytes:
                            raise PersonaStreamingStorageError(
                                f"shard {name} exceeds max_shard_bytes"
                            )
                        if total_rows > limits.max_total_rows:
                            raise PersonaStreamingStorageError(
                                "artifact exceeds max_total_rows while reading"
                            )
                        if total_bytes > limits.max_total_bytes:
                            raise PersonaStreamingStorageError(
                                "artifact exceeds max_total_bytes while reading"
                            )
                        shard_digest.update(line)
                        total_digest.update(line)
                        yield JsonlRecord(
                            shard_ordinal=descriptor["ordinal"],
                            byte_offset=offset,
                            byte_length=len(line),
                            row_sha256=hashlib.sha256(line).hexdigest(),
                            value=value,
                        )
                        offset += len(line)
                finally:
                    handle.close()
                opened_after = os.fstat(shard_fd)
            finally:
                os.close(shard_fd)
            try:
                after = os.stat(name, dir_fd=shards_fd, follow_symlinks=False)
            except OSError as exc:
                raise PersonaStreamingStorageError(
                    f"shard {name} disappeared while reading"
                ) from exc
            if (
                not _is_plain_file(after)
                or after.st_nlink != 1
                or _stable_fingerprint(opened_after) != _stable_fingerprint(opened)
                or _stable_fingerprint(after) != _stable_fingerprint(opened)
            ):
                raise PersonaStreamingStorageError(f"shard {name} changed while reading")
            shard_fingerprints[name] = _stable_fingerprint(after)
            if (
                shard_rows != descriptor["rows"]
                or shard_bytes != descriptor["bytes"]
                or shard_digest.hexdigest() != descriptor["sha256"]
            ):
                raise PersonaStreamingStorageError(
                    f"shard {name} content differs from its descriptor"
                )
            prior_descriptor = descriptor
        if (
            total_rows != envelope["totals"]["rows"]
            or total_bytes != envelope["totals"]["bytes"]
            or total_digest.hexdigest() != envelope["canonical_rows_sha256"]
        ):
            raise PersonaStreamingStorageError(
                "artifact content differs from aggregate descriptors"
            )
        _require_exact_directory_entries(
            shards_fd,
            {Path(row["file"]).name for row in envelope["shards"]},
            maximum_entries=limits.max_shards + 1,
            label="shards directory at verification completion",
        )
        for descriptor in envelope["shards"]:
            name = Path(descriptor["file"]).name
            try:
                final_shard = os.stat(
                    name, dir_fd=shards_fd, follow_symlinks=False
                )
            except OSError as exc:
                raise PersonaStreamingStorageError(
                    f"shard {name} disappeared before verification completed"
                ) from exc
            if (
                not _is_plain_file(final_shard)
                or final_shard.st_nlink != 1
                or _stable_fingerprint(final_shard) != shard_fingerprints[name]
            ):
                raise PersonaStreamingStorageError(
                    f"shard {name} changed before verification completed"
                )
        _require_exact_directory_entries(
            root_fd,
            frozenset(
                (STORAGE_ENVELOPE_NAME, READY_NAME, SHARDS_DIRECTORY_NAME)
            ),
            maximum_entries=4,
            label="artifact root at verification completion",
        )
        final_envelope_raw, final_envelope_fingerprint = _read_plain_file_at(
            root_fd,
            STORAGE_ENVELOPE_NAME,
            MAX_ENVELOPE_BYTES,
            "storage envelope",
        )
        final_ready_raw, final_ready_fingerprint = _read_plain_file_at(
            root_fd, READY_NAME, MAX_ENVELOPE_BYTES, "READY marker"
        )
        if (
            final_envelope_raw != envelope_raw
            or final_envelope_fingerprint != envelope_fingerprint
            or final_ready_raw != ready_raw
            or final_ready_fingerprint != ready_fingerprint
        ):
            raise PersonaStreamingStorageError(
                "storage envelope or READY marker changed during verification"
            )
        current_shards = os.fstat(shards_fd)
        current_root = os.fstat(root_fd)
        final_root_fd = -1
        try:
            final_root_fd, apparent_root = _open_directory_path(
                root, "streaming artifact root final identity"
            )
        finally:
            if final_root_fd >= 0:
                os.close(final_root_fd)
        if (
            _stable_fingerprint(current_shards)
            != _stable_fingerprint(shards_metadata)
            or _stable_fingerprint(current_root) != _stable_fingerprint(root_metadata)
            or _stable_fingerprint(apparent_root) != _stable_fingerprint(root_metadata)
        ):
            raise PersonaStreamingStorageError(
                "artifact directory metadata changed during verification"
            )
        return _receipt_from_envelope(root, envelope, envelope_sha256)
    finally:
        os.close(shards_fd)
        os.close(root_fd)


def iter_jsonl_records(
    destination: os.PathLike[str] | str,
    *,
    limits: ArtifactLimits = DEFAULT_LIMITS,
    expected_envelope_sha256: str | None = None,
) -> Iterator[JsonlRecord]:
    """Yield canonical rows with stable shard/offset/hash locator metadata.

    Exhaustion is mandatory for whole-artifact verification.  Closing or
    abandoning the iterator early makes no verification claim.
    """
    yield from _stream_records(
        destination,
        limits=limits,
        expected_envelope_sha256=expected_envelope_sha256,
    )


def iter_jsonl_artifact(
    destination: os.PathLike[str] | str,
    *,
    limits: ArtifactLimits = DEFAULT_LIMITS,
    expected_envelope_sha256: str | None = None,
) -> Iterator[dict[str, object]]:
    """Yield decoded rows without materializing the artifact."""
    for record in iter_jsonl_records(
        destination,
        limits=limits,
        expected_envelope_sha256=expected_envelope_sha256,
    ):
        yield record.value


def verify_jsonl_artifact(
    destination: os.PathLike[str] | str,
    *,
    limits: ArtifactLimits = DEFAULT_LIMITS,
    expected_envelope_sha256: str | None = None,
) -> ArtifactReceipt:
    """Read, canonical-decode, hash, and metadata-verify the complete artifact."""
    stream = _stream_records(
        destination,
        limits=limits,
        expected_envelope_sha256=expected_envelope_sha256,
    )
    while True:
        try:
            next(stream)
        except StopIteration as stopped:
            return stopped.value


def _write_small_commit_file(path: Path, value: dict[str, object]) -> None:
    raw = _canonical_file_bytes(value)
    if len(raw) > MAX_ENVELOPE_BYTES:
        raise PersonaStreamingStorageError("commit file exceeds its byte bound")
    try:
        storage.atomic_write_file(path, raw, mode=0o600)
    except storage.PersonaStorageError as exc:
        raise PersonaStreamingStorageError(str(exc)) from exc


def _reconcile_existing_artifact_durability(root: Path) -> None:
    """Synchronize a verified existing artifact after an ambiguous prior run.

    A previous process can successfully rename the artifact and then observe a
    parent-directory ``fsync`` failure.  Merely reading that final directory on
    retry does not repair namespace durability, so an exact no-op explicitly
    syncs the shards directory, artifact root, and its parent before its final
    bound verification.
    """
    parent_fd = -1
    root_fd = -1
    shards_fd = -1
    try:
        parent_fd, _ = _open_directory_path(
            root.parent, "existing artifact parent durability root"
        )
        root_fd, _ = _open_directory_at(
            parent_fd, root.name, "existing artifact durability root"
        )
        shards_fd, _ = _open_directory_at(
            root_fd, SHARDS_DIRECTORY_NAME, "existing shards durability root"
        )
        os.fsync(shards_fd)
        os.fsync(root_fd)
        os.fsync(parent_fd)
    except OSError as exc:
        raise PersonaStreamingStorageError(
            "cannot reconcile existing artifact namespace durability"
        ) from exc
    finally:
        if shards_fd >= 0:
            os.close(shards_fd)
        if root_fd >= 0:
            os.close(root_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def publish_jsonl_artifact(
    destination: os.PathLike[str] | str,
    rows: Iterable[dict[str, object]],
    *,
    limits: ArtifactLimits = DEFAULT_LIMITS,
) -> PublishResult:
    """Stream and atomically publish one deterministic canonical-JSONL artifact.

    The input iterable is consumed exactly once.  The final path is never
    replaced.  Existing valid identical content returns ``published=False``;
    every conflicting destination fails closed and remains untouched.  The
    separately reported formal-publication blocker covers the unportable race
    between verifying the source directory name and renaming that name.
    """
    _require_supported_platform()
    if not isinstance(limits, ArtifactLimits):
        raise TypeError("limits must be ArtifactLimits")
    root = _absolute_lexical(destination)
    if root == Path(root.anchor):
        raise PersonaStreamingStorageError("refusing filesystem root artifact")
    try:
        existing = root.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None:
        # Reject partial/foreign roots before consuming a potentially large
        # input, then verify again after recomputing the expected descriptor.
        first = verify_jsonl_artifact(root, limits=limits)
        _, expected_raw = _consume_rows(rows, limits=limits, shards_fd=None)
        expected_sha256 = hashlib.sha256(expected_raw).hexdigest()
        if first.storage_envelope_sha256 != expected_sha256:
            raise PersonaStreamingStorageError(
                "existing artifact is valid but differs from streamed input"
            )
        _reconcile_existing_artifact_durability(root)
        second = verify_jsonl_artifact(
            root, limits=limits, expected_envelope_sha256=expected_sha256
        )
        return PublishResult(artifact=second, published=False)

    parent = root.parent
    try:
        parent_fd, parent_metadata = _open_directory_path(
            parent, "streaming artifact parent"
        )
    except PersonaStreamingStorageError as exc:
        raise PersonaStreamingStorageError(
            f"artifact parent must be an existing plain directory: {parent}"
        ) from exc
    if parent_fd < 0:  # Defensive; Windows is rejected above.
        raise PersonaStreamingStorageError("safe parent directory handle unavailable")
    staging = None
    try:
        try:
            staging = Path(
                tempfile.mkdtemp(
                    prefix=f".{root.name}.stream-", suffix=".staging", dir=parent
                )
            )
        except OSError as exc:
            raise PersonaStreamingStorageError("cannot create streaming stage") from exc
        staging_metadata = staging.lstat()
        if not _is_plain_directory(staging_metadata):
            raise PersonaStreamingStorageError("streaming stage is not a plain directory")
        try:
            staged_at_parent = os.stat(
                staging.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except OSError as exc:
            raise PersonaStreamingStorageError(
                "streaming stage was not created in the opened parent"
            ) from exc
        if (
            not _is_plain_directory(staged_at_parent)
            or (staged_at_parent.st_dev, staged_at_parent.st_ino)
            != (staging_metadata.st_dev, staging_metadata.st_ino)
        ):
            raise PersonaStreamingStorageError(
                "streaming stage identity differs from its opened parent entry"
            )
        try:
            os.mkdir(staging / SHARDS_DIRECTORY_NAME, 0o700)
        except OSError as exc:
            raise PersonaStreamingStorageError("cannot create stage shards directory") from exc
        shards_fd, _ = _open_directory_path(
            staging / SHARDS_DIRECTORY_NAME, "unpublished shards directory"
        )
        try:
            envelope, envelope_raw = _consume_rows(
                rows, limits=limits, shards_fd=shards_fd
            )
        finally:
            os.close(shards_fd)
        envelope_sha256 = hashlib.sha256(envelope_raw).hexdigest()
        _write_small_commit_file(staging / STORAGE_ENVELOPE_NAME, envelope)
        # READY is deliberately the final stage write.
        _write_small_commit_file(
            staging / READY_NAME,
            {
                "schema": READY_SCHEMA,
                "schema_version": SCHEMA_VERSION,
                "storage_envelope_sha256": envelope_sha256,
            },
        )
        stage_receipt = verify_jsonl_artifact(
            staging,
            limits=limits,
            expected_envelope_sha256=envelope_sha256,
        )
        if stage_receipt.storage_envelope_sha256 != envelope_sha256:
            raise PersonaStreamingStorageError("stage readback descriptor drifted")
        final_parent_fd = -1
        try:
            final_parent_fd, apparent_parent = _open_directory_path(
                parent, "streaming artifact parent final identity"
            )
        finally:
            if final_parent_fd >= 0:
                os.close(final_parent_fd)
        try:
            apparent_stage = os.stat(
                staging.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except OSError as exc:
            raise PersonaStreamingStorageError(
                "streaming stage disappeared before rename"
            ) from exc
        if (
            (apparent_parent.st_dev, apparent_parent.st_ino)
            != (parent_metadata.st_dev, parent_metadata.st_ino)
            or (apparent_stage.st_dev, apparent_stage.st_ino)
            != (staging_metadata.st_dev, staging_metadata.st_ino)
        ):
            raise PersonaStreamingStorageError("publication namespace changed before rename")
        try:
            storage._rename_directory_noreplace(
                parent_fd, parent, staging.name, root.name
            )
        except FileExistsError as exc:
            raise PersonaStreamingStorageError(
                f"final artifact appeared; left it and stage untouched: {staging}"
            ) from exc
        except (OSError, storage.PersonaStorageError) as exc:
            raise PersonaStreamingStorageError(
                f"atomic no-replace publication failed; stage retained: {staging}"
            ) from exc
        os.fsync(parent_fd)
        try:
            published_metadata = os.stat(
                root.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except OSError as exc:
            raise PersonaStreamingStorageError(
                "published artifact cannot be reconciled"
            ) from exc
        if (
            published_metadata.st_dev,
            published_metadata.st_ino,
        ) != (staging_metadata.st_dev, staging_metadata.st_ino):
            raise PersonaStreamingStorageError("published artifact inode differs from stage")
        receipt = verify_jsonl_artifact(
            root,
            limits=limits,
            expected_envelope_sha256=envelope_sha256,
        )
        return PublishResult(artifact=receipt, published=True)
    finally:
        os.close(parent_fd)


__all__ = (
    "ABSOLUTE_MAX_ROW_BYTES",
    "ABSOLUTE_MAX_ROWS_PER_SHARD",
    "ABSOLUTE_MAX_SHARD_BYTES",
    "ABSOLUTE_MAX_SHARDS",
    "ABSOLUTE_MAX_TOTAL_ROWS",
    "ABSOLUTE_MAX_TOTAL_BYTES",
    "ArtifactLimits",
    "ArtifactReceipt",
    "CANONICALIZATION",
    "DEFAULT_LIMITS",
    "FORMAL_PUBLICATION_BLOCKER",
    "FORMAL_PUBLICATION_BLOCKERS",
    "JsonlRecord",
    "MAX_ENVELOPE_BYTES",
    "PersonaStreamingStorageError",
    "PublishResult",
    "READY_NAME",
    "READY_SCHEMA",
    "SCHEMA_VERSION",
    "SHARDS_DIRECTORY_NAME",
    "SHARD_NAME_TEMPLATE",
    "STORAGE_ENVELOPE_NAME",
    "STORAGE_ENVELOPE_SCHEMA",
    "ShardDescriptor",
    "canonical_json_bytes",
    "iter_jsonl_artifact",
    "iter_jsonl_records",
    "publish_jsonl_artifact",
    "verify_jsonl_artifact",
)
