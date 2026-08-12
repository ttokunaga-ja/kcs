#!/usr/bin/env python3
"""評価ランナー (Kio 検索評価ハーネス, docs/09-mvp-scope.md §4.3).

golden-queries.jsonl を読み、`kio search --json` を叩いて Recall@10 を
シナリオ別 (M3-1 / M3-2 / M3-3) に集計し、results.json + report.md を出力する。

判定 (docs/09 §4.3、射影は step4b-contract-tests-p3b.md QB24/裁定4 で 3 要素化):
    Recall@10 = |expected ∩ 上位10件の distinct (raw_hash, section, path_at_commit)|
                / |expected| のクエリ平均
    Done 条件 = synthetic で各シナリオ Recall@10 >= 0.8
    旧射影 (raw_hash, section) のみだと、リネーム前後で raw_hash・section が
    同一のチャンクが 1 要素に畳み込まれ、M3-2 (--all-history) がリネーム前後
    どちらの版を実際に recall したかを区別できない。path_at_commit を加えた
    3 要素射影はリネーム前後を別要素として数える。

解決層 (2026-07-03 J2 裁定、2026-07-22 QB24 拡張):
    golden-queries の expected.section は英語ニーモニック (例 "recall") であり、
    実 section_id ではない。実 section_id は docs/04 §4.1 の slug 規則で
    「見出しテキスト」から導く (例: 見出し「回収率と精度」→ section_id "回収率と精度")。
    ハーネスは corpus_spec の anchor 定義 (ニーモニック ↔ 見出し ↔ ファイル) を
    corpus-manifest.json / history-manifest.json 経由で参照し、
      expected {scope, file, section(ニーモニック)}
        -> (raw_hash="sha256:"+raw_sha256, section_id=slugify(heading),
            path_at_commit=file)
    に解決する。raw_sha256 は corpus/history manifest がファイル bytes から記録する。
    path_at_commit は expected.file そのもの (スコープ相対パス、Kio の
    evidence_pointer.path_at_commit と同じ空間)。

exit コード (2026-07-03 J2 裁定):
    - `KIO-E-*-NOT-IMPLEMENTED*` 系 error_code のクエリ: unimplemented (採点対象外)。
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
    python3 eval/run_eval.py --dry-run --corpus /tmp/kio-eval-corpus
    python3 eval/run_eval.py --corpus /tmp/kio-eval-corpus --bin target/release/kio
    python3 eval/run_eval.py --scenario M3-1 --corpus /tmp/kio-eval-corpus --bin target/release/kio
"""

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_spec as spec  # noqa: E402
from eval_env import subprocess_env  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIOS = ["M3-1", "M3-2", "M3-3"]
SCENARIO_FLAG = {"M3-1": None, "M3-2": "--all-history", "M3-3": "--include-deleted"}
RECALL_TARGET = 0.8
LATENCY_TARGET_MS = {"M3-1": 5_000.0, "M3-2": 7_000.0, "M3-3": 7_000.0}
HISTORY_QUERY_COUNT = 16
REQUIRED_POINTER_FIELDS = {
    "schema_version", "commit", "raw_hash", "tool_profile_hash", "chunk_hash", "scope_id",
}
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_COMMIT_OBJECT_BYTES = 1024 * 1024
MAX_TREE_OBJECT_BYTES = 16 * 1024 * 1024
MAX_CHUNK_OBJECT_BYTES = 128 * 1024 * 1024
MAX_TREE_ENTRIES = 10_000
MAX_POINTER_ATTESTATIONS_PER_QUERY = 10
MAX_POINTER_ATTESTATION_BYTES = 512 * 1024 * 1024
# Kio's machine-readable stdout/stderr is UTF-8 on every platform.  Leaving
# `text=True` to choose the host locale makes a Japanese JSON response fail to
# decode under a Windows cp932 Python process before the evaluator can score it.
KIO_SUBPROCESS_TEXT = {"text": True, "encoding": "utf-8", "errors": "strict"}


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


def _history_anchor(scope, file_name):
    return next((anchor for anchor in spec.ANCHORS
                 if anchor["scope"] == scope and anchor["file"] == file_name), None)


def _expected_history_messages(scope):
    """Exact newest-first log messages emitted by replay_history.py for one scope."""
    messages = []
    deletes = [item for item in spec.HISTORY["deletes"] if item["scope"] == scope]
    if deletes:
        messages.extend([
            "delete: " + ", ".join(item["file"] for item in deletes),
            "kio index auto snapshot",
        ])
    renames = [item for item in spec.HISTORY["renames"] if item["scope"] == scope]
    if renames:
        messages.extend([
            "rename: " + ", ".join(
                f"{item['old_file']}->{item['new_file']}" for item in renames),
            "kio index auto snapshot",
        ])
    edits = [item for item in spec.HISTORY["edits"] if item["scope"] == scope]
    if edits:
        messages.extend([
            "edit: " + ", ".join(item["file"] for item in edits),
            "kio index auto snapshot",
        ])
    messages.extend(["baseline", "kio index auto snapshot"])
    return messages


