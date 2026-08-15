"""Read-only owner-marker lock for one published persona replay root.

The lock deliberately reuses the immutable W0 owner marker as its carrier.
It never creates a lock file or rewrites the marker, so acquiring it does not
change the exact W0 tree.  A later prepare/replay executor must hold one lease
for its complete root-wide transaction and must still validate its own
history-ready and suite-manifest receipts.

Only POSIX ``flock`` is implemented.  Windows remains fail-closed until a
native handle/byte-range lock with equivalent identity guarantees exists.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Iterator

from . import persona_artifacts
from . import persona_storage as storage


class PersonaRootLockError(RuntimeError):
    """Raised when an owned replay root cannot be locked safely."""


@dataclass(frozen=True)
class ReplayRootLease:
    """Opaque proof that this process currently holds one replay-root lock."""

    root: Path
    profile: str
    replay_id: str
    artifact_bundle_sha256: str
    root_binding_sha256: str
    root_device: int
    root_inode: int
    owner_device: int
    owner_inode: int
    root_binding_device: int
    root_binding_inode: int
    owner_pid: int
    _state: object


@dataclass
class _LeaseState:
    root_fd: int
    owner_fd: int
    root_binding_fd: int
    expected_owner_bytes: bytes
    expected_root_binding_bytes: bytes
    owner_pid: int
    active: bool = True


_PROCESS_GUARD = threading.Lock()
_ACTIVE_ROOT_IDENTITIES: set[tuple[int, int]] = set()
_ROOT_BINDING_FILE_NAME = "persona-root-binding.json"
_ROOT_BINDING_SCHEMA = "kio.persona.storage-root-binding/v2"
_MAX_ROOT_BINDING_BYTES = 64 * 1024
_ROOT_BINDING_FIELDS = {
    "schema",
    "fixture_id",
    "profile",
    "replay_id",
    "plan_digest",
    "artifact_bundle_sha256",
    "plan_sha256",
    "schedule_sha256",
    "render_sha256",
    "destination_root",
    "filesystem_device",
    "sources_materialized",
    "actual_kio_evidence",
    "history_ready",
}


def _reset_process_guard_after_fork() -> None:
    """Replace a possibly locked inherited mutex in the child process."""
    global _PROCESS_GUARD
    _PROCESS_GUARD = threading.Lock()


if hasattr(os, "register_at_fork"):  # pragma: no branch - POSIX capability.
    os.register_at_fork(after_in_child=_reset_process_guard_after_fork)


def _canonical_owner_bytes(owner: dict[str, object]) -> bytes:
    return storage.canonical_json_bytes(owner)


def _open_flags(*, directory: bool) -> int:
    flags = os.O_RDONLY
    required = ["O_CLOEXEC", "O_NOFOLLOW"]
    if directory:
        required.append("O_DIRECTORY")
    for name in required:
        value = getattr(os, name, None)
        if type(value) is not int or value == 0:
            raise PersonaRootLockError(
                f"required descriptor flag {name} is unavailable"
            )
        flags |= value
    return flags


def _plain_root_metadata(metadata: os.stat_result) -> bool:
    return storage.is_plain_directory_metadata(metadata)


def _plain_owner_metadata(metadata: os.stat_result) -> bool:
    return (
        storage.is_plain_regular_file_metadata(metadata)
        and metadata.st_nlink == 1
        and 0 <= metadata.st_size <= storage.MAX_OWNER_BYTES
    )


def _read_bound_owner(
    owner_fd: int,
    *,
    expected_bytes: bytes,
) -> os.stat_result:
    before = os.fstat(owner_fd)
    if not _plain_owner_metadata(before):
        raise PersonaRootLockError("owner marker fd is not a single-link plain file")
    try:
        os.lseek(owner_fd, 0, os.SEEK_SET)
        raw = b""
        while len(raw) <= storage.MAX_OWNER_BYTES:
            block = os.read(
                owner_fd,
                min(64 * 1024, storage.MAX_OWNER_BYTES + 1 - len(raw)),
            )
            if not block:
                break
            raw += block
    except OSError as error:
        raise PersonaRootLockError("cannot read owner marker through its fd") from error
    after = os.fstat(owner_fd)
    if (
        not _plain_owner_metadata(after)
        or (before.st_dev, before.st_ino, before.st_size)
        != (after.st_dev, after.st_ino, after.st_size)
        or len(raw) != before.st_size
        or raw != expected_bytes
    ):
        raise PersonaRootLockError("owner marker bytes or identity changed")
    return after


def _read_bound_root_binding(
    descriptor: int,
    *,
    expected_bytes: bytes | None,
    expected_sha256: str,
) -> tuple[os.stat_result, bytes, dict[str, object]]:
    before = os.fstat(descriptor)
    if (
        not storage.is_plain_regular_file_metadata(before)
        or before.st_nlink != 1
        or not 0 <= before.st_size <= _MAX_ROOT_BINDING_BYTES
    ):
        raise PersonaRootLockError("root binding is not a bounded single-link file")
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = b""
        while len(raw) <= _MAX_ROOT_BINDING_BYTES:
            block = os.read(
                descriptor,
                min(64 * 1024, _MAX_ROOT_BINDING_BYTES + 1 - len(raw)),
            )
            if not block:
                break
            raw += block
    except OSError as error:
        raise PersonaRootLockError("cannot read root binding through its fd") from error
    after = os.fstat(descriptor)
    if (
        not storage.is_plain_regular_file_metadata(after)
        or after.st_nlink != 1
        or not 0 <= after.st_size <= _MAX_ROOT_BINDING_BYTES
        or (before.st_dev, before.st_ino, before.st_size)
        != (after.st_dev, after.st_ino, after.st_size)
        or len(raw) != before.st_size
        or "sha256:" + hashlib.sha256(raw).hexdigest() != expected_sha256
        or (expected_bytes is not None and raw != expected_bytes)
    ):
        raise PersonaRootLockError("root binding bytes or identity changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PersonaRootLockError("root binding is invalid JSON") from error
    if type(value) is not dict or storage.canonical_json_bytes(value) != raw:
        raise PersonaRootLockError("root binding is not canonical JSON")
    if (
        set(value) != _ROOT_BINDING_FIELDS
        or value.get("schema") != _ROOT_BINDING_SCHEMA
        or value.get("fixture_id") != storage.FIXTURE_ID
    ):
        raise PersonaRootLockError("root binding schema or fields differ")
    for field in (
        "plan_digest",
        "artifact_bundle_sha256",
        "plan_sha256",
        "schedule_sha256",
        "render_sha256",
    ):
        digest = value.get(field)
        if (
            type(digest) is not str
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        ):
            raise PersonaRootLockError(f"root binding {field} is invalid")
    if value["plan_digest"] != value["plan_sha256"]:
        raise PersonaRootLockError("root binding plan digest differs from plan bytes")
    expected_artifact = persona_artifacts.artifact_bundle_record(
        fixture_id=value["fixture_id"],
        profile=value.get("profile"),
        plan_digest=value["plan_digest"],
        plan_sha256=value["plan_sha256"],
        schedule_sha256=value["schedule_sha256"],
        render_sha256=value["render_sha256"],
    )
    expected_artifact_sha256 = "sha256:" + hashlib.sha256(
        storage.canonical_json_bytes(expected_artifact)
    ).hexdigest()
    if value["artifact_bundle_sha256"] != expected_artifact_sha256:
        raise PersonaRootLockError("root binding artifact bundle digest differs")
    return after, raw, value


def _validate_bound_namespace(lease: ReplayRootLease) -> None:
    state = lease._state
    if type(state) is not _LeaseState or not state.active:
        raise PersonaRootLockError("replay root lease is not active")
    if os.getpid() != state.owner_pid or lease.owner_pid != state.owner_pid:
        raise PersonaRootLockError(
            "replay root lease belongs to a different process"
        )
    try:
        opened_root = os.fstat(state.root_fd)
        apparent_root = lease.root.lstat()
    except OSError as error:
        raise PersonaRootLockError("replay root changed while locked") from error
    expected_root = (lease.root_device, lease.root_inode)
    if (
        not _plain_root_metadata(opened_root)
        or not _plain_root_metadata(apparent_root)
        or lease.root.is_symlink()
        or (opened_root.st_dev, opened_root.st_ino) != expected_root
        or (apparent_root.st_dev, apparent_root.st_ino) != expected_root
    ):
        raise PersonaRootLockError("replay root identity changed while locked")
    opened_owner = _read_bound_owner(
        state.owner_fd,
        expected_bytes=state.expected_owner_bytes,
    )
    try:
        apparent_owner = os.stat(
            storage.OWNER_MARKER_NAME,
            dir_fd=state.root_fd,
            follow_symlinks=False,
        )
    except OSError as error:
        raise PersonaRootLockError("owner marker namespace changed") from error
    expected_owner = (lease.owner_device, lease.owner_inode)
    if (
        not _plain_owner_metadata(apparent_owner)
        or (opened_owner.st_dev, opened_owner.st_ino) != expected_owner
        or (apparent_owner.st_dev, apparent_owner.st_ino) != expected_owner
    ):
        raise PersonaRootLockError("owner marker namespace identity changed")
    opened_binding, _raw, binding = _read_bound_root_binding(
        state.root_binding_fd,
        expected_bytes=state.expected_root_binding_bytes,
        expected_sha256=lease.root_binding_sha256,
    )
    try:
        apparent_binding = os.stat(
            _ROOT_BINDING_FILE_NAME,
            dir_fd=state.root_fd,
            follow_symlinks=False,
        )
    except OSError as error:
        raise PersonaRootLockError("root binding namespace changed") from error
    expected_binding = (lease.root_binding_device, lease.root_binding_inode)
    if (
        not storage.is_plain_regular_file_metadata(apparent_binding)
        or apparent_binding.st_nlink != 1
        or (opened_binding.st_dev, opened_binding.st_ino) != expected_binding
        or (apparent_binding.st_dev, apparent_binding.st_ino) != expected_binding
        or binding.get("profile") != lease.profile
        or binding.get("replay_id") != lease.replay_id
        or binding.get("artifact_bundle_sha256") != lease.artifact_bundle_sha256
        or binding.get("destination_root") != str(lease.root)
        or binding.get("filesystem_device") != lease.root_device
        or binding.get("sources_materialized") is not False
        or binding.get("actual_kio_evidence") is not False
        or binding.get("history_ready") is not False
    ):
        raise PersonaRootLockError("root binding namespace or semantics changed")


def require_active_lease(
    lease: ReplayRootLease,
    expected_root: os.PathLike[str] | str | None = None,
) -> ReplayRootLease:
    """Revalidate a held lease before a prepare/replay sub-operation."""
    if type(lease) is not ReplayRootLease:
        raise PersonaRootLockError("invalid replay root lease")
    if expected_root is not None:
        apparent = Path(os.path.abspath(os.path.expanduser(os.fspath(expected_root))))
        if apparent != lease.root:
            raise PersonaRootLockError("replay root lease path differs")
    _validate_bound_namespace(lease)
    return lease


def _root_descriptor_metadata(
    descriptor: int,
    *,
    lease: ReplayRootLease,
    expected_nlink: int | None,
    label: str,
) -> os.stat_result:
    try:
        metadata = os.fstat(descriptor)
    except OSError as error:
        raise PersonaRootLockError(f"{label} is not open") from error
    if (
        not _plain_root_metadata(metadata)
        or (metadata.st_dev, metadata.st_ino)
        != (lease.root_device, lease.root_inode)
        or metadata.st_nlink <= 0
        or (expected_nlink is not None and metadata.st_nlink != expected_nlink)
    ):
        raise PersonaRootLockError(f"{label} identity changed")
    return metadata


def _shares_open_directory_description(anchor_fd: int, candidate_fd: int) -> bool:
    """Probe whether two directory fds share one POSIX open description.

    ``fstat`` alone cannot distinguish a real ``dup`` from closing and
    reopening the same inode.  Mutable file-status flags belong to the open
    file description, so a real duplicate follows both an ``O_NONBLOCK``
    transition and its restoration while an independently opened descriptor
    does not.  The anchor is always restored before returning.

    This remains an in-process, non-authoritative probe: another thread can
    race the transitions.  It is nevertheless portable across the Darwin and
    Linux directory-offset behaviours used by supported CI hosts.
    """
    try:
        import fcntl
    except ImportError:  # pragma: no cover - guarded by POSIX callers.
        return False

    anchor_flags = None
    restored = False
    try:
        if anchor_fd == candidate_fd:
            return False
        anchor_flags = fcntl.fcntl(anchor_fd, fcntl.F_GETFL)
        candidate_flags = fcntl.fcntl(candidate_fd, fcntl.F_GETFL)
        if candidate_flags != anchor_flags:
            return False
        probe_flags = anchor_flags ^ os.O_NONBLOCK
        fcntl.fcntl(anchor_fd, fcntl.F_SETFL, probe_flags)
        probe_anchor = fcntl.fcntl(anchor_fd, fcntl.F_GETFL)
        probe_candidate = fcntl.fcntl(candidate_fd, fcntl.F_GETFL)
        fcntl.fcntl(anchor_fd, fcntl.F_SETFL, anchor_flags)
        restored = True
        restored_anchor = fcntl.fcntl(anchor_fd, fcntl.F_GETFL)
        restored_candidate = fcntl.fcntl(candidate_fd, fcntl.F_GETFL)
        return (
            probe_anchor == probe_flags
            and probe_candidate == probe_anchor
            and restored_anchor == anchor_flags
            and restored_candidate == anchor_flags
        )
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if anchor_flags is not None and not restored:
            try:
                fcntl.fcntl(anchor_fd, fcntl.F_SETFL, anchor_flags)
            except OSError:
                pass


def _is_owned_root_duplicate(
    anchor_fd: int,
    candidate_fd: int,
    expected_metadata: os.stat_result,
) -> bool:
    """Return true only while ``candidate_fd`` is still our anchor duplicate."""
    try:
        candidate = os.fstat(candidate_fd)
    except OSError:
        return False
    return (
        _plain_root_metadata(candidate)
        and candidate.st_nlink > 0
        and (
            candidate.st_dev,
            candidate.st_ino,
            candidate.st_nlink,
        )
        == (
            expected_metadata.st_dev,
            expected_metadata.st_ino,
            expected_metadata.st_nlink,
        )
        and _shares_open_directory_description(anchor_fd, candidate_fd)
    )


@contextmanager
def active_root_descriptor(
    lease: ReplayRootLease,
    expected_root: os.PathLike[str] | str | None = None,
) -> Iterator[int]:
    """Yield a private, non-inheritable duplicate of a lease-held root fd.

    The duplicate is derived from the descriptor already held by ``lease``;
    this function never reopens the diagnostic root path.  It therefore closes
    that particular path-check/open seam for a cooperating in-process reader.
    The caller must treat the yielded descriptor as borrowed.  A descriptor
    that remains closed, remains rebound to a foreign object, or remains
    inheritable is rejected on exit.

    This is not protection against hostile same-UID ABA changes, same-root or
    transient fd rebinding, leaked duplicates, or concurrent manipulation by
    another thread in the same process.  A formal execution boundary still
    requires a quiesced snapshot and process isolation.
    """
    if type(lease) is not ReplayRootLease:
        raise PersonaRootLockError("invalid replay root lease")
    canonical_expected_root = None
    if expected_root is not None:
        try:
            canonical_expected_root = Path(
                os.path.abspath(os.path.expanduser(os.fspath(expected_root)))
            )
        except Exception as error:
            raise PersonaRootLockError(
                "expected replay root path is invalid"
            ) from error
    require_active_lease(lease, canonical_expected_root)
    state = lease._state
    if type(state) is not _LeaseState:  # Defensive after exact lease validation.
        raise PersonaRootLockError("replay root lease state is invalid")
    held_metadata = _root_descriptor_metadata(
        state.root_fd,
        lease=lease,
        expected_nlink=None,
        label="lease-held replay root descriptor",
    )
    expected_nlink = held_metadata.st_nlink
    descriptor = -1
    body_error = None
    body_traceback = None
    release_error = None
    try:
        try:
            descriptor = os.dup(state.root_fd)
            if not _is_owned_root_duplicate(
                state.root_fd, descriptor, held_metadata
            ):
                raise PersonaRootLockError(
                    "cannot prove active replay root descriptor ownership"
                )
            os.set_inheritable(descriptor, False)
            duplicated = _root_descriptor_metadata(
                descriptor,
                lease=lease,
                expected_nlink=expected_nlink,
                label="active replay root descriptor",
            )
            if (
                (duplicated.st_dev, duplicated.st_ino, duplicated.st_nlink)
                != (held_metadata.st_dev, held_metadata.st_ino, held_metadata.st_nlink)
                or os.get_inheritable(descriptor)
                or not _is_owned_root_duplicate(
                    state.root_fd, descriptor, held_metadata
                )
            ):
                raise PersonaRootLockError(
                    "active replay root descriptor is not a private "
                    "non-inheritable duplicate"
                )
        except PersonaRootLockError:
            raise
        except OSError as error:
            raise PersonaRootLockError(
                "cannot duplicate the active replay root descriptor"
            ) from error

        try:
            yield descriptor
        except BaseException as error:  # Preserve body failure if release is clean.
            body_error = error
            body_traceback = error.__traceback__

        try:
            after = os.fstat(descriptor)
            descriptor_still_bound = _is_owned_root_duplicate(
                state.root_fd, descriptor, held_metadata
            )
            if (
                not descriptor_still_bound
                or (after.st_dev, after.st_ino, after.st_nlink)
                != (
                    held_metadata.st_dev,
                    held_metadata.st_ino,
                    held_metadata.st_nlink,
                )
                or os.get_inheritable(descriptor)
                or not _is_owned_root_duplicate(
                    state.root_fd, descriptor, held_metadata
                )
            ):
                raise PersonaRootLockError(
                    "active replay root descriptor was rebound or made inheritable"
                )
        except OSError as error:
            descriptor_still_bound = False
            release_error = PersonaRootLockError(
                "active replay root descriptor was closed or changed"
            )
            release_error.__cause__ = error
        except BaseException as error:
            release_error = error

        try:
            current_held = _root_descriptor_metadata(
                state.root_fd,
                lease=lease,
                expected_nlink=expected_nlink,
                label="lease-held replay root descriptor",
            )
            if (
                current_held.st_dev,
                current_held.st_ino,
                current_held.st_nlink,
            ) != (
                held_metadata.st_dev,
                held_metadata.st_ino,
                held_metadata.st_nlink,
            ):
                raise PersonaRootLockError(
                    "lease-held replay root descriptor identity changed"
                )
            require_active_lease(lease, canonical_expected_root)
        except BaseException as error:
            if release_error is None:
                release_error = error
    finally:
        if descriptor >= 0 and _is_owned_root_duplicate(
            state.root_fd, descriptor, held_metadata
        ):
            try:
                os.close(descriptor)
            except OSError as error:
                if release_error is None:
                    release_error = PersonaRootLockError(
                        "cannot close the active replay root descriptor"
                    )
                    release_error.__cause__ = error

    if release_error is not None:
        if body_error is not None:
            raise release_error from body_error
        raise release_error
    if body_error is not None:
        raise body_error.with_traceback(body_traceback)


@contextmanager
def replay_root_lock(
    root: os.PathLike[str] | str,
    *,
    expected_profile: str,
    expected_replay_id: str,
    expected_artifact_bundle_sha256: str,
    expected_root_binding_sha256: str,
) -> Iterator[ReplayRootLease]:
    """Hold a nonblocking exclusive lock on one ready-owned replay root.

    The owner marker is opened and locked without following links.  Its exact
    canonical bytes and both the root and marker namespace identities are
    checked before and after acquisition and again before unlock.
    """
    if os.name == "nt":  # pragma: no cover - Windows CI contract.
        raise PersonaRootLockError(
            "persona replay root lock is unavailable on Windows"
        )
    try:
        import fcntl
    except ImportError as error:  # pragma: no cover - non-POSIX fallback.
        raise PersonaRootLockError("POSIX flock is unavailable") from error

    try:
        expected_owner = storage.make_owner_marker(
            profile=expected_profile,
            replay_id=expected_replay_id,
            state="ready",
            artifact_bundle_sha256=expected_artifact_bundle_sha256,
            root_binding_sha256=expected_root_binding_sha256,
        )
    except storage.PersonaStorageError as error:
        raise PersonaRootLockError(str(error)) from error

    root_path = Path(os.path.abspath(os.path.expanduser(os.fspath(root))))
    try:
        preflight_root = root_path.lstat()
    except OSError as error:
        raise PersonaRootLockError("cannot inspect replay root") from error
    if not _plain_root_metadata(preflight_root) or root_path.is_symlink():
        raise PersonaRootLockError("replay root is not a plain directory")
    try:
        storage.require_ready_owned_root(
            root_path,
            profile=expected_profile,
            replay_id=expected_replay_id,
            artifact_bundle_sha256=expected_artifact_bundle_sha256,
            root_binding_sha256=expected_root_binding_sha256,
        )
    except storage.PersonaStorageError as error:
        raise PersonaRootLockError(str(error)) from error
    root_fd = -1
    owner_fd = -1
    root_binding_fd = -1
    process_identity = None
    guard_registered = False
    root_locked = False
    owner_locked = False
    state = None
    body_error = None
    body_traceback = None
    release_error = None
    try:
        try:
            root_fd = os.open(root_path, _open_flags(directory=True))
            opened_root = os.fstat(root_fd)
            apparent_root = root_path.lstat()
        except OSError as error:
            raise PersonaRootLockError("cannot safely open replay root") from error
        if (
            not _plain_root_metadata(opened_root)
            or not _plain_root_metadata(apparent_root)
            or root_path.is_symlink()
            or (opened_root.st_dev, opened_root.st_ino)
            != (apparent_root.st_dev, apparent_root.st_ino)
            or (opened_root.st_dev, opened_root.st_ino)
            != (preflight_root.st_dev, preflight_root.st_ino)
        ):
            raise PersonaRootLockError("replay root is not a stable plain directory")

        try:
            owner_fd = os.open(
                storage.OWNER_MARKER_NAME,
                _open_flags(directory=False),
                dir_fd=root_fd,
            )
            opened_owner = os.fstat(owner_fd)
            apparent_owner = os.stat(
                storage.OWNER_MARKER_NAME,
                dir_fd=root_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            raise PersonaRootLockError("cannot safely open owner marker") from error
        if (
            not _plain_owner_metadata(opened_owner)
            or not _plain_owner_metadata(apparent_owner)
            or (opened_owner.st_dev, opened_owner.st_ino)
            != (apparent_owner.st_dev, apparent_owner.st_ino)
        ):
            raise PersonaRootLockError("owner marker is not a stable plain file")

        try:
            root_binding_fd = os.open(
                _ROOT_BINDING_FILE_NAME,
                _open_flags(directory=False),
                dir_fd=root_fd,
            )
            opened_binding, root_binding_bytes, root_binding = (
                _read_bound_root_binding(
                    root_binding_fd,
                    expected_bytes=None,
                    expected_sha256=expected_root_binding_sha256,
                )
            )
            apparent_binding = os.stat(
                _ROOT_BINDING_FILE_NAME,
                dir_fd=root_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            raise PersonaRootLockError("cannot safely open root binding") from error
        if (
            not storage.is_plain_regular_file_metadata(apparent_binding)
            or apparent_binding.st_nlink != 1
            or (opened_binding.st_dev, opened_binding.st_ino)
            != (apparent_binding.st_dev, apparent_binding.st_ino)
            or root_binding.get("profile") != expected_profile
            or root_binding.get("replay_id") != expected_replay_id
            or root_binding.get("artifact_bundle_sha256") != expected_artifact_bundle_sha256
            or root_binding.get("destination_root") != str(root_path)
            or root_binding.get("filesystem_device") != opened_root.st_dev
            or root_binding.get("sources_materialized") is not False
            or root_binding.get("actual_kio_evidence") is not False
            or root_binding.get("history_ready") is not False
        ):
            raise PersonaRootLockError("root binding does not bind this root")

        expected_bytes = _canonical_owner_bytes(expected_owner)
        _read_bound_owner(owner_fd, expected_bytes=expected_bytes)
        process_identity = (opened_root.st_dev, opened_root.st_ino)
        with _PROCESS_GUARD:
            if process_identity in _ACTIVE_ROOT_IDENTITIES:
                raise PersonaRootLockError("replay root lock is already held")
            _ACTIVE_ROOT_IDENTITIES.add(process_identity)
            guard_registered = True
        try:
            fcntl.flock(root_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            root_locked = True
            fcntl.flock(owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            owner_locked = True
        except OSError as error:
            contention_errors = {
                errno.EACCES,
                errno.EAGAIN,
                getattr(errno, "EWOULDBLOCK", errno.EAGAIN),
            }
            if error.errno in contention_errors:
                raise PersonaRootLockError("replay root lock is contended") from error
            raise PersonaRootLockError("cannot acquire replay root lock") from error

        state = _LeaseState(
            root_fd=root_fd,
            owner_fd=owner_fd,
            root_binding_fd=root_binding_fd,
            expected_owner_bytes=expected_bytes,
            expected_root_binding_bytes=root_binding_bytes,
            owner_pid=os.getpid(),
        )
        lease = ReplayRootLease(
            root=root_path,
            profile=expected_profile,
            replay_id=expected_replay_id,
            artifact_bundle_sha256=expected_artifact_bundle_sha256,
            root_binding_sha256=expected_root_binding_sha256,
            root_device=opened_root.st_dev,
            root_inode=opened_root.st_ino,
            owner_device=opened_owner.st_dev,
            owner_inode=opened_owner.st_ino,
            root_binding_device=opened_binding.st_dev,
            root_binding_inode=opened_binding.st_ino,
            owner_pid=state.owner_pid,
            _state=state,
        )
        _validate_bound_namespace(lease)
        try:
            yield lease
        except BaseException as error:  # Preserve body failure if release is clean.
            body_error = error
            body_traceback = error.__traceback__
        try:
            _validate_bound_namespace(lease)
        except BaseException as error:
            release_error = error
    finally:
        inherited_after_fork = (
            state is not None and os.getpid() != state.owner_pid
        )
        if state is not None:
            state.active = False
        if owner_fd >= 0 and owner_locked and not inherited_after_fork:
            try:
                fcntl.flock(owner_fd, fcntl.LOCK_UN)
            except OSError as error:
                if release_error is None:
                    release_error = PersonaRootLockError(
                        "cannot release replay root lock"
                    )
                    release_error.__cause__ = error
        if owner_fd >= 0:
            try:
                os.close(owner_fd)
            except OSError as error:
                if release_error is None:
                    release_error = PersonaRootLockError(
                        "cannot close replay root owner marker"
                    )
                    release_error.__cause__ = error
        if root_binding_fd >= 0:
            try:
                os.close(root_binding_fd)
            except OSError as error:
                if release_error is None:
                    release_error = PersonaRootLockError(
                        "cannot close replay root binding"
                    )
                    release_error.__cause__ = error
        if root_fd >= 0 and root_locked and not inherited_after_fork:
            try:
                fcntl.flock(root_fd, fcntl.LOCK_UN)
            except OSError as error:
                if release_error is None:
                    release_error = PersonaRootLockError(
                        "cannot release replay root directory lock"
                    )
                    release_error.__cause__ = error
        if root_fd >= 0:
            try:
                os.close(root_fd)
            except OSError as error:
                if release_error is None:
                    release_error = PersonaRootLockError(
                        "cannot close replay root directory"
                    )
                    release_error.__cause__ = error
        if process_identity is not None and guard_registered:
            with _PROCESS_GUARD:
                _ACTIVE_ROOT_IDENTITIES.discard(process_identity)

    if release_error is not None:
        if body_error is not None:
            raise release_error from body_error
        raise release_error
    if body_error is not None:
        raise body_error.with_traceback(body_traceback)
