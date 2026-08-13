#!/usr/bin/env python3
"""Compatibility entry point for Rust-owned corpus generation.

The fixture renderer, manifest and overwrite policy live in ``kio-eval
generate-corpus``.  This shim deliberately has no Python or Cargo fallback so
CI exercises the same binary boundary users invoke.
"""

import os
import sys

from run_eval import evaluator_binary


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    binary = evaluator_binary()
    os.execv(binary, [binary, "generate-corpus", *args])


if __name__ == "__main__":
    main()
