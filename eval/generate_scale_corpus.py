#!/usr/bin/env python3
"""Generate the independent 20-scope / 120k-current-chunk scale corpus.

The output root is owner-marked.  A non-empty unowned directory is never
modified, and an owned directory is only reset after every direct child has
been checked against the fixture allow-list.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scale_fixture_spec as spec  # noqa: E402


MAX_OWNER_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_LOCK_BYTES = 4 * 1024
HASH_HEX_LENGTH = 64
LOCK_BYTES = b"kcs-scale-fixture-lock-v1\n"
ATOMIC_TEMP_RANDOM_RE = re.compile(r"[a-z0-9_]{8}")
WINDOWS_REPARSE_POINT_ATTRIBUTE = 0x400
KNOWN_RUNTIME_FILES = {
    spec.ATTESTATION_NAME,
    spec.PREPARE_REPORT_NAME,
}


class ScaleGenerationError(RuntimeError):
    pass


def _is_windows_reparse_point(metadata):
    return bool(
        (
            getattr(metadata, "st_file_attributes", 0)
            & WINDOWS_REPARSE_POINT_ATTRIBUTE
        )
        or getattr(metadata, "st_reparse_tag", 0)
    )


def _is_plain_regular_file(metadata):
    return stat.S_ISREG(metadata.st_mode) and not _is_windows_reparse_point(metadata)


def _is_plain_directory(metadata):
    return stat.S_ISDIR(metadata.st_mode) and not _is_windows_reparse_point(metadata)


def _optional_lstat(path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _json_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _compact_json_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _regular_file_bytes(path, maximum, label):
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ScaleGenerationError(f"{label} is missing: {path}") from exc
    if not _is_plain_regular_file(metadata):
        raise ScaleGenerationError(f"{label} must be a plain regular file: {path}")
    if metadata.st_size > maximum:
        raise ScaleGenerationError(
            f"{label} exceeds {maximum} bytes: {path} ({metadata.st_size})"
        )
    with path.open("rb") as handle:
        return handle.read(maximum + 1)


def _load_json(path, maximum, label):
    raw = _regular_file_bytes(path, maximum, label)
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScaleGenerationError(f"{label} is invalid JSON: {path}: {exc}") from exc


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def _bounded_children(path, expected_maximum, label):
    """Read at most one entry beyond a directory's declared upper bound."""
    children = []
    with os.scandir(path) as entries:
        for entry in entries:
            if len(children) == expected_maximum:
                raise ScaleGenerationError(
                    f"{label} exceeds {expected_maximum} entries: {path}"
                )
            children.append(Path(entry.path))
    return children


def _lock_file_bytes(handle):
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    if size > MAX_LOCK_BYTES:
        raise ScaleGenerationError(
            f"scale fixture lock exceeds {MAX_LOCK_BYTES} bytes"
        )
    handle.seek(0)
    return handle.read(MAX_LOCK_BYTES + 1)


def _initialize_locked_file(handle, root):
    raw = _lock_file_bytes(handle)
    if raw == LOCK_BYTES:
        return
    # A one-byte sentinel is the only recoverable state between creating a
    # Windows-compatible byte-range lock and publishing its identifying bytes.
    # It is accepted only when the root contains no other fixture/user state.
    if raw != b"\0":
        raise ScaleGenerationError(
            f"scale fixture lock has invalid contents: {root / spec.LOCK_NAME}"
        )
    marker_path = root / spec.OWNER_MARKER_NAME
    children = _bounded_children(
        root, len(spec.SCOPES) + len(KNOWN_RUNTIME_FILES) + 5,
        "uninitialized scale fixture root",
    )
    if {path.name for path in children} != {spec.LOCK_NAME}:
        # This migrates a valid fixture created before the persistent lock was
        # introduced. Arbitrary non-empty unowned roots remain untouchable.
        marker_metadata = _optional_lstat(marker_path)
        if marker_metadata is None or not _is_plain_regular_file(marker_metadata):
            raise ScaleGenerationError(
                f"scale fixture lock is uninitialized in a non-empty root: {root}"
            )
        _load_owner(root, require_ready=False)
    handle.seek(0)
    handle.write(LOCK_BYTES)
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


