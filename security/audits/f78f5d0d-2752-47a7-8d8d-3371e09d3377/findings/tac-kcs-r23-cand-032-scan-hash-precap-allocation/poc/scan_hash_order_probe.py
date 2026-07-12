#!/usr/bin/env python3
"""Safe source-order probe for KCS-R23-CAND-032.

The probe verifies the vulnerable ordering without running KCS or creating a
large file. When --repo is supplied it reads the exact revision with git show;
otherwise it falls back to embedded source excerpts from the affected revision.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile

REVISION = "0e19f3c6489da458e93a982a333c308d92d0a0ae"

SCAN_RS_EXCERPT = r'''
let size_bytes = entry.metadata().pipeline_io(&path)?.len();
let secret = classify_secret(&relative);
let ignored = ignored_by_rules(
    &relative,
    file_type.is_dir(),
    ignore_rules,
    case_insensitive,
) || secret == Some(SecretTier::TierA)
    && !explicitly_unignored(
        &relative,
        file_type.is_dir(),
        ignore_rules,
        case_insensitive,
    );
let raw_hash = if include_raw_hashes && !ignored {
    Some(hash_bytes(&std::fs::read(&path).pipeline_io(&path)?))
} else {
    None
};
'''

MAIN_RS_EXCERPT = r'''
let preview = build_scan_preview(ScanPreviewRequest {
    scope_path: repo.root().display().to_string(),
    include_raw_hashes: !args.preview,
    require_network_approval: !args.offline,
})
.map_err(pipeline_to_kcs)?;

if args.preview {
    return Ok(index_preview_json(repo.root(), &preview));
}

let max_input_bytes = effective_max_input_bytes(repo);
for candidate in preview
    .candidates
    .iter()
    .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
{
    if candidate.size_bytes > max_input_bytes {
        result.skipped_oversized_files += 1;
        continue;
    }
}
'''


def git_show(repo: pathlib.Path, rev: str, path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{rev}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def source_text(repo: str | None, rev: str, path: str, fallback: str) -> str:
    if repo:
        return git_show(pathlib.Path(repo), rev, path)
    return fallback


def require_order(text: str, first: str, second: str, label: str) -> None:
    first_index = text.find(first)
    second_index = text.find(second)
    if first_index < 0:
        raise AssertionError(f"missing marker before check: {first!r}")
    if second_index < 0:
        raise AssertionError(f"missing marker after check: {second!r}")
    if first_index >= second_index:
        raise AssertionError(f"order check failed for {label}")


def require_contains(text: str, marker: str) -> None:
    if marker not in text:
        raise AssertionError(f"missing marker: {marker!r}")


def bounded_read_demo() -> int:
    with tempfile.TemporaryDirectory(prefix="kcs-cand-032-") as tmp:
        path = pathlib.Path(tmp) / "bounded.bin"
        path.write_bytes(b"A" * 1_048_576)
        data = path.read_bytes()
        hashlib.sha256(data).hexdigest()
        return len(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("KCS_SOURCE_ROOT"))
    parser.add_argument("--rev", default=REVISION)
    args = parser.parse_args()

    scan_rs = source_text(
        args.repo,
        args.rev,
        "crates/kcs-pipeline/src/scan.rs",
        SCAN_RS_EXCERPT,
    )
    main_rs = source_text(
        args.repo,
        args.rev,
        "crates/kcs-cli/src/main.rs",
        MAIN_RS_EXCERPT,
    )

    require_order(
        main_rs,
        "include_raw_hashes: !args.preview",
        "if args.preview",
        "normal index raw hash request",
    )
    print("[ok] normal index enables raw scan hashes before preview returns")

    require_order(
        scan_rs,
        "let size_bytes = entry.metadata().pipeline_io(&path)?.len();",
        "std::fs::read(&path)",
        "metadata length before whole-file read",
    )
    print("[ok] scanner records metadata length before the raw-hash read")

    require_contains(scan_rs, "let raw_hash = if include_raw_hashes && !ignored")
    require_contains(scan_rs, "Some(hash_bytes(&std::fs::read(&path).pipeline_io(&path)?))")
    print("[ok] raw-hash branch performs a whole-file read before the adapter cap")

    require_order(
        main_rs,
        "let max_input_bytes = effective_max_input_bytes(repo);",
        "if candidate.size_bytes > max_input_bytes",
        "adapter cap branch",
    )
    require_contains(main_rs, "for candidate in preview")
    print("[ok] downstream max_input_bytes gate is adapter-only and post-preview")

    allocated = bounded_read_demo()
    print(f"[ok] bounded local read demo allocated {allocated} bytes for hashing")
    print("[safe] no KCS command executed; no network, credentials, or large files used")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        raise SystemExit(1)
