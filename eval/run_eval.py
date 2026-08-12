#!/usr/bin/env python3
"""Compatibility entry point for the canonical Rust ``kio-eval`` runner.

The evaluator's CLI, reporting and exit-code contract live in ``kio-eval``.
Python intentionally does not fall back to a second production implementation:
use ``KIO_EVAL_BIN`` to select an explicitly built evaluator during tests.
"""

import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)


def evaluator_binary():
    """Return the explicitly selected or repository-local evaluator binary."""
    override = os.environ.get("KIO_EVAL_BIN")
    candidates = [override] if override else [
        os.path.join(REPO_ROOT, "target", "release", "kio-eval"),
        os.path.join(REPO_ROOT, "target", "debug", "kio-eval"),
    ]
    if os.name == "nt":
        candidates = [path if path and path.lower().endswith(".exe") else f"{path}.exe"
                      for path in candidates]
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return os.path.abspath(path)
    searched = ", ".join(path for path in candidates if path)
    raise SystemExit(
        "[error] Rust evaluator kio-eval が見つからないか実行できません: "
        f"{searched}\n        cargo build --release --locked --all-features を実行するか、"
        "KIO_EVAL_BIN を指定してください。")


def main(argv=None):
    """Replace this process so argv, streams and exit status stay transparent."""
    args = sys.argv[1:] if argv is None else list(argv)
    binary = evaluator_binary()
    os.execv(binary, [binary, *args])


if __name__ == "__main__":
    main()