@contextmanager
def fixture_lock(corpus_dir):
    """Hold the fixture's persistent, portable, exclusive advisory lock."""
    root = _safe_output_root(corpus_dir)
    root_metadata = _optional_lstat(root)
    if root_metadata is None or not _is_plain_directory(root_metadata):
        raise ScaleGenerationError(f"scale corpus root is not a directory: {root}")
    lock_path = root / spec.LOCK_NAME
    lock_metadata = _optional_lstat(lock_path)
    if lock_metadata is not None and not _is_plain_regular_file(lock_metadata):
        raise ScaleGenerationError(
            f"scale fixture lock must be a regular file: {lock_path}"
        )
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ScaleGenerationError(f"cannot open scale fixture lock: {lock_path}") from exc
    handle = os.fdopen(descriptor, "r+b", buffering=0)
    locked = False
    try:
        metadata = os.fstat(handle.fileno())
        if not _is_plain_regular_file(metadata):
            raise ScaleGenerationError(
                f"scale fixture lock must be a regular file: {lock_path}"
            )
        path_metadata = lock_path.lstat()
        if not _is_plain_regular_file(path_metadata):
            raise ScaleGenerationError(
                f"scale fixture lock must not be a symlink: {lock_path}"
            )
        if (metadata.st_dev, metadata.st_ino) != (
            path_metadata.st_dev,
            path_metadata.st_ino,
        ):
            raise ScaleGenerationError(
                f"scale fixture lock changed while opening: {lock_path}"
            )
        if metadata.st_size == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())

        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        locked = True
        path_metadata = lock_path.lstat()
        if not _is_plain_regular_file(path_metadata):
            raise ScaleGenerationError(
                f"scale fixture lock became unsafe while acquiring: {lock_path}"
            )
        if (metadata.st_dev, metadata.st_ino) != (
            path_metadata.st_dev,
            path_metadata.st_ino,
        ):
            raise ScaleGenerationError(
                f"scale fixture lock changed while acquiring: {lock_path}"
            )
        _initialize_locked_file(handle, root)
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _safe_output_root(out_dir):
    root = Path(out_dir).expanduser().absolute()
    if root == Path(root.anchor) or root == Path.home().absolute():
        raise ScaleGenerationError(f"refusing unsafe output root: {root}")
    metadata = _optional_lstat(root)
    if metadata is not None and not _is_plain_directory(metadata):
        raise ScaleGenerationError(f"output root must be a plain directory: {root}")
    return root


def _owner_value(profile_name, state, manifest_sha256=None):
    value = {
        "schema_version": spec.SCHEMA_VERSION,
        "owner": spec.GENERATOR_ID,
        "fixture_id": spec.FIXTURE_ID,
        "profile": profile_name,
        "state": state,
    }
    if manifest_sha256 is not None:
        value["manifest_sha256"] = manifest_sha256
    return value


def _validate_owner(owner, require_ready=False):
    required = {"schema_version", "owner", "fixture_id", "profile", "state"}
    allowed = required | {"manifest_sha256"}
    if not isinstance(owner, dict) or set(owner) - allowed or not required.issubset(owner):
        raise ScaleGenerationError("scale owner marker has an invalid field set")
    if owner["schema_version"] != spec.SCHEMA_VERSION:
        raise ScaleGenerationError("scale owner marker schema_version mismatch")
    if owner["owner"] != spec.GENERATOR_ID or owner["fixture_id"] != spec.FIXTURE_ID:
        raise ScaleGenerationError("output directory is not owned by this generator")
    if owner["profile"] not in spec.PROFILES:
        raise ScaleGenerationError("scale owner marker profile is invalid")
    if owner["state"] not in ("building", "ready"):
        raise ScaleGenerationError("scale owner marker state is invalid")
    if require_ready and owner["state"] != "ready":
        raise ScaleGenerationError("scale output is incomplete (owner state is not ready)")
    if owner["state"] == "ready":
        digest = owner.get("manifest_sha256")
        if (not isinstance(digest, str) or len(digest) != HASH_HEX_LENGTH
                or any(ch not in "0123456789abcdef" for ch in digest)):
            raise ScaleGenerationError("ready owner marker lacks manifest_sha256")
    return owner


def _allowed_root_names():
    return {
        spec.OWNER_MARKER_NAME,
        spec.LOCK_NAME,
        spec.MANIFEST_NAME,
        spec.DEVICE_DIR_NAME,
        *KNOWN_RUNTIME_FILES,
        *(scope["name"] for scope in spec.SCOPES),
    }


