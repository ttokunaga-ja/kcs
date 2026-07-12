#!/usr/bin/env python3
"""Offline probe for KCS incremental unit-mapping matrix growth.

The script mirrors the allocation shape and nested loop of
`lcs_fingerprint_pairs` with synthetic fingerprints. It keeps executable
default sizes small and computes larger memory estimates without allocating
them.
"""

from __future__ import annotations

import argparse
import time


def byte_string(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.2f} {unit}"
        amount /= 1024.0
    return f"{value} B"


def matrix_cells(old_count: int, new_count: int) -> int:
    return (old_count + 1) * (new_count + 1)


def rust_matrix_bytes(old_count: int, new_count: int, usize_bytes: int) -> int:
    return matrix_cells(old_count, new_count) * usize_bytes


def synthetic_fingerprints(count: int, prefix: str) -> list[str]:
    return [f"{prefix}-{index:08x}" for index in range(count)]


def run_lcs_probe(size: int) -> tuple[int, float, int]:
    old = synthetic_fingerprints(size, "old")
    new = synthetic_fingerprints(size, "new")
    start = time.perf_counter()
    dp = [[0] * (len(new) + 1) for _ in range(len(old) + 1)]
    comparisons = 0
    for i in range(len(old) - 1, -1, -1):
        for j in range(len(new) - 1, -1, -1):
            comparisons += 1
            if old[i] == new[j]:
                dp[i][j] = 1 + dp[i + 1][j + 1]
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    elapsed = time.perf_counter() - start
    return matrix_cells(size, size), elapsed, comparisons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demonstrate quadratic LCS matrix growth with synthetic KCS units."
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[64, 128, 256, 512],
        help="bounded square sizes to allocate and time",
    )
    parser.add_argument(
        "--estimate-only",
        nargs="+",
        type=int,
        default=[10_000, 20_000, 50_000],
        help="larger square sizes to estimate without allocation",
    )
    parser.add_argument(
        "--allocate-up-to",
        type=int,
        default=512,
        help="refuse to allocate executable probes above this square size",
    )
    parser.add_argument(
        "--usize-bytes",
        type=int,
        default=8,
        help="target Rust usize width for memory estimates",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[+] bounded synthetic LCS probe")
    for size in args.sizes:
        cells = matrix_cells(size, size)
        estimate = rust_matrix_bytes(size, size, args.usize_bytes)
        if size > args.allocate_up_to:
            print(
                f"[!] {size}x{size}: skipped allocation; "
                f"cells={cells:,} rust_matrix={byte_string(estimate)}"
            )
            continue
        cells, elapsed, comparisons = run_lcs_probe(size)
        print(
            f"[+] {size}x{size}: cells={cells:,} comparisons={comparisons:,} "
            f"rust_matrix={byte_string(estimate)} elapsed={elapsed:.4f}s"
        )

    print("[+] large-size estimates only")
    for size in args.estimate_only:
        cells = matrix_cells(size, size)
        estimate = rust_matrix_bytes(size, size, args.usize_bytes)
        print(
            f"[+] {size}x{size}: cells={cells:,} "
            f"rust_matrix={byte_string(estimate)} (not allocated)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
