#!/usr/bin/env python3
"""評価ランナー (KCS 検索評価ハーネス, docs/09-mvp-scope.md §4.3).

golden-queries.jsonl を読み、`kcs search --json` を叩いて Recall@10 を
シナリオ別 (M3-1 / M3-2 / M3-3) に集計し、results.json + report.md を出力する。

判定 (docs/09 §4.3):
    Recall@10 = |expected ∩ 上位10件の distinct (raw_hash, section_id)| / |expected| のクエリ平均
    Done 条件 = synthetic で各シナリオ Recall@10 >= 0.8

解決層 (2026-07-03 J2 裁定):
    golden-queries の expected.section は英語ニーモニック (例 "recall") であり、
    実 section_id ではない。実 section_id は docs/04 §4.1 の slug 規則で
    「見出しテキスト」から導く (例: 見出し「回収率と精度」→ section_id "回収率と精度")。
    ハーネスは corpus_spec の anchor 定義 (ニーモニック ↔ 見出し ↔ ファイル) を
    corpus-manifest.json / history-manifest.json 経由で参照し、
      expected {scope, file, section(ニーモニック)}
        -> (raw_hash="sha256:"+raw_sha256, section_id=slugify(heading))
    に解決する。raw_sha256 は corpus/history manifest がファイル bytes から記録する。

exit コード (2026-07-03 J2 裁定):
    - `KCS-E-*-NOT-IMPLEMENTED*` 系 error_code のクエリ: unimplemented (採点対象外)。
      1 件でもあれば最終 exit 2 (未実装状態を green にしない)。
    - exit 3 (部分成功): stdout の JSON を parse して採点対象。
    - その他の非 0 exit: 当該クエリ fail (recall 0)。scored 集合に 0.0 を加える。
      → 最終 exit 1 (実バグを隠さない)。
    - 全シナリオ target 達成: exit 0。

--dry-run:
    search を叩かず、golden-queries の各 expected {scope, file, section} が
    corpus-manifest.json / history-manifest.json に実在し、かつ
    (raw_hash, section_id) へ解決できる (slugify が空にならない) ことを検証する。
    全て green で exit 0、不整合が 1 件でもあれば exit 1。

使い方:
    # 事前: generate_corpus.py と replay_history.py を実行しておく
    python3 eval/run_eval.py --dry-run --corpus /tmp/kcs-eval-corpus
    python3 eval/run_eval.py --corpus /tmp/kcs-eval-corpus --bin target/release/kcs
    python3 eval/run_eval.py --scenario M3-1 --corpus /tmp/kcs-eval-corpus --bin target/release/kcs
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_spec as spec  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIOS = ["M3-1", "M3-2", "M3-3"]
SCENARIO_FLAG = {"M3-1": None, "M3-2": "--all-history", "M3-3": "--include-deleted"}
RECALL_TARGET = 0.8


# --------------------------------------------------------------------------- #
# slug (docs/04-pipeline.md §4.1)
# --------------------------------------------------------------------------- #
# 許可: 英数字 (ASCII) / ハイフン / アンダースコア / 日本語文字。それ以外を除去。
# 日本語文字 = ひらがな (U+3040-309F) / カタカナ (U+30A0-30FF) / 漢字 (U+4E00-9FFF)。
# 非 raw 文字列にして \u を Python 側で実文字へ展開する (末尾 "-" は literal)。
_DISALLOWED_RE = re.compile(
    "[^0-9A-Za-z_぀-ゟ゠-ヿ一-鿿-]")


def slugify(text):
    """docs/04-pipeline.md §4.1 の slug 規則をそのまま実装する。

    NFC 正規化 → ASCII 英字を小文字化 → 空白列を "-" に →
    英数字・ハイフン・アンダースコア・日本語文字以外を除去 →
    連続 "-" を 1 つに → 先頭末尾の "-" を除去。

    heading_path 要素 1 つ分の slug を返す (section_id は要素 slug を "/" 連結したもの)。
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFC", text)
    # ASCII 英字のみ小文字化 (日本語などケースを持たない文字はそのまま)。
    s = "".join(c.lower() if "A" <= c <= "Z" else c for c in s)
    s = re.sub(r"\s+", "-", s)
    s = _DISALLOWED_RE.sub("", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


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
# 解決層: expected {scope, file, section(ニーモニック)} -> (raw_hash, section_id)
# --------------------------------------------------------------------------- #
class ResolveError(Exception):
    pass


class Resolver:
    """corpus/history manifest の anchor 情報から expected を (raw_hash, section_id) へ解決する.

    - raw_sha256: ファイル bytes の sha256 (manifest が記録)。raw_hash = "sha256:"+raw_sha256。
    - heading: ニーモニック slug -> 実見出しテキスト (manifest の sections が記録)。
    - section_id: slugify(heading) (docs/04 §4.1)。
    history manifest が持つ「旧内容」を優先 (M3-2 編集/リネーム・M3-3 削除が指すのは旧版のため)。
    """

    def __init__(self, corpus_manifest, history_manifest):
        # (scope, file) -> {"raw_sha256": str|None, "sections": {slug: heading}}
        self.by_key = {}
        for e in corpus_manifest.get("files", []):
            if not e.get("anchor"):
                continue
            self.by_key[(e["scope"], e["file"])] = {
                "raw_sha256": e.get("raw_sha256"),
                "sections": {s["slug"]: s.get("heading") for s in e.get("sections", [])},
            }
        for r in history_manifest.get("renamed", []):
            self._overlay((r["scope"], r["old_file"]), r)
        for e in history_manifest.get("edited", []):
            self._overlay((e["scope"], e["file"]), e)
        for d in history_manifest.get("deleted", []):
            self._overlay((d["scope"], d["file"]), d)

    def _overlay(self, key, entry):
        secs = {s["slug"]: s.get("heading") for s in entry.get("sections", [])}
        raw = entry.get("raw_sha256")
        cur = self.by_key.get(key, {})
        if raw or secs:
            self.by_key[key] = {
                "raw_sha256": raw or cur.get("raw_sha256"),
                "sections": secs or cur.get("sections", {}),
            }

    def resolve_one(self, scope, file_, mnemonic):
        """(raw_hash, section_id) を返す。解決不能なら ResolveError."""
        info = self.by_key.get((scope, file_))
        if info is None:
            raise ResolveError(f"file が anchor manifest に不在: {scope}/{file_}")
        raw = info.get("raw_sha256")
        if not raw:
            raise ResolveError(f"raw_sha256 未記録: {scope}/{file_}")
        headings = info.get("sections", {})
        if mnemonic not in headings or not headings.get(mnemonic):
            raise ResolveError(
                f"section ニーモニック {mnemonic!r} の見出しが解決不能: "
                f"{scope}/{file_} (有効: {sorted(headings)})")
        section_id = slugify(headings[mnemonic])
        if not section_id:
            raise ResolveError(
                f"slugify(heading={headings[mnemonic]!r}) が空: "
                f"{scope}/{file_}#{mnemonic}")
        return ("sha256:" + raw, section_id)

    def resolve_expected(self, expected):
        """(resolved_set, errors) を返す。resolved_set は {(raw_hash, section_id)}."""
        resolved = set()
        errors = []
        for e in expected:
            try:
                resolved.add(self.resolve_one(
                    e.get("scope"), e.get("file"), e.get("section")))
            except ResolveError as exc:
                errors.append(str(exc))
        return resolved, errors


# --------------------------------------------------------------------------- #
# --dry-run: expected 実在チェック + 解決検証
# --------------------------------------------------------------------------- #
def validate_query(q, model, resolver):
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

    # 解決検証: (raw_hash, section_id) に解決できること (slugify が空でないこと含む)。
    _, resolve_errors = resolver.resolve_expected(expected)
    problems.extend(resolve_errors)
    return problems


def run_dry_run(queries, model, resolver, active):
    print("=== dry-run: golden-queries expected 実在 + 解決チェック ===")
    per_scenario = {s: {"total": 0, "ok": 0} for s in active}
    n_fail = 0
    for idx, q in enumerate(queries, 1):
        sc = q.get("scenario")
        if sc in per_scenario:
            per_scenario[sc]["total"] += 1
        problems = validate_query(q, model, resolver)
        if problems:
            n_fail += 1
            print(f"  [FAIL] #{idx} [{sc}] {q.get('query', '')[:48]}")
            for p in problems:
                print(f"         - {p}")
        else:
            if sc in per_scenario:
                per_scenario[sc]["ok"] += 1
    print("--- シナリオ別 ---")
    for s in active:
        c = per_scenario[s]
        print(f"  {s}: {c['ok']}/{c['total']} queries green")
    total = len(queries)
    print(f"--- 合計 {total - n_fail}/{total} green ---")
    if n_fail:
        print(f"[NG] {n_fail} 件の不整合。golden-queries と corpus/history/解決層を確認。")
        return 1
    print("[OK] 全クエリの expected が corpus/history に実在し (raw_hash, section_id) へ解決可能。")
    return 0


# --------------------------------------------------------------------------- #
# 実行部
# --------------------------------------------------------------------------- #
def scope_dir_for(corpus_dir, scope):
    return os.path.join(corpus_dir, scope)


def run_search(bin_path, corpus_dir, query, flags):
    """kcs search --json を実行し returncode/stdout/stderr をそのまま返す."""
    # multi-scope search はデフォルト全 indexed scope 横断 (docs/05 §1.8)。
    # ここでは代表として最初の scope ディレクトリを cwd に実行する。
    cwd = scope_dir_for(corpus_dir, spec.SCOPES[0])
    cmd = [bin_path, "--json", "search", query, "--all-scopes"] + list(flags)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return {"returncode": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


def _parse_json(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _is_not_implemented(error_code):
    return bool(error_code) and error_code.startswith("KCS-E-") \
        and "NOT-IMPLEMENTED" in error_code


def classify_outcome(outcome):
    """search 実行結果を分類する.

    返り値 (kind, response, error_code, detail):
      - kind="unimplemented": NOT-IMPLEMENTED 系 error_code (採点対象外)
      - kind="scored":        exit 0 / exit 3 で stdout が JSON (採点対象)
      - kind="fail":          その他の非 0 exit、または JSON 不正 (recall 0)
    """
    rc = outcome["returncode"]
    stdout_json = _parse_json(outcome["stdout"])
    stderr_json = _parse_json(outcome["stderr"])
    # error_code は stdout レスポンス (05 §1.7) か stderr エラー JSON のいずれかに載る。
    error_code = None
    for j in (stdout_json, stderr_json):
        if isinstance(j, dict) and j.get("error_code"):
            error_code = j["error_code"]
            break

    if _is_not_implemented(error_code):
        return ("unimplemented", None, error_code, "search 未実装 (NOT-IMPLEMENTED)")

    if rc == 0:
        if isinstance(stdout_json, dict):
            return ("scored", stdout_json, error_code, None)
        return ("fail", None, error_code, "exit 0 だが stdout が JSON レスポンスでない")

    if rc == 3:  # 部分成功: stdout の JSON を採点
        if isinstance(stdout_json, dict):
            return ("scored", stdout_json, error_code, "partial(exit 3)")
        return ("fail", None, error_code, "exit 3 だが stdout が JSON レスポンスでない")

    # その他の非 0 exit → 実バグ扱い (recall 0)。
    detail = None
    if isinstance(stderr_json, dict):
        detail = stderr_json.get("message")
    detail = detail or (outcome["stderr"].strip() or outcome["stdout"].strip())
    return ("fail", None, error_code, f"exit={rc}: {detail}")


def _pointer_section(pointer):
    """evidence_pointer から突き合わせ用の section 識別子を取り出す.

    docs/08 §2 の section_id は heading_path の各 slug を "/" 連結したものだが、
    J2 裁定に従い最深 (leaf) 見出しの slug を突き合わせ単位とする
    (見出し「回収率と精度」→ "回収率と精度")。pointer が section_id を持てば
    最後の "/" セグメント、無ければ heading_path 末尾を slugify する。
    """
    sid = pointer.get("section_id")
    if sid:
        return sid.split("/")[-1]
    hp = pointer.get("heading_path")
    if hp:
        return slugify(hp[-1])
    return None


def _result_keys(response, k):
    """上位 k 件の distinct (raw_hash, section) を返す (docs/05 §1.7 / 08 §2)."""
    keys = set()
    for r in (response.get("results") or [])[:k]:
        pointer = r.get("evidence_pointer") or {}
        raw_hash = pointer.get("raw_hash")
        if not raw_hash:
            continue
        keys.add((raw_hash, _pointer_section(pointer)))
    return keys


def recall_at_k(response, expected_set, k=10):
    """Recall@k = |expected ∩ 上位 k 件の distinct (raw_hash, section)| / |expected|.

    expected_set は解決済み {(raw_hash, section_id)}。
    """
    if not expected_set:
        return 0.0
    got = _result_keys(response, k)
    return len(expected_set & got) / len(expected_set)


def run_full_eval(queries, resolver, corpus_dir, bin_path, out_path, report_path,
                  active):
    print("=== eval: kcs search 実行 + Recall@10 集計 ===")
    results = {"target_recall_at_10": RECALL_TARGET, "scenarios": {}, "queries": []}
    per_scenario_scores = {s: [] for s in active}
    n_unimplemented = 0
    n_failed = 0

    for q in queries:
        sc = q["scenario"]
        expected_set, resolve_errors = resolver.resolve_expected(q["expected"])
        outcome = run_search(bin_path, corpus_dir, q["query"], q.get("flags", []))
        kind, response, error_code, detail = classify_outcome(outcome)

        if kind == "unimplemented":
            n_unimplemented += 1
            results["queries"].append({
                "scenario": sc, "query": q["query"], "status": "unimplemented",
                "error_code": error_code, "detail": detail,
            })
            continue

        if resolve_errors:
            # 解決不能は採点不能 → fail 扱い (recall 0) にして表面化させる。
            kind, detail = "fail", "; ".join(resolve_errors)

        if kind == "fail":
            n_failed += 1
            per_scenario_scores.setdefault(sc, []).append(0.0)
            results["queries"].append({
                "scenario": sc, "query": q["query"], "status": "failed",
                "recall_at_10": 0.0, "error_code": error_code, "detail": detail,
            })
            continue

        score = recall_at_k(response, expected_set, k=10)
        per_scenario_scores.setdefault(sc, []).append(score)
        results["queries"].append({
            "scenario": sc, "query": q["query"], "status": "scored",
            "recall_at_10": score,
            **({"detail": detail} if detail else {}),
        })

    for s in active:
        scores = per_scenario_scores.get(s, [])
        avg = sum(scores) / len(scores) if scores else None
        results["scenarios"][s] = {
            "n_queries": sum(1 for q in queries if q["scenario"] == s),
            "n_scored": len(scores),
            "recall_at_10": avg,
            "passes_target": (avg is not None and avg >= RECALL_TARGET),
        }

    results["counts"] = {
        "n_queries": len(queries),
        "n_unimplemented": n_unimplemented,
        "n_failed": n_failed,
        "n_scored": sum(len(v) for v in per_scenario_scores.values()),
    }

    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    _write_report(report_path, results, active)

    # exit コード判定 (J2 裁定)。
    if n_unimplemented > 0:
        print(f"[note] kcs search が未実装のクエリが {n_unimplemented} 件 "
              f"(NOT-IMPLEMENTED)。Recall 判定は未実装のため無効。")
        print(f"       results: {out_path}")
        print(f"       report:  {report_path}")
        return 2

    all_pass = (n_failed == 0)
    for s in active:
        scv = results["scenarios"][s]
        if scv["n_scored"] == 0 or not scv["passes_target"]:
            all_pass = False
    verdict = "OK" if all_pass else "NG"
    if n_failed:
        print(f"[note] 実行失敗 (非 0 exit / 不正レスポンス / 解決不能) が {n_failed} 件。")
    print(f"[{verdict}] Recall@10 集計完了。 results: {out_path}")
    return 0 if all_pass else 1


def _write_report(path, results, active):
    counts = results.get("counts", {})
    lines = ["# KCS 検索評価レポート (synthetic)", ""]
    lines.append(f"- 目標: 各シナリオ Recall@10 >= {RECALL_TARGET} (docs/09 §4.3)")
    lines.append(f"- クエリ数: {counts.get('n_queries', 0)} "
                 f"(scored={counts.get('n_scored', 0)} / "
                 f"failed={counts.get('n_failed', 0)} / "
                 f"unimplemented={counts.get('n_unimplemented', 0)})")
    if counts.get("n_unimplemented", 0) > 0:
        lines.append("- 状態: **kcs search 未実装のクエリあり (NOT-IMPLEMENTED)**。"
                     "Recall 判定は無効 (exit 2)。")
    lines.append("")
    lines.append("| シナリオ | クエリ数 | scored | Recall@10 | 判定 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for s in active:
        sc = results["scenarios"][s]
        rec = "-" if sc["recall_at_10"] is None else f"{sc['recall_at_10']:.3f}"
        if sc["n_scored"] == 0:
            verdict = "n/a"
        else:
            verdict = "PASS" if sc["passes_target"] else "FAIL"
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
    ap.add_argument("--scenario", action="append", choices=SCENARIOS, default=None,
                    help="対象シナリオ (複数指定可。既定は全シナリオ)")
    ap.add_argument("--dry-run", action="store_true",
                    help="search を叩かず expected の実在 + 解決を検証")
    args = ap.parse_args(argv)

    queries = load_golden(args.golden)

    # --scenario フィルタ (複数可)。既定は全シナリオ。
    if args.scenario:
        wanted = set(args.scenario)
        queries = [q for q in queries if q.get("scenario") in wanted]
        if not queries:
            raise SystemExit(f"[error] --scenario {sorted(wanted)} に該当するクエリが無い。")

    cm_path = args.corpus_manifest
    if cm_path is None:
        if not args.corpus:
            raise SystemExit("[error] --corpus か --corpus-manifest を指定すること。")
        cm_path = os.path.join(os.path.abspath(args.corpus), spec.CORPUS_MANIFEST_NAME)
    corpus_manifest = load_json(cm_path, "corpus-manifest.json")
    history_manifest = load_json(args.history_manifest, "history-manifest.json")
    model = CorpusModel(corpus_manifest, history_manifest)
    resolver = Resolver(corpus_manifest, history_manifest)

    active = [s for s in SCENARIOS if any(q.get("scenario") == s for q in queries)]

    counts = {s: sum(1 for q in queries if q.get("scenario") == s) for s in SCENARIOS}
    print(f"golden queries: {len(queries)} 件 "
          f"(M3-1/M3-2/M3-3 = {counts['M3-1']}/{counts['M3-2']}/{counts['M3-3']})")

    if args.dry_run:
        return run_dry_run(queries, model, resolver, active)

    if not args.corpus:
        raise SystemExit("[error] 実行モードには --corpus が必要 (scope の cwd に使う)。")
    bin_path = os.path.abspath(args.bin)
    if not os.path.exists(bin_path):
        raise SystemExit(f"[error] kcs バイナリ不在: {bin_path}")
    return run_full_eval(queries, resolver, os.path.abspath(args.corpus),
                         bin_path, args.out, args.report, active)


if __name__ == "__main__":
    raise SystemExit(main())
