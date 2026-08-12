#!/usr/bin/env python3
"""Regression tests for the cross-scope evaluation result artifact."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_crossscope  # noqa: E402


class TestCrossscopeResultArtifact(unittest.TestCase):
    def test_main_writes_replica_only_schema_with_rank_summary_and_lf(self):
        with tempfile.TemporaryDirectory(prefix="kio-crossscope-result-") as directory:
            bin_path = os.path.join(directory, "kio")
            output_path = os.path.join(directory, "crossscope-results.json")
            with open(bin_path, "wb"):
                pass
            query = {
                "scenario": "M3-1",
                "query": "two-scope query",
                "expected": [
                    {"scope": "alpha", "file": "a.md", "section": "a"},
                    {"scope": "beta", "file": "b.md", "section": "b"},
                ],
            }
            resolver = mock.Mock()
            resolver.resolve_expected.return_value = ({("a", "b", "c")}, [])
            response = {"results": []}
            outcome = {"duration_ms": 12.5}

            with mock.patch.object(
                    run_crossscope.eval_oracle, "load_golden", return_value=[query]), \
                 mock.patch.object(
                    run_crossscope.eval_oracle, "load_json", return_value={}), \
                 mock.patch.object(
                    run_crossscope.eval_oracle, "CorpusModel", return_value=mock.Mock()), \
                 mock.patch.object(
                    run_crossscope.eval_oracle, "Resolver", return_value=resolver), \
                 mock.patch.object(
                    run_crossscope.eval_oracle, "run_search", return_value=outcome), \
                 mock.patch.object(
                    run_crossscope.eval_oracle, "classify_outcome",
                    return_value=("scored", response, None, "")), \
                 mock.patch.object(
                    run_crossscope.eval_oracle, "evidence_problems", return_value=[]), \
                 mock.patch.object(
                    run_crossscope.eval_oracle, "recall_at_k", return_value=1.0), \
                 mock.patch.object(
                    run_crossscope.eval_oracle, "percentile_nearest_rank", return_value=12.5), \
                 mock.patch.object(
                    run_crossscope.eval_oracle, "passes_latency_target", return_value=True), \
                 mock.patch.object(run_crossscope, "worst_expected_rank", return_value=2):
                exit_code = run_crossscope.main([
                    "--corpus", directory,
                    "--bin", bin_path,
                    "--out", output_path,
                ])

            self.assertEqual(exit_code, 0)
            with open(output_path, "rb") as handle:
                raw = handle.read()
            self.assertNotIn(b"\r\n", raw)
            payload = json.loads(raw.decode("utf-8"))
            self.assertEqual(payload["counts"], {
                "n_failed": 0,
                "n_queries": 1,
                "worst_expected_rank_mean": 2.0,
                "worst_expected_rank_max": 2,
            })
            self.assertNotIn("aggregator_applied", payload["counts"])
            self.assertNotIn("aggregator", payload["queries"][0])


if __name__ == "__main__":
    unittest.main()
