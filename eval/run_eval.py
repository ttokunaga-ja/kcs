#!/usr/bin/env python3
"""評価ランナー (KCS 検索評価ハーネス, docs/09-mvp-scope.md §4.3).

golden-queries.jsonl を読み、`kcs search --json` を叩いて Recall@10 を
シナリオ別 (M3-1 / M3-2 / M3-3) に集計し、results.json + report.md を出力する。

判定 (docs/09 §4.3):
    Recall@10 = |expected ∩ 上位10件の distinct (raw_hash, section)| / |expected| のクエリ平均
    Done 条件 = synthetic で各シナリオ Recall@10 >= 0.8

現状 (Step 3 未実装):
    `kcs search` は未実装のため、実行部はスケルトン。search 未実装は明示メッセージで報告する。
    **--dry-run** は search を叩かず、golden-queries.jsonl の各 expected {scope, file, section}
    が生成コーパス (corpus-manifest.json) / 履歴 (history-manifest.json) に実在するかを
    検証する。整合が取れていれば green で exit 0、不整合が 1 件でもあれば exit 1。

使い方:
    # 事前: generate_corpus.py と replay_history.py を実行しておく
    python3 eval/run_eval.py --dry-run --corpus /tmp/kcs-eval-corpus
    python3 eval/run_eval.py --corpus /tmp/kcs-eval-corpus --bin target/release/kcs
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_spec as spec  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIOS = ["M3-1", "M3-2", "M3-3"]
SCENARIO_FLAG = {"M3-1": None, "M3-2": "--all-history", "M3-3": "--include-deleted"}
RECALL_TARGET = 0.8


# --------------------------------------------------------------------------- #
# 入力ロード
# --------------------------------------------------------------------------- #
def load_golden(path):
    queries = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                q = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"[error] {path}:{lineno} JSON parse: {exc}")
            queries.append(q)
    return queries


def load_json(path, label):
    if not os.path.exists(path):
        raise SystemExit(
            f"[error] {label} が見つからない: {path}\n"
            f"        先に generate_corpus.py / replay_history.py を実行すること。")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


class CorpusModel:
    """corpus-manifest.json + history-manifest.json から現行/履歴状態を再構築する."""

    def __init__(self, corpus_manifest, history_manifest):
        self.sections = {}          # (scope, file) -> set(slug)
        self.original = set()       # 生成時点の (scope, file)
        for e in corpus_manifest["files"]:
            key = (e["scope"], e["file"])
            self.original.add(key)
            self.sections[key] = {s["slug"] for s in e.get("sections", [])}

        self.renames_old = set()
        self.renames_new = set()
        self.rename_new_to_old = {}
        for r in history_manifest["renamed"]:
            old = (r["scope"], r["old_file"])
            new = (r["scope"], r["new_file"])
            self.renames_old.add(old)
            self.renames_new.add(new)
            self.rename_new_to_old[new] = old
        self.deleted = {(d["scope"], d["file"]) for d in history_manifest["deleted"]}
        self.edited = {(e["scope"], e["file"]) for e in history_manifest["edited"]}

        # 現行 working tree = 原状 - リネーム元 - 削除 + リネーム先
        self.current = (self.original - self.renames_old - self.deleted) | self.renames_new

    def sections_of(self, key):
        if key in self.sections:
            return self.sections[key]
        if key in self.rename_new_to_old:
            return self.sections.get(self.rename_new_to_old[key], set())
        return None

    def classify(self, key):
        """(scope,file) の履歴上の位置づけを返す."""
        tags = []
        if key in self.current:
            tags.append("current")
        if key in self.renames_old:
            tags.append("renamed_from")
        if key in self.edited:
            tags.append("edited")
        if key in self.deleted:
            tags.append("deleted")
        if key in self.original:
            tags.append("original")
        return tags


# --------------------------------------------------------------------------- #
# --dry-run: expected 実在チェック
# --------------------------------------------------------------------------- #
def validate_query(idx, q, model):
    problems = []
    scenario = q.get("scenario")
    flags = q.get("flags", [])
    expected = q.get("expected", [])

    if scenario not in SCENARIOS:
        problems.append(f"unknown scenario {scenario!r}")
    if not expected:
        problems.append("expected が空")

    # flags とシナリオの整合
    want_flag = SCENARIO_FLAG.get(scenario)
    if want_flag is None:
        if flags:
            problems.append(f"M3-1 は flags なしのはず (got {flags})")
    else:
        if want_flag not in flags:
            problems.append(f"{scenario} は flags に {want_flag} が必要 (got {flags})")

    for e in expected:
        scope, file_, section = e.get("scope"), e.get("file"), e.get("section")
        key = (scope, file_)
        if scope not in spec.SCOPES:
            problems.append(f"未知の scope {scope!r}")
            continue
        secs = model.sections_of(key)
        if secs is None:
            problems.append(f"file がコーパスに不在: {scope}/{file_}")
            continue
        if section not in secs:
            problems.append(
                f"section が不在: {scope}/{file_}#{section} "
                f"(有効: {sorted(secs)})")
        tags = model.classify(key)
        # シナリオ別の履歴前提
        if scenario == "M3-1":
            if "current" not in tags or "renamed_from" in tags or "deleted" in tags:
                problems.append(
                    f"M3-1 は現行 tree の file を指すべき: {scope}/{file_} tags={tags}")
        elif scenario == "M3-2":
            if not ({"renamed_from", "edited"} & set(tags)):
                problems.append(
                    f"M3-2 は履歴 (renamed_from / edited) の file を指すべき: "
                    f"{scope}/{file_} tags={tags}")
        elif scenario == "M3-3":
            if "deleted" not in tags:
                problems.append(
                    f"M3-3 は削除済み file を指すべき: {scope}/{file_} tags={tags}")
    return problems


def run_dry_run(queries, model):
    print("=== dry-run: golden-queries expected 実在チェック ===")
    per_scenario = {s: {"total": 0, "ok": 0} for s in SCENARIOS}
    n_fail = 0
    for idx, q in enumerate(queries, 1):
        sc = q.get("scenario")
        if sc in per_scenario:
            per_scenario[sc]["total"] += 1
        problems = validate_query(idx, q, model)
        if problems:
            n_fail += 1
            print(f"  [FAIL] #{idx} [{sc}] {q.get('query','')[:48]}")
            for p in problems:
                print(f"         - {p}")
        else:
            if sc in per_scenario:
                per_scenario[sc]["ok"] += 1
    print("--- シナリオ別 ---")
    for s in SCENARIOS:
        c = per_scenario[s]
        print(f"  {s}: {c['ok']}/{c['total']} queries green")
    total = len(queries)
    print(f"--- 合計 {total - n_fail}/{total} green ---")
    if n_fail:
        print(f"[NG] {n_fail} 件の不整合。golden-queries と corpus/history を確認。")
        return 1
    print("[OK] 全クエリの expected が corpus/history に実在。")
    return 0


# --------------------------------------------------------------------------- #
# 実行部 (Step 3 実装後に動く前提のスケルトン)
# --------------------------------------------------------------------------- #
def scope_dir_for(corpus_dir, scope):
    return os.path.join(corpus_dir, scope)


def run_search(bin_path, corpus_dir, query, flags):
    """kcs search --json を実行し結果 dict を返す。未実装なら status を返す."""
    # multi-scope search はデフォルト全 indexed scope 横断 (docs/05 §1.8)。
    # ここでは代表として最初の scope ディレクトリを cwd に実行する。
    cwd = scope_dir_for(corpus_dir, spec.SCOPES[0])
    cmd = [bin_path, "--json", "search", query, "--all-scopes"] + list(flags)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"_status": "error", "returncode": proc.returncode,
                "stderr": proc.stderr.strip(), "stdout": proc.stdout.strip()}
    try:
        return {"_status": "ok", "response": json.loads(proc.stdout)}
    except json.JSONDecodeError:
        return {"_status": "unparsable", "stdout": proc.stdout.strip()}


def recall_at_k(response, expected, k=10):
    """上位 k 件の distinct (raw_hash, section) と expected の一致率.

    docs/05 §1.7 の検索レスポンス schema 確定後に results[].raw_hash /
    heading_path/section_id を読む。現状はプレースホルダ (Step 3 で実装)。
    """
    results = response.get("results", [])[:k]
    hit_keys = set()
    for r in results:
        raw_hash = r.get("raw_hash")
        section = (r.get("section_id") or "/".join(r.get("heading_path", [])) or None)
        if raw_hash is not None:
            hit_keys.add((raw_hash, section))
    # expected は {scope,file,section}; raw_hash 解決はハーネスが取り込み時に行う (§4.3)。
    # search 実装後に file->raw_hash 解決を突き合わせる。現状は 0.0 を返す。
    if not expected:
        return 0.0
    return 0.0  # placeholder until kcs search + raw_hash 解決が実装される


def run_full_eval(queries, model, corpus_dir, bin_path, out_path, report_path):
    print("=== eval: kcs search 実行 (Step 3 実装後に有効) ===")
    results = {"target_recall_at_10": RECALL_TARGET, "scenarios": {}, "queries": []}
    search_unimplemented = False
    per_scenario_scores = {s: [] for s in SCENARIOS}

    for idx, q in enumerate(queries, 1):
        sc = q["scenario"]
        outcome = run_search(bin_path, corpus_dir, q["query"], q.get("flags", []))
        if outcome["_status"] == "error":
            # Step 3 未実装だと not_implemented で失敗する。
            search_unimplemented = True
            per_scenario_scores.setdefault(sc, [])
            results["queries"].append({
                "scenario": sc, "query": q["query"],
                "status": "search_unimplemented",
                "detail": outcome.get("stderr") or outcome.get("stdout"),
            })
            continue
        score = recall_at_k(outcome["response"], q["expected"], k=10)
        per_scenario_scores[sc].append(score)
        results["queries"].append({
            "scenario": sc, "query": q["query"],
            "status": "scored", "recall_at_10": score,
        })

    for s in SCENARIOS:
        scores = per_scenario_scores[s]
        avg = sum(scores) / len(scores) if scores else None
        results["scenarios"][s] = {
            "n_queries": sum(1 for q in queries if q["scenario"] == s),
            "n_scored": len(scores),
            "recall_at_10": avg,
            "passes_target": (avg is not None and avg >= RECALL_TARGET),
        }

    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    _write_report(report_path, results, search_unimplemented)

    if search_unimplemented:
        print("[note] kcs search は未実装 (Step 3)。実行部はスケルトンとして完走し、")
        print("       results.json / report.md を出力した。Recall は Step 3 実装後に有効。")
        print(f"       results: {out_path}")
        print(f"       report:  {report_path}")
        return 0
    all_pass = all(results["scenarios"][s]["passes_target"] for s in SCENARIOS)
    print(f"[{'OK' if all_pass else 'NG'}] Recall@10 集計完了。 results: {out_path}")
    return 0 if all_pass else 1


def _write_report(path, results, unimplemented):
    lines = ["# KCS 検索評価レポート (synthetic)", ""]
    lines.append(f"- 目標: 各シナリオ Recall@10 >= {RECALL_TARGET} (docs/09 §4.3)")
    if unimplemented:
        lines.append("- 状態: **kcs search 未実装 (Step 3)**。以下は実装後に有効なスケルトン。")
    lines.append("")
    lines.append("| シナリオ | クエリ数 | scored | Recall@10 | 判定 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for s in SCENARIOS:
        sc = results["scenarios"][s]
        rec = "-" if sc["recall_at_10"] is None else f"{sc['recall_at_10']:.3f}"
        verdict = "n/a" if unimplemented else ("PASS" if sc["passes_target"] else "FAIL")
        lines.append(f"| {s} | {sc['n_queries']} | {sc['n_scored']} | {rec} | {verdict} |")
    lines.append("")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description="KCS 検索評価ランナー")
    ap.add_argument("--golden", default=os.path.join(HERE, "golden-queries.jsonl"))
    ap.add_argument("--corpus", help="コーパスディレクトリ (corpus-manifest.json を含む)")
    ap.add_argument("--corpus-manifest",
                    help="corpus-manifest.json のパス (既定 <corpus>/corpus-manifest.json)")
    ap.add_argument("--history-manifest",
                    default=os.path.join(HERE, "history-manifest.json"))
    ap.add_argument("--bin", default="target/release/kcs")
    ap.add_argument("--out", default=os.path.join(HERE, "results.json"))
    ap.add_argument("--report", default=os.path.join(HERE, "report.md"))
    ap.add_argument("--dry-run", action="store_true",
                    help="search を叩かず expected の実在のみ検証")
    args = ap.parse_args(argv)

    queries = load_golden(args.golden)

    cm_path = args.corpus_manifest
    if cm_path is None:
        if not args.corpus:
            raise SystemExit("[error] --corpus か --corpus-manifest を指定すること。")
        cm_path = os.path.join(os.path.abspath(args.corpus), spec.CORPUS_MANIFEST_NAME)
    corpus_manifest = load_json(cm_path, "corpus-manifest.json")
    history_manifest = load_json(args.history_manifest, "history-manifest.json")
    model = CorpusModel(corpus_manifest, history_manifest)

    print(f"golden queries: {len(queries)} 件 "
          f"(M3-1/M3-2/M3-3 = "
          f"{sum(1 for q in queries if q['scenario']=='M3-1')}/"
          f"{sum(1 for q in queries if q['scenario']=='M3-2')}/"
          f"{sum(1 for q in queries if q['scenario']=='M3-3')})")

    if args.dry_run:
        return run_dry_run(queries, model)

    if not args.corpus:
        raise SystemExit("[error] 実行モードには --corpus が必要 (scope の cwd に使う)。")
    bin_path = os.path.abspath(args.bin)
    if not os.path.exists(bin_path):
        raise SystemExit(f"[error] kcs バイナリ不在: {bin_path}")
    return run_full_eval(queries, model, os.path.abspath(args.corpus),
                         bin_path, args.out, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
