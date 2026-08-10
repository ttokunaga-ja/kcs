#!/usr/bin/env python3
"""Pass 3 of the reranker differential: score the reordering.

Reads `rerank_dump.py`'s input file and the GPU box's output, applies the new
order, and reports Recall@10 before and after. Nothing here talks to a model or
to `kio` — it is arithmetic over two frozen files, so the number can be
recomputed by anyone holding them.

## The output format this expects

    {
      "model": "<what actually served, e.g. BAAI/bge-reranker-v2-m3>",
      "queries": [
        {"id": "<the dump's query id>", "ranking": [<candidate index>, ...]}
      ]
    }

`ranking` holds indices into that query's `candidates` array **in the dump**,
best first. Indices rather than ids or text: the dump is the authority on what
was offered, so an index that is out of range or repeated is a detectable
error rather than something to reconcile. A query the output omits keeps its
original order and is reported as `unranked`, never silently scored as if it
had been reranked.

## What this measures, and what it does not

Recall@10 over the same 3-element projection `run_eval.py` scores
(`raw_hash`, `section_id`, `path_at_commit`). It is a lower bound on what an
integrated reranker could do: the dump sees at most the CLI's 100-result cap
while 05 §1.3's `candidate_depth` is 200.

It says nothing about latency, and nothing about the configuration a user
actually runs unless the dump was taken from one. A dump taken with mock
embeddings fills pools with arbitrary candidates, which flatters a reranker —
see `tasks/rerank-differential-plan.md` §2.5.

Usage:

    python3 eval/rerank_apply.py --input /tmp/rerank-input.json \\
        --output /tmp/rerank-output.json
"""

import argparse
import json


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def recall_at_10(keys, expected):
    """Same projection and formula as `run_eval.recall_at_k`."""
    if not expected:
        return 0.0
    top = {tuple(key) for key in keys[:10]}
    return len(expected & top) / len(expected)


def reorder(candidates, ranking):
    """Apply `ranking`, then append anything it left out, order preserved.

    A reranker that returns `top_n` shorter than the pool has not rejected the
    rest — it just stopped ranking. Dropping the tail would score a truncation
    as if it were a judgement.
    """
    seen = set()
    ordered = []
    for index in ranking:
        if not isinstance(index, int) or not 0 <= index < len(candidates):
            raise ValueError(f"ranking index {index!r} is not a candidate")
        if index in seen:
            raise ValueError(f"ranking repeats index {index}")
        seen.add(index)
        ordered.append(candidates[index])
    ordered.extend(c for i, c in enumerate(candidates) if i not in seen)
    return ordered


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="rerank_dump.py の出力")
    ap.add_argument("--output", required=True, help="GPU 機の出力")
    ap.add_argument("--report", default=None, help="per-query の表を書き出す先")
    args = ap.parse_args(argv)

    dump = load(args.input)
    result = load(args.output)
    ranked = {entry["id"]: entry.get("ranking") or []
              for entry in result.get("queries") or []}

    rows, problems = [], []
    for query in dump.get("queries") or []:
        expected = {tuple(key) for key in query["expected"]}
        candidates = query["candidates"]
        before = recall_at_10([c["key"] for c in candidates], expected)
        ranking = ranked.get(query["id"])
        if ranking is None:
            problems.append(f"{query['id']}: absent from the rerank output")
            after, state = before, "unranked"
        else:
            try:
                after = recall_at_10(
                    [c["key"] for c in reorder(candidates, ranking)], expected)
                state = "ranked"
            except ValueError as exc:
                problems.append(f"{query['id']}: {exc}")
                after, state = before, "invalid"
        rows.append({
            "id": query["id"],
            "query": query["query"],
            "candidates": len(candidates),
            "before": before,
            "after": after,
            "state": state,
        })

    if not rows:
        raise SystemExit("[error] 入力に採点できるクエリが無い。")

    scored = [row for row in rows if row["state"] == "ranked"]
    before = sum(row["before"] for row in rows) / len(rows)
    after = sum(row["after"] for row in rows) / len(rows)
    improved = sum(1 for row in rows if row["after"] > row["before"])
    worsened = sum(1 for row in rows if row["after"] < row["before"])

    print(f"model     : {result.get('model', '(unrecorded)')}")
    print(f"queries   : {len(rows)} ({len(scored)} ranked)")
    print(f"Recall@10 : {before:.4f} -> {after:.4f}  ({after - before:+.4f})")
    print(f"improved  : {improved}   worsened: {worsened}")
    if worsened:
        print("  worsened queries:")
        for row in rows:
            if row["after"] < row["before"]:
                print(f"    {row['before']:.2f} -> {row['after']:.2f}  {row['query'][:48]}")
    for problem in problems:
        print(f"[warn] {problem}")

    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"summary": {"before": before, "after": after,
                                   "improved": improved, "worsened": worsened,
                                   "model": result.get("model")},
                       "queries": rows, "problems": problems},
                      handle, ensure_ascii=False, indent=1, sort_keys=True)
            handle.write("\n")
        print(f"report    : {args.report}")

    # A differential that could not rank anything is not a pass.
    return 0 if scored and not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