def _allowed_scope_names(profile_name):
    selected = spec.profile(profile_name)
    return {
        ".kcs",
        *(spec.document_name(index) for index in range(selected["files_per_scope"])),
    }


def _check_owned_tree(root, profile_name):
    allowed_root = _allowed_root_names()
    scope_names = {scope["name"] for scope in spec.SCOPES}
    root_children = _bounded_children(
        root, len(allowed_root), "owned scale fixture root"
    )
    unexpected_root = sorted(
        path.name for path in root_children if path.name not in allowed_root
    )
    if unexpected_root:
        raise ScaleGenerationError(
            "owned output contains unknown root entries: " + ", ".join(unexpected_root)
        )
    for path in root_children:
        metadata = path.lstat()
        if path.name in scope_names or path.name == spec.DEVICE_DIR_NAME:
            if not _is_plain_directory(metadata):
                raise ScaleGenerationError(
                    f"owned directory path is unsafe: {path}"
                )
        elif not _is_plain_regular_file(metadata):
            raise ScaleGenerationError(f"owned runtime path is unsafe: {path}")
    allowed_scope = _allowed_scope_names(profile_name)
    for scope in spec.SCOPES:
        scope_dir = root / scope["name"]
        metadata = _optional_lstat(scope_dir)
        if metadata is None:
            continue
        if not _is_plain_directory(metadata):
            raise ScaleGenerationError(f"scope path must be a directory: {scope_dir}")
        scope_children = _bounded_children(
            scope_dir, len(allowed_scope), f"owned scope {scope['name']}"
        )
        unexpected = sorted(
            path.name for path in scope_children if path.name not in allowed_scope
        )
        if unexpected:
            raise ScaleGenerationError(
                f"owned scope contains unknown entries ({scope['name']}): "
                + ", ".join(unexpected)
            )
        for path in scope_children:
            metadata = path.lstat()
            if path.name == ".kcs":
                if not _is_plain_directory(metadata):
                    raise ScaleGenerationError(
                        f"scope .kcs path is unsafe: {path}"
                    )
            elif not _is_plain_regular_file(metadata):
                raise ScaleGenerationError(f"scope source path is unsafe: {path}")


def _atomic_temp_target(name, targets):
    for target in targets:
        prefix = f".{target}."
        suffix = ".tmp"
        if not name.startswith(prefix) or not name.endswith(suffix):
            continue
        random_part = name[len(prefix):-len(suffix)]
        if ATOMIC_TEMP_RANDOM_RE.fullmatch(random_part):
            return target
    return None


def _recover_unowned_building_temp(root, profile_name):
    """Recover only our exact initial-owner temp in an otherwise empty root."""
    children = _bounded_children(root, 2, "unowned scale fixture root")
    non_lock = [path for path in children if path.name != spec.LOCK_NAME]
    if not non_lock:
        return
    if len(non_lock) != 1:
        raise ScaleGenerationError(
            f"refusing non-empty unowned output directory: {root}"
        )
    candidate = non_lock[0]
    if _atomic_temp_target(candidate.name, {spec.OWNER_MARKER_NAME}) is None:
        raise ScaleGenerationError(
            f"refusing non-empty unowned output directory: {root}"
        )
    expected = _json_bytes(_owner_value(profile_name, "building"))
    if _regular_file_bytes(
        candidate, len(expected), "initial scale owner temporary file"
    ) != expected:
        raise ScaleGenerationError(
            f"refusing invalid unowned atomic temporary file: {candidate}"
        )
    candidate.unlink()