def validate_history_manifest(history_manifest):
    """Reject a missing/stale replay manifest before it can authorize scoring."""
    problems = []
    if history_manifest.get("replay") != "eval/replay_history.py":
        problems.append("replay identity mismatch")
    if history_manifest.get("seed") != spec.SEED:
        problems.append("history seed mismatch")
    if history_manifest.get("scopes") != spec.SCOPES:
        problems.append("history scope order/set mismatch")

    def identities(items, fields):
        return [tuple(item.get(field) for field in fields) for item in items]

    operation_specs = (
        ("renamed", spec.HISTORY["renames"], ("scope", "old_file", "new_file")),
        ("edited", spec.HISTORY["edits"], ("scope", "file", "old_value", "new_value")),
        ("deleted", spec.HISTORY["deletes"], ("scope", "file")),
    )
    for manifest_key, expected, fields in operation_specs:
        actual = history_manifest.get(manifest_key)
        if not isinstance(actual, list) or identities(actual, fields) != identities(expected, fields):
            problems.append(f"history {manifest_key} operations mismatch")
            continue
        file_field = "old_file" if manifest_key == "renamed" else "file"
        for entry in actual:
            anchor = _history_anchor(entry["scope"], entry[file_field])
            if anchor is None:
                problems.append(f"history {manifest_key} anchor mismatch")
                continue
            expected_hash = hashlib.sha256(
                spec.render_anchor(anchor).encode("utf-8")).hexdigest()
            if entry.get("raw_sha256") != expected_hash:
                problems.append(
                    f"history {manifest_key} raw_sha256 mismatch: "
                    f"{entry['scope']}/{entry[file_field]}")
            expected_sections = [
                {"slug": section["slug"], "heading": section["heading"]}
                for section in anchor["sections"]
            ]
            if entry.get("sections") != expected_sections:
                problems.append(
                    f"history {manifest_key} sections mismatch: "
                    f"{entry['scope']}/{entry[file_field]}")

    verified = history_manifest.get("verified")
    if not isinstance(verified, dict) or set(verified) != set(spec.SCOPES):
        problems.append("history verified scope set mismatch")
        return problems
    for scope in spec.SCOPES:
        expected_steps = ["baseline"]
        if any(item["scope"] == scope for item in spec.HISTORY["edits"]):
            expected_steps.append("edit")
        if any(item["scope"] == scope for item in spec.HISTORY["renames"]):
            expected_steps.append("rename")
        if any(item["scope"] == scope for item in spec.HISTORY["deletes"]):
            expected_steps.append("delete")
        record = verified.get(scope) or {}
        if record.get("steps") != expected_steps:
            problems.append(f"history verified steps mismatch: {scope}")
        if record.get("commit_count") != 2 * len(expected_steps):
            problems.append(f"history verified commit_count mismatch: {scope}")
        if record.get("messages") != _expected_history_messages(scope):
            problems.append(f"history verified messages mismatch: {scope}")
    return problems


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
        """(raw_hash, section_id, path_at_commit) を返す。解決不能なら ResolveError.

        U142 (step4b-contract-tests-p3b.md QB24, 裁定4): 射影キーに
        `path_at_commit` (= 解決元の `file_`、リネーム前後で別要素になる
        スコープ相対パス) を含める。旧 2 要素射影 (raw_hash, section_id) は
        リネーム前後で同一 raw_hash・同一 section のチャンクを 1 要素に
        畳み込み、M3-2 (--all-history) がリネーム前後どちらの版を実際に
        recall したかを区別できなかった。
        """
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
        return ("sha256:" + raw, section_id, file_)

    def resolve_expected(self, expected):
        """(resolved_set, errors) を返す。

        resolved_set は {(raw_hash, section_id, path_at_commit)}
        (QB24/裁定4: 3 要素射影)。
        """
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
    """kio search --json を実行し returncode/stdout/stderr をそのまま返す."""
    # multi-scope search はデフォルト全 indexed scope 横断 (docs/05 §1.8)。
    # ここでは代表として最初の scope ディレクトリを cwd に実行する。
    cwd = scope_dir_for(corpus_dir, spec.SCOPES[0])
    cmd = [bin_path, "--json", "search", query, "--all-scopes"] + list(flags)
    started = time.monotonic()
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True,
        **KIO_SUBPROCESS_TEXT,
        env=subprocess_env(corpus_dir))
    duration_ms = (time.monotonic() - started) * 1000.0
    return {"returncode": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr,
            "duration_ms": duration_ms}


