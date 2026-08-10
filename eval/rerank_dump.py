#!/usr/bin/env python3
"""Pass 1 of the reranker differential: freeze what the text lane returned.

The reranker runs on a machine that cannot run `kio` (no Rust — see
`tasks/gpu-reranker-verification.md` §3), and this machine has no NVIDIA GPU.
There is no network route between them either, so the measurement is split in
two halves joined by git:

    rerank_dump.py   (here)   search -> rerank-input.json
    tasks/gpu-rerank-differential.md  (GPU box)  -> rerank-output.json
    rerank_apply.py  (here)   reorder -> Recall@10 before/after

This half runs every golden query, records the candidates the text lane
produced **in its own order**, and reconstructs each candidate's exact chunk
text from the evidence pointer's byte span so the reranker scores the same
characters the index holds. The baseline Recall@10 is computed here too, from
the unreordered list, so the second half never has to be trusted about what
the starting point was.

## Why current-tree queries only

A candidate's text is read from `path_at_commit` under its scope. For
`--all-history` / `--include-deleted` results that file may be renamed or gone,
and its bytes live only in CAS. Rather than mix full chunk text with truncated
snippets — which would make a score difference impossible to attribute — this
dumps only queries that carry no history flags. That is M3-1 plus the whole
short-query set: the saturated set can still detect harm, and the short set is
the one with measured headroom (22/24).

## Why `--limit 100`

05 §1.3's `candidate_depth` is 200, but the CLI caps `--limit` at 100, so from
outside the process only the top 100 are visible. A reranker integrated inside
would see 200. This measurement is therefore a **lower bound** on what one
could recover.

Usage:

    python3 eval/rerank_dump.py --corpus /tmp/kio-eval-corpus \\
        --bin target/release/kio --out /tmp/rerank-input.json
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import corpus_spec as spec  # noqa: E402
from eval_env import subprocess_env  # noqa: E402
from run_eval import (  # noqa: E402
    CorpusModel,
    Resolver,
    load_golden,
    load_json,
    recall_at_k,
    scope_dir_for,
)

DEFAULT_GOLDEN = [
    os.path.join(HERE, "golden-queries.jsonl"),
    os.path.join(HERE, "golden-queries-short.jsonl"),
]


def chunk_text(corpus_dir, pointer):
    """The candidate's exact bytes, from the evidence pointer's span.

    03 §8.1: `byte_start`/`byte_end` are unit-local UTF-8 byte offsets, so this
    is the chunk as indexed rather than a re-derived approximation. Returns
    `None` when the unit is not on disk at this path, which is what excludes
    history results.
    """
    scope_path = pointer.get("scope_path")
    path_at_commit = pointer.get("path_at_commit")
    start = pointer.get("byte_start")
    end = pointer.get("byte_end")
    if not (scope_path and path_at_commit) or start is None or end is None:
        return None
    # `scope_path` is the absolute path of the scope's `.kio` directory, so the
    # scope root — where `path_at_commit` is relative to — is its parent.
    scope_root = os.path.dirname(scope_path.rstrip(os.sep))
    absolute = os.path.join(scope_root, path_at_commit)
    if not os.path.isfile(absolute):
        # Fall back to locating the scope under the corpus by name, which keeps
        # a dump readable after the corpus directory has been moved.
        absolute = os.path.join(corpus_dir, os.path.basename(scope_root), path_at_commit)
        if not os.path.isfile(absolute):
            return None
    try:
        with open(absolute, "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    if end > len(raw) or start > end:
        return None
    return raw[start:end].decode("utf-8", errors="strict")


def result_key(pointer):
    """The same 3-element projection `run_eval._result_keys` scores against."""
    section = pointer.get("section_id")
    return [pointer.get("raw_hash"), section, pointer.get("path_at_commit")]


def run_search(bin_path, corpus_dir, query, limit):
    cwd = scope_dir_for(corpus_dir, spec.SCOPES[0])
    command = [
        bin_path, "--json", "search", query, "--all-scopes",
        "--limit", str(limit),
    ]
    proc = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True,
        env=subprocess_env(corpus_dir))
    if proc.returncode != 0:
        return None, f"exit {proc.returncode}: {proc.stderr.strip()[:200]}"
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"unparseable response: {exc}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--bin", default="target/release/kio")
    ap.add_argument("--golden", action="append", default=None,
                    help="ゴールデンファイル (複数可)。既定は 50 問 + 短問 24 問")
    ap.add_argument("--limit", type=int, default=100,
                    help="1 クエリあたりの候補数 (CLI 上限 100)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    corpus_dir = os.path.abspath(args.corpus)
    bin_path = os.path.abspath(args.bin)
    if not os.path.exists(bin_path):
        raise SystemExit(f"[error] kio バイナリ不在: {bin_path}")

    corpus_manifest = load_json(
        os.path.join(corpus_dir, "corpus-manifest.json"), "corpus-manifest.json")
    history_manifest = load_json(
        os.path.join(corpus_dir, "history-manifest.json"), "history-manifest.json")
    CorpusModel(corpus_manifest, history_manifest)
    resolver = Resolver(corpus_manifest, history_manifest)

    golden_files = args.golden or DEFAULT_GOLDEN
    dumped, skipped = [], []
    for golden in golden_files:
        for index, query in enumerate(load_golden(golden)):
            flags = query.get("flags") or []
            if flags:
                # History queries read bytes that are no longer at
                # `path_at_commit`; see the module docstring.
                skipped.append({"query": query["query"], "reason": f"flags {flags}"})
                continue
            expected, errors = resolver.resolve_expected(query["expected"])
            if errors or not expected:
                skipped.append({"query": query["query"],
                                "reason": f"expected unresolved: {errors}"})
                continue
            response, problem = run_search(
                bin_path, corpus_dir, query["query"], args.limit)
            if problem:
                skipped.append({"query": query["query"], "reason": problem})
                continue

            candidates, missing = [], 0
            for result in response.get("results") or []:
                pointer = result.get("evidence_pointer") or {}
                text = chunk_text(corpus_dir, pointer)
                if text is None:
                    missing += 1
                    continue
                candidates.append({"key": result_key(pointer), "text": text})
            if missing:
                # Partial reconstruction would silently shrink the pool the
                # reranker sees, which is exactly the kind of quiet truncation
                # that makes a later number unattributable.
                skipped.append({"query": query["query"],
                                "reason": f"{missing} candidate(s) not reconstructible"})
                continue
            if not candidates:
                skipped.append({"query": query["query"], "reason": "no candidates"})
                continue

            dumped.append({
                "id": f"{os.path.basename(golden)}#{index}",
                "scenario": query.get("scenario"),
                "query": query["query"],
                "expected": [list(key) for key in sorted(expected)],
                "baseline_recall_at_10": recall_at_k(response, expected, k=10),
                "candidates": candidates,
            })

    payload = {
        "note": "pass 1 of the reranker differential; see eval/rerank_dump.py",
        "limit": args.limit,
        "queries": dumped,
        "skipped": skipped,
    }
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")

    baseline = (sum(q["baseline_recall_at_10"] for q in dumped) / len(dumped)) if dumped else 0.0
    total_candidates = sum(len(q["candidates"]) for q in dumped)
    print(f"dumped   : {len(dumped)} queries, {total_candidates} candidates")
    print(f"skipped  : {len(skipped)}")
    print(f"baseline : Recall@10 = {baseline:.4f}")
    print(f"out      : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
