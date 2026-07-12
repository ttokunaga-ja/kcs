#!/usr/bin/env bash
set -euo pipefail

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

python3 - "$workdir" <<'PY'
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
(root / ".kcs").mkdir()
(root / "alpha.bin").write_bytes(b"A" * 32768)
(root / "bravo.bin").write_bytes(b"B" * 65536)
(root / "notes.txt").write_text("small file\n", encoding="utf-8")
(root / "subdir").mkdir()

missing_hash = "0" * 64
visited = []
total_bytes = 0
peak_allocation = 0

for child in sorted(root.iterdir(), key=lambda item: item.name):
    if child.name == ".kcs":
        continue
    if not child.is_file():
        continue

    data = child.read_bytes()
    visited.append((child.name, len(data)))
    total_bytes += len(data)
    peak_allocation = max(peak_allocation, len(data))
    if hashlib.sha256(data).hexdigest() == missing_hash:
        raise AssertionError("the all-zero hash should not match synthetic input")

chunk_cap = 4096
streamed_files = 0
for child in sorted(root.iterdir(), key=lambda item: item.name):
    if child.name == ".kcs" or not child.is_file():
        continue

    streamed_files += 1
    digest = hashlib.sha256()
    with child.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_cap)
            if not chunk:
                break
            if len(chunk) > chunk_cap:
                raise AssertionError("chunk reader exceeded cap")
            digest.update(chunk)
    if digest.hexdigest() == missing_hash:
        raise AssertionError("the all-zero hash should not match synthetic input")

print("[+] synthetic files created: alpha.bin=32768, bravo.bin=65536, notes.txt=11")
print(f"[+] vulnerable-style absent-hash scan visited {len(visited)} regular files")
print(f"[+] vulnerable-style total bytes read: {total_bytes}")
print(f"[+] vulnerable-style largest single allocation: {peak_allocation}")
print(f"[+] streaming regression probe hashed the same files with a {chunk_cap}-byte chunk cap")
print("[+] no live KCS command, credentials, network, or large allocation was used")

assert len(visited) == 3
assert streamed_files == 3
assert total_bytes == 32768 + 65536 + len("small file\n")
assert peak_allocation == 65536
PY