def validate_replayed_history(bin_path, corpus_dir, history_manifest):
    """Compare the live CAS-backed log shape with the replay manifest."""
    problems = []
    for scope in spec.SCOPES:
        cwd = scope_dir_for(corpus_dir, scope)
        proc = subprocess.run(
            [bin_path, "--json", "log"], cwd=cwd, capture_output=True,
            **KIO_SUBPROCESS_TEXT, env=subprocess_env(corpus_dir))
        response = _parse_json(proc.stdout)
        if proc.returncode != 0 or not isinstance(response, dict):
            problems.append(f"history log unavailable: {scope}")
            continue
        commits = response.get("commits") or []
        expected = history_manifest["verified"][scope]
        messages = [commit.get("message") for commit in commits]
        if len(commits) != expected["commit_count"] or messages != expected["messages"]:
            problems.append(f"history log is stale: {scope}")
    return problems


def _parse_json(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _is_not_implemented(error_code):
    return bool(error_code) and error_code.startswith("KIO-E-") \
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
    """上位 k 件の distinct (raw_hash, section, path_at_commit) を返す
    (docs/05 §1.7 / 08 §2、射影は QB24/裁定4 で 3 要素化 — リネーム前後を
    別要素として数える)。
    """
    keys = set()
    for r in (response.get("results") or [])[:k]:
        pointer = r.get("evidence_pointer") or {}
        raw_hash = pointer.get("raw_hash")
        if not raw_hash:
            continue
        keys.add((raw_hash, _pointer_section(pointer), pointer.get("path_at_commit")))
    return keys


def recall_at_k(response, expected_set, k=10):
    """Recall@k = |expected ∩ 上位 k 件の distinct (raw_hash, section, path_at_commit)|
    / |expected|.

    expected_set は解決済み {(raw_hash, section_id, path_at_commit)}
    (QB24/裁定4: 3 要素射影)。
    """
    if not expected_set:
        return 0.0
    got = _result_keys(response, k)
    return len(expected_set & got) / len(expected_set)


def evidence_problems(response):
    """Validate required Evidence fields for every returned scored hit."""
    problems = []
    for index, result in enumerate(response.get("results") or []):
        pointer = result.get("evidence_pointer")
        if not isinstance(pointer, dict):
            problems.append(f"result[{index}] has no evidence_pointer")
            continue
        missing = sorted(REQUIRED_POINTER_FIELDS - set(pointer))
        if missing:
            problems.append(f"result[{index}] missing Evidence fields: {missing}")
        if pointer.get("schema_version") != 1:
            problems.append(f"result[{index}] has invalid Evidence schema_version")
        for field in REQUIRED_POINTER_FIELDS - {"schema_version"}:
            if not isinstance(pointer.get(field), str) or not pointer[field]:
                problems.append(f"result[{index}] has invalid Evidence field: {field}")
    return problems


class PointerAttestationError(RuntimeError):
    """A content-free pointer/CAS identity attestation failure."""


def _canonical_json_bytes(value):
    """Canonical bytes for the frozen ASCII-key object shapes used here."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _hash_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _chunk_identity_hash(chunk):
    # 03-data-model.md §8.1: byte_start/byte_end are the unit-local UTF-8 byte
    # span (2026-07 rename from char_start/char_end). This must track
    # crates/kio-core/src/cas.rs ChunkObject::identity_hash() exactly, or a real
    # on-disk chunk object (produced by the compiled `kio` binary, which the
    # PointerAttestor below reads and re-verifies) would silently mismatch here.
    identity_fields = (
        "spec_version", "raw_hash", "tool_profile_hash", "gen", "unit_key",
        "heading_path", "section_id", "byte_start", "byte_end",
    )
    identity = {field: chunk[field] for field in identity_fields if field in chunk}
    return _hash_bytes(_canonical_json_bytes(identity))


def _read_json_bounded(path, max_bytes, label):
    """Read one no-follow regular JSON file with a strict pre/post size bound."""
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise PointerAttestationError(f"{label} unavailable") from exc
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise PointerAttestationError(f"{label} is not a private regular file")
    if before.st_size > max_bytes:
        raise PointerAttestationError(f"{label} exceeds byte bound")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise PointerAttestationError(f"{label} unavailable") from exc
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise PointerAttestationError(f"{label} changed during read")
        with os.fdopen(fd, "rb", closefd=False) as fh:
            data = fh.read(max_bytes + 1)
    finally:
        os.close(fd)
    if len(data) > max_bytes:
        raise PointerAttestationError(f"{label} exceeds byte bound")
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PointerAttestationError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise PointerAttestationError(f"{label} is not a JSON object")
    return value, data


class PointerAttestor:
    """Bounded immutable-CAS attestation for historical result pointers."""

    _KINDS = {
        "commit": ("commits", MAX_COMMIT_OBJECT_BYTES),
        "tree": ("trees", MAX_TREE_OBJECT_BYTES),
        "chunk": ("chunks", MAX_CHUNK_OBJECT_BYTES),
    }

    def __init__(self, corpus_dir):
        self.corpus_dir = os.path.abspath(corpus_dir)
        self.scope_dirs = {}
        self.scope_errors = {}
        self.object_cache = {}
        self.verified_bytes = 0
        self._load_scope_map()

    def _load_scope_map(self):
        # The frozen corpus has a small fixed scope list; never scan arbitrary
        # filesystem descendants while resolving an untrusted pointer scope_id.
        for scope in spec.SCOPES:
            kio_dir = os.path.join(scope_dir_for(self.corpus_dir, scope), ".kio")
            scope_path = os.path.join(kio_dir, "scope.json")
            if not os.path.isdir(kio_dir):
                continue
            try:
                value, _ = _read_json_bounded(scope_path, 64 * 1024, "scope record")
            except PointerAttestationError as exc:
                self.scope_errors[scope] = str(exc)
                continue
            scope_id = value.get("scope_id")
            if not isinstance(scope_id, str) or not scope_id:
                self.scope_errors[scope] = "scope record has invalid scope_id"
                continue
            if scope_id in self.scope_dirs:
                self.scope_errors[scope_id] = "scope_id is ambiguous"
                self.scope_dirs.pop(scope_id, None)
                continue
            self.scope_dirs[scope_id] = kio_dir

    @staticmethod
    def _object_path(kio_dir, subdir, object_hash):
        if not isinstance(object_hash, str) or not HASH_RE.fullmatch(object_hash):
            raise PointerAttestationError("pointer contains an invalid object hash")
        digest = object_hash.removeprefix("sha256:")
        return os.path.join(kio_dir, "objects", subdir, digest[:2], digest[2:4], digest)

    def _read_object(self, scope_id, kind, object_hash):
        key = (scope_id, kind, object_hash)
        if key in self.object_cache:
            return self.object_cache[key]
        if scope_id in self.scope_errors:
            raise PointerAttestationError(self.scope_errors[scope_id])
        kio_dir = self.scope_dirs.get(scope_id)
        if kio_dir is None:
            raise PointerAttestationError("pointer scope_id is not in the synthetic corpus")
        subdir, max_bytes = self._KINDS[kind]
        path = self._object_path(kio_dir, subdir, object_hash)
        remaining = MAX_POINTER_ATTESTATION_BYTES - self.verified_bytes
        if remaining <= 0:
            raise PointerAttestationError("pointer attestation byte bound exhausted")
        value, data = _read_json_bounded(
            path, min(max_bytes, remaining), f"{kind} object")
        self.verified_bytes += len(data)
        if kind in ("commit", "tree") and _hash_bytes(data) != object_hash:
            raise PointerAttestationError(f"{kind} object hash mismatch")
        if kind == "chunk" and _chunk_identity_hash(value) != object_hash:
            raise PointerAttestationError("chunk object identity mismatch")
        self.object_cache[key] = value
        return value

    def attest(self, pointer):
        if not isinstance(pointer, dict):
            raise PointerAttestationError("result has no evidence_pointer")
        scope_id = pointer.get("scope_id")
        commit_hash = pointer.get("commit")
        chunk_hash = pointer.get("chunk_hash")
        path_at_commit = pointer.get("path_at_commit")
        raw_hash = pointer.get("raw_hash")
        profile_hash = pointer.get("tool_profile_hash")
        if not isinstance(scope_id, str) or not scope_id:
            raise PointerAttestationError("pointer has invalid scope_id")
        if not isinstance(path_at_commit, str) or not path_at_commit:
            raise PointerAttestationError("pointer has invalid path_at_commit")
        for name, value in (
                ("commit", commit_hash), ("chunk_hash", chunk_hash),
                ("raw_hash", raw_hash), ("tool_profile_hash", profile_hash)):
            if not isinstance(value, str) or not HASH_RE.fullmatch(value):
                raise PointerAttestationError(f"pointer has invalid {name}")

        commit = self._read_object(scope_id, "commit", commit_hash)
        if commit.get("object_type") != "commit":
            raise PointerAttestationError("commit object has wrong object_type")
        tree_hash = commit.get("tree")
        if not isinstance(tree_hash, str) or not HASH_RE.fullmatch(tree_hash):
            raise PointerAttestationError("commit has invalid tree hash")
        if pointer.get("tree") not in (None, tree_hash):
            raise PointerAttestationError("pointer tree does not match commit")

        tree = self._read_object(scope_id, "tree", tree_hash)
        if tree.get("object_type") != "tree":
            raise PointerAttestationError("tree object has wrong object_type")
        entries = tree.get("entries")
        if not isinstance(entries, list) or len(entries) > MAX_TREE_ENTRIES:
            raise PointerAttestationError("tree entries are invalid or exceed bound")
        matching = [entry for entry in entries
                    if isinstance(entry, dict) and entry.get("path") == path_at_commit]
        if len(matching) != 1:
            raise PointerAttestationError("tree does not contain exactly one pointer path")
        entry = matching[0]
        if entry.get("raw_hash") != raw_hash:
            raise PointerAttestationError("tree path raw_hash does not match pointer")
        normalize = entry.get("normalize")
        if not isinstance(normalize, dict):
            raise PointerAttestationError("tree path has no normalized identity")
        if normalize.get("tool_profile_hash") != profile_hash:
            raise PointerAttestationError("tree path profile does not match pointer")
        gen = normalize.get("gen", 0)
        if isinstance(gen, bool) or not isinstance(gen, int) or gen < 0:
            raise PointerAttestationError("tree path has invalid normalized generation")

        chunk = self._read_object(scope_id, "chunk", chunk_hash)
        if chunk.get("spec_version") != 1:
            raise PointerAttestationError("chunk object has invalid spec_version")
        if chunk.get("raw_hash") != raw_hash:
            raise PointerAttestationError("chunk raw_hash does not match pointer")
        if chunk.get("tool_profile_hash") != profile_hash:
            raise PointerAttestationError("chunk profile does not match pointer")
        if chunk.get("gen") != gen:
            raise PointerAttestationError("chunk generation does not match tree path")


def pointer_attestation_problems(response, attestor, k=MAX_POINTER_ATTESTATIONS_PER_QUERY):
    """Attest every bounded top-k result pointer used by M3-2 scoring."""
    problems = []
    results = response.get("results") or []
    if not isinstance(results, list):
        return ["results is not an array"]
    for index, result in enumerate(results[:k]):
        if not isinstance(result, dict):
            problems.append(f"result[{index}] is not an object")
            continue
        try:
            attestor.attest(result.get("evidence_pointer"))
        except PointerAttestationError as exc:
            problems.append(f"result[{index}] pointer attestation failed: {exc}")
    return problems


def percentile_nearest_rank(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def passes_latency_target(scenario, p95_ms):
    """Return whether p95 satisfies the scenario-specific strict upper bound."""
    return p95_ms is not None and p95_ms < LATENCY_TARGET_MS[scenario]


def assess_history_coverage(responses_by_scenario, history_manifest):
    """Structural guards that prevent HEAD-only Recall from false-passing."""
    def correctly_recalled_results(scenario):
        recalled = []
        for record in responses_by_scenario.get(scenario, []):
            expected = record.get("expected_set") or set()
            for result in (record.get("response", {}).get("results") or [])[:10]:
                pointer = result.get("evidence_pointer") or {}
                # QB24/裁定4: expected_set は 3 要素射影 (raw_hash, section,
                # path_at_commit) — identity もそれに合わせる。
                identity = (
                    pointer.get("raw_hash"),
                    _pointer_section(pointer),
                    pointer.get("path_at_commit"),
                )
                if identity in expected:
                    recalled.append(result)
        return recalled

    # A historical identity only counts when it is a correct Recall@10 hit for
    # that query. Irrelevant noise in another query's top ten cannot satisfy a
    # structural gate merely by carrying the same raw hash.
    m32_results = correctly_recalled_results("M3-2")
    m33_results = correctly_recalled_results("M3-3")
    m32_raws = {
        (result.get("evidence_pointer") or {}).get("raw_hash") for result in m32_results
    }
    edited_required = {
        "sha256:" + entry["raw_sha256"] for entry in history_manifest.get("edited", [])
    }
    edited_missing = sorted(edited_required - m32_raws)

    rename_failures = []
    m32_records = responses_by_scenario.get("M3-2", [])
    for entry in history_manifest.get("renamed", []):
        raw_hash = "sha256:" + entry["raw_sha256"]
        hits = [result for result in m32_results
                if (result.get("evidence_pointer") or {}).get("raw_hash") == raw_hash]
        # QB24/裁定4 (U142) の 3 要素射影の帰結: golden は旧名しか記さないため
        # expected_set 経由 (= m32_results) では新 path の alias 行が correctly
        # recalled になり得ず、旧実装の {old,new} ⊆ paths は構造的に充足不能
        # だった (射影変更の本ガードへの非伝播 — 2026-07-22 回帰補修)。新 path
        # 側は「旧 identity の new_file 双子」として、当該 raw を expected に
        # 持つ query 自身の top-10 から直接クレジットする (無関係 query の
        # ノイズでは満たせない、という本ガードの原則は維持)。
        twin_hits = []
        for record in m32_records:
            expected = record.get("expected_set") or set()
            twin_identities = {
                (raw, section, entry["new_file"])
                for (raw, section, path) in expected
                if raw == raw_hash and path == entry["old_file"]
            }
            if not twin_identities:
                continue
            for result in (record.get("response", {}).get("results") or [])[:10]:
                pointer = result.get("evidence_pointer") or {}
                identity = (
                    pointer.get("raw_hash"),
                    _pointer_section(pointer),
                    pointer.get("path_at_commit"),
                )
                if identity in twin_identities:
                    twin_hits.append(result)
        paths = {(result.get("evidence_pointer") or {}).get("path_at_commit")
                 for result in hits}
        paths.update((result.get("evidence_pointer") or {}).get("path_at_commit")
                     for result in twin_hits)
        required_paths = {entry["old_file"], entry["new_file"]}
        aliases_valid = bool(hits) and all(
            result.get("current_paths") == [entry["new_file"]]
            and result.get("current_path") == entry["new_file"]
            for result in hits + twin_hits)
        if not required_paths.issubset(paths) or not aliases_valid:
            rename_failures.append({
                "scope": entry["scope"], "raw_hash": raw_hash,
                "paths": sorted(path for path in paths if path),
            })

    m33_by_raw = {}
    for result in m33_results:
        raw_hash = (result.get("evidence_pointer") or {}).get("raw_hash")
        if raw_hash:
            m33_by_raw.setdefault(raw_hash, result)
    deleted_required = {
        "sha256:" + entry["raw_sha256"] for entry in history_manifest.get("deleted", [])
    }
    deleted_missing = sorted(deleted_required - set(m33_by_raw))
    return {
        "edited_old_required": len(edited_required),
        "edited_old_missing": edited_missing,
        "rename_required": len(history_manifest.get("renamed", [])),
        "rename_failures": rename_failures,
        "deleted_required": len(deleted_required),
        "deleted_missing": deleted_missing,
        "passes_m3_2": not edited_missing and not rename_failures,
        "passes_m3_3": not deleted_missing,
        "deleted_results": m33_by_raw,
    }


def _working_tree_fingerprint(corpus_dir):
    rows = []
    for scope in spec.SCOPES:
        scope_dir = scope_dir_for(corpus_dir, scope)
        for name in sorted(os.listdir(scope_dir)):
            if name == ".kio":
                continue
            path = os.path.join(scope_dir, name)
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    rows.append((scope, name, hashlib.sha256(fh.read()).hexdigest()))
    return rows


def verify_deleted_restore(bin_path, corpus_dir, history_manifest, deleted_results):
    """Restore one pointer for every deleted identity without mutating the corpus."""
    before = _working_tree_fingerprint(corpus_dir)
    problems = []
    cwd = scope_dir_for(corpus_dir, spec.SCOPES[0])
    for entry in history_manifest.get("deleted", []):
        raw_hash = "sha256:" + entry["raw_sha256"]
        result = deleted_results.get(raw_hash)
        if not result:
            problems.append(f"deleted result absent for restore: {entry['scope']}/{entry['file']}")
            continue
        pointer = result.get("evidence_pointer")
        with tempfile.TemporaryDirectory(prefix="kio-eval-restore-") as destination:
            proc = subprocess.run(
                [bin_path, "--json", "restore", json.dumps(pointer, separators=(",", ":")),
                 "--to", destination],
                cwd=cwd, capture_output=True, **KIO_SUBPROCESS_TEXT,
                env=subprocess_env(corpus_dir))
            if proc.returncode != 0:
                problems.append(
                    f"restore failed for {entry['scope']}/{entry['file']}: {proc.stderr.strip()}")
                continue
            restored = []
            for root, _, files in os.walk(destination):
                restored.extend(os.path.join(root, name) for name in files)
            if len(restored) != 1:
                problems.append(f"restore count mismatch for {entry['scope']}/{entry['file']}")
                continue
            with open(restored[0], "rb") as fh:
                actual = hashlib.sha256(fh.read()).hexdigest()
            if actual != entry["raw_sha256"]:
                problems.append(f"restore hash mismatch for {entry['scope']}/{entry['file']}")
    if _working_tree_fingerprint(corpus_dir) != before:
        problems.append("restore mutated the source corpus working tree")
    return problems


def run_full_eval(queries, resolver, history_manifest, corpus_dir, bin_path,
                  out_path, report_path, active, recall_target=RECALL_TARGET):
    print("=== eval: kio search 実行 + Recall@10 集計 ===")
    results = {"target_recall_at_10": recall_target, "scenarios": {}, "queries": []}
    per_scenario_scores = {s: [] for s in active}
    per_scenario_latencies = {s: [] for s in active}
    responses_by_scenario = {s: [] for s in active}
    n_unimplemented = 0
    n_failed = 0
    n_pointer_attested = 0
    n_pointer_attestation_failed = 0
    pointer_attestor = PointerAttestor(corpus_dir) if "M3-2" in active else None

    for q in queries:
        sc = q["scenario"]
        expected_set, resolve_errors = resolver.resolve_expected(q["expected"])
        outcome = run_search(bin_path, corpus_dir, q["query"], q.get("flags", []))
        kind, response, error_code, detail = classify_outcome(outcome)
        duration_ms = float(outcome.get("duration_ms", 0.0))

        if kind == "unimplemented":
            n_unimplemented += 1
            results["queries"].append({
                "scenario": sc, "query": q["query"], "status": "unimplemented",
                "error_code": error_code, "detail": detail, "duration_ms": duration_ms,
            })
            continue

        if resolve_errors:
            # 解決不能は採点不能 → fail 扱い (recall 0) にして表面化させる。
            kind, detail = "fail", "; ".join(resolve_errors)

        if kind == "fail":
            n_failed += 1
            per_scenario_scores.setdefault(sc, []).append(0.0)
            per_scenario_latencies.setdefault(sc, []).append(duration_ms)
            results["queries"].append({
                "scenario": sc, "query": q["query"], "status": "failed",
                "recall_at_10": 0.0, "error_code": error_code, "detail": detail,
                "duration_ms": duration_ms,
            })
            continue

        pointer_problems = evidence_problems(response)
        if pointer_problems:
            n_failed += 1
            per_scenario_scores.setdefault(sc, []).append(0.0)
            per_scenario_latencies.setdefault(sc, []).append(duration_ms)
            results["queries"].append({
                "scenario": sc, "query": q["query"], "status": "failed",
                "recall_at_10": 0.0, "detail": "; ".join(pointer_problems),
                "duration_ms": duration_ms,
            })
            continue

        attestation_problems = []
        if sc == "M3-2":
            attestation_problems = pointer_attestation_problems(
                response, pointer_attestor)
            if attestation_problems:
                n_failed += 1
                n_pointer_attestation_failed += 1
                per_scenario_scores.setdefault(sc, []).append(0.0)
                per_scenario_latencies.setdefault(sc, []).append(duration_ms)
                results["queries"].append({
                    "scenario": sc, "query": q["query"], "status": "failed",
                    "recall_at_10": 0.0,
                    "detail": "; ".join(attestation_problems),
                    "duration_ms": duration_ms,
                })
                continue
            n_pointer_attested += min(
                len(response.get("results") or []), MAX_POINTER_ATTESTATIONS_PER_QUERY)

        score = recall_at_k(response, expected_set, k=10)
        per_scenario_scores.setdefault(sc, []).append(score)
        per_scenario_latencies.setdefault(sc, []).append(duration_ms)
        responses_by_scenario.setdefault(sc, []).append({
            "response": response,
            "expected_set": expected_set,
        })
        results["queries"].append({
            "scenario": sc, "query": q["query"], "status": "scored",
            "recall_at_10": score, "duration_ms": duration_ms,
            **({"pointer_attested": min(
                len(response.get("results") or []),
                MAX_POINTER_ATTESTATIONS_PER_QUERY)} if sc == "M3-2" else {}),
            **({"detail": detail} if detail else {}),
        })

    for s in active:
        scores = per_scenario_scores.get(s, [])
        latencies = per_scenario_latencies.get(s, [])
        avg = sum(scores) / len(scores) if scores else None
        p95_ms = percentile_nearest_rank(latencies, 0.95)
        latency_target_ms = LATENCY_TARGET_MS[s]
        results["scenarios"][s] = {
            "n_queries": sum(1 for q in queries if q["scenario"] == s),
            "n_scored": len(scores),
            "recall_at_10": avg,
            "passes_target": (avg is not None and avg >= recall_target),
            "p95_ms": p95_ms,
            "latency_target_ms": latency_target_ms,
            "passes_latency": passes_latency_target(s, p95_ms),
        }

    history_coverage = assess_history_coverage(responses_by_scenario, history_manifest)
    deleted_results = history_coverage.pop("deleted_results")
    restore_problems = []
    if "M3-3" in active and history_coverage["passes_m3_3"]:
        restore_problems = verify_deleted_restore(
            bin_path, corpus_dir, history_manifest, deleted_results)
    history_coverage["restore_problems"] = restore_problems
    history_coverage["passes_restore"] = not restore_problems
    history_coverage["pointer_attested"] = n_pointer_attested
    history_coverage["pointer_attestation_failures"] = n_pointer_attestation_failed
    history_coverage["passes_pointer_attestation"] = n_pointer_attestation_failed == 0
    results["history_coverage"] = history_coverage

    results["counts"] = {
        "n_queries": len(queries),
        "n_unimplemented": n_unimplemented,
        "n_failed": n_failed,
        "n_scored": sum(len(v) for v in per_scenario_scores.values()),
        "n_pointer_attested": n_pointer_attested,
    }

    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    _write_report(report_path, results, active)

    # exit コード判定 (J2 裁定)。
    if n_unimplemented > 0:
        print(f"[note] kio search が未実装のクエリが {n_unimplemented} 件 "
              f"(NOT-IMPLEMENTED)。Recall 判定は未実装のため無効。")
        print(f"       results: {out_path}")
        print(f"       report:  {report_path}")
        return 2

    all_pass = (n_failed == 0)
    for s in active:
        scv = results["scenarios"][s]
        expected_count = sum(1 for query in queries if query["scenario"] == s)
        if (scv["n_scored"] != expected_count or not scv["passes_target"]
                or not scv["passes_latency"]):
            all_pass = False
        if s in ("M3-2", "M3-3") and expected_count != HISTORY_QUERY_COUNT:
            all_pass = False
    if "M3-2" in active and not history_coverage["passes_m3_2"]:
        all_pass = False
    if "M3-2" in active and not history_coverage["passes_pointer_attestation"]:
        all_pass = False
    if "M3-3" in active and (
            not history_coverage["passes_m3_3"] or not history_coverage["passes_restore"]):
        all_pass = False
    verdict = "OK" if all_pass else "NG"
    if n_failed:
        print(f"[note] 実行失敗 (非 0 exit / 不正レスポンス / 解決不能) が {n_failed} 件。")
    print(f"[{verdict}] Recall@10 集計完了。 results: {out_path}")
    return 0 if all_pass else 1


def _write_report(path, results, active):
    counts = results.get("counts", {})
    lines = ["# Kio 検索評価レポート (synthetic)", ""]
    lines.append(
        f"- 目標: 各シナリオ Recall@10 >= "
        f"{results.get('target_recall_at_10', RECALL_TARGET)} (docs/09 §4.3)")
    lines.append(f"- クエリ数: {counts.get('n_queries', 0)} "
                 f"(scored={counts.get('n_scored', 0)} / "
                 f"failed={counts.get('n_failed', 0)} / "
                 f"unimplemented={counts.get('n_unimplemented', 0)})")
    if counts.get("n_unimplemented", 0) > 0:
        lines.append("- 状態: **kio search 未実装のクエリあり (NOT-IMPLEMENTED)**。"
                     "Recall 判定は無効 (exit 2)。")
    lines.append("")
    lines.append("| シナリオ | クエリ数 | scored | Recall@10 | p95 ms | 目標 ms | 判定 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for s in active:
        sc = results["scenarios"][s]
        rec = "-" if sc["recall_at_10"] is None else f"{sc['recall_at_10']:.3f}"
        if sc["n_scored"] == 0:
            verdict = "n/a"
        else:
            verdict = "PASS" if sc["passes_target"] and sc["passes_latency"] else "FAIL"
        p95 = "-" if sc["p95_ms"] is None else f"{sc['p95_ms']:.1f}"
        target = f"<{sc['latency_target_ms']:.0f}"
        lines.append(
            f"| {s} | {sc['n_queries']} | {sc['n_scored']} | {rec} | {p95} | "
            f"{target} | {verdict} |")
    coverage = results.get("history_coverage", {})
    if "M3-2" in active:
        lines.append("")
        lines.append(f"- M3-2 edited/rename structural coverage: "
                     f"{'PASS' if coverage.get('passes_m3_2') else 'FAIL'}")
        lines.append(f"- M3-2 pointer CAS attestation: "
                     f"{'PASS' if coverage.get('passes_pointer_attestation') else 'FAIL'} "
                     f"({coverage.get('pointer_attested', 0)} pointers)")
    if "M3-3" in active:
        lines.append(f"- M3-3 deleted coverage: "
                     f"{'PASS' if coverage.get('passes_m3_3') else 'FAIL'}")
        lines.append(f"- M3-3 restore verification: "
                     f"{'PASS' if coverage.get('passes_restore') else 'FAIL'}")
    lines.append("")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description="Kio 検索評価ランナー")
    ap.add_argument("--golden", default=os.path.join(HERE, "golden-queries.jsonl"))
    ap.add_argument("--corpus", help="コーパスディレクトリ (corpus-manifest.json を含む)")
    ap.add_argument("--corpus-manifest",
                    help="corpus-manifest.json のパス (既定 <corpus>/corpus-manifest.json)")
    ap.add_argument("--history-manifest", default=None,
                    help="既定 <corpus>/history-manifest.json")
    ap.add_argument("--bin", default="target/release/kio")
    ap.add_argument("--out", default=os.path.join(HERE, "results.json"))
    ap.add_argument("--report", default=os.path.join(HERE, "report.md"))
    ap.add_argument("--scenario", action="append", choices=SCENARIOS, default=None,
                    help="対象シナリオ (複数指定可。既定は全シナリオ)")
    ap.add_argument("--min-recall", type=float, default=RECALL_TARGET,
                    help="Recall@10 の下限 (既定 0.8)。短問ゲートは 22/24 を指定する。")
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
    history_path = args.history_manifest
    if history_path is None:
        if not args.corpus:
            raise SystemExit("[error] --history-manifest か --corpus を指定すること。")
        history_path = os.path.join(os.path.abspath(args.corpus), "history-manifest.json")
    history_manifest = load_json(history_path, "history-manifest.json")
    history_problems = validate_history_manifest(history_manifest)
    if history_problems:
        for problem in history_problems:
            print(f"[error] {problem}", file=sys.stderr)
        return 1
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
        raise SystemExit(f"[error] kio バイナリ不在: {bin_path}")
    corpus_dir = os.path.abspath(args.corpus)
    replay_problems = validate_replayed_history(bin_path, corpus_dir, history_manifest)
    if replay_problems:
        for problem in replay_problems:
            print(f"[error] {problem}", file=sys.stderr)
        return 1
    if not 0.0 <= args.min_recall <= 1.0:
        raise SystemExit("[error] --min-recall は 0.0 から 1.0 の範囲で指定すること。")
    return run_full_eval(queries, resolver, history_manifest, corpus_dir,
                         bin_path, args.out, args.report, active, args.min_recall)


if __name__ == "__main__":
    raise SystemExit(main())
