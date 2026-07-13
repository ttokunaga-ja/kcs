#!/usr/bin/env python3
"""Fail-closed W0 KCS command runner primitives for persona-PC fixtures.

This module is deliberately narrower than a persona prepare orchestrator.  It
validates the two fresh-W0 commands ``init .`` and ``index --offline --yes``,
but public environment creation and all binary execution remain fail-closed
until trusted binary provenance plus a handle-relative, network-contained
execution boundary can keep ``cwd`` and every mutable device path inside the
leased replay root.  It does not inspect KCS internals, reset a device registry,
delete a ``.kcs`` directory, run a history wave, or claim that a persona is
history-ready.

The command-receipt schemas are explicitly unbound.  After safe execution is
implemented, a later semantic attestor and root-lease-integrated orchestrator
must still bind them before history replay can become executable.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import tempfile
import time

from eval import eval_env
from eval import persona_root_lock as root_lock


class PersonaKcsRunnerError(RuntimeError):
    """A fail-closed W0 runner validation or execution failure."""


BINARY_IDENTITY_SCHEMA = "kcs.persona.kcs-binary-identity/v1"
ENVIRONMENT_RECEIPT_SCHEMA = "kcs.persona.kcs-environment-receipt/v1"
INIT_RECEIPT_SCHEMA = "kcs.persona.kcs-init-receipt/v1"
OFFLINE_INDEX_RECEIPT_SCHEMA = "kcs.persona.kcs-offline-index-receipt/v1"
RESUME_CLASSIFICATION_SCHEMA = "kcs.persona.kcs-resume-classification/v1"

# A replay-root lease prevents cooperating writers from running concurrently,
# but it does not make pathname resolution safe.  In particular, a validated
# scope can be renamed and replaced with a symlink before ``Popen(cwd=...)``
# resolves it.  Keep physical W0 command execution unavailable until the child
# is entered through a proven handle-relative/non-escape boundary.
HANDLE_RELATIVE_EXECUTION_AVAILABLE = False
PERSONA_FILESYSTEM_MUTATION_AVAILABLE = False
# Path, inode, mode, and SHA-256 attest integrity only.  They do not authorize
# executing caller-selected code or prove that ``--version`` is side-effect
# free.  Keep even version probing disabled until expected artifact provenance,
# operator authorization, filesystem confinement, and network isolation are
# bound by the orchestrator.
TRUSTED_BINARY_EXECUTION_AVAILABLE = False

MAX_BINARY_BYTES = 512 * 1024 * 1024
MAX_JSON_OUTPUT_BYTES = 1024 * 1024
MAX_VERSION_OUTPUT_BYTES = 16 * 1024
MAX_DIAGNOSTIC_CHARS = 4_096
WINDOWS_REPARSE_POINT_ATTRIBUTE = 0x400
HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
HEX_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
UTC_SECONDS_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z"
)

EXPECTED_OFFLINE_COUNT_KEYS = frozenset({
    "physical_files",
    "normalized_files",
    "pending_online_tasks",
    "skipped_unrecognized_binary_files",
    "failed_files",
    "pending_files",
    "skipped_oversized_files",
    "completed_online_tasks",
    "external_cost_microusd",
})

_INIT_RESULT_KEYS = frozenset({"status", "repaired", "path", "kcs_path"})
_INDEX_RESULT_KEYS = frozenset({
    "status",
    "approval_method",
    "network_allowed",
    "network_opt_in",
    "pending_online_tasks",
    "paused_tasks",
    "failed_files",
    "normalized_files",
    "pending_files",
    "skipped_oversized_files",
    "skipped_unrecognized_binary_files",
    "embedding_tasks_executed",
    "embedding_tasks_failed",
    "tree_hash",
    "commit_hash",
    "commit",
    "budget_warning",
    "skipped_units",
})
_COMMIT_KEYS = frozenset({
    "commit_type",
    "created_at",
    "message",
    "object_type",
    "parents",
    "stats",
    "tool_lock_hash",
    "tree",
})
_COMMIT_STATS_KEYS = frozenset({
    "files_added", "files_modified", "files_deleted"
})
UNBOUND_COMMAND_RECEIPTS_STATUS = (
    "unbound_command_receipts_require_plan_root_store_semantic_binding"
)
_UNBOUND_CLAIMS = {
    "receipt_binding_status": UNBOUND_COMMAND_RECEIPTS_STATUS,
    "actual_kcs_chunks_attested": False,
    "opaque_runtime_contents_attested": False,
    "history_ready_attested": False,
    "history_assignment_executable": False,
}
_CONTROLLED_ENVIRONMENT_KEYS = frozenset({
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "TMPDIR",
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
})
_KNOWN_CREDENTIAL_NAMES = frozenset({
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AZURE_CLIENT_SECRET",
})
_EVAL_ENV_AMBIENT_CREDENTIALS = frozenset({
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
})


@dataclass(frozen=True)
class SubprocessLimits:
    """Finite bounds for one child process and each captured stream."""

    runtime_seconds: float = 60 * 60
    output_bytes: int = MAX_JSON_OUTPUT_BYTES
    poll_seconds: float = 0.02

    def validate(self) -> "SubprocessLimits":
        if (
            isinstance(self.runtime_seconds, bool)
            or not isinstance(self.runtime_seconds, (int, float))
            or not 0 < self.runtime_seconds <= 4 * 60 * 60
        ):
            raise PersonaKcsRunnerError("invalid subprocess runtime bound")
        if (
            type(self.output_bytes) is not int
            or not 1 <= self.output_bytes <= 8 * 1024 * 1024
        ):
            raise PersonaKcsRunnerError("invalid subprocess output bound")
        if (
            isinstance(self.poll_seconds, bool)
            or not isinstance(self.poll_seconds, (int, float))
            or not 0 < self.poll_seconds <= 1
        ):
            raise PersonaKcsRunnerError("invalid subprocess poll interval")
        return self


VERSION_LIMITS = SubprocessLimits(
    runtime_seconds=10,
    output_bytes=MAX_VERSION_OUTPUT_BYTES,
    poll_seconds=0.01,
)


def _is_reparse_point(metadata):
    return bool(
        getattr(metadata, "st_file_attributes", 0)
        & WINDOWS_REPARSE_POINT_ATTRIBUTE
    ) or bool(getattr(metadata, "st_reparse_tag", 0))


def _is_plain_regular(metadata):
    return stat.S_ISREG(metadata.st_mode) and not _is_reparse_point(metadata)


def _is_plain_directory(metadata):
    return stat.S_ISDIR(metadata.st_mode) and not _is_reparse_point(metadata)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _matches(pattern, value):
    return type(value) is str and pattern.fullmatch(value) is not None


def _canonical_json_bytes(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _strict_integer(value, label, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise PersonaKcsRunnerError(f"{label} must be an integer >= {minimum}")
    return value


def _canonical_existing_path(path, label):
    supplied = Path(path).expanduser()
    if not supplied.is_absolute():
        raise PersonaKcsRunnerError(f"{label} must be an absolute canonical path")
    normalized = Path(os.path.normpath(os.fspath(supplied)))
    if supplied != normalized:
        raise PersonaKcsRunnerError(f"{label} is not a canonical path: {supplied}")
    supplied = normalized
    try:
        canonical = supplied.resolve(strict=True)
    except OSError as error:
        raise PersonaKcsRunnerError(f"{label} is missing or inaccessible: {supplied}") from error
    if supplied != canonical:
        raise PersonaKcsRunnerError(f"{label} is not a canonical path: {supplied}")
    return canonical


def _require_plain_directory(path, label):
    path = _canonical_existing_path(path, label)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise PersonaKcsRunnerError(f"cannot inspect {label}: {path}") from error
    if path.is_symlink() or not _is_plain_directory(metadata):
        raise PersonaKcsRunnerError(f"{label} must be a plain directory: {path}")
    return path, metadata


def _binary_path(path):
    path = _canonical_existing_path(path, "kcs binary")
    try:
        metadata = path.lstat()
    except OSError as error:
        raise PersonaKcsRunnerError(f"cannot inspect kcs binary: {path}") from error
    if path.is_symlink() or not _is_plain_regular(metadata):
        raise PersonaKcsRunnerError("kcs binary must be a plain regular file")
    if metadata.st_nlink != 1:
        raise PersonaKcsRunnerError("kcs binary must have exactly one hard link")
    mode = stat.S_IMODE(metadata.st_mode)
    if not mode & 0o111 or mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
        raise PersonaKcsRunnerError("kcs binary has an unsafe executable mode")
    if mode & 0o022:
        raise PersonaKcsRunnerError("kcs binary must not be group/world writable")
    if not 0 < metadata.st_size <= MAX_BINARY_BYTES:
        raise PersonaKcsRunnerError("kcs binary size is outside the safe bound")
    return path


def _read_binary_snapshot(path):
    """Read one stable executable identity through a no-follow descriptor."""
    path = _binary_path(path)
    if os.name != "posix":
        raise PersonaKcsRunnerError(
            "safe persona kcs binary inspection requires POSIX descriptors"
        )
    required_flags = {}
    for name in ("O_CLOEXEC", "O_NOFOLLOW"):
        value = getattr(os, name, None)
        if type(value) is not int or value == 0:
            raise PersonaKcsRunnerError(
                f"required descriptor flag {name} is unavailable"
            )
        required_flags[name] = value
    flags = os.O_RDONLY | required_flags["O_CLOEXEC"] | required_flags["O_NOFOLLOW"]
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise PersonaKcsRunnerError(f"cannot open kcs binary safely: {path}") from error
    try:
        before = os.fstat(descriptor)
        if not _is_plain_regular(before) or before.st_nlink != 1:
            raise PersonaKcsRunnerError("opened kcs binary is not a single-link plain file")
        if not 0 < before.st_size <= MAX_BINARY_BYTES:
            raise PersonaKcsRunnerError("opened kcs binary exceeds its size bound")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_BINARY_BYTES:
                raise PersonaKcsRunnerError("kcs binary grew beyond its size bound")
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    fields_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        getattr(before, "st_mtime_ns", None),
        getattr(before, "st_ctime_ns", None),
    )
    fields_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        getattr(after, "st_mtime_ns", None),
        getattr(after, "st_ctime_ns", None),
    )
    try:
        path_after = path.lstat()
    except OSError as error:
        raise PersonaKcsRunnerError("kcs binary disappeared while hashing") from error
    if fields_before != fields_after or (
        path_after.st_dev,
        path_after.st_ino,
        path_after.st_mode,
        path_after.st_nlink,
        path_after.st_size,
    ) != (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
    ):
        raise PersonaKcsRunnerError("kcs binary identity changed while hashing")
    return {
        "canonical_path": str(path),
        "device": before.st_dev,
        "inode": before.st_ino,
        "mode": stat.S_IMODE(before.st_mode),
        "size": before.st_size,
        "mtime_ns": getattr(before, "st_mtime_ns", 0),
        "ctime_ns": getattr(before, "st_ctime_ns", 0),
        "sha256": digest.hexdigest(),
    }


def _binary_projection(identity):
    return {
        key: identity[key]
        for key in (
            "canonical_path", "device", "inode", "mode", "size",
            "mtime_ns", "ctime_ns", "sha256",
        )
    }


def _validate_binary_identity_shape(identity):
    expected_keys = {
        "schema", "schema_version", "canonical_path", "device", "inode",
        "mode", "size", "mtime_ns", "ctime_ns", "sha256", "version",
        "version_stdout_sha256", "version_stderr_sha256",
    }
    if type(identity) is not dict or set(identity) != expected_keys:
        raise PersonaKcsRunnerError("kcs binary identity has an invalid shape")
    if (
        identity.get("schema") != BINARY_IDENTITY_SCHEMA
        or type(identity.get("schema_version")) is not int
        or identity.get("schema_version") != 1
        or type(identity.get("canonical_path")) is not str
        or type(identity.get("version")) is not str
        or not identity["version"]
        or not _matches(HEX_SHA256_RE, identity.get("sha256"))
        or not _matches(HEX_SHA256_RE, identity.get("version_stdout_sha256"))
        or not _matches(HEX_SHA256_RE, identity.get("version_stderr_sha256"))
    ):
        raise PersonaKcsRunnerError("kcs binary identity fields are invalid")
    for field in ("device", "inode", "mode", "size", "mtime_ns", "ctime_ns"):
        _strict_integer(identity.get(field), f"binary identity {field}")
    return dict(identity)


def _probe_environment():
    return {
        "PATH": os.defpath,
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
    }


def _terminate_process_group(process):
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            if process.poll() is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
    elif process.poll() is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass


def _capture_bounded(handle, limit, label):
    size = os.fstat(handle.fileno()).st_size
    handle.seek(0)
    value = handle.read(limit + 1)
    if size > limit or len(value) > limit:
        raise PersonaKcsRunnerError(f"{label} exceeded {limit} bytes")
    return value


def _run_process_bounded(command, cwd, environment, limits):
    _require_trusted_binary_execution()
    limits = limits.validate()
    options = {}
    if os.name == "posix":
        options["start_new_session"] = True
    elif os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        raise PersonaKcsRunnerError("unsupported subprocess platform")
    with (
        tempfile.TemporaryFile(mode="w+b") as stdout_file,
        tempfile.TemporaryFile(mode="w+b") as stderr_file,
    ):
        try:
            process = subprocess.Popen(
                list(command),
                cwd=cwd,
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                close_fds=True,
                **options,
            )
        except OSError as error:
            raise PersonaKcsRunnerError(
                f"cannot start bounded subprocess: {command[0]}"
            ) from error
        deadline = time.monotonic() + limits.runtime_seconds
        timed_out = False
        overflow = False
        try:
            while process.poll() is None:
                if any(
                    os.fstat(handle.fileno()).st_size > limits.output_bytes
                    for handle in (stdout_file, stderr_file)
                ):
                    overflow = True
                    _terminate_process_group(process)
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    _terminate_process_group(process)
                    break
                time.sleep(min(limits.poll_seconds, remaining))
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _terminate_process_group(process)
                process.wait(timeout=5)
        finally:
            if process.poll() is None:
                _terminate_process_group(process)
                process.wait(timeout=5)
            # A child may exit after spawning a descendant in the new group.
            _terminate_process_group(process)
        stdout = _capture_bounded(stdout_file, limits.output_bytes, "stdout")
        stderr = _capture_bounded(stderr_file, limits.output_bytes, "stderr")
        if overflow:
            raise PersonaKcsRunnerError(
                f"subprocess output exceeded {limits.output_bytes} bytes per stream"
            )
        if timed_out:
            raise PersonaKcsRunnerError(
                f"subprocess exceeded {limits.runtime_seconds} seconds"
            )
        return process.returncode, stdout, stderr


def _require_trusted_binary_execution():
    if TRUSTED_BINARY_EXECUTION_AVAILABLE is not True:
        raise PersonaKcsRunnerError(
            "trusted persona KCS binary execution is unavailable"
        )


def _version_probe(path, limits=VERSION_LIMITS):
    _require_trusted_binary_execution()
    returncode, stdout, stderr = _run_process_bounded(
        [str(path), "--version"],
        path.parent,
        _probe_environment(),
        limits,
    )
    if returncode != 0:
        raise PersonaKcsRunnerError(
            f"kcs --version failed with exit {returncode}"
        )
    if stderr:
        raise PersonaKcsRunnerError("kcs --version wrote to stderr")
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PersonaKcsRunnerError("kcs --version is not UTF-8") from error
    if "\x00" in text or not text.endswith("\n") or text.count("\n") != 1:
        raise PersonaKcsRunnerError("kcs --version must be one newline-terminated line")
    version = text[:-1]
    if not version or version.strip() != version:
        raise PersonaKcsRunnerError("kcs --version line is empty or non-canonical")
    return version, stdout, stderr


def attest_kcs_binary(path, *, version_limits=VERSION_LIMITS):
    """Hash a safe executable path, then refuse untrusted version execution."""
    first = _read_binary_snapshot(path)
    _require_trusted_binary_execution()
    version_a, stdout_a, stderr_a = _version_probe(
        Path(first["canonical_path"]), version_limits
    )
    middle = _read_binary_snapshot(first["canonical_path"])
    version_b, stdout_b, stderr_b = _version_probe(
        Path(first["canonical_path"]), version_limits
    )
    final = _read_binary_snapshot(first["canonical_path"])
    if first != middle or first != final:
        raise PersonaKcsRunnerError("kcs binary identity changed during attestation")
    if (version_a, stdout_a, stderr_a) != (version_b, stdout_b, stderr_b):
        raise PersonaKcsRunnerError("kcs binary version output is unstable")
    return {
        "schema": BINARY_IDENTITY_SCHEMA,
        "schema_version": 1,
        **first,
        "version": version_a,
        "version_stdout_sha256": _sha256(stdout_a),
        "version_stderr_sha256": _sha256(stderr_a),
    }


def require_stable_kcs_binary(identity):
    """Re-read binary bytes, then refuse untrusted version re-execution."""
    identity = _validate_binary_identity_shape(identity)
    observed = _read_binary_snapshot(identity["canonical_path"])
    if observed != _binary_projection(identity):
        raise PersonaKcsRunnerError("kcs binary no longer matches its identity")
    version, stdout, stderr = _version_probe(Path(identity["canonical_path"]))
    final = _read_binary_snapshot(identity["canonical_path"])
    if final != observed:
        raise PersonaKcsRunnerError(
            "kcs binary identity changed during version revalidation"
        )
    if (
        version != identity["version"]
        or _sha256(stdout) != identity["version_stdout_sha256"]
        or _sha256(stderr) != identity["version_stderr_sha256"]
    ):
        raise PersonaKcsRunnerError("kcs binary version no longer matches its identity")
    return identity


def binary_identity_sha256(identity):
    identity = _validate_binary_identity_shape(identity)
    return _sha256(_canonical_json_bytes(identity))


def _forbidden_environment_names(environment):
    return sorted(
        name
        for name in environment
        if name.startswith("KCS_")
        or name in _KNOWN_CREDENTIAL_NAMES
        or name.endswith("_API_KEY")
    )


def _require_person_under_lease(lease, person_root):
    try:
        lease = root_lock.require_active_lease(lease)
    except root_lock.PersonaRootLockError as error:
        raise PersonaKcsRunnerError("an active replay-root lease is required") from error
    person, person_metadata = _require_plain_directory(person_root, "persona root")
    devices = lease.root / "devices"
    _devices, devices_metadata = _require_plain_directory(
        devices, "leased devices directory"
    )
    if person.parent != devices or not _matches(IDENTIFIER_RE, person.name):
        raise PersonaKcsRunnerError(
            "persona root must be one canonical devices/<slug> child of the leased root"
        )
    binding = (
        devices_metadata.st_dev,
        devices_metadata.st_ino,
        person_metadata.st_dev,
        person_metadata.st_ino,
    )
    return lease, person, binding


def _revalidate_person_under_lease(lease, person, binding, label):
    try:
        root_lock.require_active_lease(lease, lease.root)
        _devices, devices_metadata = _require_plain_directory(
            lease.root / "devices", "leased devices directory"
        )
        observed_person, person_metadata = _require_plain_directory(
            person, "persona root"
        )
    except (root_lock.PersonaRootLockError, PersonaKcsRunnerError) as error:
        raise PersonaKcsRunnerError(
            f"replay-root/person identity changed during {label}"
        ) from error
    observed = (
        devices_metadata.st_dev,
        devices_metadata.st_ino,
        person_metadata.st_dev,
        person_metadata.st_ino,
    )
    if observed_person != person or observed != binding:
        raise PersonaKcsRunnerError(
            f"replay-root/person identity changed during {label}"
        )


def _revalidate_scope(scope, expected_identity, label):
    try:
        observed, metadata = _require_plain_directory(scope, "scope directory")
    except PersonaKcsRunnerError as error:
        raise PersonaKcsRunnerError(f"scope identity changed during {label}") from error
    if observed != scope or (metadata.st_dev, metadata.st_ino) != expected_identity:
        raise PersonaKcsRunnerError(f"scope identity changed during {label}")


def _preflight_optional_directory(path, label):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise PersonaKcsRunnerError(f"cannot inspect {label}: {path}") from error
    if path.is_symlink() or not _is_plain_directory(metadata):
        raise PersonaKcsRunnerError(f"{label} is not a plain directory: {path}")


def _require_persona_filesystem_mutation():
    if PERSONA_FILESYSTEM_MUTATION_AVAILABLE is not True:
        raise PersonaKcsRunnerError(
            "handle-relative persona filesystem mutation is unavailable"
        )


def build_person_subprocess_environment(person_root, *, lease, home_dir=None):
    """Validate the leased persona binding, then refuse unsafe path mutation.

    The currently unreachable implementation rejects unsafe pre-existing
    runtime path types, delegates isolated XDG creation to
    ``eval_env.subprocess_env``, then projects only a fixed key set.  It must not
    become reachable until those creations are handle-relative and non-escaping.
    """
    lease, root, person_binding = _require_person_under_lease(lease, person_root)
    home = root / "home" if home_dir is None else _canonical_existing_path(
        home_dir, "persona home"
    )
    if home != root / "home":
        raise PersonaKcsRunnerError("persona home must be the canonical root/home")
    _require_plain_directory(home, "persona home")
    _require_persona_filesystem_mutation()
    device = root / ".kcs-eval-device"
    _preflight_optional_directory(device, "isolated device root")
    for leaf in ("config", "data", "cache"):
        _preflight_optional_directory(device / leaf, f"isolated device {leaf}")

    # eval_env intentionally scrubs every KCS_* seam and the two production
    # adapter credentials.  Any other credential-shaped ambient value is not
    # part of that contract, so reject it before eval_env creates a directory.
    unexpected_ambient = sorted(
        name
        for name in _forbidden_environment_names(os.environ)
        if not name.startswith("KCS_")
        and name not in _EVAL_ENV_AMBIENT_CREDENTIALS
    )
    if unexpected_ambient:
        raise PersonaKcsRunnerError(
            "ambient credential-like variables are outside eval_env scrubbing: "
            + ", ".join(unexpected_ambient)
        )

    try:
        scrubbed = eval_env.subprocess_env(root, home_dir=home)
        forbidden = _forbidden_environment_names(scrubbed)
        if forbidden:
            raise PersonaKcsRunnerError(
                "ambient credential-like variables remain after eval_env scrubbing: "
                + ", ".join(forbidden)
            )
        cache = Path(scrubbed["XDG_CACHE_HOME"])
        temporary = cache / "tmp"
        _preflight_optional_directory(temporary, "isolated temporary directory")
        try:
            temporary.mkdir(mode=0o700, exist_ok=True)
        except OSError as error:
            raise PersonaKcsRunnerError(
                "cannot create isolated temporary directory"
            ) from error

        environment = {
            "HOME": scrubbed["HOME"],
            "XDG_CONFIG_HOME": scrubbed["XDG_CONFIG_HOME"],
            "XDG_DATA_HOME": scrubbed["XDG_DATA_HOME"],
            "XDG_CACHE_HOME": scrubbed["XDG_CACHE_HOME"],
            "TMPDIR": str(temporary),
            "PATH": os.defpath,
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
            # The command line is also forced offline.  These deterministic dead
            # proxies are defense in depth, not evidence that a network sandbox ran.
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
        validate_person_subprocess_environment(environment, root)
        return environment
    finally:
        _revalidate_person_under_lease(
            lease, root, person_binding, "environment preparation"
        )


def validate_person_subprocess_environment(environment, person_root):
    if type(environment) is not dict or set(environment) != _CONTROLLED_ENVIRONMENT_KEYS:
        raise PersonaKcsRunnerError("effective persona environment has unexpected keys")
    forbidden = _forbidden_environment_names(environment)
    if forbidden:
        raise PersonaKcsRunnerError(
            "effective persona environment contains forbidden variables: "
            + ", ".join(forbidden)
        )
    if any(type(value) is not str or "\x00" in value for value in environment.values()):
        raise PersonaKcsRunnerError("effective persona environment contains invalid values")
    root, _ = _require_plain_directory(person_root, "persona root")
    expected = {
        "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / ".kcs-eval-device" / "config"),
        "XDG_DATA_HOME": str(root / ".kcs-eval-device" / "data"),
        "XDG_CACHE_HOME": str(root / ".kcs-eval-device" / "cache"),
        "TMPDIR": str(root / ".kcs-eval-device" / "cache" / "tmp"),
        "PATH": os.defpath,
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "",
    }
    if environment != expected:
        raise PersonaKcsRunnerError("effective persona environment is not canonical")
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMPDIR"):
        _require_plain_directory(environment[key], f"environment {key}")
    return dict(environment)


def environment_receipt(environment, person_root):
    environment = validate_person_subprocess_environment(environment, person_root)
    return {
        "schema": ENVIRONMENT_RECEIPT_SCHEMA,
        "schema_version": 1,
        "persona_root": str(_canonical_existing_path(person_root, "persona root")),
        "controlled_environment": environment,
        "effective_environment_forbidden_credentials_present": False,
        "external_api_execution_authorized": False,
        **_UNBOUND_CLAIMS,
    }


def environment_receipt_sha256(environment, person_root):
    return _sha256(_canonical_json_bytes(environment_receipt(environment, person_root)))


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PersonaKcsRunnerError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value):
    raise PersonaKcsRunnerError(f"non-finite JSON number is forbidden: {value}")


def _reject_json_float(value):
    raise PersonaKcsRunnerError(f"floating-point JSON number is forbidden: {value}")


def parse_strict_json_object(raw, *, label="kcs output", maximum_bytes=MAX_JSON_OUTPUT_BYTES):
    """Decode one UTF-8 JSON object, rejecting duplicate keys at every depth."""
    if type(raw) is not bytes:
        raise PersonaKcsRunnerError(f"{label} must be bytes")
    if not 0 < len(raw) <= maximum_bytes:
        raise PersonaKcsRunnerError(f"{label} size is outside its bound")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise PersonaKcsRunnerError(f"{label} must not contain a UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
        )
    except PersonaKcsRunnerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PersonaKcsRunnerError(f"{label} is not strict UTF-8 JSON") from error
    if type(value) is not dict:
        raise PersonaKcsRunnerError(f"{label} must be one JSON object")
    return value


def validate_init_result(value, scope_dir):
    scope, _ = _require_plain_directory(scope_dir, "scope directory")
    if type(value) is not dict or set(value) != _INIT_RESULT_KEYS:
        raise PersonaKcsRunnerError("init result has an unexpected shape")
    if (
        value.get("status") != "initialized"
        or value.get("repaired") != []
        or value.get("path") != str(scope)
        or value.get("kcs_path") != str(scope / ".kcs")
    ):
        raise PersonaKcsRunnerError("init result does not prove a fresh initialization")
    return dict(value)


def validate_expected_offline_counts(expected_counts):
    if type(expected_counts) is not dict or set(expected_counts) != EXPECTED_OFFLINE_COUNT_KEYS:
        raise PersonaKcsRunnerError("offline counter oracle has an unexpected shape")
    result = {}
    for key in sorted(EXPECTED_OFFLINE_COUNT_KEYS):
        result[key] = _strict_integer(expected_counts.get(key), f"offline oracle {key}")
    if (
        result["failed_files"] != 0
        or result["pending_files"] != 0
        or result["skipped_oversized_files"] != 0
        or result["completed_online_tasks"] != 0
        or result["external_cost_microusd"] != 0
    ):
        raise PersonaKcsRunnerError("offline counter oracle contains nonzero failure/online cost")
    return result


def _validate_commit(commit, result, expected_counts):
    if type(commit) is not dict or set(commit) != _COMMIT_KEYS:
        raise PersonaKcsRunnerError("index commit has an unexpected shape")
    if (
        commit.get("commit_type") != "auto"
        or commit.get("message") != "kcs index auto snapshot"
        or commit.get("object_type") != "commit"
        or commit.get("parents") != []
        or not _matches(UTC_SECONDS_RE, commit.get("created_at"))
        or not _matches(HASH_RE, commit.get("tool_lock_hash"))
        or commit.get("tree") != result.get("tree_hash")
    ):
        raise PersonaKcsRunnerError("index commit is not the fresh W0 auto commit")
    stats = commit.get("stats")
    if type(stats) is not dict or set(stats) != _COMMIT_STATS_KEYS:
        raise PersonaKcsRunnerError("index commit stats have an unexpected shape")
    for key in _COMMIT_STATS_KEYS:
        _strict_integer(stats.get(key), f"commit stats {key}")
    if stats != {
        "files_added": expected_counts["physical_files"],
        "files_modified": 0,
        "files_deleted": 0,
    }:
        raise PersonaKcsRunnerError("fresh W0 commit stats differ from physical files")
    observed_hash = "sha256:" + _sha256(_canonical_json_bytes(commit).rstrip(b"\n"))
    if result.get("commit_hash") != observed_hash:
        raise PersonaKcsRunnerError("index commit_hash does not authenticate commit")


def validate_offline_index_result(value, expected_counts, *, expected_status="indexed"):
    expected_counts = validate_expected_offline_counts(expected_counts)
    if expected_status not in ("indexed", "noop"):
        raise PersonaKcsRunnerError("invalid expected index status")
    if type(value) is not dict or set(value) != _INDEX_RESULT_KEYS:
        raise PersonaKcsRunnerError("offline index result has an unexpected shape")
    if (
        value.get("status") != expected_status
        or value.get("approval_method") != "yes"
        or value.get("network_allowed") is not False
        or value.get("network_opt_in") is not False
        or value.get("paused_tasks") != 0
        or value.get("embedding_tasks_executed") != 0
        or value.get("embedding_tasks_failed") != 0
        or value.get("budget_warning") is not None
        or value.get("skipped_units") != []
    ):
        raise PersonaKcsRunnerError("offline index result violates its offline/no-cost contract")
    for key in (
        "pending_online_tasks", "failed_files", "normalized_files", "pending_files",
        "skipped_oversized_files", "skipped_unrecognized_binary_files",
        "paused_tasks", "embedding_tasks_executed", "embedding_tasks_failed",
    ):
        _strict_integer(value.get(key), f"offline index {key}")
    for key in (
        "pending_online_tasks", "failed_files", "normalized_files", "pending_files",
        "skipped_oversized_files", "skipped_unrecognized_binary_files",
    ):
        if value[key] != expected_counts[key]:
            raise PersonaKcsRunnerError(
                f"offline index {key} mismatch: expected {expected_counts[key]}, got {value[key]}"
            )
    if not _matches(HASH_RE, value.get("tree_hash")):
        raise PersonaKcsRunnerError("offline index tree_hash is invalid")
    if expected_status == "indexed":
        if not _matches(HASH_RE, value.get("commit_hash")):
            raise PersonaKcsRunnerError("fresh offline index commit_hash is invalid")
        _validate_commit(value.get("commit"), value, expected_counts)
    elif value.get("commit_hash") is not None or value.get("commit") is not None:
        raise PersonaKcsRunnerError("noop offline index unexpectedly advanced HEAD")
    return dict(value)


def _diagnostic(raw):
    text = raw.decode("utf-8", errors="replace")
    if len(text) > MAX_DIAGNOSTIC_CHARS:
        return text[:MAX_DIAGNOSTIC_CHARS] + "...[truncated]"
    return text


def _run_kcs_json(identity, scope, arguments, environment, limits):
    identity = require_stable_kcs_binary(identity)
    binary = identity["canonical_path"]
    returncode, stdout, stderr = _run_process_bounded(
        [binary, "--json", *arguments], scope, environment, limits
    )
    require_stable_kcs_binary(identity)
    if returncode != 0:
        raise PersonaKcsRunnerError(
            f"kcs {' '.join(arguments)} failed with exit {returncode}; "
            f"stdout={_diagnostic(stdout)!r}; stderr={_diagnostic(stderr)!r}"
        )
    if stderr:
        raise PersonaKcsRunnerError(
            f"successful kcs command wrote to stderr: {_diagnostic(stderr)!r}"
        )
    value = parse_strict_json_object(stdout)
    return value, {
        "returncode": 0,
        "stdout_sha256": _sha256(stdout),
        "stderr_sha256": _sha256(stderr),
    }


def _safe_kcs_directory(scope, *, required):
    path = scope / ".kcs"
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if required:
            raise PersonaKcsRunnerError(f"scope .kcs is missing: {scope}")
        return None
    except OSError as error:
        raise PersonaKcsRunnerError(f"cannot inspect scope .kcs: {scope}") from error
    if path.is_symlink() or not _is_plain_directory(metadata):
        raise PersonaKcsRunnerError(f"scope .kcs is not a plain directory: {scope}")
    return metadata


def _require_handle_relative_execution():
    if HANDLE_RELATIVE_EXECUTION_AVAILABLE is not True:
        raise PersonaKcsRunnerError(
            "handle-relative persona KCS execution is unavailable"
        )


def run_scope_init(
    identity,
    person_root,
    scope_dir,
    *,
    lease,
    persona_id,
    scope_id,
    environment,
    limits=SubprocessLimits(),
):
    """Validate fresh ``kcs --json init .`` inputs; execution is gated off."""
    lease, root, person_binding = _require_person_under_lease(lease, person_root)
    if not _matches(IDENTIFIER_RE, persona_id) or not _matches(IDENTIFIER_RE, scope_id):
        raise PersonaKcsRunnerError("persona_id or scope_id is invalid")
    scope, scope_metadata = _require_plain_directory(scope_dir, "scope directory")
    scope_identity = (scope_metadata.st_dev, scope_metadata.st_ino)
    try:
        scope.relative_to(root / "home")
    except ValueError as error:
        raise PersonaKcsRunnerError("scope is outside the persona home") from error
    validate_person_subprocess_environment(environment, root)
    if _safe_kcs_directory(scope, required=False) is not None:
        raise PersonaKcsRunnerError(
            "fresh init refused because .kcs exists; classify resume instead"
        )
    _require_handle_relative_execution()
    try:
        value, execution = _run_kcs_json(
            identity, scope, ("init", "."), environment, limits
        )
        value = validate_init_result(value, scope)
        _safe_kcs_directory(scope, required=True)
        return {
            "schema": INIT_RECEIPT_SCHEMA,
            "schema_version": 1,
            "persona_id": persona_id,
            "scope_id": scope_id,
            "scope_path": str(scope),
            "command": ["init", "."],
            "binary_identity_sha256": binary_identity_sha256(identity),
            "environment_receipt_sha256": environment_receipt_sha256(environment, root),
            "execution": execution,
            "validated_result": value,
            "external_api_calls_attested": False,
            "network_observation": "unavailable",
            **_UNBOUND_CLAIMS,
        }
    finally:
        _revalidate_person_under_lease(lease, root, person_binding, "fresh init")
        _revalidate_scope(scope, scope_identity, "fresh init")


def run_scope_offline_index(
    identity,
    person_root,
    scope_dir,
    expected_counts,
    *,
    lease,
    persona_id,
    scope_id,
    environment,
    expected_status="indexed",
    limits=SubprocessLimits(),
):
    """Validate offline-index inputs and refuse unsafe pathname execution."""
    lease, root, person_binding = _require_person_under_lease(lease, person_root)
    if not _matches(IDENTIFIER_RE, persona_id) or not _matches(IDENTIFIER_RE, scope_id):
        raise PersonaKcsRunnerError("persona_id or scope_id is invalid")
    scope, scope_metadata = _require_plain_directory(scope_dir, "scope directory")
    scope_identity = (scope_metadata.st_dev, scope_metadata.st_ino)
    try:
        scope.relative_to(root / "home")
    except ValueError as error:
        raise PersonaKcsRunnerError("scope is outside the persona home") from error
    validate_person_subprocess_environment(environment, root)
    before = _safe_kcs_directory(scope, required=True)
    _require_handle_relative_execution()
    try:
        value, execution = _run_kcs_json(
            identity,
            scope,
            ("index", "--offline", "--yes"),
            environment,
            limits,
        )
        value = validate_offline_index_result(
            value, expected_counts, expected_status=expected_status
        )
        after = _safe_kcs_directory(scope, required=True)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise PersonaKcsRunnerError("scope .kcs identity changed during offline index")
        return {
            "schema": OFFLINE_INDEX_RECEIPT_SCHEMA,
            "schema_version": 1,
            "persona_id": persona_id,
            "scope_id": scope_id,
            "scope_path": str(scope),
            "command": ["index", "--offline", "--yes"],
            "binary_identity_sha256": binary_identity_sha256(identity),
            "environment_receipt_sha256": environment_receipt_sha256(environment, root),
            "expected_counts": validate_expected_offline_counts(expected_counts),
            "execution": execution,
            "validated_result": value,
            "external_api_calls_attested": False,
            "network_observation": "unavailable",
            **_UNBOUND_CLAIMS,
        }
    finally:
        _revalidate_person_under_lease(lease, root, person_binding, "offline index")
        _revalidate_scope(scope, scope_identity, "offline index")


def _relative_scope_path(value):
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise PersonaKcsRunnerError("scope relative_path is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
        or len(path.parts) < 2
        or path.parts[0] != "home"
        or len(path.parts) > 32
        or len(value.encode("utf-8")) > 1024
    ):
        raise PersonaKcsRunnerError("scope relative_path is not a safe relative path")
    return path


def _validate_unbound_index_receipt_shape(receipt, persona_id, scope_id, scope_path):
    expected_keys = {
        "schema", "schema_version", "persona_id", "scope_id", "scope_path",
        "command", "binary_identity_sha256", "environment_receipt_sha256",
        "expected_counts", "execution", "validated_result",
        "external_api_calls_attested", "network_observation",
        *_UNBOUND_CLAIMS.keys(),
    }
    if type(receipt) is not dict or set(receipt) != expected_keys:
        raise PersonaKcsRunnerError("resume index receipt has an invalid shape")
    if (
        receipt.get("schema") != OFFLINE_INDEX_RECEIPT_SCHEMA
        or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or receipt.get("persona_id") != persona_id
        or receipt.get("scope_id") != scope_id
        or receipt.get("scope_path") != str(scope_path)
        or receipt.get("command") != ["index", "--offline", "--yes"]
        or receipt.get("external_api_calls_attested") is not False
        or receipt.get("network_observation") != "unavailable"
        or receipt.get("receipt_binding_status")
        != UNBOUND_COMMAND_RECEIPTS_STATUS
        or any(
            receipt.get(key) is not False
            for key in (
                "actual_kcs_chunks_attested",
                "opaque_runtime_contents_attested",
                "history_ready_attested",
                "history_assignment_executable",
            )
        )
        or not _matches(HEX_SHA256_RE, receipt.get("binary_identity_sha256"))
        or not _matches(HEX_SHA256_RE, receipt.get("environment_receipt_sha256"))
    ):
        raise PersonaKcsRunnerError("unbound resume index receipt claims are invalid")
    execution = receipt.get("execution")
    validated_result = receipt.get("validated_result")
    if type(validated_result) is not dict:
        raise PersonaKcsRunnerError("resume index validated_result is invalid")
    if (
        type(execution) is not dict
        or set(execution) != {"returncode", "stdout_sha256", "stderr_sha256"}
        or type(execution.get("returncode")) is not int
        or execution.get("returncode") != 0
        or not _matches(HEX_SHA256_RE, execution.get("stdout_sha256"))
        or execution.get("stderr_sha256") != _sha256(b"")
    ):
        raise PersonaKcsRunnerError("resume index execution projection is invalid")
    expected = validate_expected_offline_counts(receipt.get("expected_counts"))
    validate_offline_index_result(
        validated_result,
        expected,
        expected_status=validated_result.get("status"),
    )


def classify_person_resume(
    person_root,
    *,
    persona_id,
    scopes,
    completed_index_receipts=(),
    registry_state,
):
    """Classify a person's W0 resume state without mutating any scope store.

    ``registry_state`` is an upstream read-only assessment: ``valid``,
    ``absent``, or ``invalid``.  This function only declares whether reset is
    required.  It intentionally contains no registry reset implementation and
    never removes, renames, repairs, or recreates a ``.kcs`` directory.
    """
    root, _ = _require_plain_directory(person_root, "persona root")
    if not _matches(IDENTIFIER_RE, persona_id):
        raise PersonaKcsRunnerError("persona_id is invalid")
    if registry_state not in ("valid", "absent", "invalid"):
        raise PersonaKcsRunnerError("registry_state must be valid, absent, or invalid")
    if type(scopes) not in (list, tuple) or not scopes:
        raise PersonaKcsRunnerError("person resume scopes must be a nonempty sequence")
    scope_rows = []
    seen_ids = set()
    seen_paths = set()
    for row in scopes:
        if type(row) is not dict or set(row) != {"scope_id", "relative_path"}:
            raise PersonaKcsRunnerError("person resume scope row is invalid")
        scope_id = row.get("scope_id")
        if (
            type(scope_id) is not str
            or not _matches(IDENTIFIER_RE, scope_id)
            or scope_id in seen_ids
        ):
            raise PersonaKcsRunnerError("person resume scope_id is invalid or duplicated")
        relative = _relative_scope_path(row.get("relative_path"))
        relative_text = relative.as_posix()
        if relative_text.casefold() in seen_paths:
            raise PersonaKcsRunnerError("person resume scope path is duplicated")
        seen_ids.add(scope_id)
        seen_paths.add(relative_text.casefold())
        scope_path = root.joinpath(*relative.parts)
        _require_plain_directory(scope_path, f"scope {scope_id}")
        scope_rows.append((scope_id, relative_text, scope_path))

    receipts = {}
    for receipt in completed_index_receipts:
        if type(receipt) is not dict:
            raise PersonaKcsRunnerError("person resume receipt is invalid")
        scope_id = receipt.get("scope_id")
        if scope_id in receipts:
            raise PersonaKcsRunnerError("person resume receipt is duplicated")
        receipts[scope_id] = receipt
    if not set(receipts) <= seen_ids:
        raise PersonaKcsRunnerError("person resume receipt names an unknown scope")

    states = []
    store_inodes = set()
    stores_present = 0
    for scope_id, relative, scope_path in scope_rows:
        receipt = receipts.get(scope_id)
        metadata = _safe_kcs_directory(scope_path, required=False)
        if metadata is None:
            if receipt is not None:
                raise PersonaKcsRunnerError(
                    f"completed receipt exists but .kcs is missing: {scope_id}"
                )
            state = "fresh_init_required"
        else:
            stores_present += 1
            inode = (metadata.st_dev, metadata.st_ino)
            if inode in store_inodes:
                raise PersonaKcsRunnerError("scope .kcs inode is reused")
            store_inodes.add(inode)
            if receipt is None:
                state = "semantic_attestation_required"
            else:
                _validate_unbound_index_receipt_shape(
                    receipt, persona_id, scope_id, scope_path
                )
                state = "unbound_command_receipt_present"
        states.append({
            "scope_id": scope_id,
            "relative_path": relative,
            "scope_path": str(scope_path),
            "state": state,
        })

    registry_reset_required = (
        registry_state == "invalid"
        or (registry_state == "absent" and stores_present > 0)
    )
    if registry_reset_required:
        classification = "registry_reset_required"
    elif any(row["state"] == "semantic_attestation_required" for row in states):
        classification = "semantic_attestation_required"
    elif any(row["state"] == "fresh_init_required" for row in states):
        classification = "fresh_prepare_required"
    else:
        classification = UNBOUND_COMMAND_RECEIPTS_STATUS
    return {
        "schema": RESUME_CLASSIFICATION_SCHEMA,
        "schema_version": 1,
        "persona_id": persona_id,
        "persona_root": str(root),
        "classification": classification,
        "scopes": states,
        "registry": {
            "observed_state": registry_state,
            "reset_required": registry_reset_required,
            "reset_implemented": False,
            "reset_performed": False,
        },
        "scope_store_deletions_performed": 0,
        "filesystem_mutations_performed": 0,
        **_UNBOUND_CLAIMS,
    }
