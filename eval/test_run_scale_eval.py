"""Unit tests for the manual default-auto scale latency runner."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_scale_eval as runner  # noqa: E402


def _scope_reports():
    return [
        {
            "name": f"scope-{index:02d}",
            "scope_id": f"scope-id-{index:02d}",
            "historical_or_ineligible_chunks": 0,
        }
        for index in range(20)
    ]


def _full_fixture_values():
    manifest = {
        "profile": "full",
        "query_workload_id": runner.spec.QUERY_WORKLOAD_ID,
        "shape": {
            "scope_count": 20,
            "expected_current_chunks": 120_000,
        },
        "needles": [
            {
                "query": f"needle {index}",
                "scope": f"scope-{index:02d}",
                "file": "document-0000.md",
                "heading": f"Heading {index}",
            }
            for index in range(20)
        ],
    }
    attestation = {
        "profile": "full",
        "query_workload_id": runner.spec.QUERY_WORKLOAD_ID,
        "totals": {
            "current_eligible_chunks": 120_000,
            "physical_chunks": 120_000,
        },
        "scopes": _scope_reports(),
    }
    return manifest, attestation


def _search_metric(result_count=1):
    return {
        "ts": "2026-07-13T00:00:00Z",
        "level": "info",
        "code": "KIO-M-SEARCH-001",
        "component": "search",
        "message": "search completed",
        "metric": "search.latency_ms",
        "value": 12.5,
        "context": {
            "mode": "text",
            "scope_count": 20,
            "result_count": result_count,
        },
    }


def _metric_line(result_count=1):
    return (json.dumps(_search_metric(result_count), separators=(",", ":")) + "\n").encode()


class PercentileTests(unittest.TestCase):
    def test_nearest_rank_on_100_samples(self):
        values = list(range(1, 101))
        self.assertEqual(runner.percentile_nearest_rank(values, 0.50), 50.0)
        self.assertEqual(runner.percentile_nearest_rank(values, 0.95), 95.0)
        self.assertEqual(runner.percentile_nearest_rank(values, 0.99), 99.0)

    def test_empty_and_invalid_percentile(self):
        self.assertIsNone(runner.percentile_nearest_rank([], 0.95))
        with self.assertRaises(ValueError):
            runner.percentile_nearest_rank([1], 0)

    def test_samples_below_100_are_rejected(self):
        with self.assertRaisesRegex(runner.ScaleLatencyError, "at least 100"):
            runner.validate_measurement_counts(99, 1)
        with self.assertRaisesRegex(runner.ScaleLatencyError, "warmups"):
            runner.validate_measurement_counts(100, 0)
        runner.validate_measurement_counts(100, 1)


class FixtureBindingTests(unittest.TestCase):
    def test_full_fixture_requires_20_scopes_and_more_than_100k_current_chunks(self):
        manifest, attestation = _full_fixture_values()
        expected = runner.validate_full_fixture(manifest, attestation)
        self.assertEqual(len(expected), 20)

        manifest["profile"] = "tiny"
        with self.assertRaisesRegex(runner.ScaleLatencyError, "profile=full"):
            runner.validate_full_fixture(manifest, attestation)

    def test_historical_or_ineligible_rows_are_rejected(self):
        manifest, attestation = _full_fixture_values()
        attestation["totals"]["physical_chunks"] += 1
        with self.assertRaisesRegex(runner.ScaleLatencyError, "historical/ineligible"):
            runner.validate_full_fixture(manifest, attestation)

    def test_query_mix_binds_manifest_names_to_attested_scope_ids(self):
        manifest, attestation = _full_fixture_values()
        cases = runner.build_query_mix(manifest, attestation)
        self.assertEqual(len(cases), 20)
        self.assertEqual(cases[7]["scope_id"], "scope-id-07")
        self.assertEqual(cases[7]["file"], "document-0000.md")

    def test_release_binary_is_bounded_hashed_and_path_checked(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-binary-") as temp:
            release = Path(temp) / "target" / "release"
            release.mkdir(parents=True)
            binary = release / ("kio.exe" if os.name == "nt" else "kio")
            binary.write_bytes(b"release-binary")
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
            binding = runner.resolve_release_binary(binary)
            self.assertEqual(binding["bytes"], len(b"release-binary"))
            self.assertEqual(len(binding["sha256"]), 64)

            wrong = Path(temp) / "kio"
            wrong.write_bytes(b"not-release-path")
            wrong.chmod(wrong.stat().st_mode | stat.S_IXUSR)
            with self.assertRaisesRegex(runner.ScaleLatencyError, "release artifact"):
                runner.resolve_release_binary(wrong)

    def test_release_binary_rejects_reparse_backed_regular_file(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-binary-reparse-") as temp:
            release = Path(temp) / "target" / "release"
            release.mkdir(parents=True)
            binary = release / ("kio.exe" if os.name == "nt" else "kio")
            binary.write_bytes(b"release-binary")
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
            with mock.patch.object(runner, "_is_plain_regular_file", return_value=False):
                with self.assertRaisesRegex(runner.ScaleLatencyError, "regular file"):
                    runner.resolve_release_binary(binary)

    def test_stored_attestation_must_equal_live_attestation(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-attestation-") as temp:
            root = Path(temp)
            path = root / runner.spec.ATTESTATION_NAME
            value = {"passed": True, "totals": {"current_eligible_chunks": 120_000}}
            path.write_text(json.dumps(value), encoding="utf-8")
            binding = runner._load_stored_attestation(root, value)
            self.assertEqual(binding["path"], str(path))
            self.assertEqual(len(binding["sha256"]), 64)
            with self.assertRaisesRegex(runner.ScaleLatencyError, "stale"):
                runner._load_stored_attestation(root, {"passed": False})


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "index": 0,
            "query": "needle 0",
            "scope": "scope-00",
            "scope_id": "scope-id-00",
            "file": "document-0000.md",
        }
        self.scope_ids = {f"scope-id-{index:02d}" for index in range(20)}
        self.response = {
            "query": self.case["query"],
            "requested_mode": "auto",
            "resolved_mode": "text",
            "fallback": True,
            "fallback_reason": "embedding_endpoint_not_configured",
            "searched_scopes": [
                {"scope_id": f"scope-id-{index:02d}"} for index in range(20)
            ],
            "excluded_scopes": [],
            "results": [
                {
                    "evidence_pointer": {
                        "scope_id": self.case["scope_id"],
                        "path_at_commit": self.case["file"],
                    }
                }
            ],
        }

    def outcome(self):
        return {
            "returncode": 0,
            "stdout": json.dumps(self.response),
            "stderr": "",
            "duration_ms": 1.0,
        }

    def test_response_requires_exact_scopes_no_exclusions_and_expected_hit(self):
        result = runner.validate_search_response(
            self.outcome(), self.case, self.scope_ids
        )
        self.assertEqual(result["resolved_mode"], "text")

        self.response["excluded_scopes"] = [{"reason": "timeout"}]
        with self.assertRaisesRegex(runner.ScaleLatencyError, "excluded"):
            runner.validate_search_response(self.outcome(), self.case, self.scope_ids)

    def test_response_requires_expected_file_and_scope_identity(self):
        self.response["results"][0]["evidence_pointer"]["path_at_commit"] = "wrong.md"
        with self.assertRaisesRegex(runner.ScaleLatencyError, "expected scale hit"):
            runner.validate_search_response(self.outcome(), self.case, self.scope_ids)

    def test_nonzero_exit_is_never_accepted(self):
        outcome = self.outcome()
        outcome.update({"returncode": 3, "stderr": "partial"})
        with self.assertRaisesRegex(runner.ScaleLatencyError, "exit 3"):
            runner.validate_search_response(outcome, self.case, self.scope_ids)


class MetricsTests(unittest.TestCase):
    def test_exactly_one_new_metric_is_read_and_validated(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-metric-") as temp:
            path = Path(temp) / "metrics.jsonl"
            old = _metric_line(0)
            path.write_bytes(old)
            snapshot = runner.snapshot_metrics_log(path)
            with path.open("ab") as handle:
                handle.write(_metric_line(1))
            metric, append = runner.read_one_appended_metric(snapshot)
            self.assertEqual(append["delta_bytes"], len(_metric_line(1)))
            self.assertFalse(append["rotated"])
            response = {"results": [{}]}
            self.assertEqual(runner.validate_search_metric(metric, response), 12.5)

    def test_metric_rotation_reads_only_the_new_live_line(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-metric-rotate-") as temp:
            path = Path(temp) / "metrics.jsonl"
            rotated = Path(temp) / "metrics-2026-07-12.jsonl"
            path.write_bytes(_metric_line(0))
            snapshot = runner.snapshot_metrics_log(path)
            path.replace(rotated)
            path.write_bytes(_metric_line(1))
            metric, append = runner.read_one_appended_metric(snapshot)
            self.assertTrue(append["rotated"])
            self.assertEqual(runner.validate_search_metric(metric, {"results": [{}]}), 12.5)

    def test_missing_or_multiple_metric_appends_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-metric-count-") as temp:
            path = Path(temp) / "metrics.jsonl"
            path.write_bytes(_metric_line(0))
            missing = runner.snapshot_metrics_log(path)
            with self.assertRaisesRegex(runner.ScaleLatencyError, "did not append"):
                runner.read_one_appended_metric(missing)

            multiple = runner.snapshot_metrics_log(path)
            with path.open("ab") as handle:
                handle.write(_metric_line(1))
                handle.write(_metric_line(1))
            with self.assertRaisesRegex(runner.ScaleLatencyError, "exactly one"):
                runner.read_one_appended_metric(multiple)

    def test_metric_line_and_delta_bounds_are_enforced(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-metric-bound-") as temp:
            path = Path(temp) / "metrics.jsonl"
            snapshot = runner.snapshot_metrics_log(path)
            path.write_bytes(b"x" * 17 + b"\n")
            with mock.patch.object(runner, "MAX_METRIC_LINE_BYTES", 16):
                with self.assertRaisesRegex(runner.ScaleLatencyError, "line exceeds"):
                    runner.read_one_appended_metric(snapshot)

            delta_snapshot = runner.snapshot_metrics_log(Path(temp) / "delta.jsonl")
            (Path(temp) / "delta.jsonl").write_bytes(b"x" * 17 + b"\n")
            with mock.patch.object(runner, "MAX_METRICS_DELTA_BYTES", 16):
                with self.assertRaisesRegex(runner.ScaleLatencyError, "append exceeds"):
                    runner.read_one_appended_metric(delta_snapshot)

    def test_metrics_log_rejects_reparse_backed_regular_file(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-metric-reparse-") as temp:
            path = Path(temp) / "metrics.jsonl"
            path.write_bytes(_metric_line(0))
            with mock.patch.object(runner, "_is_plain_regular_file", return_value=False):
                with self.assertRaisesRegex(runner.ScaleLatencyError, "regular file"):
                    runner.snapshot_metrics_log(path)

    def test_metric_rejects_query_or_path_and_response_mismatch(self):
        metric = _search_metric(1)
        metric["context"]["query"] = "secret"
        with self.assertRaisesRegex(runner.ScaleLatencyError, "leaks query/path"):
            runner.validate_search_metric(metric, {"results": [{}]})

        metric = _search_metric(2)
        with self.assertRaisesRegex(runner.ScaleLatencyError, "disagrees"):
            runner.validate_search_metric(metric, {"results": [{}]})


class WorkloadTests(unittest.TestCase):
    def test_search_command_uses_default_scope_selector_and_auto_mode(self):
        case = {"query": "needle"}
        command = runner.build_search_command("target/release/kio", case, runner.SCENARIOS[0])
        self.assertEqual(
            command,
            ["target/release/kio", "--json", "search", "needle", "--limit", "10"],
        )
        for explicit in ("--all-scopes", "--text", "--vector", "--hybrid"):
            self.assertNotIn(explicit, command)

    def test_schedule_is_deterministic_interleaved_and_labels_history_as_nonformal(self):
        manifest, attestation = _full_fixture_values()
        query_mix = runner.build_query_mix(manifest, attestation)
        calls = []

        def execute(scenario, case, phase, sequence):
            calls.append((phase, sequence, scenario["name"], case["index"]))
            internal = sequence + {
                "M3-1": 1,
                "M3-2": 2,
                "M3-3": 3,
            }[scenario["name"]]
            return {
                "internal_duration_ms": internal,
                "wall_duration_ms": internal + 10,
                "metric_delta_bytes": 200,
                "metric_log_rotated": False,
            }

        report = runner.execute_workload(query_mix, 100, 2, execute)
        self.assertEqual(len(calls), 3 * 102)
        self.assertEqual(
            calls[:3],
            [
                ("warmups", 0, "M3-1", 0),
                ("warmups", 0, "M3-2", 0),
                ("warmups", 0, "M3-3", 0),
            ],
        )
        measured_indices = [
            record["query_index"] for record in report["M3-1"]["samples"]
        ]
        self.assertEqual(measured_indices.count(0), 5)
        self.assertEqual(measured_indices.count(19), 5)
        self.assertEqual(report["M3-1"]["sample_count"], 100)
        self.assertEqual(
            report["M3-1"]["measurement_class"],
            "default-auto-high-selectivity-current-text-baseline",
        )
        self.assertIn(
            "passes_default_auto_current_text_baseline_target", report["M3-1"]
        )
        self.assertEqual(
            report["M3-1"]["primary_clock_source"],
            "KIO-M-SEARCH-001 search.latency_ms",
        )
        self.assertLess(
            report["M3-1"]["internal_search_statistics_ms"]["p95"],
            report["M3-1"]["process_wall_statistics_ms"]["p95"],
        )
        self.assertFalse(report["M3-1"]["formal_hybrid_mvp_latency_gate"])
        for scenario in ("M3-2", "M3-3"):
            self.assertEqual(report[scenario]["measurement_class"], "execution-path-only")
            self.assertFalse(report[scenario]["formal_history_latency"])
            self.assertIsNone(report[scenario]["passes_formal_history_latency_gate"])
            self.assertIn("no edit, rename, delete", report[scenario]["limitation"])


class ProcessAndPublicationTests(unittest.TestCase):
    def test_report_defaults_to_sibling_and_rejects_corpus_descendants(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-report-path-") as temp:
            root = Path(temp) / "corpus"
            root.mkdir()
            default = runner._resolve_report_path(root, None)
            self.assertEqual(default, Path(str(root.resolve()) + ".latency.json"))
            with self.assertRaisesRegex(runner.ScaleLatencyError, "outside"):
                runner._resolve_report_path(root, root / "report.json")
            with self.assertRaisesRegex(runner.ScaleLatencyError, "outside"):
                runner._resolve_report_path(root, root / "child" / ".." / "report.json")

    def test_report_rejects_outside_symlink_parent_resolving_inside_corpus(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-report-link-") as temp:
            root = Path(temp) / "corpus"
            root.mkdir()
            apparent_outside = Path(temp) / "outside-link"
            try:
                apparent_outside.symlink_to(root, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")
            with self.assertRaisesRegex(runner.ScaleLatencyError, "resolve outside"):
                runner._resolve_report_path(root, apparent_outside / "report.json")

    def test_process_stdout_is_capped(self):
        with mock.patch.object(runner, "MAX_STDOUT_BYTES", 16):
            with self.assertRaisesRegex(runner.ScaleLatencyError, "stdout exceeded"):
                runner.run_bounded_process(
                    [sys.executable, "-c", "import sys;sys.stdout.write('x'*17)"],
                    os.getcwd(),
                    os.environ.copy(),
                    5.0,
                )

    def test_process_stderr_is_capped(self):
        with mock.patch.object(runner, "MAX_STDERR_BYTES", 16):
            with self.assertRaisesRegex(runner.ScaleLatencyError, "stderr exceeded"):
                runner.run_bounded_process(
                    [sys.executable, "-c", "import sys;sys.stderr.write('x'*17)"],
                    os.getcwd(),
                    os.environ.copy(),
                    5.0,
                )

    def test_output_overflow_kills_sleeping_child_early_and_joins_readers(self):
        command = (
            "import sys,time;"
            "sys.stdout.buffer.write(b'x'*17);"
            "sys.stdout.buffer.flush();"
            "time.sleep(10)"
        )
        started = time.monotonic()
        with mock.patch.object(runner, "MAX_STDOUT_BYTES", 16):
            with self.assertRaisesRegex(runner.ScaleLatencyError, "stdout exceeded"):
                runner.run_bounded_process(
                    [sys.executable, "-c", command],
                    os.getcwd(),
                    os.environ.copy(),
                    8.0,
                )
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertFalse(
            any(
                thread.name.startswith("kio-scale-")
                for thread in threading.enumerate()
            )
        )

    def test_process_timeout_is_enforced(self):
        with self.assertRaisesRegex(runner.ScaleLatencyError, "timeout"):
            runner.run_bounded_process(
                [sys.executable, "-c", "import time;time.sleep(2)"],
                os.getcwd(),
                os.environ.copy(),
                0.01,
            )
        self.assertFalse(
            any(
                thread.name.startswith("kio-scale-")
                for thread in threading.enumerate()
            )
        )

    def test_atomic_report_publication(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-report-") as temp:
            path = Path(temp) / "report.json"
            runner._atomic_write_json(path, {"passed": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"passed": True})
            leftovers = list(path.parent.glob(f".{path.name}.*.tmp"))
            self.assertEqual(leftovers, [])

    def test_atomic_report_rejects_reparse_backed_regular_destination(self):
        with tempfile.TemporaryDirectory(prefix="kio-scale-report-reparse-") as temp:
            path = Path(temp) / "report.json"
            path.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(runner, "_is_plain_regular_file", return_value=False):
                with self.assertRaisesRegex(runner.ScaleLatencyError, "unsafe"):
                    runner._atomic_write_json(path, {"passed": True})

    def test_main_holds_fixture_lock_through_report_publication(self):
        events = []

        @contextmanager
        def fake_lock(_root):
            events.append("lock-enter")
            try:
                yield
            finally:
                events.append("lock-exit")

        report = {
            "passed": True,
            "fixture": {"scopes": 20, "current_eligible_chunks": 120_000},
            "scenarios": {
                "M3-1": {"internal_search_statistics_ms": {"p95": 12.5}}
            },
        }

        def fake_write(_path, _report):
            self.assertEqual(events, ["lock-enter", "measure"])
            events.append("write")

        def fake_measure(*_args, **_kwargs):
            events.append("measure")
            return report

        with tempfile.TemporaryDirectory(prefix="kio-scale-main-") as temp:
            root = Path(temp) / "corpus"
            root.mkdir()
            out = Path(temp) / "result.json"
            with mock.patch.object(runner.generator, "fixture_lock", fake_lock), mock.patch.object(
                runner, "run_locked_measurement", fake_measure
            ), mock.patch.object(runner, "_atomic_write_json", fake_write):
                exit_code = runner.main(
                    [
                        "--corpus",
                        str(root),
                        "--bin",
                        "target/release/kio",
                        "--out",
                        str(out),
                    ]
                )
        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["lock-enter", "measure", "write", "lock-exit"])


if __name__ == "__main__":
    unittest.main()