def _recover_owned_atomic_temp(root, profile_name):
    """Remove one strictly named regular temp left by an interrupted publish."""
    candidates = []
    allowed_root = _allowed_root_names()
    root_targets = {
        spec.OWNER_MARKER_NAME,
        spec.MANIFEST_NAME,
        *KNOWN_RUNTIME_FILES,
    }
    root_children = _bounded_children(
        root, len(allowed_root) + 1, "recoverable owned scale fixture root"
    )
    for path in root_children:
        if path.name in allowed_root:
            continue
        if _atomic_temp_target(path.name, root_targets) is None:
            raise ScaleGenerationError(
                f"owned output contains unknown root entry: {path.name}"
            )
        candidates.append(path)

    allowed_scope = _allowed_scope_names(profile_name)
    source_targets = allowed_scope - {".kcs"}
    for scope in spec.SCOPES:
        scope_dir = root / scope["name"]
        metadata = _optional_lstat(scope_dir)
        if metadata is None:
            continue
        if not _is_plain_directory(metadata):
            raise ScaleGenerationError(f"scope path must be a directory: {scope_dir}")
        scope_children = _bounded_children(
            scope_dir,
            len(allowed_scope) + 1,
            f"recoverable owned scope {scope['name']}",
        )
        for path in scope_children:
            if path.name in allowed_scope:
                continue
            if _atomic_temp_target(path.name, source_targets) is None:
                raise ScaleGenerationError(
                    f"owned scope contains unknown entry ({scope['name']}): {path.name}"
                )
            candidates.append(path)

    if len(candidates) > 1:
        raise ScaleGenerationError(
            "owned output contains multiple atomic temporary files"
        )
    if candidates:
        candidate = candidates[0]
        metadata = candidate.lstat()
        if not _is_plain_regular_file(metadata):
            raise ScaleGenerationError(
                f"owned atomic temporary path is unsafe: {candidate}"
            )
        candidate.unlink()


def _load_owner(root, require_ready=False):
    owner = _load_json(
        root / spec.OWNER_MARKER_NAME, MAX_OWNER_BYTES, "scale owner marker"
    )
    return _validate_owner(owner, require_ready=require_ready)


def _content_root_digest(scope_entries):
    rows = []
    for scope in scope_entries:
        for file_entry in scope["files"]:
            rows.append({
                "scope": scope["name"],
                "path": file_entry["path"],
                "raw_sha256": file_entry["raw_sha256"],
                "bytes": file_entry["bytes"],
                "expected_chunks": file_entry["expected_chunks"],
            })
    rows.sort(key=lambda row: (row["scope"], row["path"]))
    return _sha256(_compact_json_bytes(rows))


def _shape(profile_name):
    selected = spec.profile(profile_name)
    return {
        "scope_count": selected["scope_count"],
        "files_per_scope": selected["files_per_scope"],
        "sections_per_file": selected["sections_per_file"],
        "expected_files": selected["expected_files"],
        "expected_current_chunks": selected["expected_current_chunks"],
        "minimum_current_chunks": selected["minimum_current_chunks"],
        "body_chars": selected["body_chars"],
    }


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ScaleGenerationError("scale manifest must be an object")
    required = {
        "schema_version", "fixture_id", "generator", "seed", "profile",
        "chunking", "shape", "scopes", "needles", "content_root_sha256",
    }
    if set(manifest) != required:
        raise ScaleGenerationError("scale manifest field set mismatch")
    if manifest["schema_version"] != spec.SCHEMA_VERSION:
        raise ScaleGenerationError("scale manifest schema_version mismatch")
    if manifest["fixture_id"] != spec.FIXTURE_ID:
        raise ScaleGenerationError("scale manifest fixture_id mismatch")
    if manifest["generator"] != spec.GENERATOR_ID or manifest["seed"] != spec.SEED:
        raise ScaleGenerationError("scale manifest generator/seed mismatch")
    profile_name = manifest["profile"]
    expected_shape = _shape(profile_name)
    if manifest["shape"] != expected_shape:
        raise ScaleGenerationError("scale manifest shape mismatch")
    if manifest["chunking"] != {
        "strategy": spec.CHUNKING_STRATEGY,
        "max_chars": spec.CHUNKING_MAX_CHARS,
        "chunking_config_hash": spec.CHUNKING_CONFIG_HASH,
    }:
        raise ScaleGenerationError("scale manifest chunking contract mismatch")
    selected = spec.profile(profile_name)
    scopes = manifest["scopes"]
    if not isinstance(scopes, list) or len(scopes) != len(spec.SCOPES):
        raise ScaleGenerationError("scale manifest scope count mismatch")
    for scope_index, (actual, expected) in enumerate(zip(scopes, spec.SCOPES)):
        expected_keys = {
            "name", "persona", "use_case", "expected_files",
            "expected_current_chunks", "files",
        }
        if not isinstance(actual, dict) or set(actual) != expected_keys:
            raise ScaleGenerationError(f"scope manifest field set mismatch: {scope_index}")
        for key in ("name", "persona", "use_case"):
            if actual[key] != expected[key]:
                raise ScaleGenerationError(f"scope manifest identity mismatch: {scope_index}")
        if actual["expected_files"] != selected["files_per_scope"]:
            raise ScaleGenerationError(f"scope file count mismatch: {actual['name']}")
        expected_chunks = selected["files_per_scope"] * selected["sections_per_file"]
        if actual["expected_current_chunks"] != expected_chunks:
            raise ScaleGenerationError(f"scope chunk count mismatch: {actual['name']}")
        files = actual["files"]
        if not isinstance(files, list) or len(files) != selected["files_per_scope"]:
            raise ScaleGenerationError(f"scope file entries mismatch: {actual['name']}")
        for file_index, file_entry in enumerate(files):
            if set(file_entry) != {"path", "raw_sha256", "bytes", "expected_chunks"}:
                raise ScaleGenerationError("scale file manifest field set mismatch")
            if file_entry["path"] != spec.document_name(file_index):
                raise ScaleGenerationError("scale file ordering/path mismatch")
            digest = file_entry["raw_sha256"]
            if (not isinstance(digest, str) or len(digest) != HASH_HEX_LENGTH
                    or any(ch not in "0123456789abcdef" for ch in digest)):
                raise ScaleGenerationError("scale file raw_sha256 is invalid")
            if not isinstance(file_entry["bytes"], int) or file_entry["bytes"] <= 0:
                raise ScaleGenerationError("scale file byte count is invalid")
            if file_entry["expected_chunks"] != selected["sections_per_file"]:
                raise ScaleGenerationError("scale file expected_chunks mismatch")
            expected_data = spec.render_document(
                scope_index, file_index, profile_name
            ).encode("utf-8")
            if file_entry["bytes"] != len(expected_data):
                raise ScaleGenerationError("scale file byte count mismatch")
            if digest != _sha256(expected_data):
                raise ScaleGenerationError("scale file raw_sha256 mismatch")
    if manifest["content_root_sha256"] != _content_root_digest(scopes):
        raise ScaleGenerationError("scale manifest content_root_sha256 mismatch")
    needles = manifest["needles"]
    if not isinstance(needles, list) or len(needles) != len(spec.SCOPES):
        raise ScaleGenerationError("scale manifest needle count mismatch")
    for scope_index, (needle, scope) in enumerate(zip(needles, spec.SCOPES)):
        expected = {
            "query": spec.section_query(scope_index, 0, 0),
            "scope": scope["name"],
            "file": spec.document_name(0),
            "heading": spec.section_heading(scope_index, 0, 0),
        }
        if needle != expected:
            raise ScaleGenerationError(
                f"scale manifest needle mismatch: {scope['name']}"
            )
    return manifest


