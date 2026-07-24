#!/usr/bin/env python3
"""Manual 20-scope / 100k-plus high-selectivity search baseline measurement.

This runner deliberately does not replace the frozen Recall evaluation.  It
measures the release CLI's default ``auto`` search against the independently
attested embedding-free ``full`` scale fixture, where it must resolve to text.
It is not a formal hybrid/MVP gate.  M3-2 and M3-3 selectors are exercised, but
the fixture contains no edit/rename/delete history; those two measurements are
execution-path observations, never formal history-latency results.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attest_scale_corpus as attestor  # noqa: E402
from eval_env import subprocess_env  # noqa: E402
import generate_scale_corpus as generator  # noqa: E402
import scale_fixture_spec as spec  # noqa: E402


MIN_SAMPLES_PER_SCENARIO = 100
DEFAULT_SAMPLES_PER_SCENARIO = 100
DEFAULT_WARMUPS_PER_SCENARIO = 5
DEFAULT_TIMEOUT_SECONDS = 30.0
EXPECTED_SCOPE_COUNT = 20
MINIMUM_SCALE_CHUNKS = 100_001
RESULT_LIMIT = 10
MAX_STDOUT_BYTES = 2 * 1024 * 1024
MAX_STDERR_BYTES = 128 * 1024
MAX_ATTESTATION_BYTES = 16 * 1024 * 1024
MAX_BINARY_BYTES = 512 * 1024 * 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_METRICS_LOG_BYTES = 64 * 1024 * 1024
MAX_METRICS_DELTA_BYTES = 64 * 1024
MAX_METRIC_LINE_BYTES = 32 * 1024
REPORT_SUFFIX = ".latency.json"

SCENARIOS = (
    {
        "name": "M3-1",
        "flag": None,
        "target_p95_ms": 5_000.0,
        "measurement_class": "default-auto-high-selectivity-current-text-baseline",
        "formal_history_latency": None,
    },
    {
        "name": "M3-2",
        "flag": "--all-history",
        "target_p95_ms": 7_000.0,
        "measurement_class": "execution-path-only",
        "formal_history_latency": False,
    },
    {
        "name": "M3-3",
        "flag": "--include-deleted",
        "target_p95_ms": 7_000.0,
        "measurement_class": "execution-path-only",
        "formal_history_latency": False,
    },
)


class ScaleLatencyError(RuntimeError):
    pass


def _is_plain_regular_file(metadata):
    """Reject Windows reparse-backed files as well as non-regular files."""
    return generator._is_plain_regular_file(metadata)


def percentile_nearest_rank(values, percentile):
    """Return the nearest-rank percentile used by the Recall evaluator."""
    if not values:
        return None
    if not 0 < percentile <= 1:
        raise ValueError("percentile must be in (0, 1]")
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _statistics(values):
    if not values:
        raise ScaleLatencyError("latency sample set is empty")
    return {
        "p50": round(percentile_nearest_rank(values, 0.50), 3),
        "p95": round(percentile_nearest_rank(values, 0.95), 3),
        "p99": round(percentile_nearest_rank(values, 0.99), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def validate_measurement_counts(samples_per_scenario, warmups_per_scenario):
    if samples_per_scenario < MIN_SAMPLES_PER_SCENARIO:
        raise ScaleLatencyError(
            "samples-per-scenario must be at least "
            f"{MIN_SAMPLES_PER_SCENARIO} so nearest-rank p99 is meaningful"
        )
    if warmups_per_scenario < 1:
        raise ScaleLatencyError("warmups-per-scenario must be at least 1")


def _bounded_regular_bytes(path, maximum, label):
    path = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ScaleLatencyError(f"cannot open {label}: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not _is_plain_regular_file(before):
            raise ScaleLatencyError(f"{label} must be a regular file: {path}")
        if before.st_size > maximum:
            raise ScaleLatencyError(
                f"{label} exceeds {maximum} bytes: {path} ({before.st_size})"
            )
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise ScaleLatencyError(f"{label} grew beyond {maximum} bytes: {path}")
        after = os.fstat(descriptor)
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise ScaleLatencyError(f"{label} changed while being read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _hash_regular_file(path, maximum, label):
    path = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ScaleLatencyError(f"cannot open {label}: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not _is_plain_regular_file(before):
            raise ScaleLatencyError(f"{label} must be a regular file: {path}")
        if before.st_size > maximum:
            raise ScaleLatencyError(
                f"{label} exceeds {maximum} bytes: {path} ({before.st_size})"
            )
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise ScaleLatencyError(f"{label} grew beyond {maximum} bytes: {path}")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise ScaleLatencyError(f"{label} changed while being hashed: {path}")
        return {"sha256": digest.hexdigest(), "bytes": total}
    finally:
        os.close(descriptor)


def resolve_release_binary(bin_path):
    path = Path(bin_path).expanduser().absolute()
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ScaleLatencyError(f"release kio binary is missing: {path}") from exc
    if not _is_plain_regular_file(metadata):
        raise ScaleLatencyError(f"release kio binary must be a regular file: {path}")
    if path.parent.name != "release" or path.name not in ("kio", "kio.exe"):
        raise ScaleLatencyError(
            "--bin must identify the release artifact target/release/kio "
            f"(or kio.exe), got: {path}"
        )
    if not os.access(path, os.X_OK):
        raise ScaleLatencyError(f"release kio binary is not executable: {path}")
    digest = _hash_regular_file(path, MAX_BINARY_BYTES, "release kio binary")
    return {"path": str(path), **digest}


def validate_full_fixture(manifest, attestation):
    if manifest.get("profile") != "full" or attestation.get("profile") != "full":
        raise ScaleLatencyError("scale latency measurement requires profile=full")
    if (
        manifest.get("query_workload_id") != spec.QUERY_WORKLOAD_ID
        or attestation.get("query_workload_id") != spec.QUERY_WORKLOAD_ID
    ):
        raise ScaleLatencyError("scale query workload identity mismatch")
    shape = manifest.get("shape")
    totals = attestation.get("totals")
    scopes = attestation.get("scopes")
    if not isinstance(shape, dict) or not isinstance(totals, dict):
        raise ScaleLatencyError("scale manifest/attestation lacks shape totals")
    if shape.get("scope_count") != EXPECTED_SCOPE_COUNT:
        raise ScaleLatencyError("scale manifest must declare exactly 20 scopes")
    if not isinstance(scopes, list) or len(scopes) != EXPECTED_SCOPE_COUNT:
        raise ScaleLatencyError("scale attestation must contain exactly 20 scopes")
    current = totals.get("current_eligible_chunks")
    if not isinstance(current, int) or current < MINIMUM_SCALE_CHUNKS:
        raise ScaleLatencyError(
            f"scale fixture must contain more than 100,000 current chunks, got {current!r}"
        )
    if current != shape.get("expected_current_chunks"):
        raise ScaleLatencyError("attested current chunks differ from manifest shape")
    physical = totals.get("physical_chunks")
    if physical != current:
        raise ScaleLatencyError(
            "current-text fixture contains historical/ineligible chunks; regenerate a fresh full fixture"
        )
    historical = [scope.get("historical_or_ineligible_chunks") for scope in scopes]
    if any(value != 0 for value in historical):
        raise ScaleLatencyError(
            "current-text fixture contains per-scope historical/ineligible chunks"
        )
    scope_ids = [scope.get("scope_id") for scope in scopes]
    if any(not isinstance(value, str) or not value for value in scope_ids):
        raise ScaleLatencyError("scale attestation has an invalid scope_id")
    if len(set(scope_ids)) != EXPECTED_SCOPE_COUNT:
        raise ScaleLatencyError("scale attestation scope_ids are not unique")
    return set(scope_ids)


def build_query_mix(manifest, attestation):
    """Bind each manifest needle to its attested immutable scope identity."""
    by_name = {scope["name"]: scope["scope_id"] for scope in attestation["scopes"]}
    needles = manifest.get("needles")
    if not isinstance(needles, list) or len(needles) != EXPECTED_SCOPE_COUNT:
        raise ScaleLatencyError("scale manifest must contain one needle per scope")
    cases = []
    for index, needle in enumerate(needles):
        if not isinstance(needle, dict):
            raise ScaleLatencyError(f"scale needle {index} is not an object")
        scope = needle.get("scope")
        query = needle.get("query")
        file_name = needle.get("file")
        if scope not in by_name:
            raise ScaleLatencyError(f"scale needle references unknown scope: {scope!r}")
        if not isinstance(query, str) or not query:
            raise ScaleLatencyError(f"scale needle has an invalid query: {index}")
        if not isinstance(file_name, str) or not file_name:
            raise ScaleLatencyError(f"scale needle has an invalid file: {index}")
        cases.append(
            {
                "index": index,
                "query": query,
                "scope": scope,
                "scope_id": by_name[scope],
                "file": file_name,
                "heading": needle.get("heading"),
            }
        )
    return cases


def build_search_command(binary_path, case, scenario):
    """Use both the default scope selector and the default ``auto`` mode."""
    command = [
        binary_path,
        "--json",
        "search",
        case["query"],
        "--limit",
        str(RESULT_LIMIT),
    ]
    if scenario["flag"] is not None:
        command.append(scenario["flag"])
    return command


def _metrics_open_flags():
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def snapshot_metrics_log(path):
    """Hold the pre-search live log inode and its exact append offset."""
    path = Path(path)
    try:
        descriptor = os.open(path, _metrics_open_flags())
    except FileNotFoundError:
        return {"path": path, "descriptor": None, "stat": None, "size": 0}
    except OSError as exc:
        raise ScaleLatencyError(f"cannot open metrics log: {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not _is_plain_regular_file(metadata):
            raise ScaleLatencyError(f"metrics log must be a regular file: {path}")
        if metadata.st_size > MAX_METRICS_LOG_BYTES:
            raise ScaleLatencyError(
                f"metrics log exceeds {MAX_METRICS_LOG_BYTES} bytes: {path}"
            )
        if metadata.st_size:
            os.lseek(descriptor, metadata.st_size - 1, os.SEEK_SET)
            if os.read(descriptor, 1) != b"\n":
                raise ScaleLatencyError("existing metrics log lacks a final newline")
        return {
            "path": path,
            "descriptor": descriptor,
            "stat": metadata,
            "size": metadata.st_size,
        }
    except Exception:
        os.close(descriptor)
        raise


def close_metrics_snapshot(snapshot):
    descriptor = snapshot.get("descriptor")
    if descriptor is not None:
        os.close(descriptor)
        snapshot["descriptor"] = None


def _read_exact_descriptor(descriptor, offset, size, label):
    os.lseek(descriptor, offset, os.SEEK_SET)
    chunks = []
    remaining = size
    while remaining:
        chunk = os.read(descriptor, min(64 * 1024, remaining))
        if not chunk:
            raise ScaleLatencyError(f"{label} was truncated while reading")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_one_appended_metric(snapshot):
    """Read exactly one append, accepting daily rotation but failing closed."""
    path = snapshot["path"]
    old_descriptor = snapshot.get("descriptor")
    current_descriptor = None
    selected_descriptor = None
    rotated = False
    try:
        try:
            current_descriptor = os.open(path, _metrics_open_flags())
        except OSError as exc:
            raise ScaleLatencyError(f"metrics log was not published: {path}") from exc
        current_stat = os.fstat(current_descriptor)
        if not _is_plain_regular_file(current_stat):
            raise ScaleLatencyError(f"metrics log must remain a regular file: {path}")
        if current_stat.st_size > MAX_METRICS_LOG_BYTES:
            raise ScaleLatencyError(
                f"metrics log exceeds {MAX_METRICS_LOG_BYTES} bytes: {path}"
            )

        old_stat = snapshot.get("stat")
        same_file = (
            old_descriptor is not None
            and old_stat is not None
            and os.path.samestat(old_stat, current_stat)
        )
        if same_file:
            selected_descriptor = old_descriptor
            os.close(current_descriptor)
            current_descriptor = None
            start = snapshot["size"]
            final_stat = os.fstat(selected_descriptor)
            if final_stat.st_size < start:
                raise ScaleLatencyError("metrics log shrank during a search")
        else:
            # append_jsonl_rotating may atomically rename the prior live file and
            # publish a fresh metrics.jsonl before appending this search's line.
            selected_descriptor = current_descriptor
            current_descriptor = None
            start = 0
            final_stat = os.fstat(selected_descriptor)
            rotated = old_descriptor is not None

        delta = final_stat.st_size - start
        if delta <= 0:
            raise ScaleLatencyError("search did not append a metrics line")
        if delta > MAX_METRICS_DELTA_BYTES:
            raise ScaleLatencyError(
                f"metrics append exceeds {MAX_METRICS_DELTA_BYTES} bytes ({delta})"
            )
        if delta > MAX_METRIC_LINE_BYTES:
            raise ScaleLatencyError(
                f"search metric line exceeds {MAX_METRIC_LINE_BYTES} bytes ({delta})"
            )
        raw = _read_exact_descriptor(
            selected_descriptor, start, delta, "metrics append"
        )
        after_read = os.fstat(selected_descriptor)
        if (
            after_read.st_size != final_stat.st_size
            or after_read.st_mtime_ns != final_stat.st_mtime_ns
        ):
            raise ScaleLatencyError("metrics log changed while reading its append")
        try:
            path_stat = path.lstat()
        except FileNotFoundError as exc:
            raise ScaleLatencyError("metrics log disappeared after search") from exc
        if not _is_plain_regular_file(path_stat):
            raise ScaleLatencyError(f"metrics log must remain a plain regular file: {path}")
        if not os.path.samestat(after_read, path_stat):
            raise ScaleLatencyError("metrics log was replaced while reading its append")
        if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
            raise ScaleLatencyError(
                "search must append exactly one newline-terminated metrics line"
            )
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ScaleLatencyError("appended search metric is invalid JSON") from exc
        if not isinstance(value, dict):
            raise ScaleLatencyError("appended search metric must be an object")
        return value, {"delta_bytes": delta, "rotated": rotated}
    finally:
        if selected_descriptor is not None and selected_descriptor != old_descriptor:
            os.close(selected_descriptor)
        if current_descriptor is not None:
            os.close(current_descriptor)
        close_metrics_snapshot(snapshot)


def validate_search_metric(metric, response):
    required = {
        "ts",
        "level",
        "code",
        "component",
        "message",
        "metric",
        "value",
        "context",
    }
    if set(metric) != required:
        raise ScaleLatencyError("search metric field set is invalid or leaks query/path")
    if (
        not isinstance(metric["ts"], str)
        or not metric["ts"]
        or metric["level"] != "info"
        or metric["code"] != "KIO-M-SEARCH-001"
        or metric["component"] != "search"
        or metric["message"] != "search completed"
        or metric["metric"] != "search.latency_ms"
    ):
        raise ScaleLatencyError("search metric envelope is invalid")
    context = metric["context"]
    if not isinstance(context, dict) or set(context) != {
        "mode",
        "scope_count",
        "result_count",
    }:
        raise ScaleLatencyError("search metric context is invalid or leaks query/path")
    results = response.get("results")
    if (
        context.get("mode") != "text"
        or context.get("scope_count") != EXPECTED_SCOPE_COUNT
        or not isinstance(results, list)
        or context.get("result_count") != len(results)
    ):
        raise ScaleLatencyError("search metric context disagrees with the response")
    latency = metric["value"]
    if (
        isinstance(latency, bool)
        or not isinstance(latency, (int, float))
        or not math.isfinite(float(latency))
        or float(latency) < 0
    ):
        raise ScaleLatencyError("search metric latency value is invalid")
    return float(latency)


def _kill_process(process):
    if process.poll() is None:
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            pass


def _capture_pipe_bounded(
    stream,
    maximum,
    key,
    process,
    captured,
    overflow,
    overflow_streams,
    capture_errors,
    state_lock,
):
    """Drain one pipe while retaining at most ``maximum`` bytes in memory."""
    chunks = []
    retained = 0
    try:
        while True:
            # One raw pipe read returns currently available bytes; BufferedReader
            # ``read(n)`` may wait for all n bytes and delay overflow detection.
            chunk = os.read(stream.fileno(), 64 * 1024)
            if not chunk:
                break
            remaining = maximum - retained
            if remaining > 0:
                kept = chunk[:remaining]
                chunks.append(kept)
                retained += len(kept)
            if len(chunk) > remaining:
                with state_lock:
                    overflow_streams.add(key)
                overflow.set()
                # Do not wait for the coordinator's polling interval: output
                # overflow is a hard resource-bound violation, so terminate the
                # child from the detecting reader immediately, then keep draining
                # until the killed process closes its pipe.
                _kill_process(process)
    except Exception as exc:  # pragma: no cover - OS pipe failures are rare
        with state_lock:
            capture_errors.append(exc)
        _kill_process(process)
    finally:
        stream.close()
        with state_lock:
            captured[key] = b"".join(chunks)


def run_bounded_process(command, cwd, env, timeout_seconds):
    """Capture bounded pipes, kill on overflow, and leave no reader behind."""
    started = time.perf_counter_ns()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ScaleLatencyError(f"cannot execute release kio binary: {command[0]}") from exc
    assert process.stdout is not None
    assert process.stderr is not None

    captured = {}
    overflow = threading.Event()
    overflow_streams = set()
    capture_errors = []
    state_lock = threading.Lock()
    readers = [
        threading.Thread(
            name="kio-scale-stdout-reader",
            target=_capture_pipe_bounded,
            args=(
                process.stdout,
                MAX_STDOUT_BYTES,
                "stdout",
                process,
                captured,
                overflow,
                overflow_streams,
                capture_errors,
                state_lock,
            ),
            daemon=False,
        ),
        threading.Thread(
            name="kio-scale-stderr-reader",
            target=_capture_pipe_bounded,
            args=(
                process.stderr,
                MAX_STDERR_BYTES,
                "stderr",
                process,
                captured,
                overflow,
                overflow_streams,
                capture_errors,
                state_lock,
            ),
            daemon=False,
        ),
    ]
    deadline = time.monotonic() + timeout_seconds
    returncode = None
    timed_out = False
    started_readers = []
    try:
        for reader in readers:
            reader.start()
            started_readers.append(reader)
        while returncode is None:
            if overflow.is_set() or capture_errors:
                _kill_process(process)
                returncode = process.wait()
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _kill_process(process)
                returncode = process.wait()
                break
            try:
                returncode = process.wait(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                pass
    finally:
        _kill_process(process)
        if process.poll() is None:
            process.wait()
        # Readers are deliberately non-daemon and always joined.  This holds on
        # success, timeout, overflow, capture failure, and partial thread startup.
        for reader in started_readers:
            reader.join()
        if len(started_readers) < len(readers):
            if not process.stdout.closed:
                process.stdout.close()
            if not process.stderr.closed:
                process.stderr.close()

    duration_ms = (time.perf_counter_ns() - started) / 1_000_000.0
    if capture_errors:
        raise ScaleLatencyError(
            f"failed to capture kio subprocess output: {capture_errors[0]}"
        )
    if overflow.is_set():
        with state_lock:
            streams = sorted(overflow_streams)
        limits = {
            "stdout": MAX_STDOUT_BYTES,
            "stderr": MAX_STDERR_BYTES,
        }
        detail = ", ".join(f"{stream} exceeded {limits[stream]} bytes" for stream in streams)
        raise ScaleLatencyError(f"kio subprocess output limit exceeded: {detail}")
    if timed_out:
        raise ScaleLatencyError(
            f"kio search exceeded {timeout_seconds:.3f}s timeout "
            f"(observed {duration_ms:.3f}ms)"
        )
    stdout = captured.get("stdout", b"")
    stderr = captured.get("stderr", b"")
    try:
        stdout_text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScaleLatencyError("kio search stdout is not UTF-8") from exc
    stderr_text = stderr.decode("utf-8", errors="replace")
    return {
        "returncode": returncode,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "duration_ms": duration_ms,
    }


def validate_search_response(outcome, case, expected_scope_ids):
    if outcome.get("returncode") != 0:
        detail = (outcome.get("stderr") or "").strip()
        raise ScaleLatencyError(
            f"search failed for query {case['index']} (exit {outcome.get('returncode')}): "
            f"{detail[:MAX_STDERR_BYTES]}"
        )
    try:
        response = json.loads(outcome.get("stdout") or "")
    except json.JSONDecodeError as exc:
        raise ScaleLatencyError(f"search returned invalid JSON for query {case['index']}") from exc
    if not isinstance(response, dict):
        raise ScaleLatencyError("search response must be an object")
    if response.get("query") != case["query"]:
        raise ScaleLatencyError("search response query does not match the request")
    if (
        response.get("requested_mode") != "auto"
        or response.get("resolved_mode") != "text"
        or response.get("fallback") is not True
        or response.get("fallback_reason") != "embedding_endpoint_not_configured"
    ):
        raise ScaleLatencyError(
            "scale latency runner requires default auto mode resolving to the "
            "embedding-free text fallback"
        )
    searched = response.get("searched_scopes")
    excluded = response.get("excluded_scopes")
    if not isinstance(searched, list) or len(searched) != EXPECTED_SCOPE_COUNT:
        raise ScaleLatencyError("search did not report exactly 20 searched scopes")
    if excluded != []:
        raise ScaleLatencyError("search excluded one or more scale scopes")
    actual_ids = [scope.get("scope_id") for scope in searched if isinstance(scope, dict)]
    if len(actual_ids) != EXPECTED_SCOPE_COUNT or set(actual_ids) != expected_scope_ids:
        raise ScaleLatencyError("searched scope identities differ from the attested fixture")
    results = response.get("results")
    if not isinstance(results, list) or not results:
        raise ScaleLatencyError(f"search returned no result for query {case['index']}")
    if len(results) > RESULT_LIMIT:
        raise ScaleLatencyError("search returned more results than the requested limit")
    expected_hit = False
    for result in results:
        if not isinstance(result, dict):
            continue
        pointer = result.get("evidence_pointer")
        if not isinstance(pointer, dict):
            continue
        if (
            pointer.get("scope_id") == case["scope_id"]
            and pointer.get("path_at_commit") == case["file"]
        ):
            expected_hit = True
            break
    if not expected_hit:
        raise ScaleLatencyError(
            f"expected scale hit is absent for {case['scope']}/{case['file']}"
        )
    return response


def execute_workload(query_mix, samples_per_scenario, warmups_per_scenario, execute_one):
    """Execute an interleaved deterministic schedule and aggregate each scenario."""
    validate_measurement_counts(samples_per_scenario, warmups_per_scenario)
    if not query_mix:
        raise ScaleLatencyError("scale query mix is empty")
    collected = {
        scenario["name"]: {
            "warmups": [],
            "samples": [],
            "warmup_internal_values": [],
            "sample_internal_values": [],
            "warmup_wall_values": [],
            "sample_wall_values": [],
        }
        for scenario in SCENARIOS
    }
    for phase, count in (
        ("warmups", warmups_per_scenario),
        ("samples", samples_per_scenario),
    ):
        for sequence in range(count):
            case = query_mix[sequence % len(query_mix)]
            for scenario in SCENARIOS:
                measurement = execute_one(scenario, case, phase, sequence)
                if not isinstance(measurement, dict):
                    raise ScaleLatencyError("search executor returned an invalid measurement")
                internal_ms = float(measurement["internal_duration_ms"])
                wall_ms = float(measurement["wall_duration_ms"])
                record = {
                    "sequence": sequence,
                    "query_index": case["index"],
                    "query": case["query"],
                    "expected_scope": case["scope"],
                    "expected_file": case["file"],
                    "internal_search_duration_ms": round(internal_ms, 3),
                    "process_wall_duration_ms": round(wall_ms, 3),
                    "metric_delta_bytes": measurement["metric_delta_bytes"],
                    "metric_log_rotated": measurement["metric_log_rotated"],
                }
                collected[scenario["name"]][phase].append(record)
                prefix = "warmup" if phase == "warmups" else "sample"
                collected[scenario["name"]][f"{prefix}_internal_values"].append(
                    internal_ms
                )
                collected[scenario["name"]][f"{prefix}_wall_values"].append(wall_ms)

    report = {}
    for scenario in SCENARIOS:
        name = scenario["name"]
        measurements = collected[name]["samples"]
        internal_measurements = collected[name]["sample_internal_values"]
        wall_measurements = collected[name]["sample_wall_values"]
        internal_stats = _statistics(internal_measurements)
        wall_stats = _statistics(wall_measurements)
        observed = (
            percentile_nearest_rank(internal_measurements, 0.95)
            < scenario["target_p95_ms"]
        )
        value = {
            "selector_flag": scenario["flag"],
            "measurement_class": scenario["measurement_class"],
            "formal_history_latency": scenario["formal_history_latency"],
            "formal_hybrid_mvp_latency_gate": False,
            "primary_clock_source": "KIO-M-SEARCH-001 search.latency_ms",
            "secondary_clock_source": "runner process wall time",
            "warmup_count": len(collected[name]["warmups"]),
            "sample_count": len(measurements),
            "internal_search_statistics_ms": internal_stats,
            "process_wall_statistics_ms": wall_stats,
            "nominal_target_p95_ms": scenario["target_p95_ms"],
            "internal_p95_below_nominal_target": observed,
            "warmups": collected[name]["warmups"],
            "samples": measurements,
        }
        if name == "M3-1":
            value["passes_default_auto_current_text_baseline_target"] = observed
            value["limitation"] = (
                "a highly selective exact token used default auto resolving to text on "
                "an embedding-free fixture; this is not the formal broad-query/hybrid "
                "MVP latency gate"
            )
        else:
            value["passes_formal_history_latency_gate"] = None
            value["limitation"] = (
                "execution-path-only: this fresh current-text corpus has no "
                "edit, rename, delete, or historical chunk load"
            )
        report[name] = value
    return report


def _canonical_json_hash(value):
    raw = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_stored_attestation(root, live_attestation):
    path = root / spec.ATTESTATION_NAME
    raw = _bounded_regular_bytes(path, MAX_ATTESTATION_BYTES, "stored scale attestation")
    try:
        stored = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScaleLatencyError(f"stored scale attestation is invalid JSON: {path}") from exc
    if stored != live_attestation:
        raise ScaleLatencyError(
            "stored scale attestation is stale; rerun prepare_scale_corpus.py"
        )
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def _platform_binding():
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "sys_platform": sys.platform,
        "os_name": os.name,
    }


def _atomic_write_json(path, value):
    data = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(data) > MAX_REPORT_BYTES:
        raise ScaleLatencyError(
            f"scale latency report exceeds {MAX_REPORT_BYTES} bytes"
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if not _is_plain_regular_file(metadata):
            raise ScaleLatencyError(f"report destination is unsafe: {path}")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _default_report_path(root):
    # Keep generated benchmark evidence entirely outside the generator-owned
    # tree and its strict allow-list.
    return Path(str(root) + REPORT_SUFFIX)


def _resolve_report_path(root, out_path):
    lexical_root = Path(os.path.abspath(os.path.expanduser(str(root))))
    try:
        canonical_root = lexical_root.resolve(strict=True)
    except OSError as exc:
        raise ScaleLatencyError(f"cannot canonicalize scale corpus: {lexical_root}") from exc
    if not canonical_root.is_dir():
        raise ScaleLatencyError(f"scale corpus must be a directory: {canonical_root}")
    lexical_path = Path(
        os.path.abspath(os.path.expanduser(str(out_path)))
        if out_path
        else _default_report_path(canonical_root)
    )
    # Resolve the existing parent now and return that canonical parent, not the
    # user-supplied symlink/junction path.  A later reparse retarget therefore
    # cannot redirect publication into the fixture after this containment check.
    try:
        canonical_parent = lexical_path.parent.resolve(strict=True)
    except OSError as exc:
        raise ScaleLatencyError(
            f"report parent must already exist: {lexical_path.parent}"
        ) from exc
    if not canonical_parent.is_dir():
        raise ScaleLatencyError(f"report parent must be a directory: {canonical_parent}")
    path = canonical_parent / lexical_path.name
    try:
        path.relative_to(canonical_root)
    except ValueError:
        return path
    raise ScaleLatencyError(
        "scale latency report must resolve outside the owned corpus"
    )


def run_locked_measurement(
    corpus_dir,
    bin_path,
    samples_per_scenario,
    warmups_per_scenario,
    timeout_seconds,
):
    validate_measurement_counts(samples_per_scenario, warmups_per_scenario)
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ScaleLatencyError("timeout-seconds must be a finite positive number")

    root, owner, manifest = generator.load_owned_manifest(corpus_dir)
    live_before = attestor.attest_corpus(root)
    expected_scope_ids = validate_full_fixture(manifest, live_before)
    stored_attestation = _load_stored_attestation(root, live_before)
    manifest_binding = _hash_regular_file(
        root / spec.MANIFEST_NAME,
        generator.MAX_MANIFEST_BYTES,
        "scale manifest",
    )
    if owner.get("manifest_sha256") != manifest_binding["sha256"]:
        raise ScaleLatencyError("owner marker does not bind the scale manifest")
    binary_before = resolve_release_binary(bin_path)
    query_mix = build_query_mix(manifest, live_before)
    env = subprocess_env(root)
    cwd = root / manifest["scopes"][0]["name"]
    metrics_path = Path(env["XDG_DATA_HOME"]) / "kio" / "logs" / "metrics.jsonl"

    def execute_one(scenario, case, _phase, _sequence):
        command = build_search_command(binary_before["path"], case, scenario)
        metric_snapshot = snapshot_metrics_log(metrics_path)
        try:
            outcome = run_bounded_process(command, cwd, env, timeout_seconds)
        except Exception:
            close_metrics_snapshot(metric_snapshot)
            raise
        metric, append = read_one_appended_metric(metric_snapshot)
        response = validate_search_response(outcome, case, expected_scope_ids)
        internal_duration_ms = validate_search_metric(metric, response)
        return {
            "wall_duration_ms": outcome["duration_ms"],
            "internal_duration_ms": internal_duration_ms,
            "metric_delta_bytes": append["delta_bytes"],
            "metric_log_rotated": append["rotated"],
        }

    scenario_reports = execute_workload(
        query_mix,
        samples_per_scenario,
        warmups_per_scenario,
        execute_one,
    )

    binary_after = resolve_release_binary(bin_path)
    if binary_after != binary_before:
        raise ScaleLatencyError("release kio binary changed during measurement")
    live_after = attestor.attest_corpus(root)
    if live_after != live_before:
        raise ScaleLatencyError("scale fixture attestation changed during measurement")
    manifest_after = _hash_regular_file(
        root / spec.MANIFEST_NAME,
        generator.MAX_MANIFEST_BYTES,
        "scale manifest",
    )
    if manifest_after != manifest_binding:
        raise ScaleLatencyError("scale manifest changed during measurement")

    m31_passed = scenario_reports["M3-1"][
        "passes_default_auto_current_text_baseline_target"
    ]
    return {
        "schema_version": 1,
        "benchmark": "kio-default-auto-high-selectivity-current-text-scale-baseline",
        "passed": m31_passed,
        "formal_hybrid_mvp_latency_gate": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture": {
            "fixture_id": spec.FIXTURE_ID,
            "profile": "full",
            "query_workload_id": spec.QUERY_WORKLOAD_ID,
            "scopes": EXPECTED_SCOPE_COUNT,
            "current_eligible_chunks": live_before["totals"]["current_eligible_chunks"],
            "physical_chunks": live_before["totals"]["physical_chunks"],
            "historical_or_ineligible_chunks": 0,
            "manifest": {"path": str(root / spec.MANIFEST_NAME), **manifest_binding},
            "stored_attestation": stored_attestation,
            "live_attestation_canonical_sha256": _canonical_json_hash(live_before),
        },
        "binary": binary_before,
        "platform": _platform_binding(),
        "configuration": {
            "requested_search_mode": "auto",
            "required_resolved_mode": "text",
            "required_fallback_reason": "embedding_endpoint_not_configured",
            "primary_clock_source": "KIO-M-SEARCH-001 search.latency_ms",
            "secondary_clock_source": "runner process wall time",
            "result_limit": RESULT_LIMIT,
            "query_mix_size": len(query_mix),
            "query_class": "exact deterministic reference token",
            "query_schedule": "manifest-order round-robin, scenarios interleaved",
            "warmups_per_scenario": warmups_per_scenario,
            "samples_per_scenario": samples_per_scenario,
            "timeout_seconds": timeout_seconds,
            "stdout_limit_bytes": MAX_STDOUT_BYTES,
            "stderr_limit_bytes": MAX_STDERR_BYTES,
            "metrics_log_limit_bytes": MAX_METRICS_LOG_BYTES,
            "metrics_delta_limit_bytes": MAX_METRICS_DELTA_BYTES,
            "metric_line_limit_bytes": MAX_METRIC_LINE_BYTES,
        },
        "limitations": {
            "hybrid_latency_measured": False,
            "broad_multi_scope_query_ranking_measured": False,
            "m3_1_is_formal_hybrid_mvp_latency": False,
            "history_operations_present": False,
            "m3_2_m3_3_are_formal_history_latency": False,
            "note": (
                "M3-1 uses one highly selective exact reference token per expected section; "
                "it does not measure broad multi-scope ranking and is not the formal "
                "hybrid/MVP gate. M3-2/M3-3 only exercise selector paths on a fresh "
                "current-only corpus; a history-bearing fixture is required for formal "
                "history p95."
            ),
        },
        "scenarios": scenario_reports,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Measure the high-selectivity default-auto current-text baseline on the "
            "attested full 120k fixture"
        )
    )
    parser.add_argument("--corpus", required=True, help="prepared full scale corpus")
    parser.add_argument(
        "--bin", required=True, help="release artifact target/release/kio (or kio.exe)"
    )
    parser.add_argument("--out", help="JSON report path")
    parser.add_argument(
        "--samples-per-scenario",
        type=int,
        default=DEFAULT_SAMPLES_PER_SCENARIO,
    )
    parser.add_argument(
        "--warmups-per-scenario",
        type=int,
        default=DEFAULT_WARMUPS_PER_SCENARIO,
    )
    parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    args = parser.parse_args(argv)

    root = Path(args.corpus).expanduser().absolute()
    try:
        report_path = _resolve_report_path(root, args.out)
        # Searches append bounded metrics logs. Hold the same portable fixture
        # lock from validation through publication of the external atomic report.
        with generator.fixture_lock(root):
            report = run_locked_measurement(
                root,
                args.bin,
                args.samples_per_scenario,
                args.warmups_per_scenario,
                args.timeout_seconds,
            )
            _atomic_write_json(report_path, report)
    except (
        OSError,
        ValueError,
        generator.ScaleGenerationError,
        attestor.ScaleAttestationError,
        ScaleLatencyError,
    ) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    m31 = report["scenarios"]["M3-1"]
    print(
        "[ok] high-selectivity default-auto current-text scale baseline measured: "
        f"scopes={report['fixture']['scopes']} "
        f"chunks={report['fixture']['current_eligible_chunks']} "
        f"samples/scenario={args.samples_per_scenario} "
        "M3-1-internal-p95="
        f"{m31['internal_search_statistics_ms']['p95']:.3f}ms"
    )
    print("     M3-1: high-selectivity baseline only (not formal broad-query/hybrid MVP latency)")
    print("     M3-2/M3-3: execution-path-only (not formal history latency)")
    print(f"     report: {report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
