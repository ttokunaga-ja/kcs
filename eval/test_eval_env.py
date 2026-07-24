#!/usr/bin/env python3
"""Focused tests for hermetic synthetic-evaluation device environments."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from eval.eval_env import subprocess_env


class TestEvalEnvironment(unittest.TestCase):
    def test_device_state_is_isolated_and_ambient_seams_are_removed(self):
        with tempfile.TemporaryDirectory(prefix="kio-eval-env-") as directory:
            corpus = Path(directory) / "persona"
            ambient = {
                "GEMINI_API_KEY": "not-a-real-key",
                "MISTRAL_API_KEY": "not-a-real-key",
                "KIO_FIXED_NOW": "2030-01-01T00:00:00Z",
                "KIO_TEST_GEMINI_EMBED": "mock",
                "KIO_TEST_MISTRAL_OCR": "mock",
                "KIO_TEST_MARKDOWNIZE_ADAPTER": "mock",
                "KIO_TEST_SCOPE_SEARCH_DELAY_MS": "99999",
                "KIO_TEST_HOLD_LOCK_MS": "99999",
                "KIO_TEST_PURGE_FAIL_AFTER_PHASE": "publish",
                "KIO_FUTURE_UNKNOWN_SEAM": "must-not-leak",
                "KIO_UNRELATED_TEST_VALUE": "preserved",
                "NON_KIO_UNRELATED_TEST_VALUE": "preserved",
            }
            with mock.patch.dict(os.environ, ambient, clear=False):
                environment = subprocess_env(corpus)

            device = corpus.absolute() / ".kio-eval-device"
            self.assertEqual(environment["HOME"], str(device / "home"))
            self.assertEqual(environment["XDG_CONFIG_HOME"], str(device / "config"))
            self.assertEqual(environment["XDG_DATA_HOME"], str(device / "data"))
            self.assertEqual(environment["XDG_CACHE_HOME"], str(device / "cache"))
            self.assertTrue((device / "config").is_dir())
            self.assertTrue((device / "data").is_dir())
            self.assertTrue((device / "cache").is_dir())
            self.assertTrue((device / "home").is_dir())
            for name in ambient:
                if name == "NON_KIO_UNRELATED_TEST_VALUE":
                    self.assertEqual(environment[name], "preserved")
                else:
                    self.assertNotIn(name, environment)

    def test_persona_home_can_be_selected_explicitly(self):
        with tempfile.TemporaryDirectory(prefix="kio-eval-home-") as directory:
            corpus = Path(directory) / "persona"
            persona_home = corpus / "home"
            environment = subprocess_env(corpus, home_dir=persona_home)
            self.assertEqual(environment["HOME"], str(persona_home.absolute()))
            self.assertTrue(persona_home.is_dir())


if __name__ == "__main__":
    unittest.main()
