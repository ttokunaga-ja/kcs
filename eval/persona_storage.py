"""Storage-safety primitives for the synthetic persona-PC generator.

The large persona corpus is intentionally generated outside Git.  This module
contains the small, standard-library-only boundary used before a generator is
allowed to touch an output path.  It deliberately has no recursive reset or
cleanup API: an unknown tree is never made safe by deleting it.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Callable, Mapping

OWNER_MARKER_NAME = ".kio-persona-owner.json"
STAGING_OWNER_MARKER_NAME = ".kio-persona-staging-owner.json"
NOREPLACE_PROBE_SOURCE = ".kio-persona-noreplace-source"
NOREPLACE_PROBE_DESTINATION = ".kio-persona-noreplace-destination"
OWNER_ID = "kio.persona.storage-owner/v2"
OWNER_SCHEMA_VERSION = 2
FIXTURE_ID = "kio-persona-pc-v2"
MAX_OWNER_BYTES = 64 * 1024
WINDOWS_REPARSE_POINT_ATTRIBUTE = 0x400
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 0x00000004

_PROFILES = frozenset(("tiny", "pilot", "full"))
_OWNER_STATES = frozenset(("building", "ready"))
REPLAY_IDS = frozenset(("replay-01", "replay-02", "replay-03"))
_HEX_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


class PersonaStorageError(RuntimeError):
    """Raised when a storage operation would violate the fixture contract."""


def _is_windows_reparse_point(metadata: os.stat_result) -> bool:
    return bool(
        (
            getattr(metadata, "st_file_attributes", 0)
            & WINDOWS_REPARSE_POINT_ATTRIBUTE
        )
        or getattr(metadata, "st_reparse_tag", 0)
    )


def _is_plain_directory(metadata: os.stat_result) -> bool:
    return stat.S_ISDIR(metadata.st_mode) and not _is_windows_reparse_point(metadata)


def _is_plain_regular_file(metadata: os.stat_result) -> bool:
    return stat.S_ISREG(metadata.st_mode) and not _is_windows_reparse_point(metadata)


def is_plain_directory_metadata(metadata: os.stat_result) -> bool:
    """Public cross-platform predicate for generator exact-tree walks."""
    return _is_plain_directory(metadata)


def is_plain_regular_file_metadata(metadata: os.stat_result) -> bool:
    """Public cross-platform predicate for generator exact-tree walks."""
    return _is_plain_regular_file(metadata)


def _optional_lstat(path: Path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _absolute_lexical(path: os.PathLike[str] | str) -> Path:
    """Return an absolute normalized path without following a symlink."""
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _same_or_ancestor(candidate: Path, child: Path) -> bool:
    return candidate == child or candidate in child.parents


def _same_or_descendant(candidate: Path, parent: Path) -> bool:
    return candidate == parent or parent in candidate.parents


def _boundary_spellings(path: Path) -> frozenset[Path]:
    """Return lexical and canonical spellings of a protected boundary."""
    try:
        canonical = path.resolve(strict=False)
    except (OSError, RuntimeError):
        canonical = path
    return frozenset((path, canonical))


def _validate_existing_directory_chain(path: Path) -> None:
    """Reject every existing symlink, reparse point, file, or special component."""
    current = Path(path.anchor)
    metadata = _optional_lstat(current)
    if metadata is None or not _is_plain_directory(metadata):
        raise PersonaStorageError(f"filesystem anchor is not a plain directory: {current}")
    for component in path.parts[1:]:
        current = current / component
        metadata = _optional_lstat(current)
        if metadata is None:
            return
        if not _is_plain_directory(metadata):
            raise PersonaStorageError(
                f"output path component must be a plain directory: {current}"
            )


def _validate_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or _HEX_DIGEST_RE.fullmatch(value) is None:
        raise PersonaStorageError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    """One deterministic JSON+LF encoding for Python boundary metadata."""
    return _json_bytes(value)


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _read_plain_file(path: Path, maximum: int, label: str) -> bytes:
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise PersonaStorageError(f"{label} is missing: {path}") from exc
    if not _is_plain_regular_file(before) or before.st_nlink != 1:
        raise PersonaStorageError(
            f"{label} must be a single-link plain regular file: {path}"
        )
    if before.st_size > maximum:
        raise PersonaStorageError(f"{label} exceeds {maximum} bytes: {path}")
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not _is_plain_regular_file(opened)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino)
                != (before.st_dev, before.st_ino)
            ):
                raise PersonaStorageError(f"{label} changed while opening: {path}")
            raw = handle.read(maximum + 1)
    except OSError as exc:
        raise PersonaStorageError(f"cannot read {label}: {path}") from exc
    after = path.lstat()
    if (
        not _is_plain_regular_file(after)
        or after.st_nlink != 1
        or (after.st_dev, after.st_ino, after.st_size, after.st_nlink)
        != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_nlink)
    ):
        raise PersonaStorageError(f"{label} changed while reading: {path}")
    if len(raw) > maximum:
        raise PersonaStorageError(f"{label} exceeds {maximum} bytes: {path}")
    return raw


def make_owner_marker(*, profile: str, replay_id: str, state: str,
                      artifact_bundle_sha256: str, root_binding_sha256: str) -> dict[str, object]:
    """Build and validate the exact marker stored in one replay output root."""
    if not isinstance(profile, str) or profile not in _PROFILES:
        raise PersonaStorageError(f"unknown persona profile: {profile!r}")
    if not isinstance(replay_id, str) or replay_id not in REPLAY_IDS:
        raise PersonaStorageError(f"invalid replay id: {replay_id!r}")
    if not isinstance(state, str) or state not in _OWNER_STATES:
        raise PersonaStorageError(f"invalid owner state: {state!r}")
    marker: dict[str, object] = {
        "schema_version": OWNER_SCHEMA_VERSION,
        "owner": OWNER_ID,
        "fixture_id": FIXTURE_ID,
        "profile": profile,
        "replay_id": replay_id,
        "state": state,
        "artifact_bundle_sha256": _validate_digest(artifact_bundle_sha256, "artifact_bundle_sha256"),
        "root_binding_sha256": _validate_digest(root_binding_sha256, "root_binding_sha256"),
    }
    return marker


def validate_owner_marker(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PersonaStorageError("persona owner marker must be an object")
    required = {
        "schema_version",
        "owner",
        "fixture_id",
        "profile",
        "replay_id",
        "state",
        "artifact_bundle_sha256", "root_binding_sha256",
    }
    if set(value) != required:
        raise PersonaStorageError("persona owner marker has an invalid field set")
    if (
        isinstance(value["schema_version"], bool)
        or not isinstance(value["schema_version"], int)
        or value["schema_version"] != OWNER_SCHEMA_VERSION
    ):
        raise PersonaStorageError("persona owner marker schema mismatch")
    if value["owner"] != OWNER_ID or value["fixture_id"] != FIXTURE_ID:
        raise PersonaStorageError("output root is not owned by this generator")
    # Reconstructing applies all state-dependent and digest validation.
    expected = make_owner_marker(
        profile=value["profile"],
        replay_id=value["replay_id"],
        state=value["state"],
        artifact_bundle_sha256=value["artifact_bundle_sha256"],
        root_binding_sha256=value["root_binding_sha256"],
    )
    if value != expected:
        raise PersonaStorageError("persona owner marker is not canonical")
    return dict(value)


def make_staging_owner_marker(*, profile: str, replay_id: str,
                              artifact_bundle_sha256: str, root_binding_sha256: str) -> dict[str, object]:
    """Build the immutable receipt retained before and after root publication."""
    ready = make_owner_marker(
        profile=profile,
        replay_id=replay_id,
        state="ready",
        artifact_bundle_sha256=artifact_bundle_sha256,
        root_binding_sha256=root_binding_sha256,
    )
    ready["state"] = "staging_bound"
    return ready


def validate_staging_owner_marker(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("state") != "staging_bound":
        raise PersonaStorageError("persona staging owner marker must be staging_bound")
    ready_form = dict(value)
    ready_form["state"] = "ready"
    validate_owner_marker(ready_form)
    return dict(value)


def _load_marker_file(path: Path, label: str) -> dict[str, object]:
    raw = _read_plain_file(path, MAX_OWNER_BYTES, label)
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PersonaStorageError(f"{label} is invalid JSON: {path}") from exc
    return validate_owner_marker(value)


def load_owner_marker(root: os.PathLike[str] | str) -> dict[str, object]:
    root_path = _absolute_lexical(root)
    _validate_existing_directory_chain(root_path)
    path = root_path / OWNER_MARKER_NAME
    return _load_marker_file(path, "persona owner marker")


def load_staging_owner_marker(root: os.PathLike[str] | str) -> dict[str, object]:
    """Validate a retained unpublished stage without authorizing final reuse."""
    root_path = _absolute_lexical(root)
    _validate_existing_directory_chain(root_path)
    path = root_path / STAGING_OWNER_MARKER_NAME
    raw = _read_plain_file(path, MAX_OWNER_BYTES, "persona staging owner marker")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PersonaStorageError(
            f"persona staging owner marker is invalid JSON: {path}"
        ) from exc
    return validate_staging_owner_marker(value)


def require_owned_root(
    root: os.PathLike[str] | str,
    *,
    profile: str,
    replay_id: str,
    artifact_bundle_sha256: str,
    state: str | None = None,
    root_binding_sha256: str | None = None,
) -> dict[str, object]:
    """Validate an existing root for safe generator resume or ready reuse."""
    inspected = preflight_destination(
        root,
        expected_profile=profile,
        expected_replay_id=replay_id,
        expected_artifact_bundle_sha256=artifact_bundle_sha256,
    )
    if inspected.disposition != "owned" or inspected.owner is None:
        raise PersonaStorageError(f"persona output root is not owned: {inspected.root}")
    owner = inspected.owner
    if state is not None and owner["state"] != state:
        raise PersonaStorageError(
            f"persona owner state is {owner['state']!r}, not {state!r}"
        )
    if root_binding_sha256 is not None:
        _validate_digest(root_binding_sha256, "root_binding_sha256")
        if owner["root_binding_sha256"] != root_binding_sha256:
            raise PersonaStorageError("persona owner root binding mismatch")
    return dict(owner)


def require_ready_owned_root(
    root: os.PathLike[str] | str,
    *,
    profile: str,
    replay_id: str,
    artifact_bundle_sha256: str,
    root_binding_sha256: str,
) -> dict[str, object]:
    """Strict primitive for generator-side reuse of a completed replay root."""
    return require_owned_root(
        root,
        profile=profile,
        replay_id=replay_id,
        artifact_bundle_sha256=artifact_bundle_sha256,
        state="ready",
        root_binding_sha256=root_binding_sha256,
    )


@dataclass(frozen=True)
class DestinationInspection:
    root: Path
    disposition: str  # missing, empty, or owned
    owner: dict[str, object] | None = None


def preflight_destination(
    destination: os.PathLike[str] | str,
    *,
    home: os.PathLike[str] | str | None = None,
    repo_root: os.PathLike[str] | str | None = None,
    expected_profile: str | None = None,
    expected_replay_id: str | None = None,
    expected_artifact_bundle_sha256: str | None = None,
) -> DestinationInspection:
    """Inspect a proposed root without creating or modifying any path.

    Existing descendants are permitted only when the root has a valid persona
    owner marker.  Tree allow-list validation remains the generator's job.
    """
    root = _absolute_lexical(destination)
    home_path = _absolute_lexical(Path.home() if home is None else home)
    repository = _absolute_lexical(
        Path(__file__).parents[1] if repo_root is None else repo_root
    )
    anchor = Path(root.anchor)
    if root == anchor:
        raise PersonaStorageError(f"refusing filesystem root output: {root}")
    if any(_same_or_ancestor(root, boundary) for boundary in _boundary_spellings(home_path)):
        raise PersonaStorageError(f"output must not be home or its ancestor: {root}")
    if any(
        _same_or_ancestor(root, boundary)
        for boundary in _boundary_spellings(repository)
    ):
        raise PersonaStorageError(
            f"output must not be the repository or its ancestor: {root}"
        )
    if any(
        _same_or_descendant(root, boundary)
        for boundary in _boundary_spellings(repository)
    ):
        raise PersonaStorageError(f"persona output must remain outside Git: {root}")

    _validate_existing_directory_chain(root)
    metadata = _optional_lstat(root)
    if metadata is None:
        return DestinationInspection(root, "missing")

    marker_metadata = _optional_lstat(root / OWNER_MARKER_NAME)
    if marker_metadata is not None:
        if not _is_plain_regular_file(marker_metadata):
            raise PersonaStorageError(
                f"persona owner marker must be a plain regular file: "
                f"{root / OWNER_MARKER_NAME}"
            )
        owner = load_owner_marker(root)
        if expected_profile is not None and owner["profile"] != expected_profile:
            raise PersonaStorageError("persona owner profile mismatch")
        if expected_replay_id is not None and owner["replay_id"] != expected_replay_id:
            raise PersonaStorageError("persona owner replay binding mismatch")
        if expected_artifact_bundle_sha256 is not None:
            _validate_digest(expected_artifact_bundle_sha256, "expected_artifact_bundle_sha256")
            if owner["artifact_bundle_sha256"] != expected_artifact_bundle_sha256:
                raise PersonaStorageError("persona owner artifact bundle binding mismatch")
        return DestinationInspection(root, "owned", owner)

    # Read no more than one entry from an arbitrary unowned directory.
    try:
        with os.scandir(root) as entries:
            first = next(entries, None)
    except OSError as exc:
        raise PersonaStorageError(f"cannot inspect output directory: {root}") from exc
    if first is not None:
        raise PersonaStorageError(
            f"refusing non-empty unowned persona output directory: {root}"
        )
    return DestinationInspection(root, "empty")


def _assert_plain_parent(parent: Path) -> os.stat_result:
    metadata = _optional_lstat(parent)
    if metadata is None or not _is_plain_directory(metadata):
        raise PersonaStorageError(f"parent must be a plain existing directory: {parent}")
    return metadata


def _same_file_identity(path: Path, expected: os.stat_result) -> bool:
    current = _optional_lstat(path)
    return bool(
        current is not None
        and current.st_dev == expected.st_dev
        and current.st_ino == expected.st_ino
    )


def _fsync_directory(path: Path) -> None:
    # Python cannot open a directory fd on Windows.  ``os.rename``/``os.link``
    # still provide the required no-clobber namespace operation there; a
    # platform-native directory durability receipt is outside this primitive.
    if os.name == "nt":  # pragma: no cover - exercised by Windows CI
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PersonaStorageError(f"cannot open directory for sync: {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not _is_plain_directory(metadata):
            raise PersonaStorageError(f"directory became unsafe while syncing: {path}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _open_plain_directory(path: Path) -> tuple[int, os.stat_result]:
    """Open and identity-bind a directory used for an atomic publication."""
    if os.name == "nt":  # pragma: no cover - exercised by Windows CI
        metadata = path.lstat()
        if not _is_plain_directory(metadata):
            raise PersonaStorageError(f"directory is not plain: {path}")
        return -1, metadata
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PersonaStorageError(f"cannot safely open directory: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        apparent = path.lstat()
        if not _is_plain_directory(opened) or not _is_plain_directory(apparent):
            raise PersonaStorageError(f"directory is not plain: {path}")
        if (opened.st_dev, opened.st_ino) != (apparent.st_dev, apparent.st_ino):
            raise PersonaStorageError(f"directory changed while opening: {path}")
        return descriptor, opened
    except BaseException:
        os.close(descriptor)
        raise


def confirm_ready_root_durability(root: os.PathLike[str] | str) -> None:
    """Re-establish namespace durability and identity for ready-root reuse.

    This lets a later strict no-op recover safely from a prior post-rename
    parent-fsync warning without rewriting or adopting any tree entry.
    """
    root_path = _absolute_lexical(root)
    _validate_existing_directory_chain(root_path)
    parent_descriptor, parent_metadata = _open_plain_directory(root_path.parent)
    root_descriptor = -1
    try:
        root_descriptor, root_metadata = _open_plain_directory(root_path)
        if root_descriptor >= 0:
            os.fsync(root_descriptor)
        if parent_descriptor >= 0:
            os.fsync(parent_descriptor)
        if not _same_file_identity(root_path.parent, parent_metadata):
            raise PersonaStorageError("ready-root parent changed during durability sync")
        if not _same_file_identity(root_path, root_metadata):
            raise PersonaStorageError("ready root changed during durability sync")
    finally:
        if root_descriptor >= 0:
            os.close(root_descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


def _raise_rename_error(result: int, source: str, destination: str) -> None:
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in (errno.EEXIST, errno.ENOTEMPTY):
        raise FileExistsError(
            error_number,
            "atomic destination already exists",
            destination,
        )
    raise OSError(error_number, os.strerror(error_number), f"{source} -> {destination}")


def _require_noreplace_directory_support() -> None:
    """Fail before staging writes when root publication is unavailable."""
    if sys.platform == "darwin":
        if not hasattr(ctypes.CDLL(None), "renameatx_np"):
            raise PersonaStorageError(
                "this Darwin runtime lacks atomic no-replace directory publication"
            )
        return
    if sys.platform.startswith("linux"):
        if getattr(ctypes.CDLL(None), "renameat2", None) is None:
            raise PersonaStorageError(
                "this libc lacks atomic no-replace directory publication"
            )
        return
    if os.name == "nt":
        return
    raise PersonaStorageError(
        "platform lacks atomic no-replace directory publication support"
    )


def _rename_directory_noreplace(
    parent_descriptor: int,
    parent_path: Path,
    source_name: str,
    destination_name: str,
) -> None:
    """Rename one sibling directory without ever replacing the destination."""
    encoded_source = os.fsencode(source_name)
    encoded_destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.renameatx_np
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        ctypes.set_errno(0)
        _raise_rename_error(
            function(
                parent_descriptor,
                encoded_source,
                parent_descriptor,
                encoded_destination,
                _RENAME_EXCL,
            ),
            source_name,
            destination_name,
        )
        return
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        function = getattr(libc, "renameat2", None)
        if function is None:
            raise PersonaStorageError(
                "this libc lacks atomic no-replace directory publication"
            )
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        ctypes.set_errno(0)
        _raise_rename_error(
            function(
                parent_descriptor,
                encoded_source,
                parent_descriptor,
                encoded_destination,
                _RENAME_NOREPLACE,
            ),
            source_name,
            destination_name,
        )
        return
    if os.name == "nt":  # Windows rename already refuses an existing target.
        os.rename(parent_path / source_name, parent_path / destination_name)
        return
    raise PersonaStorageError(
        "platform lacks atomic no-replace directory publication support"
    )


def _attest_filesystem_noreplace(staging: Path) -> None:
    """Prove no-replace on this filesystem before expensive population.

    The two empty proof directories are retained as publication receipts, so
    this check never conditionally deletes a raced or unknown path.
    """
    source = staging / NOREPLACE_PROBE_SOURCE
    destination = staging / NOREPLACE_PROBE_DESTINATION
    os.mkdir(source, 0o700)
    os.mkdir(destination, 0o700)
    source_metadata = source.lstat()
    destination_metadata = destination.lstat()
    descriptor, _ = _open_plain_directory(staging)
    try:
        try:
            _rename_directory_noreplace(
                descriptor, staging, source.name, destination.name
            )
        except FileExistsError:
            pass
        else:
            raise PersonaStorageError(
                "filesystem ignored no-replace and replaced the proof target"
            )
        if not _same_file_identity(source, source_metadata) or not _same_file_identity(
            destination, destination_metadata
        ):
            raise PersonaStorageError("filesystem no-replace proof changed an endpoint")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def atomic_create_directory(
    path: os.PathLike[str] | str,
    *,
    parents: bool = False,
    mode: int = 0o700,
    plan_only: bool = False,
) -> bool:
    """Atomically create directory components; return whether any was created."""
    target = _absolute_lexical(path)
    _validate_existing_directory_chain(target)
    if _optional_lstat(target) is not None:
        return False
    if plan_only:
        return True

    if parents:
        missing = []
        current = target
        while _optional_lstat(current) is None:
            missing.append(current)
            if current == Path(current.anchor):
                break
            current = current.parent
        _validate_existing_directory_chain(current)
        for directory in reversed(missing):
            try:
                os.mkdir(directory, mode)
            except FileExistsError:
                metadata = directory.lstat()
                if not _is_plain_directory(metadata):
                    raise PersonaStorageError(
                        f"directory path changed to an unsafe entry: {directory}"
                    )
            metadata = directory.lstat()
            if not _is_plain_directory(metadata):
                raise PersonaStorageError(f"created directory is unsafe: {directory}")
            _fsync_directory(directory.parent)
        return True

    _assert_plain_parent(target.parent)
    try:
        os.mkdir(target, mode)
    except FileExistsError as exc:
        metadata = target.lstat()
        if not _is_plain_directory(metadata):
            raise PersonaStorageError(f"directory target is unsafe: {target}") from exc
        return False
    metadata = target.lstat()
    if not _is_plain_directory(metadata):
        raise PersonaStorageError(f"created directory is unsafe: {target}")
    _fsync_directory(target.parent)
    return True


def atomic_write_file(
    path: os.PathLike[str] | str,
    data: bytes,
    *,
    mode: int = 0o600,
    plan_only: bool = False,
) -> None:
    """Publish a new file atomically without ever replacing a destination."""
    if not isinstance(data, bytes):
        raise TypeError("atomic_write_file data must be bytes")
    target = _absolute_lexical(path)
    _validate_existing_directory_chain(target.parent)
    parent_metadata = _optional_lstat(target.parent)
    if parent_metadata is None:
        if plan_only:
            return
        raise PersonaStorageError(f"file parent does not exist: {target.parent}")
    if not _is_plain_directory(parent_metadata):
        raise PersonaStorageError(f"file parent is unsafe: {target.parent}")
    if _optional_lstat(target) is not None:
        raise PersonaStorageError(f"refusing to replace existing path: {target}")
    if plan_only:
        return

    parent_descriptor, opened_parent = _open_plain_directory(target.parent)
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
    except BaseException:
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        raise
    temporary = Path(temporary_name)
    temporary_metadata = os.fstat(descriptor)
    try:
        if not _is_plain_regular_file(temporary_metadata):
            raise PersonaStorageError(f"atomic temporary is not a regular file: {temporary}")
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        else:  # pragma: no cover - Windows Python without fchmod
            os.chmod(temporary, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        if not _same_file_identity(target.parent, opened_parent):
            raise PersonaStorageError(f"file parent changed during publication: {target.parent}")
        if not _same_file_identity(temporary, temporary_metadata):
            raise PersonaStorageError(f"atomic temporary changed during publication: {temporary}")
        # A no-replace rename consumes our temporary on success and leaves it
        # intact on failure.  There is deliberately no conditional unlink.
        _rename_directory_noreplace(
            parent_descriptor,
            target.parent,
            temporary.name,
            target.name,
        )
        temporary_name = ""
        if parent_descriptor >= 0:
            linked = os.stat(
                target.name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        else:  # pragma: no cover - Windows CI
            linked = target.lstat()
        if (linked.st_dev, linked.st_ino) != (
            temporary_metadata.st_dev,
            temporary_metadata.st_ino,
        ):
            raise PersonaStorageError(
                f"published file identity changed unexpectedly: {target}"
            )
        if not _same_file_identity(target.parent, opened_parent):
            raise PersonaStorageError(
                f"file parent changed during no-replace publication: {target.parent}"
            )
        if parent_descriptor >= 0:
            os.fsync(parent_descriptor)
        _fsync_directory(target.parent)
    except FileExistsError as exc:
        raise PersonaStorageError(
            f"file target appeared during no-replace publication: {target}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        # Failed publications retain the random, identity-bound temporary as
        # evidence.  This module never conditionally deletes a mutable path.
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


@dataclass(frozen=True)
class PublishResult:
    root: Path
    owner: dict[str, object]
    published: bool
    plan_only: bool
    staging_root: Path | None = None
    durability_confirmed: bool = False
    identity_confirmed: bool = False
    warning: str | None = None


def atomic_publish_owned_root(
    destination: os.PathLike[str] | str,
    *,
    profile: str,
    replay_id: str,
    artifact_bundle_sha256: str,
    root_binding_sha256: str,
    populate: Callable[[Path], None],
    validate: Callable[[Path], None],
    plan_only: bool = False,
    home: os.PathLike[str] | str | None = None,
    repo_root: os.PathLike[str] | str | None = None,
) -> PublishResult:
    """Build in an owned sibling stage and publish one complete ready root.

    The final path must be missing.  The function never removes a final path or
    a failed staging tree.  A concurrent final-path creation therefore fails
    closed and leaves both the foreign final and the owned staging evidence.
    """
    if not callable(populate) or not callable(validate):
        raise TypeError("populate and validate must be callable")
    ready = make_owner_marker(
        profile=profile,
        replay_id=replay_id,
        state="ready",
        artifact_bundle_sha256=artifact_bundle_sha256,
        root_binding_sha256=root_binding_sha256,
    )
    staging_owner = make_staging_owner_marker(
        profile=profile,
        replay_id=replay_id,
        artifact_bundle_sha256=artifact_bundle_sha256,
        root_binding_sha256=root_binding_sha256,
    )
    inspected = preflight_destination(
        destination,
        home=home,
        repo_root=repo_root,
        expected_profile=profile,
        expected_replay_id=replay_id,
        expected_artifact_bundle_sha256=artifact_bundle_sha256,
    )
    _require_noreplace_directory_support()
    if inspected.disposition != "missing":
        raise PersonaStorageError(
            f"atomic persona publication requires a missing final root: {inspected.root}"
        )
    if plan_only:
        return PublishResult(
            root=inspected.root,
            owner=ready,
            published=False,
            plan_only=True,
        )
    parent = inspected.root.parent
    parent_metadata = _optional_lstat(parent)
    if parent_metadata is None or not _is_plain_directory(parent_metadata):
        raise PersonaStorageError(
            f"atomic persona publication requires an existing plain parent: {parent}"
        )
    parent_descriptor, opened_parent = _open_plain_directory(parent)
    try:
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{inspected.root.name}.persona-",
                suffix=".staging",
                dir=parent,
            )
        )
    except BaseException:
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        raise
    staging_metadata = staging.lstat()
    try:
        if not _is_plain_directory(staging_metadata):
            raise PersonaStorageError(f"staging root is unsafe: {staging}")
        atomic_write_file(
            staging / STAGING_OWNER_MARKER_NAME, _json_bytes(staging_owner)
        )
        _attest_filesystem_noreplace(staging)
        populate(staging)
        if not _same_file_identity(staging, staging_metadata):
            raise PersonaStorageError(f"staging root changed during population: {staging}")
        if _read_plain_file(
            staging / STAGING_OWNER_MARKER_NAME,
            MAX_OWNER_BYTES,
            "staging owner marker",
        ) != _json_bytes(staging_owner):
            raise PersonaStorageError("staging owner marker changed during population")
        validate(staging)
        if not _same_file_identity(staging, staging_metadata):
            raise PersonaStorageError(f"staging root changed during validation: {staging}")
        atomic_write_file(staging / OWNER_MARKER_NAME, _json_bytes(ready))
        if load_owner_marker(staging) != ready:
            raise PersonaStorageError("ready staging owner marker failed validation")
        if load_staging_owner_marker(staging) != staging_owner:
            raise PersonaStorageError("staging publication receipt failed validation")
        if not _same_file_identity(parent, opened_parent):
            raise PersonaStorageError(f"publication parent changed: {parent}")
        try:
            _rename_directory_noreplace(
                parent_descriptor,
                parent,
                staging.name,
                inspected.root.name,
            )
        except FileExistsError as exc:
            raise PersonaStorageError(
                f"final root appeared; left final untouched and staging at {staging}"
            ) from exc
        warnings = []
        durability_confirmed = True
        if parent_descriptor >= 0:
            try:
                os.fsync(parent_descriptor)
            except OSError as exc:
                durability_confirmed = False
                warnings.append(f"parent fsync failed after publication: {exc}")
        parent_confirmed = _same_file_identity(parent, opened_parent)
        identity_confirmed = False
        if parent_confirmed:
            try:
                published_metadata = inspected.root.lstat()
                identity_confirmed = (
                    published_metadata.st_dev,
                    published_metadata.st_ino,
                ) == (staging_metadata.st_dev, staging_metadata.st_ino)
            except OSError as exc:
                warnings.append(f"cannot reconcile published root identity: {exc}")
        else:
            warnings.append("publication parent changed after atomic rename")
        if not identity_confirmed and parent_confirmed:
            warnings.append("published root identity is no longer the staged inode")
        return PublishResult(
            root=inspected.root,
            owner=ready,
            published=True,
            plan_only=False,
            durability_confirmed=durability_confirmed,
            identity_confirmed=identity_confirmed,
            warning="; ".join(warnings) or None,
        )
    finally:
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