def load_owned_manifest(corpus_dir, require_ready=True):
    root = _safe_output_root(corpus_dir)
    root_metadata = _optional_lstat(root)
    if root_metadata is None or not _is_plain_directory(root_metadata):
        raise ScaleGenerationError(f"scale corpus root is not a directory: {root}")
    owner = _load_owner(root, require_ready=require_ready)
    _check_owned_tree(root, owner["profile"])
    manifest_path = root / spec.MANIFEST_NAME
    raw = _regular_file_bytes(manifest_path, MAX_MANIFEST_BYTES, "scale manifest")
    if owner.get("manifest_sha256") != _sha256(raw):
        raise ScaleGenerationError("scale owner marker does not bind the manifest bytes")
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScaleGenerationError(f"scale manifest is invalid JSON: {exc}") from exc
    validate_manifest(manifest)
    if owner["profile"] != manifest["profile"]:
        raise ScaleGenerationError("scale owner/manifest profile mismatch")
    return root, owner, manifest


def _manifest_for_files(root, profile_name, write_missing):
    selected = spec.profile(profile_name)
    scope_entries = []
    needles = []
    for scope_index, scope in enumerate(spec.SCOPES):
        scope_dir = root / scope["name"]
        metadata = _optional_lstat(scope_dir)
        if metadata is not None:
            if not _is_plain_directory(metadata):
                raise ScaleGenerationError(f"scope path is not a directory: {scope_dir}")
        elif write_missing:
            scope_dir.mkdir()
        else:
            raise ScaleGenerationError(f"generated scope is missing: {scope_dir}")
        files = []
        for file_index in range(selected["files_per_scope"]):
            name = spec.document_name(file_index)
            data = spec.render_document(scope_index, file_index, profile_name).encode("utf-8")
            path = scope_dir / name
            if _optional_lstat(path) is not None:
                actual = _regular_file_bytes(path, len(data), "scale source file")
                if actual != data:
                    raise ScaleGenerationError(
                        f"existing generated file differs; use --reset-owned: {path}"
                    )
            elif write_missing:
                _atomic_write(path, data)
            else:
                raise ScaleGenerationError(f"generated file is missing: {path}")
            files.append({
                "path": name,
                "raw_sha256": _sha256(data),
                "bytes": len(data),
                "expected_chunks": selected["sections_per_file"],
            })
        scope_entries.append({
            "name": scope["name"],
            "persona": scope["persona"],
            "use_case": scope["use_case"],
            "expected_files": selected["files_per_scope"],
            "expected_current_chunks": (
                selected["files_per_scope"] * selected["sections_per_file"]
            ),
            "files": files,
        })
        needles.append({
            "query": spec.section_query(scope_index, 0, 0),
            "scope": scope["name"],
            "file": spec.document_name(0),
            "heading": spec.section_heading(scope_index, 0, 0),
        })
    manifest = {
        "schema_version": spec.SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "generator": spec.GENERATOR_ID,
        "seed": spec.SEED,
        "profile": profile_name,
        "chunking": {
            "strategy": spec.CHUNKING_STRATEGY,
            "max_chars": spec.CHUNKING_MAX_CHARS,
            "chunking_config_hash": spec.CHUNKING_CONFIG_HASH,
        },
        "shape": _shape(profile_name),
        "scopes": scope_entries,
        "needles": needles,
        "content_root_sha256": _content_root_digest(scope_entries),
    }
    validate_manifest(manifest)
    return manifest


