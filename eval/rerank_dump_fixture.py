#!/usr/bin/env python3
"""Pass 1 over fixture-B — the corpus where a reranker can actually be measured.

`rerank_dump.py` targets the synthetic history corpus, which cannot pose the
question: offline runs carry no vector lane, so `fuse_rrf` sees only what FTS
matched and 24 of 25 queries come back with ten or fewer candidates. Reranking
cannot change Recall@10 when the whole result set already fits in the top ten.
`tasks/rerank-differential-plan.md` has the measurement.

This one runs against fixture-B with embeddings present, where all 24 queries
fill the 100-result cap. It is a separate file rather than a flag because the
two corpora score differently, the same reason `run_eval.py`, `run_qhard.py`
and `run_baseline.py` are separate: fixture-B matches on the result's `title`
(the ORIGINAL filename — the normalized corpus appends `.md`, and `title`
carries the name before that), against `Path(expected.path).name`. Following
`run_qhard.py` here rather than inventing a projection is deliberate; pass 1
already shipped one bug from reimplementing a scorer's key.

`rerank_apply.py` needs no change: it intersects whatever projection both sides
agree on, so a one-element `[title]` key works the same as the synthetic set's
three-element one.

Expects the fixture layout `embed_full.py` builds:

    <root>/tree/...              working copy, one scope per directory
    <root>/{h,c,d,k}             HOME and XDG_{CONFIG,DATA,CACHE}_HOME

Usage:

    python3 eval/rerank_dump_fixture.py --root /tmp/fixture-online \\
        --bin target/release/kio --out /tmp/rerank-input.json
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_GOLDEN = os.path.join(HERE, "golden-queries-fixture-b.jsonl")


def normalized_title(title):
    """The original filename, before the normalizer's `.md` suffix.

    `eval/fixtures/normalized-corpus/` stores recovered text as `<original>.md`,
    so a source `latency-review.docx` is on disk as `latency-review.docx.md`
    and `title` reports that doubled name. fixture-B's `expected` names the
    ORIGINAL (`Path(e["path"]).name`), so exactly one trailing `.md` comes off.
    """
    if title and title.endswith(".md"):
        return title[: -len(".md")]
    return title


def fixture_env(root):
    """The device environment `embed_full.py` indexed under.

    `KIO_*` is stripped for the same reason `eval_env.subprocess_env` strips it
    — a stray override from the developer shell would silently change what is
    being measured.

    **The API key must be present in the caller's environment.** Measured: the
    hundred-candidate pools this whole measurement depends on come from the
    vector lane, and the vector lane has to embed the QUERY at search time. Run
    without a key, search silently falls back to text-only and returns one
    result where it should return a hundred — which reads as a broken dump
    rather than as a missing credential.
    """
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("KIO_"):
            env.pop(name)
    env.update({
        "HOME": os.path.join(root, "h"),
        "XDG_CONFIG_HOME": os.path.join(root, "c"),
        "XDG_DATA_HOME": os.path.join(root, "d"),
        "XDG_CACHE_HOME": os.path.join(root, "k"),
    })
    return env


def first_scope(tree):
    for directory, _, files in sorted(os.walk(tree)):
        if any(os.path.isfile(os.path.join(directory, name)) for name in files):
            return directory
    raise SystemExit(f"[error] no scope found under {tree}")


def chunk_text(pointer):
    """The candidate's exact bytes, from the evidence pointer's span (03 §8.1).

    `scope_path` is the scope's `.kio` directory, so the scope root is its
    parent and `path_at_commit` is relative to that.
    """
    scope_path = pointer.get("scope_path")
    path_at_commit = pointer.get("path_at_commit")
    start, end = pointer.get("byte_start"), pointer.get("byte_end")
    if not (scope_path and path_at_commit) or start is None or end is None:
        return None
    absolute = os.path.join(os.path.dirname(scope_path.rstrip(os.sep)), path_at_commit)
    if not os.path.isfile(absolute):
        return None
    try:
        with open(absolute, "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    if start > end or start > len(raw):
        return None
    # Measured: a file's LAST chunk can carry a `byte_end` one past EOF — 3726
    # against a 3725-byte file, 607 against 606 — because the indexed unit ends
    # with a newline the file does not. Clamping to EOF recovers exactly the
    # chunk; refusing the one-byte overshoot cost 9 to 16 candidates per query
    # and, under a skip-the-query-on-any-miss rule, every query in the set.
    return raw[start:min(end, len(raw))].decode("utf-8", errors="strict")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="embed_full.py の出力ルート")
    ap.add_argument("--bin", default="target/release/kio")
    ap.add_argument("--golden", default=DEFAULT_GOLDEN)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    tree = os.path.join(root, "tree")
    bin_path = os.path.abspath(args.bin)
    if not os.path.isdir(tree):
        raise SystemExit(f"[error] fixture tree 不在: {tree}")
    if not os.path.exists(bin_path):
        raise SystemExit(f"[error] kio バイナリ不在: {bin_path}")

    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit(
            "[error] GEMINI_API_KEY absent. Without it the query cannot be "
            "embedded, search falls back to text-only, and the pools this "
            "measurement needs do not exist. See fixture_env's docstring.")
    env = fixture_env(root)
    cwd = first_scope(tree)
    golden = [json.loads(line) for line in open(args.golden, encoding="utf-8")
              if line.strip()]

    dumped, skipped = [], []
    for query in golden:
        expected = sorted({os.path.basename(e["path"]) for e in query["expected"]})
        proc = subprocess.run(
            [bin_path, "--json", "search", query["query"], "--all-scopes",
             "--limit", str(args.limit)],
            cwd=cwd, env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            skipped.append({"query_id": query["query_id"],
                            "reason": f"exit {proc.returncode}"})
            continue
        try:
            response = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            skipped.append({"query_id": query["query_id"], "reason": str(exc)})
            continue

        candidates, missing = [], 0
        for result in response.get("results") or []:
            pointer = result.get("evidence_pointer") or {}
            text = chunk_text(pointer)
            if text is None:
                missing += 1
                continue
            # `title` is the projection run_qhard.py scores on.
            candidates.append(
                {"key": [normalized_title(result.get("title"))], "text": text})
        if missing:
            skipped.append({"query_id": query["query_id"],
                            "reason": f"{missing} candidate(s) not reconstructible"})
            continue
        if not candidates:
            skipped.append({"query_id": query["query_id"], "reason": "no candidates"})
            continue

        top = {tuple(c["key"]) for c in candidates[:10]}
        want = {(name,) for name in expected}
        dumped.append({
            "id": query["query_id"],
            "scenario": query.get("class"),
            "query": query["query"],
            "expected": [[name] for name in expected],
            "baseline_recall_at_10": len(want & top) / len(want),
            "candidates": candidates,
        })

    payload = {
        "note": "pass 1 over fixture-B; see eval/rerank_dump_fixture.py",
        "limit": args.limit,
        "queries": dumped,
        "skipped": skipped,
    }
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")

    baseline = (sum(q["baseline_recall_at_10"] for q in dumped) / len(dumped)) if dumped else 0.0
    pools = sorted(len(q["candidates"]) for q in dumped)
    print(f"dumped   : {len(dumped)} queries, {sum(pools)} candidates")
    print(f"skipped  : {len(skipped)}")
    print(f"pools    : min={pools[0] if pools else 0} max={pools[-1] if pools else 0}")
    print(f"baseline : Recall@10 = {baseline:.4f}")
    print(f"out      : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
