#!/usr/bin/env python3
"""Initialize/index all scale scopes, then emit an exact SQLite attestation.

This command intentionally ends each fresh scope with an explicitly offline
``kio index`` invocation.
Do not append a separate ``kio snapshot create``: index already publishes the snapshot
and projects its HEAD tree into SQLite, while a later manual snapshot would
advance HEAD before the lazy search projection occurs.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attest_scale_corpus as attestor  # noqa: E402
from eval_env import subprocess_env  # noqa: E402
import generate_scale_corpus as generator  # noqa: E402
import scale_fixture_spec as spec  # noqa: E402


class ScalePreparationError(RuntimeError):
    pass


MAX_DEVICE_TREE_ENTRIES = 4_096
MAX_DEVICE_TREE_DEPTH = 16
MAX_SUBPROCESS_OUTPUT_BYTES = 1024 * 1024
MAX_SUBPROCESS_RUNTIME_SECONDS = 60 * 60
MAX_DIAGNOSTIC_CHARS = 4_096
MAX_REGISTRY_DB_BYTES = 16 * 1024 * 1024
MAX_REGISTRY_SHM_BYTES = 1024 * 1024
MAX_REGISTRY_SCOPE_ID_BYTES = 128
MAX_REGISTRY_PATH_BYTES = 64 * 1024
WINDOWS_REPARSE_POINT_ATTRIBUTE = 0x400
_REGISTRY_SUFFIXES = ("", "-wal", "-shm", "-journal")
_OFFLINE_INDEX_ARGS = ("index", "--offline", "--yes")


def _is_reparse_point(metadata):
    return bool(
        getattr(metadata, "st_file_attributes", 0)
        & WINDOWS_REPARSE_POINT_ATTRIBUTE
    ) or bool(getattr(metadata, "st_reparse_tag", 0))


def _is_plain_directory(metadata):
    return stat.S_ISDIR(metadata.st_mode) and not _is_reparse_point(metadata)


def _is_plain_regular_file(metadata):
    return stat.S_ISREG(metadata.st_mode) and not _is_reparse_point(metadata)


def _resolve_binary(bin_path):
    path = Path(bin_path).expanduser().absolute()
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ScalePreparationError(f"kio binary is missing: {path}") from exc
    if not _is_plain_regular_file(metadata):
        raise ScalePreparationError(f"kio binary must be a regular file: {path}")
    if not os.access(path, os.X_OK):
        raise ScalePreparationError(f"kio binary is not executable: {path}")
    return path


def _validate_isolated_device_root(root):
    device = root / spec.DEVICE_DIR_NAME
    try:
        metadata = device.lstat()
    except FileNotFoundError:
        return
    if not _is_plain_directory(metadata):
        raise ScalePreparationError(f"isolated device root is unsafe: {device}")

    # The isolated device root is fixture-owned, but still treat it as hostile
    # input: walk without following links and stop at explicit count/depth bounds.
    pending = [(device, 0)]
    seen = 0
    while pending:
        directory, depth = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    seen += 1
                    if seen > MAX_DEVICE_TREE_ENTRIES:
                        raise ScalePreparationError(
                            "isolated device tree exceeds "
                            f"{MAX_DEVICE_TREE_ENTRIES} entries: {device}"
                        )
                    try:
                        child_metadata = entry.stat(follow_symlinks=False)
                    except OSError as exc:
                        raise ScalePreparationError(
                            f"cannot inspect isolated device entry: {entry.path}: {exc}"
                        ) from exc
                    child = Path(entry.path)
                    if _is_plain_directory(child_metadata):
                        if depth >= MAX_DEVICE_TREE_DEPTH:
                            raise ScalePreparationError(
                                "isolated device tree exceeds depth "
                                f"{MAX_DEVICE_TREE_DEPTH}: {child}"
                            )
                        pending.append((child, depth + 1))
                    elif not _is_plain_regular_file(child_metadata):
                        raise ScalePreparationError(
                            "isolated device tree entries must be plain files or "
                            f"directories: {child}"
                        )
        except ScalePreparationError:
            raise
        except OSError as exc:
            raise ScalePreparationError(
                f"cannot enumerate isolated device directory: {directory}: {exc}"
            ) from exc


def _capture_file_bytes(handle):
    size = os.fstat(handle.fileno()).st_size
    handle.seek(0)
    data = handle.read(MAX_SUBPROCESS_OUTPUT_BYTES + 1)
    if size > MAX_SUBPROCESS_OUTPUT_BYTES or len(data) > MAX_SUBPROCESS_OUTPUT_BYTES:
        raise ScalePreparationError(
            "kio subprocess output exceeded "
            f"{MAX_SUBPROCESS_OUTPUT_BYTES} bytes per stream"
        )
    return data


def _terminate_process_group(proc):
    if os.name != "nt":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            if proc.poll() is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
    elif proc.poll() is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def _run_process_bounded(command, cwd, env):
    popen_options = {}
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True

    with (
        tempfile.TemporaryFile(mode="w+b") as stdout_file,
        tempfile.TemporaryFile(mode="w+b") as stderr_file,
    ):
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=stdout_file,
            stderr=stderr_file,
            env=env,
            **popen_options,
        )
        deadline = time.monotonic() + MAX_SUBPROCESS_RUNTIME_SECONDS
        returncode = None
        timed_out = False
        overflow = False
        try:
            while returncode is None:
                if any(
                    os.fstat(handle.fileno()).st_size
                    > MAX_SUBPROCESS_OUTPUT_BYTES
                    for handle in (stdout_file, stderr_file)
                ):
                    overflow = True
                    _terminate_process_group(proc)
                    returncode = proc.wait()
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    _terminate_process_group(proc)
                    returncode = proc.wait()
                    break
                returncode = proc.poll()
                if returncode is None:
                    time.sleep(min(0.02, remaining))
        finally:
            if proc.poll() is None:
                _terminate_process_group(proc)
                proc.wait()
            # Kill any descendant that inherited output from the isolated POSIX
            # session. Regular-file capture means a surviving Windows handle cannot
            # hold this process in a pipe-reader join.
            _terminate_process_group(proc)

        stdout = _capture_file_bytes(stdout_file)
        stderr = _capture_file_bytes(stderr_file)
        if overflow:
            raise ScalePreparationError(
                "kio subprocess output exceeded "
                f"{MAX_SUBPROCESS_OUTPUT_BYTES} bytes per stream"
            )
        if timed_out:
            raise ScalePreparationError(
                f"kio subprocess exceeded {MAX_SUBPROCESS_RUNTIME_SECONDS} seconds"
            )
        return returncode, stdout, stderr


def _diagnostic(data):
    value = data.decode("utf-8", errors="replace")
    if len(value) > MAX_DIAGNOSTIC_CHARS:
        return value[:MAX_DIAGNOSTIC_CHARS] + "...[truncated]"
    return value


def _run_kio(bin_path, scope_dir, args, env):
    command = [str(bin_path), "--json", *args]
    returncode, stdout_raw, stderr_raw = _run_process_bounded(
        command, scope_dir, env
    )
    if returncode != 0:
        raise ScalePreparationError(
            f"kio {' '.join(args)} failed in {scope_dir} "
            f"(exit {returncode})\nstdout={_diagnostic(stdout_raw)}"
            f"\nstderr={_diagnostic(stderr_raw)}"
        )
    try:
        stdout = stdout_raw.decode("utf-8")
        value = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScalePreparationError(
            f"kio {' '.join(args)} returned invalid JSON in {scope_dir}: "
            f"{_diagnostic(stdout_raw)!r}"
        ) from exc
    if not isinstance(value, dict):
        raise ScalePreparationError(
            f"kio {' '.join(args)} returned non-object JSON in {scope_dir}"
        )
    return value


def _validate_index_result(value, scope_manifest):
    expected = scope_manifest["expected_files"]
    status = value.get("status")
    if status not in ("indexed", "noop"):
        raise ScalePreparationError(
            f"unexpected index status for {scope_manifest['name']}: {status!r}"
        )
    exact_zero_fields = (
        "failed_files",
        "pending_files",
        "skipped_oversized_files",
        "skipped_unrecognized_binary_files",
    )
    for field in exact_zero_fields:
        if value.get(field) != 0:
            raise ScalePreparationError(
                f"index reported {field}={value.get(field)!r} "
                f"for {scope_manifest['name']}"
            )
    if value.get("normalized_files") != expected:
        raise ScalePreparationError(
            f"index normalized_files mismatch for {scope_manifest['name']}: "
            f"expected {expected}, got {value.get('normalized_files')!r}"
        )
    commit_hash = value.get("commit_hash")
    if status == "indexed":
        if not isinstance(commit_hash, str) or not attestor.HASH_RE.fullmatch(commit_hash):
            raise ScalePreparationError(
                f"index omitted a valid commit_hash for {scope_manifest['name']}"
            )
    elif commit_hash is not None:
        raise ScalePreparationError(
            f"noop index unexpectedly returned commit_hash for {scope_manifest['name']}"
        )
    return status


def _validate_reregistration_result(value, scope_manifest):
    """Validate index output only after this scope attested before the call."""
    expected = scope_manifest["expected_files"]
    if value.get("status") != "noop":
        raise ScalePreparationError(
            "registry recovery unexpectedly changed an already-attested scope "
            f"({scope_manifest['name']}): {value.get('status')!r}"
        )
    exact_zero_fields = (
        "failed_files",
        "pending_files",
        "skipped_oversized_files",
        "skipped_unrecognized_binary_files",
    )
    for field in exact_zero_fields:
        if value.get(field) != 0:
            raise ScalePreparationError(
                f"registry recovery reported {field}={value.get(field)!r} "
                f"for {scope_manifest['name']}"
            )
    if value.get("normalized_files") != expected:
        raise ScalePreparationError(
            f"registry recovery normalized_files mismatch for "
            f"{scope_manifest['name']}: expected {expected}, "
            f"got {value.get('normalized_files')!r}"
        )
    if value.get("commit_hash") is not None:
        raise ScalePreparationError(
            f"registry recovery advanced commit for {scope_manifest['name']}"
        )


def _registry_path(root):
    return root / spec.DEVICE_DIR_NAME / "data" / "kio" / "scope-registry.sqlite"


def _registry_files_are_bounded(root):
    registry = _registry_path(root)
    for suffix in _REGISTRY_SUFFIXES:
        path = Path(str(registry) + suffix)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        maximum = MAX_REGISTRY_SHM_BYTES if suffix == "-shm" else MAX_REGISTRY_DB_BYTES
        if not _is_plain_regular_file(metadata) or metadata.st_size > maximum:
            return False
    return True


def _registry_matches_attested_scopes(root, scope_reports):
    if len(scope_reports) > len(spec.SCOPES):
        return False
    if not _registry_files_are_bounded(root):
        return False
    path = _registry_path(root)
    try:
        conn = attestor._open_read_only(path)
        try:
            conn.execute("BEGIN")
            table = conn.execute(
                "SELECT 1 FROM sqlite_schema "
                "WHERE type = 'table' AND name = 'scopes' LIMIT 1"
            ).fetchone()
            if table is None:
                return False
            shapes = conn.execute(
                "SELECT typeof(scope_id), length(CAST(scope_id AS BLOB)), "
                "typeof(kio_path), length(CAST(kio_path AS BLOB)), "
                "typeof(root_path), length(CAST(root_path AS BLOB)), "
                "CASE WHEN typeof(participates_in_global_search) = 'integer' "
                "AND participates_in_global_search = 1 THEN 1 ELSE 0 END, "
                "CASE WHEN typeof(indexed) = 'integer' "
                "AND indexed = 1 THEN 1 ELSE 0 END "
                "FROM scopes LIMIT ?1",
                (len(spec.SCOPES) + 1,),
            ).fetchall()
            if len(shapes) != len(scope_reports) or any(
                scope_type != "text"
                or scope_length is None
                or scope_length > MAX_REGISTRY_SCOPE_ID_BYTES
                or kio_type != "text"
                or kio_length is None
                or kio_length > MAX_REGISTRY_PATH_BYTES
                or root_type != "text"
                or root_length is None
                or root_length > MAX_REGISTRY_PATH_BYTES
                or participates_ok != 1
                or indexed_ok != 1
                for (
                    scope_type,
                    scope_length,
                    kio_type,
                    kio_length,
                    root_type,
                    root_length,
                    participates_ok,
                    indexed_ok,
                ) in shapes
            ):
                return False
            rows = conn.execute(
                "SELECT scope_id, kio_path, root_path "
                "FROM scopes LIMIT ?1",
                (len(spec.SCOPES) + 1,),
            ).fetchall()
        finally:
            conn.close()
    except (attestor.ScaleAttestationError, sqlite3.Error, OSError):
        return False
    if len(rows) != len(scope_reports):
        return False
    try:
        expected = {
            report["scope_id"]: (
                attestor._canonical(Path(report["root_path"]) / ".kio"),
                attestor._canonical(report["root_path"]),
            )
            for report in scope_reports
        }
        actual = {
            scope_id: (attestor._canonical(kio_path), attestor._canonical(root_path))
            for scope_id, kio_path, root_path in rows
        }
    except (attestor.ScaleAttestationError, TypeError, ValueError):
        return False
    return (
        len(expected) == len(scope_reports)
        and len(actual) == len(rows)
        and actual == expected
    )


def _reset_isolated_registry(root):
    """Remove only the owned registry and SQLite sidecars after full preflight."""
    registry = _registry_path(root)
    parent = registry.parent
    try:
        parent_metadata = parent.lstat()
    except FileNotFoundError:
        return
    if not _is_plain_directory(parent_metadata):
        raise ScalePreparationError(f"scope registry parent is unsafe: {parent}")

    targets = []
    for suffix in _REGISTRY_SUFFIXES:
        path = Path(str(registry) + suffix)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if not _is_plain_regular_file(metadata):
            raise ScalePreparationError(f"scope registry reset path is unsafe: {path}")
        targets.append(path)
    for path in targets:
        path.unlink()


def _existing_scope_attestations(root, manifest):
    reports = {}
    for scope_manifest in manifest["scopes"]:
        scope_dir = root / scope_manifest["name"]
        try:
            scope_metadata = scope_dir.lstat()
        except FileNotFoundError as exc:
            raise ScalePreparationError(
                f"scale scope directory is missing: {scope_dir}"
            ) from exc
        if not _is_plain_directory(scope_metadata):
            raise ScalePreparationError(f"scope directory is unsafe: {scope_dir}")
        kio_dir = scope_dir / ".kio"
        try:
            metadata = kio_dir.lstat()
        except FileNotFoundError:
            continue
        if not _is_plain_directory(metadata):
            raise ScalePreparationError(f"scope .kio path is unsafe: {kio_dir}")
        try:
            reports[scope_manifest["name"]] = attestor.attest_scope(
                root, scope_manifest
            )
        except attestor.ScaleAttestationError:
            # An existing but incomplete scope gets one ordinary index recovery
            # attempt below; it is never eligible for the no-op shortcut.
            pass
    return reports


def _prepare_corpus_locked(corpus_dir, bin_path):
    try:
        root, _, manifest = generator.load_owned_manifest(corpus_dir)
    except generator.ScaleGenerationError as exc:
        raise ScalePreparationError(str(exc)) from exc
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise ScalePreparationError(f"cannot inspect scale corpus root: {root}") from exc
    if not _is_plain_directory(root_metadata):
        raise ScalePreparationError(f"scale corpus root is unsafe: {root}")
    for scope_manifest in manifest["scopes"]:
        scope_dir = root / scope_manifest["name"]
        try:
            scope_metadata = scope_dir.lstat()
        except FileNotFoundError as exc:
            raise ScalePreparationError(
                f"scale scope directory is missing: {scope_dir}"
            ) from exc
        if not _is_plain_directory(scope_metadata):
            raise ScalePreparationError(f"scope directory is unsafe: {scope_dir}")
    try:
        attestor.verify_source_files(root, manifest, allow_kio=True)
    except attestor.ScaleAttestationError as exc:
        raise ScalePreparationError(str(exc)) from exc
    binary = _resolve_binary(bin_path)
    _validate_isolated_device_root(root)
    env = subprocess_env(root)
    generated = []
    skipped = []
    reregistered = []
    resumed_noop = []
    scope_reports = []
    existing_reports = _existing_scope_attestations(root, manifest)
    registry_current = _registry_matches_attested_scopes(
        root, list(existing_reports.values())
    )
    if not registry_current:
        # This is an isolated, fixture-owned cache. Rebuilding only its exact DB
        # files is safer than asking index to write through a corrupt SQLite file.
        _reset_isolated_registry(root)

    for scope_manifest in manifest["scopes"]:
        scope_dir = root / scope_manifest["name"]
        try:
            scope_metadata = scope_dir.lstat()
        except FileNotFoundError as exc:
            raise ScalePreparationError(
                f"scale scope directory is missing: {scope_dir}"
            ) from exc
        if not _is_plain_directory(scope_metadata):
            raise ScalePreparationError(f"scope directory is unsafe: {scope_dir}")
        kio_dir = scope_dir / ".kio"
        scope_report = existing_reports.get(scope_manifest["name"])
        if scope_report is not None:
            if registry_current:
                skipped.append(scope_manifest["name"])
                scope_reports.append(scope_report)
                continue
            indexed = _run_kio(binary, scope_dir, _OFFLINE_INDEX_ARGS, env)
            _validate_reregistration_result(indexed, scope_manifest)
            try:
                refreshed_report = attestor.attest_scope(root, scope_manifest)
            except attestor.ScaleAttestationError as exc:
                raise ScalePreparationError(
                    "post-registration attestation failed for "
                    f"{scope_manifest['name']}: {exc}"
                ) from exc
            if refreshed_report["head"] != scope_report["head"]:
                raise ScalePreparationError(
                    "registry-only recovery advanced HEAD for "
                    f"{scope_manifest['name']}"
                )
            scope_report = refreshed_report
            generated.append(scope_manifest["name"])
            reregistered.append(scope_manifest["name"])
            scope_reports.append(scope_report)
            continue

        try:
            kio_metadata = kio_dir.lstat()
        except FileNotFoundError:
            kio_metadata = None
        if kio_metadata is not None and not _is_plain_directory(kio_metadata):
            raise ScalePreparationError(f"scope .kio path is unsafe: {kio_dir}")
        if kio_metadata is None:
            initialized = _run_kio(binary, scope_dir, ["init", "."], env)
            if initialized.get("status") != "initialized":
                raise ScalePreparationError(
                    f"unexpected init result for {scope_manifest['name']}: {initialized}"
                )
        else:
            # An existing but non-attesting scope is intentionally not skipped;
            # index gets one normal repair attempt and must satisfy strict output.
            pass

        indexed = _run_kio(binary, scope_dir, _OFFLINE_INDEX_ARGS, env)
        index_status = _validate_index_result(indexed, scope_manifest)
        try:
            scope_report = attestor.attest_scope(root, scope_manifest)
        except attestor.ScaleAttestationError as exc:
            raise ScalePreparationError(
                f"post-index attestation failed for {scope_manifest['name']}: {exc}"
            ) from exc
        if index_status == "indexed":
            generated.append(scope_manifest["name"])
        else:
            resumed_noop.append(scope_manifest["name"])
        scope_reports.append(scope_report)

    # Re-run collection-level checks, including exact isolated registry binding.
    try:
        attestation = attestor.attest_corpus(root)
    except attestor.ScaleAttestationError as exc:
        raise ScalePreparationError(str(exc)) from exc
    return {
        "schema_version": spec.SCHEMA_VERSION,
        "passed": True,
        "fixture_id": spec.FIXTURE_ID,
        "query_workload_id": spec.QUERY_WORKLOAD_ID,
        "profile": manifest["profile"],
        "binary": str(binary),
        "indexed_scopes": generated,
        "reregistered_scopes": reregistered,
        "resumed_noop_scopes": resumed_noop,
        "already_attested_scopes": skipped,
        "totals": attestation["totals"],
        "attestation": str(root / spec.ATTESTATION_NAME),
    }, attestation


def prepare_corpus(corpus_dir, bin_path):
    try:
        with generator.fixture_lock(corpus_dir):
            return _prepare_corpus_locked(corpus_dir, bin_path)
    except generator.ScaleGenerationError as exc:
        raise ScalePreparationError(str(exc)) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Initialize, index, and attest every Kio scale scope"
    )
    parser.add_argument("--corpus", required=True, help="scale collection root")
    parser.add_argument("--bin", required=True, help="path to kio executable")
    args = parser.parse_args(argv)
    try:
        # Keep initialization, registry recovery, exact attestation, and both
        # atomic report publications in one non-reentrant fixture lock lifetime.
        with generator.fixture_lock(args.corpus):
            report, attestation = _prepare_corpus_locked(args.corpus, args.bin)
            root = Path(args.corpus).expanduser().absolute()
            attestor._write_json_atomic(root / spec.ATTESTATION_NAME, attestation)
            attestor._write_json_atomic(root / spec.PREPARE_REPORT_NAME, report)
    except (OSError, generator.ScaleGenerationError, ScalePreparationError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    totals = report["totals"]
    print(
        "[ok] scale corpus prepared: "
        f"profile={report['profile']} "
        f"indexed_scopes={len(report['indexed_scopes'])} "
        f"resumed_noop_scopes={len(report['resumed_noop_scopes'])} "
        f"already_attested_scopes={len(report['already_attested_scopes'])} "
        f"current_chunks={totals['current_eligible_chunks']}"
    )
    print(f"     report: {root / spec.PREPARE_REPORT_NAME}")
    print(f"     attestation: {root / spec.ATTESTATION_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