def _reset_owned_output_locked(root):
    if _optional_lstat(root / spec.OWNER_MARKER_NAME) is None:
        children = _bounded_children(root, 1, "ownerless scale reset root")
        if {path.name for path in children} == {spec.LOCK_NAME}:
            return
        raise ScaleGenerationError(
            f"cannot resume ownerless scale reset with remaining entries: {root}"
        )
    owner = _load_owner(root, require_ready=False)
    _recover_owned_atomic_temp(root, owner["profile"])
    _check_owned_tree(root, owner["profile"])

    # Validate every deletion target before the first destructive operation. A
    # malformed late target (device/runtime output) must never leave a half-reset
    # corpus whose already-validated scope directories were removed first.
    scope_dirs = []
    for scope in spec.SCOPES:
        scope_dir = root / scope["name"]
        metadata = _optional_lstat(scope_dir)
        if metadata is None:
            continue
        if not _is_plain_directory(metadata):
            raise ScaleGenerationError(f"scope reset path is unsafe: {scope_dir}")
        allowed_scope_count = len(_allowed_scope_names(owner["profile"]))
        for child in _bounded_children(
            scope_dir, allowed_scope_count, f"reset scope {scope['name']}"
        ):
            child_metadata = child.lstat()
            if child.name == ".kcs":
                if not _is_plain_directory(child_metadata):
                    raise ScaleGenerationError(
                        f"scope .kcs reset path is unsafe: {child}"
                    )
            elif not _is_plain_regular_file(child_metadata):
                raise ScaleGenerationError(
                    f"scope source reset path is unsafe: {child}"
                )
        scope_dirs.append(scope_dir)

    device_dir = root / spec.DEVICE_DIR_NAME
    device_metadata = _optional_lstat(device_dir)
    delete_device = device_metadata is not None
    if device_metadata is not None:
        if not _is_plain_directory(device_metadata):
            raise ScaleGenerationError(f"device path is unsafe: {device_dir}")
    runtime_paths = []
    runtime_names = [spec.MANIFEST_NAME, *sorted(KNOWN_RUNTIME_FILES)]
    for name in [*runtime_names, spec.OWNER_MARKER_NAME]:
        path = root / name
        metadata = _optional_lstat(path)
        if metadata is not None:
            if not _is_plain_regular_file(metadata):
                raise ScaleGenerationError(f"owned runtime path is unsafe: {path}")
            runtime_paths.append(path)

    for scope_dir in scope_dirs:
        shutil.rmtree(scope_dir)
    if delete_device:
        shutil.rmtree(device_dir)
    # Ownership is the recovery anchor for every preceding deletion. Publish
    # the ownerless state only after all other owned entries are gone, leaving
    # exactly the persistent lock if a later process resumes the reset.
    for path in runtime_paths:
        path.unlink()


