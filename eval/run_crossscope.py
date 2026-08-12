#!/usr/bin/env python3
"""横断増補分 (eval/golden-queries-crossscope.jsonl) の専用ランナー.

09 §4.2 の凍結規律に従う**別ファイル方式** — `run_qhard.py` と同じ形である。
`eval/golden-queries.jsonl` の 50 問は digest ごと不変のまま、増補はこのファイルが
自分の digest で持つ。

## なぜ run_eval.py に相乗りしないのか

`run_eval.py` は**セット全体**の性質を 2 つ検査する。どちらも 50 問セットの契約であって、
増補の契約ではない:

- `HISTORY_QUERY_COUNT` — M3-2 / M3-3 はきっかり 16 問であること。
- `assess_history_coverage` — その run が rename 7 / edit 3 / delete 9 の**全 anchor** を
  集合として掘り起こしたこと。

増補 12 問を足せば前者は 20 になって落ち、増補だけを流せば後者が落ちる。どちらも
増補の欠陥ではなく「セット全体の検査を部分集合に当てた」だけなので、本ランナーは
**部分集合に意味のあるゲートだけ**を適用する: Recall@10 目標、レイテンシ目標、
Evidence Pointer の必須フィールド。

## このセットが測るもの

既存 50 問は**全問 expected が単一 scope に閉じている**。7 scope を `--all-scopes` で
横断するので横断ランキングそのものは通るが、「複数 scope から答えを組み立てる」形は
1 問も無かった。ここの 12 問は expected が必ず 2 scope に跨り、
`recall_at_k` が `|expected ∩ top-k| / |expected|` である以上、**両方が上位 10 件に
入らなければ 1.0 にならない** — 片方の scope の rank-1 がもう片方を押し下げる融合欠陥に
直接反応する。

正解担体は合成コーパスの anchor そのもの (`corpus_spec.ANCHORS`) であり、
コーパス・履歴・決定論には一切手を入れていない。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import corpus_spec as spec  # noqa: E402
import run_eval  # noqa: E402


def worst_expected_rank(response, expected_set, limit=50):
    """このクエリの expected のうち**最も下に沈んだもの**の 1-based 順位.

    Recall@10 は横断融合の欠陥をほぼ検出できない — 合成コーパスは小さく、各 expected は
    固有の数値を持つので、per-scope 順位でも global 順位でも 10 位以内には入る。
    実測でも replica を無効化して 16 問すべて Recall 1.000 のままだった。

    欠陥が動かすのは**順位**である: 小さな folder の rank-1 がコーパス全体の最良 hit と
    並ぶ、というのが元の症状であり、それは 1〜3 位で現れて 10 位では現れない。2 つの
    expected の**遅い方**の順位は、まさにその量を測る。ゲートではなく診断値として出す
    (合成コーパスの絶対値に閾値を置く根拠が無いため)。

    expected のいずれかが `limit` 件以内に現れない場合は None。
    """
    keys = run_eval._result_keys(response, limit)
    if not expected_set or not (expected_set <= keys):
        return None
    ordered = []
    for index in range(1, limit + 1):
        prefix = run_eval._result_keys(response, index)
        if expected_set <= prefix:
            ordered.append(index)
            break
    return ordered[0] if ordered else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--golden", default=os.path.join(HERE, "golden-queries-crossscope.jsonl"))
    ap.add_argument("--corpus", required=True,
                    help="合成コーパスディレクトリ (generate_corpus.py の出力)")
    ap.add_argument("--bin", default="target/release/kio")
    ap.add_argument("--out", default=os.path.join(HERE, "crossscope-results.json"))
    ap.add_argument("--dry-run", action="store_true",
                    help="search を叩かず expected の実在 + 解決を検証")
    args = ap.parse_args(argv)

    queries = run_eval.load_golden(args.golden)
    corpus_dir = os.path.abspath(args.corpus)
    corpus_manifest = run_eval.load_json(
        os.path.join(corpus_dir, spec.CORPUS_MANIFEST_NAME), "corpus-manifest.json")
    history_manifest = run_eval.load_json(
        os.path.join(corpus_dir, "history-manifest.json"), "history-manifest.json")
    model = run_eval.CorpusModel(corpus_manifest, history_manifest)
    resolver = run_eval.Resolver(corpus_manifest, history_manifest)
    active = [s for s in run_eval.SCENARIOS
              if any(q.get("scenario") == s for q in queries)]

    counts = {s: sum(1 for q in queries if q.get("scenario") == s)
              for s in run_eval.SCENARIOS}
    print(f"crossscope queries: {len(queries)} 件 (M3-1/M3-2/M3-3 = "
          f"{counts['M3-1']}/{counts['M3-2']}/{counts['M3-3']})")

    # 増補が増補である条件そのもの。1 scope に閉じたクエリは既存 50 問の担当であり、
    # ここに混ざれば「横断を測っている」という主張が静かに嘘になる。
    single_scope = [q["query"] for q in queries
                    if len({e["scope"] for e in q["expected"]}) < 2]
    if single_scope:
        for query in single_scope:
            print(f"[error] expected が単一 scope に閉じている: {query}", file=sys.stderr)
        return 1

    if args.dry_run:
        return run_eval.run_dry_run(queries, model, resolver, active)

    bin_path = os.path.abspath(args.bin)
    if not os.path.exists(bin_path):
        raise SystemExit(f"[error] kio バイナリ不在: {bin_path}")

    scored = {s: [] for s in active}
    latencies = {s: [] for s in active}
    rows = []
    n_failed = 0
    for q in queries:
        scenario = q["scenario"]
        expected_set, resolve_errors = resolver.resolve_expected(q["expected"])
        if resolve_errors:
            n_failed += 1
            scored[scenario].append(0.0)
            rows.append({"scenario": scenario, "query": q["query"], "status": "failed",
                         "recall_at_10": 0.0, "detail": "; ".join(resolve_errors)})
            continue
        outcome = run_eval.run_search(bin_path, corpus_dir, q["query"], q.get("flags", []))
        kind, response, error_code, detail = run_eval.classify_outcome(outcome)
        duration_ms = float(outcome.get("duration_ms", 0.0))
        latencies[scenario].append(duration_ms)
        if kind != "scored":
            n_failed += 1
            scored[scenario].append(0.0)
            rows.append({"scenario": scenario, "query": q["query"], "status": kind,
                         "recall_at_10": 0.0, "error_code": error_code, "detail": detail,
                         "duration_ms": duration_ms})
            continue
        problems = run_eval.evidence_problems(response)
        if problems:
            n_failed += 1
            scored[scenario].append(0.0)
            rows.append({"scenario": scenario, "query": q["query"], "status": "failed",
                         "recall_at_10": 0.0, "detail": "; ".join(problems),
                         "duration_ms": duration_ms})
            continue
        recall = run_eval.recall_at_k(response, expected_set, k=10)
        scored[scenario].append(recall)
        rows.append({
            "scenario": scenario, "query": q["query"], "status": "ok",
            "recall_at_10": recall, "duration_ms": duration_ms,
            "scopes": sorted({e["scope"] for e in q["expected"]}),
            "worst_expected_rank": worst_expected_rank(response, expected_set),
        })

    results = {"target_recall_at_10": run_eval.RECALL_TARGET,
               "scenarios": {}, "queries": rows,
               "counts": {"n_queries": len(queries), "n_failed": n_failed}}
    all_pass = n_failed == 0
    for scenario in active:
        values = scored[scenario]
        recall = sum(values) / len(values) if values else None
        p95 = run_eval.percentile_nearest_rank(latencies[scenario], 0.95)
        passes_target = recall is not None and recall >= run_eval.RECALL_TARGET
        passes_latency = run_eval.passes_latency_target(scenario, p95)
        results["scenarios"][scenario] = {
            "n_queries": len(values), "recall_at_10": recall, "p95_ms": p95,
            "latency_target_ms": run_eval.LATENCY_TARGET_MS[scenario],
            "passes_target": passes_target, "passes_latency": passes_latency,
        }
        if not (passes_target and passes_latency):
            all_pass = False

    ranks = [row["worst_expected_rank"] for row in rows
             if row.get("worst_expected_rank") is not None]
    results["counts"]["worst_expected_rank_mean"] = (
        sum(ranks) / len(ranks) if ranks else None)
    results["counts"]["worst_expected_rank_max"] = max(ranks) if ranks else None

    # Keep the checked-in result artifact byte-stable across Windows and POSIX.
    # The rank diagnostics are part of the artifact, not merely terminal output.
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    for scenario in active:
        summary = results["scenarios"][scenario]
        print(f"  {scenario}: Recall@10={summary['recall_at_10']:.3f} "
              f"n={summary['n_queries']} p95={summary['p95_ms']:.1f}ms "
              f"{'PASS' if summary['passes_target'] and summary['passes_latency'] else 'FAIL'}")
    if ranks:
        print(f"  worst-expected rank: mean={sum(ranks) / len(ranks):.2f} "
              f"max={max(ranks)} (診断値・ゲートではない)")
    print(f"[{'OK' if all_pass else 'NG'}] crossscope 集計完了。 results: {args.out}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
