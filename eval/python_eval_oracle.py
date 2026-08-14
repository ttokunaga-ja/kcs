#!/usr/bin/env python3
"""Python-only differential and security oracle for the Rust evaluator.

This module deliberately has no normal evaluator CLI, full-history gate, report
writer, or restore path. Rust's ``kio-eval`` owns those production concerns.
The small helpers here retain independent checks for shared vectors,
pointer attestation, and the crossscope/reranker auxiliary tools.

The independent Recall projection is retained for differential tests:
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

``classify_outcome`` and ``run_search`` are only used by the standalone
crossscope diagnostic, not the canonical full evaluator.
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
# Rust's `char::is_whitespace` follows Unicode White_Space. Python's `\s`
# additionally treats U+001C..U+001F as whitespace, so use the Rust set
# explicitly for cross-language slug vectors.
_RUST_WHITESPACE_RE = re.compile(
    r"[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+"
)


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
    s = _RUST_WHITESPACE_RE.sub("-", s)
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
            f"        先に kio-eval generate-corpus / replay_history.py を実行すること。")
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
        "unit_content_hash", "heading_path", "section_id", "byte_start", "byte_end",
    )
    identity = {
        field: chunk[field]
        for field in identity_fields
        if field in chunk and not (field == "section_id" and not chunk[field])
    }
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
    if (type(percentile) not in (int, float)
            or (type(percentile) is float and not math.isfinite(percentile))
            or not 0 < percentile <= 1):
        raise ValueError("percentile must be in the interval (0, 1]")
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def passes_latency_target(scenario, p95_ms):
    """Return whether p95 satisfies the scenario-specific strict upper bound."""
    return p95_ms is not None and p95_ms < LATENCY_TARGET_MS[scenario]