def reset_owned_output(corpus_dir):
    root = _safe_output_root(corpus_dir)
    root_metadata = _optional_lstat(root)
    if root_metadata is None or not _is_plain_directory(root_metadata):
        raise ScaleGenerationError(f"cannot reset missing scale root: {root}")
    with fixture_lock(root):
        _reset_owned_output_locked(root)


def _preflight_unowned_root(root):
    """Refuse user state before lock creation can modify the directory."""
    marker_path = root / spec.OWNER_MARKER_NAME
    marker_metadata = _optional_lstat(marker_path)
    if marker_metadata is not None:
        if not _is_plain_regular_file(marker_metadata):
            raise ScaleGenerationError(
                f"scale owner marker must be a plain regular file: {marker_path}"
            )
        _load_owner(root, require_ready=False)
        return
    children = _bounded_children(root, 2, "unowned scale fixture root")
    if not children:
        return
    names = {path.name for path in children}
    if names == {spec.LOCK_NAME}:
        return
    if len(children) == 2 and spec.LOCK_NAME in names:
        candidate = next(path for path in children if path.name != spec.LOCK_NAME)
        if _atomic_temp_target(candidate.name, {spec.OWNER_MARKER_NAME}) is not None:
            return
    raise ScaleGenerationError(
        f"refusing non-empty unowned output directory: {root}"
    )


def write_corpus(out_dir, profile_name="tiny", reset_owned=False):
    spec.profile(profile_name)  # validate before touching disk
    root = _safe_output_root(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    marker_path = root / spec.OWNER_MARKER_NAME
    _preflight_unowned_root(root)

    with fixture_lock(root):
        if reset_owned:
            _reset_owned_output_locked(root)

        if _optional_lstat(marker_path) is None:
            _recover_unowned_building_temp(root, profile_name)
            existing_names = _bounded_children(root, 1, "unowned scale fixture root")
            if {path.name for path in existing_names} != {spec.LOCK_NAME}:
                raise ScaleGenerationError(
                    f"refusing non-empty unowned output directory: {root}"
                )

        if _optional_lstat(marker_path) is not None:
            owner = _load_owner(root, require_ready=False)
            if owner["profile"] != profile_name:
                raise ScaleGenerationError(
                    f"owned output profile is {owner['profile']}, not {profile_name}; "
                    "use --reset-owned"
                )
            _recover_owned_atomic_temp(root, profile_name)
            _check_owned_tree(root, profile_name)
            if owner["state"] == "ready":
                _, _, current = load_owned_manifest(root)
                expected = _manifest_for_files(root, profile_name, write_missing=False)
                if current != expected:
                    raise ScaleGenerationError(
                        "ready scale manifest differs from deterministic specification"
                    )
                return current, False

        _atomic_write(marker_path, _json_bytes(_owner_value(profile_name, "building")))
        _check_owned_tree(root, profile_name)
        manifest = _manifest_for_files(root, profile_name, write_missing=True)
        manifest_raw = _json_bytes(manifest)
        _atomic_write(root / spec.MANIFEST_NAME, manifest_raw)
        _atomic_write(
            marker_path,
            _json_bytes(_owner_value(profile_name, "ready", _sha256(manifest_raw))),
        )
        return manifest, True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate the independent KCS scale corpus"
    )
    parser.add_argument("--out", required=True, help="output collection root")
    parser.add_argument(
        "--profile", choices=sorted(spec.PROFILES), default="tiny",
        help="tiny (20 scopes / 60 chunks) or full (20 scopes / 120k chunks)",
    )
    parser.add_argument(
        "--reset-owned", action="store_true",
        help="reset only a valid owner-marked scale output; unknown entries still fail",
    )
    args = parser.parse_args(argv)
    try:
        manifest, generated = write_corpus(
            args.out, profile_name=args.profile, reset_owned=args.reset_owned
        )
    except (OSError, ScaleGenerationError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    shape = manifest["shape"]
    action = "generated" if generated else "already current"
    print(f"[ok] scale corpus {action}: {Path(args.out).absolute()}")
    print(
        f"     profile={manifest['profile']} scopes={shape['scope_count']} "
        f"files={shape['expected_files']} "
        f"expected_current_chunks={shape['expected_current_chunks']}"
    )
    print(f"     manifest: {Path(args.out).absolute() / spec.MANIFEST_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
