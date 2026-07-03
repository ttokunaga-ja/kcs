#!/usr/bin/env python3
"""run_eval.py の軽量単体テスト (Python 標準ライブラリのみ).

実行:
    python3 -m unittest eval/test_run_eval.py
    (または)  python3 eval/test_run_eval.py

検証対象:
  - slugify: docs/04-pipeline.md §4.1 の slug 規則
  - Resolver: expected {scope,file,section(ニーモニック)} -> (raw_hash, section_id)
  - recall_at_k: 既知の hit/miss で Recall が手計算と一致すること
  - classify_outcome: NOT-IMPLEMENTED / exit 3 部分成功 / 実バグ の分類
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_spec as spec  # noqa: E402
import generate_corpus  # noqa: E402
import run_eval  # noqa: E402


class TestSlugify(unittest.TestCase):
    def test_docs_0401_rules(self):
        cases = {
            # 日本語見出しは保持 (英語ニーモニックとは一致しない = J2 の要点)
            "回収率と精度": "回収率と精度",
            "スループットとメモリ": "スループットとメモリ",
            # ASCII 英字は小文字化、空白は "-"
            "API Token": "api-token",
            "RRF 融合": "rrf-融合",
            "MMR 多様化": "mmr-多様化",
            # 数字・英字混在
            "埋め込みモデル ベンチマーク 2026Q2": "埋め込みモデル-ベンチマーク-2026q2",
            # 記号除去・連続 "-" 圧縮・前後 "-" 除去
            "  Hello -- World!!  ": "hello-world",
            # アンダースコアは保持
            "foo_bar": "foo_bar",
            # 記号だけ → 空文字列
            "!!!": "",
            "———": "",
        }
        for inp, want in cases.items():
            self.assertEqual(run_eval.slugify(inp), want, f"slugify({inp!r})")

    def test_empty_and_none(self):
        self.assertEqual(run_eval.slugify(""), "")
        self.assertEqual(run_eval.slugify(None), "")


class TestPointerSection(unittest.TestCase):
    def test_section_id_full_path_leaf(self):
        # docs/08 §2 の section_id は heading_path を "/" 連結した slug。leaf を採る。
        p = {"section_id": "埋め込みモデル-ベンチマーク-2026q2/回収率と精度"}
        self.assertEqual(run_eval._pointer_section(p), "回収率と精度")

    def test_heading_path_fallback_is_slugified(self):
        p = {"heading_path": ["検索レイテンシ調査レポート", "テールレイテンシ"]}
        self.assertEqual(run_eval._pointer_section(p), "テールレイテンシ")

    def test_no_section_info(self):
        self.assertIsNone(run_eval._pointer_section({}))


def _pointer(raw_hash, section_id=None, heading_path=None):
    p = {"raw_hash": raw_hash}
    if section_id is not None:
        p["section_id"] = section_id
    if heading_path is not None:
        p["heading_path"] = heading_path
    return {"evidence_pointer": p}


class TestRecallAtK(unittest.TestCase):
    def test_half_recall(self):
        # expected 2 件、うち 1 件ヒット -> 0.5
        expected = {("sha256:aaa", "回収率と精度"), ("sha256:ccc", "テールレイテンシ")}
        response = {"results": [
            _pointer("sha256:aaa", section_id="doc-a/回収率と精度"),   # hit
            _pointer("sha256:zzz", section_id="noise/ノイズ"),          # miss
        ]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.5)

    def test_full_recall_via_heading_path(self):
        expected = {("sha256:aaa", "回収率と精度"), ("sha256:bbb", "テールレイテンシ")}
        response = {"results": [
            _pointer("sha256:aaa", heading_path=["Doc A", "回収率と精度"]),
            _pointer("sha256:bbb", heading_path=["Doc B", "テールレイテンシ"]),
        ]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 1.0)

    def test_zero_recall(self):
        expected = {("sha256:aaa", "回収率と精度")}
        response = {"results": [_pointer("sha256:xxx", section_id="a/b")]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.0)

    def test_section_mismatch_same_raw_is_miss(self):
        # raw_hash 一致でも section が違えば (raw_hash, section) pair はミス
        expected = {("sha256:aaa", "回収率と精度")}
        response = {"results": [_pointer("sha256:aaa", section_id="a/スループットとメモリ")]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.0)

    def test_k_truncation(self):
        # 11 件目 (index 10) のヒットは k=10 では数えない
        noise = [_pointer(f"sha256:n{i}", section_id="x/y") for i in range(10)]
        hit = _pointer("sha256:aaa", section_id="a/回収率と精度")
        expected = {("sha256:aaa", "回収率と精度")}
        response = {"results": noise + [hit]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.0)
        # k=11 なら数える
        self.assertEqual(run_eval.recall_at_k(response, expected, k=11), 1.0)

    def test_distinct_dedup(self):
        # 同一 (raw_hash, section) が 2 件でも distinct 1 件として数える
        expected = {("sha256:aaa", "回収率と精度"), ("sha256:bbb", "テールレイテンシ")}
        response = {"results": [
            _pointer("sha256:aaa", section_id="a/回収率と精度"),
            _pointer("sha256:aaa", section_id="a/回収率と精度"),
        ]}
        # 1/2 = 0.5
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.5)


class TestResolver(unittest.TestCase):
    def setUp(self):
        # generate_corpus.build_manifest() は disk 不要で決定論的に manifest を返す。
        self.corpus_manifest = generate_corpus.build_manifest()
        # history は編集/リネーム/削除の旧内容 (raw_sha256 + sections) を持つ形。
        self.history_manifest = self._synth_history()
        self.resolver = run_eval.Resolver(self.corpus_manifest, self.history_manifest)

    def _synth_history(self):
        def secs(anchor):
            return [{"slug": s["slug"], "heading": s["heading"]}
                    for s in anchor["sections"]]

        def h(scope, file_):
            a = next(a for a in spec.ANCHORS
                     if a["scope"] == scope and a["file"] == file_)
            raw = hashlib.sha256(spec.render_anchor(a).encode("utf-8")).hexdigest()
            return raw, secs(a)

        renamed = []
        for r in spec.HISTORY["renames"]:
            raw, ss = h(r["scope"], r["old_file"])
            renamed.append({"scope": r["scope"], "old_file": r["old_file"],
                            "new_file": r["new_file"], "raw_sha256": raw, "sections": ss})
        edited = []
        for e in spec.HISTORY["edits"]:
            raw, ss = h(e["scope"], e["file"])
            edited.append({"scope": e["scope"], "file": e["file"],
                           "old_value": e["old_value"], "new_value": e["new_value"],
                           "raw_sha256": raw, "sections": ss})
        deleted = []
        for d in spec.HISTORY["deletes"]:
            raw, ss = h(d["scope"], d["file"])
            deleted.append({"scope": d["scope"], "file": d["file"],
                            "raw_sha256": raw, "sections": ss})
        return {"renamed": renamed, "edited": edited, "deleted": deleted}

    def _expected_raw(self, scope, file_):
        a = next(a for a in spec.ANCHORS
                 if a["scope"] == scope and a["file"] == file_)
        return "sha256:" + hashlib.sha256(
            spec.render_anchor(a).encode("utf-8")).hexdigest()

    def test_m3_1_stable(self):
        raw, sid = self.resolver.resolve_one("research", "embedding-benchmark.md", "recall")
        self.assertEqual(sid, "回収率と精度")
        self.assertEqual(raw, self._expected_raw("research", "embedding-benchmark.md"))

    def test_m3_2_renamed_by_old_name(self):
        # golden は旧名 auth-spec.md で覚えている
        raw, sid = self.resolver.resolve_one("research", "auth-spec.md", "api-token")
        self.assertEqual(sid, "api-トークン")
        self.assertEqual(raw, self._expected_raw("research", "auth-spec.md"))

    def test_m3_3_deleted(self):
        raw, sid = self.resolver.resolve_one("research", "deprecated-approach.md", "method")
        self.assertEqual(sid, "旧手法")
        self.assertEqual(raw, self._expected_raw("research", "deprecated-approach.md"))

    def test_unknown_mnemonic_raises(self):
        with self.assertRaises(run_eval.ResolveError):
            self.resolver.resolve_one("research", "embedding-benchmark.md", "nope")

    def test_unknown_file_raises(self):
        with self.assertRaises(run_eval.ResolveError):
            self.resolver.resolve_one("research", "does-not-exist.md", "recall")

    def test_all_golden_expected_resolve(self):
        # golden-queries.jsonl の全 expected が解決でき、section_id が空でないこと。
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "golden-queries.jsonl")
        queries = run_eval.load_golden(path)
        errors = []
        for q in queries:
            resolved, errs = self.resolver.resolve_expected(q["expected"])
            errors.extend(errs)
            for _, sid in resolved:
                self.assertTrue(sid, "section_id が空")
        self.assertEqual(errors, [], f"解決エラー: {errors}")


class TestClassifyOutcome(unittest.TestCase):
    def test_not_implemented_on_stderr(self):
        outcome = {
            "returncode": 1, "stdout": "",
            "stderr": '{"error_code":"KCS-E-CONFIG-NOT-IMPLEMENTED-001",'
                      '"message":"not implemented"}',
        }
        kind, resp, code, _ = run_eval.classify_outcome(outcome)
        self.assertEqual(kind, "unimplemented")
        self.assertEqual(code, "KCS-E-CONFIG-NOT-IMPLEMENTED-001")

    def test_exit0_scored(self):
        outcome = {"returncode": 0, "stdout": '{"results":[]}', "stderr": ""}
        kind, resp, code, _ = run_eval.classify_outcome(outcome)
        self.assertEqual(kind, "scored")
        self.assertEqual(resp, {"results": []})

    def test_exit3_partial_scored(self):
        outcome = {"returncode": 3,
                   "stdout": '{"results":[{"evidence_pointer":{"raw_hash":"sha256:a"}}]}',
                   "stderr": ""}
        kind, resp, code, detail = run_eval.classify_outcome(outcome)
        self.assertEqual(kind, "scored")
        self.assertIn("partial", detail)

    def test_other_nonzero_is_fail(self):
        outcome = {"returncode": 5, "stdout": "",
                   "stderr": '{"error_code":"KCS-E-SEARCH-BOOM-001","message":"boom"}'}
        kind, resp, code, detail = run_eval.classify_outcome(outcome)
        self.assertEqual(kind, "fail")
        self.assertEqual(code, "KCS-E-SEARCH-BOOM-001")

    def test_exit0_but_garbage_is_fail(self):
        outcome = {"returncode": 0, "stdout": "not json", "stderr": ""}
        kind, resp, code, detail = run_eval.classify_outcome(outcome)
        self.assertEqual(kind, "fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
