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
import copy
import json
import math
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_spec as spec  # noqa: E402
import generate_corpus  # noqa: E402
import replay_history  # noqa: E402
import run_eval  # noqa: E402


def _strict_object(value, required, optional=()):
    if type(value) is not dict:
        raise ValueError("golden vector object must be a JSON object")
    actual = set(value)
    allowed = set(required) | set(optional)
    if not set(required) <= actual or actual - allowed:
        raise ValueError("golden vector object has missing or unknown fields")


def _strict_string(value):
    if type(value) is not str:
        raise ValueError("golden vector string field must be a string")


def _strict_u64(value, label):
    if type(value) is not int or not 0 <= value <= 2**64 - 1:
        raise ValueError(f"{label} must be a u64")


def _reject_json_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def _validate_finite_json(value):
    if type(value) is float and not math.isfinite(value):
        raise ValueError("golden vectors may only contain finite JSON numbers")
    if type(value) is list:
        for item in value:
            _validate_finite_json(item)
    elif type(value) is dict:
        for item in value.values():
            _validate_finite_json(item)


def _validate_golden_vectors(vectors):
    """Mirror the Rust vector structs' `deny_unknown_fields` boundary."""
    _strict_object(vectors, {
        "schema_version", "canonical_json", "slugs", "chunk_identity",
        "recall", "percentiles",
    })
    _validate_finite_json(vectors)
    if type(vectors["schema_version"]) is not int or vectors["schema_version"] != 1:
        raise ValueError("unsupported golden vector schema_version")
    collections = ("canonical_json", "slugs", "chunk_identity", "recall", "percentiles")
    if any(type(vectors[name]) is not list for name in collections):
        raise ValueError("golden vector collections must be arrays")

    for case in vectors["canonical_json"]:
        _strict_object(case, {"name", "value", "canonical_utf8", "sha256", "python_compatible"})
        for name in ("name", "canonical_utf8", "sha256"):
            _strict_string(case[name])
        if type(case["python_compatible"]) is not bool:
            raise ValueError("python_compatible must be a boolean")
    for case in vectors["slugs"]:
        _strict_object(case, {"name", "input", "expected"})
        for value in case.values():
            _strict_string(value)
    chunk_required = {
        "spec_version", "raw_hash", "tool_profile_hash", "gen", "unit_key",
        "unit_content_hash", "heading_path", "byte_start", "byte_end", "text_hash", "text",
    }
    for case in vectors["chunk_identity"]:
        _strict_object(case, {"name", "chunk", "expected_hash"})
        _strict_string(case["name"])
        _strict_string(case["expected_hash"])
        _strict_object(case["chunk"], chunk_required, {"section_id"})
        for name in ("raw_hash", "tool_profile_hash", "unit_key", "unit_content_hash", "text_hash", "text"):
            _strict_string(case["chunk"][name])
        for name in ("spec_version", "gen", "byte_start", "byte_end"):
            _strict_u64(case["chunk"][name], f"chunk {name}")
        if "section_id" in case["chunk"] and case["chunk"]["section_id"] is not None:
            _strict_string(case["chunk"]["section_id"])
        if case["chunk"]["spec_version"] != 1:
            raise ValueError("chunk spec_version must be exactly 1")
        for name in ("raw_hash", "tool_profile_hash", "unit_content_hash", "text_hash"):
            if not run_eval.HASH_RE.fullmatch(case["chunk"][name]):
                raise ValueError(f"chunk {name} must be canonical sha256")
        if not case["chunk"]["unit_key"]:
            raise ValueError("chunk unit_key must not be empty")
        if case["chunk"]["byte_start"] > case["chunk"]["byte_end"]:
            raise ValueError("chunk byte span must be ordered")
        if run_eval._hash_bytes(case["chunk"]["text"].encode("utf-8")) != case["chunk"]["text_hash"]:
            raise ValueError("chunk text_hash must match exact text")
        if type(case["chunk"]["heading_path"]) is not list or not all(
                type(value) is str for value in case["chunk"]["heading_path"]):
            raise ValueError("chunk heading_path must be an array of strings")
    for case in vectors["recall"]:
        _strict_object(case, {"name", "expected", "results", "k", "expected_recall"})
        _strict_string(case["name"])
        if type(case["expected"]) is not list or type(case["results"]) is not list:
            raise ValueError("recall expected and results must be arrays")
        if (type(case["k"]) is not int or case["k"] < 0
                or type(case["expected_recall"]) not in (int, float)
                or (type(case["expected_recall"]) is float
                    and not math.isfinite(case["expected_recall"]))):
            raise ValueError("recall k and expected_recall have invalid types")
        for key in case["expected"]:
            if type(key) is not list or len(key) != 3 or type(key[0]) is not str or any(
                    value is not None and type(value) is not str for value in key[1:]):
                raise ValueError("recall expected key must be a 3-tuple")
        for result in case["results"]:
            _strict_object(result, {"raw_hash"}, {"section_id", "heading_path", "path_at_commit"})
            _strict_string(result["raw_hash"])
            for name in ("section_id", "path_at_commit"):
                if name in result and result[name] is not None:
                    _strict_string(result[name])
            if "heading_path" in result and (
                    result["heading_path"] is not None and (
                        type(result["heading_path"]) is not list or not all(
                            type(value) is str for value in result["heading_path"]))):
                raise ValueError("recall heading_path must be an array of strings or null")
    for case in vectors["percentiles"]:
        _strict_object(case, {"name", "values", "percentile", "expected"})
        _strict_string(case["name"])
        if type(case["values"]) is not list:
            raise ValueError("percentile values must be integer array")
        for value in case["values"]:
            _strict_u64(value, "percentile value")
        if (type(case["percentile"]) not in (int, float)
                or (type(case["percentile"]) is float and not math.isfinite(case["percentile"]))
                or not 0 < case["percentile"] <= 1):
            raise ValueError("percentile must be in the interval (0, 1]")
        if type(case["expected"]) not in (int, type(None)):
            raise ValueError("percentile case has invalid numeric fields")
        if case["expected"] is not None:
            _strict_u64(case["expected"], "percentile expected")


class TestGoldenVectors(unittest.TestCase):
    """Shared Rust/Python evaluation vectors; Python is only a differential oracle."""

    def test_shared_vectors_match_python_compatible_contracts(self):
        path = os.path.join(os.path.dirname(__file__), "golden-vectors.json")
        with open(path, encoding="utf-8") as fh:
            vectors = json.load(fh, parse_constant=_reject_json_constant)
        _validate_golden_vectors(vectors)

        for case in vectors["canonical_json"]:
            self.assertEqual(
                "sha256:" + hashlib.sha256(case["canonical_utf8"].encode("utf-8")).hexdigest(),
                case["sha256"], case["name"])
            # stdlib JSON differs from JCS for floats, so only explicitly
            # compatible shapes compare serializer output.
            if case["python_compatible"]:
                self.assertEqual(
                    run_eval._canonical_json_bytes(case["value"]),
                    case["canonical_utf8"].encode("utf-8"), case["name"])

        for case in vectors["slugs"]:
            self.assertEqual(run_eval.slugify(case["input"]), case["expected"], case["name"])
        for case in vectors["chunk_identity"]:
            self.assertEqual(
                run_eval._chunk_identity_hash(case["chunk"]), case["expected_hash"], case["name"])

        for case in vectors["recall"]:
            response = {"results": [{"evidence_pointer": result} for result in case["results"]]}
            expected = {tuple(value) for value in case["expected"]}
            self.assertEqual(
                run_eval.recall_at_k(response, expected, case["k"]),
                case["expected_recall"], case["name"])
        for case in vectors["percentiles"]:
            self.assertEqual(
                run_eval.percentile_nearest_rank(case["values"], case["percentile"]),
                case["expected"], case["name"])

    def test_vector_schema_rejects_unknown_nested_field(self):
        with self.assertRaises(ValueError):
            _validate_golden_vectors({
                "schema_version": 1,
                "canonical_json": [], "slugs": [], "chunk_identity": [], "recall": [],
                "percentiles": [{"name": "bad", "values": [], "percentile": .95,
                                 "expected": None, "unexpected": True}],
            })

    def test_vector_schema_rejects_invalid_chunk_contract(self):
        path = os.path.join(os.path.dirname(__file__), "golden-vectors.json")
        with open(path, encoding="utf-8") as fh:
            vectors = json.load(fh, parse_constant=_reject_json_constant)
        for field, value in (
                ("spec_version", 2),
                ("raw_hash", "sha256:not-a-hash"),
                ("unit_key", ""),
                ("byte_start", 6),
                ("text_hash", "sha256:" + "0" * 64)):
            invalid = copy.deepcopy(vectors)
            invalid["chunk_identity"][0]["chunk"][field] = value
            with self.assertRaises(ValueError, msg=field):
                _validate_golden_vectors(invalid)

    def test_non_finite_json_constants_are_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"number": NaN}', parse_constant=_reject_json_constant)
        vectors = {
            "schema_version": 1,
            "canonical_json": [{"name": "nonfinite", "value": float("nan"),
                                "canonical_utf8": "", "sha256": "", "python_compatible": False}],
            "slugs": [], "chunk_identity": [], "recall": [], "percentiles": [],
        }
        with self.assertRaises(ValueError):
            _validate_golden_vectors(vectors)

    def test_percentile_rejects_out_of_range_values(self):
        for percentile in (0, -.1, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                run_eval.percentile_nearest_rank([1], percentile)


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


class TestPointerAttestation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kio-eval-attest-")
        self.addCleanup(self.temp.cleanup)
        self.scope_name = spec.SCOPES[0]
        self.scope_id = "scope_eval_attestation"
        self.scope_dir = os.path.join(self.temp.name, self.scope_name)
        self.kio_dir = os.path.join(self.scope_dir, ".kio")
        os.makedirs(self.kio_dir)
        with open(os.path.join(self.kio_dir, "scope.json"), "w", encoding="utf-8") as fh:
            json.dump({"scope_id": self.scope_id}, fh)

        self.raw_hash = "sha256:" + "11" * 32
        self.profile_hash = "sha256:" + "22" * 32
        text = "historical pointer attestation"
        self.chunk = {
            "spec_version": 1,
            "raw_hash": self.raw_hash,
            "tool_profile_hash": self.profile_hash,
            "gen": 3,
            "unit_key": "section:old",
            "unit_content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
            "heading_path": ["Old Document", "Historical"],
            "section_id": "old-document/historical",
            "byte_start": 0,
            "byte_end": len(text.encode("utf-8")),
            "text_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
            "text": text,
        }
        self.chunk_hash = run_eval._chunk_identity_hash(self.chunk)
        self._publish("chunks", self.chunk, self.chunk_hash)
        self.pointer = self._publish_snapshot(gen=3)
        self.attestor = run_eval.PointerAttestor(self.temp.name)

    def _publish(self, subdir, value, object_hash=None):
        data = run_eval._canonical_json_bytes(value)
        object_hash = object_hash or run_eval._hash_bytes(data)
        digest = object_hash.removeprefix("sha256:")
        directory = os.path.join(
            self.kio_dir, "objects", subdir, digest[:2], digest[2:4])
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, digest), "wb") as fh:
            fh.write(data)
        return object_hash

    def _publish_snapshot(self, gen, profile_hash=None, raw_hash=None):
        profile_hash = profile_hash or self.profile_hash
        raw_hash = raw_hash or self.raw_hash
        tree = {
            "object_type": "tree",
            "entries": [{
                "path": "old-name.md",
                "type": "file",
                "raw_hash": raw_hash,
                "normalize": {"tool_profile_hash": profile_hash, "gen": gen},
            }],
        }
        tree_hash = self._publish("trees", tree)
        commit = {
            "object_type": "commit",
            "tree": tree_hash,
            "parents": [],
            "created_at": "2026-07-13T00:00:00Z",
            "message": "synthetic attestation",
            "tool_lock_hash": "sha256:" + "33" * 32,
            "stats": {"files_added": 1, "files_modified": 0, "files_deleted": 0},
            "commit_type": "manual",
        }
        commit_hash = self._publish("commits", commit)
        return {
            "schema_version": 1,
            "scope_id": self.scope_id,
            "commit": commit_hash,
            "tree": tree_hash,
            "raw_hash": self.raw_hash,
            "tool_profile_hash": self.profile_hash,
            "chunk_hash": self.chunk_hash,
            "path_at_commit": "old-name.md",
        }

    def test_exact_commit_tree_path_profile_and_generation_attest(self):
        response = {"results": [{"evidence_pointer": self.pointer}]}
        self.assertEqual(
            run_eval.pointer_attestation_problems(response, self.attestor), [])
        verified = self.attestor.verified_bytes
        self.assertEqual(
            run_eval.pointer_attestation_problems(response, self.attestor), [])
        self.assertEqual(self.attestor.verified_bytes, verified, "CAS reads must be cached")

    def test_wrong_historical_path_or_raw_fails(self):
        wrong_path = copy.deepcopy(self.pointer)
        wrong_path["path_at_commit"] = "current-name.md"
        problems = run_eval.pointer_attestation_problems(
            {"results": [{"evidence_pointer": wrong_path}]}, self.attestor)
        self.assertTrue(any("pointer path" in problem for problem in problems))

        wrong_raw = copy.deepcopy(self.pointer)
        wrong_raw["raw_hash"] = "sha256:" + "44" * 32
        problems = run_eval.pointer_attestation_problems(
            {"results": [{"evidence_pointer": wrong_raw}]}, self.attestor)
        self.assertTrue(any("raw_hash" in problem for problem in problems))

    def test_wrong_profile_or_chunk_generation_fails(self):
        wrong_profile = copy.deepcopy(self.pointer)
        wrong_profile["tool_profile_hash"] = "sha256:" + "55" * 32
        problems = run_eval.pointer_attestation_problems(
            {"results": [{"evidence_pointer": wrong_profile}]}, self.attestor)
        self.assertTrue(any("profile" in problem for problem in problems))

        wrong_generation = self._publish_snapshot(gen=4)
        problems = run_eval.pointer_attestation_problems(
            {"results": [{"evidence_pointer": wrong_generation}]}, self.attestor)
        self.assertTrue(any("generation" in problem for problem in problems))

    def test_reader_rejects_oversize_and_non_regular_data(self):
        path = os.path.join(self.temp.name, "oversize.json")
        with open(path, "wb") as fh:
            fh.write(b"{}")
        with self.assertRaises(run_eval.PointerAttestationError):
            run_eval._read_json_bounded(path, 1, "test object")
        with self.assertRaises(run_eval.PointerAttestationError):
            run_eval._read_json_bounded(self.temp.name, 1024, "test object")


def _pointer(raw_hash, section_id=None, heading_path=None, path_at_commit=None):
    p = {"raw_hash": raw_hash}
    if section_id is not None:
        p["section_id"] = section_id
    if heading_path is not None:
        p["heading_path"] = heading_path
    if path_at_commit is not None:
        p["path_at_commit"] = path_at_commit
    return {"evidence_pointer": p}


class TestRecallAtK(unittest.TestCase):
    """QB24/裁定4 (step4b-contract-tests-p3b.md §B): 射影は
    (raw_hash, section, path_at_commit) の 3 要素 — リネーム前後を
    別要素として数える。
    """

    def test_half_recall(self):
        # expected 2 件、うち 1 件ヒット -> 0.5
        expected = {
            ("sha256:aaa", "回収率と精度", "doc-a.md"),
            ("sha256:ccc", "テールレイテンシ", "doc-c.md"),
        }
        response = {"results": [
            _pointer("sha256:aaa", section_id="doc-a/回収率と精度", path_at_commit="doc-a.md"),  # hit
            _pointer("sha256:zzz", section_id="noise/ノイズ", path_at_commit="noise.md"),          # miss
        ]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.5)

    def test_full_recall_via_heading_path(self):
        expected = {
            ("sha256:aaa", "回収率と精度", "doc-a.md"),
            ("sha256:bbb", "テールレイテンシ", "doc-b.md"),
        }
        response = {"results": [
            _pointer("sha256:aaa", heading_path=["Doc A", "回収率と精度"], path_at_commit="doc-a.md"),
            _pointer("sha256:bbb", heading_path=["Doc B", "テールレイテンシ"], path_at_commit="doc-b.md"),
        ]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 1.0)

    def test_zero_recall(self):
        expected = {("sha256:aaa", "回収率と精度", "doc-a.md")}
        response = {"results": [_pointer("sha256:xxx", section_id="a/b", path_at_commit="x.md")]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.0)

    def test_section_mismatch_same_raw_is_miss(self):
        # raw_hash・path 一致でも section が違えば 3 要素 key はミス
        expected = {("sha256:aaa", "回収率と精度", "doc-a.md")}
        response = {"results": [
            _pointer("sha256:aaa", section_id="a/スループットとメモリ", path_at_commit="doc-a.md")
        ]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.0)

    def test_path_at_commit_mismatch_same_raw_and_section_is_miss(self):
        # QB24 の核心: raw_hash・section が一致しても path_at_commit が
        # 違えば (リネーム前後) 別要素としてミス扱いになる。
        expected = {("sha256:aaa", "回収率と精度", "old-name.md")}
        response = {"results": [
            _pointer("sha256:aaa", section_id="a/回収率と精度", path_at_commit="new-name.md")
        ]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.0)

    def test_rename_old_and_new_path_count_as_distinct_hits(self):
        # 旧名・新名の両方が返れば、それぞれが expected の別要素として満たされる。
        expected = {
            ("sha256:aaa", "回収率と精度", "old-name.md"),
            ("sha256:aaa", "回収率と精度", "new-name.md"),
        }
        response = {"results": [
            _pointer("sha256:aaa", section_id="a/回収率と精度", path_at_commit="old-name.md"),
            _pointer("sha256:aaa", section_id="a/回収率と精度", path_at_commit="new-name.md"),
        ]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 1.0)

    def test_k_truncation(self):
        # 11 件目 (index 10) のヒットは k=10 では数えない
        noise = [_pointer(f"sha256:n{i}", section_id="x/y", path_at_commit=f"n{i}.md") for i in range(10)]
        hit = _pointer("sha256:aaa", section_id="a/回収率と精度", path_at_commit="doc-a.md")
        expected = {("sha256:aaa", "回収率と精度", "doc-a.md")}
        response = {"results": noise + [hit]}
        self.assertEqual(run_eval.recall_at_k(response, expected, k=10), 0.0)
        # k=11 なら数える
        self.assertEqual(run_eval.recall_at_k(response, expected, k=11), 1.0)

    def test_distinct_dedup(self):
        # 同一 (raw_hash, section, path_at_commit) が 2 件でも distinct 1 件として数える
        expected = {
            ("sha256:aaa", "回収率と精度", "doc-a.md"),
            ("sha256:bbb", "テールレイテンシ", "doc-b.md"),
        }
        response = {"results": [
            _pointer("sha256:aaa", section_id="a/回収率と精度", path_at_commit="doc-a.md"),
            _pointer("sha256:aaa", section_id="a/回収率と精度", path_at_commit="doc-a.md"),
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
        # QB24/裁定4: resolve_one は (raw_hash, section_id, path_at_commit) の
        # 3 要素を返す — path_at_commit は解決元の file_ そのもの。
        raw, sid, path = self.resolver.resolve_one(
            "research", "embedding-benchmark.md", "recall")
        self.assertEqual(sid, "回収率と精度")
        self.assertEqual(raw, self._expected_raw("research", "embedding-benchmark.md"))
        self.assertEqual(path, "embedding-benchmark.md")

    def test_m3_2_renamed_by_old_name(self):
        # golden は旧名 auth-spec.md で覚えている — path_at_commit も旧名になる
        # (M3-2 は --all-history でその版を recall するはずなので、この
        # 旧名こそが期待される path_at_commit)。
        raw, sid, path = self.resolver.resolve_one("research", "auth-spec.md", "api-token")
        self.assertEqual(sid, "api-トークン")
        self.assertEqual(raw, self._expected_raw("research", "auth-spec.md"))
        self.assertEqual(path, "auth-spec.md")

    def test_m3_3_deleted(self):
        raw, sid, path = self.resolver.resolve_one(
            "research", "deprecated-approach.md", "method")
        self.assertEqual(sid, "旧手法")
        self.assertEqual(raw, self._expected_raw("research", "deprecated-approach.md"))
        self.assertEqual(path, "deprecated-approach.md")

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
            for _, sid, path_at_commit in resolved:
                self.assertTrue(sid, "section_id が空")
                self.assertTrue(path_at_commit, "path_at_commit が空")
        self.assertEqual(errors, [], f"解決エラー: {errors}")


class TestClassifyOutcome(unittest.TestCase):
    def test_not_implemented_on_stderr(self):
        outcome = {
            "returncode": 1, "stdout": "",
            "stderr": '{"error_code":"KIO-E-CONFIG-NOT-IMPLEMENTED-001",'
                      '"message":"not implemented"}',
        }
        kind, resp, code, _ = run_eval.classify_outcome(outcome)
        self.assertEqual(kind, "unimplemented")
        self.assertEqual(code, "KIO-E-CONFIG-NOT-IMPLEMENTED-001")

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
                   "stderr": '{"error_code":"KIO-E-SEARCH-BOOM-001","message":"boom"}'}
        kind, resp, code, detail = run_eval.classify_outcome(outcome)
        self.assertEqual(kind, "fail")
        self.assertEqual(code, "KIO-E-SEARCH-BOOM-001")

    def test_exit0_but_garbage_is_fail(self):
        outcome = {"returncode": 0, "stdout": "not json", "stderr": ""}
        kind, resp, code, detail = run_eval.classify_outcome(outcome)
        self.assertEqual(kind, "fail")


class TestUtf8KioSubprocesses(unittest.TestCase):
    """The evaluator must not inherit Windows' active console code page."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kio-eval-utf8-")
        self.addCleanup(self.temp.cleanup)

    def test_run_search_requests_strict_utf8(self):
        completed = mock.Mock(
            returncode=0, stdout='{"message":"日本語"}', stderr="")
        with mock.patch.object(
                run_eval.subprocess, "run", return_value=completed) as invoke:
            outcome = run_eval.run_search(
                "kio", self.temp.name, "日本語の検索", ["--limit", "1"])

        self.assertEqual(outcome["stdout"], '{"message":"日本語"}')
        kwargs = invoke.call_args.kwargs
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "strict")

    def test_replay_requests_strict_utf8(self):
        completed = mock.Mock(
            returncode=0, stdout='{"message":"日本語"}', stderr="")
        with mock.patch.object(
                replay_history.subprocess, "run", return_value=completed) as invoke:
            response = replay_history.run_kio(
                "kio", self.temp.name, ["log"], corpus_dir=self.temp.name)

        self.assertEqual(response, {"message": "日本語"})
        kwargs = invoke.call_args.kwargs
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "strict")


class TestStep4EvalGates(unittest.TestCase):
    @staticmethod
    def _record(results, expected_set=None):
        if expected_set is None:
            # QB24/裁定4: 3 要素射影 (raw_hash, section, path_at_commit).
            expected_set = {
                (result["evidence_pointer"]["raw_hash"],
                 run_eval._pointer_section(result["evidence_pointer"]),
                 result["evidence_pointer"].get("path_at_commit"))
                for result in results
            }
        return {"response": {"results": results}, "expected_set": expected_set}

    def _history(self):
        history = {
            "replay": "eval/replay_history.py",
            "seed": spec.SEED,
            "scopes": list(spec.SCOPES),
            "renamed": copy.deepcopy(spec.HISTORY["renames"]),
            "edited": copy.deepcopy(spec.HISTORY["edits"]),
            "deleted": copy.deepcopy(spec.HISTORY["deletes"]),
            "verified": {},
        }
        for manifest_key in ("edited", "renamed", "deleted"):
            file_field = "old_file" if manifest_key == "renamed" else "file"
            for entry in history[manifest_key]:
                anchor = run_eval._history_anchor(entry["scope"], entry[file_field])
                entry["raw_sha256"] = hashlib.sha256(
                    spec.render_anchor(anchor).encode("utf-8")).hexdigest()
                entry["sections"] = [
                    {"slug": section["slug"], "heading": section["heading"]}
                    for section in anchor["sections"]
                ]
        for scope in spec.SCOPES:
            steps = ["baseline"]
            if any(item["scope"] == scope for item in spec.HISTORY["edits"]):
                steps.append("edit")
            if any(item["scope"] == scope for item in spec.HISTORY["renames"]):
                steps.append("rename")
            if any(item["scope"] == scope for item in spec.HISTORY["deletes"]):
                steps.append("delete")
            count = 2 * len(steps)
            history["verified"][scope] = {
                "steps": steps,
                "commit_count": count,
                "messages": run_eval._expected_history_messages(scope),
            }
        return history

    def test_history_manifest_structure_accepts_exact_and_rejects_stale(self):
        history = self._history()
        self.assertEqual(run_eval.validate_history_manifest(history), [])
        stale = copy.deepcopy(history)
        stale["seed"] += 1
        stale["verified"].pop(spec.SCOPES[-1])
        problems = run_eval.validate_history_manifest(stale)
        self.assertTrue(any("seed" in problem for problem in problems))
        self.assertTrue(any("scope set" in problem for problem in problems))

        corrupt = copy.deepcopy(history)
        corrupt["edited"][0]["raw_sha256"] = "not-a-hash"
        corrupt["renamed"][0]["sections"][0]["slug"] = "stale"
        corrupt["verified"][spec.SCOPES[0]]["messages"][0] = "wrong"
        problems = run_eval.validate_history_manifest(corrupt)
        self.assertTrue(any("raw_sha256" in problem for problem in problems))
        self.assertTrue(any("sections" in problem for problem in problems))
        self.assertTrue(any("messages" in problem for problem in problems))

    def test_head_only_point_eight_one_two_five_cannot_false_pass_m3_2(self):
        history = self._history()
        # The aggregate score 13/16 = .8125 clears the numeric threshold, but none
        # of the three edited-away old identities appears.
        self.assertGreaterEqual(13 / 16, run_eval.RECALL_TARGET)
        coverage = run_eval.assess_history_coverage({"M3-2": []}, history)
        self.assertEqual(len(coverage["edited_old_missing"]), 3)
        self.assertFalse(coverage["passes_m3_2"])

    def test_all_edited_old_identities_are_required(self):
        history = self._history()
        results = []
        for entry in history["edited"]:
            results.append(_pointer("sha256:" + entry["raw_sha256"], section_id="x/y"))
        coverage = run_eval.assess_history_coverage(
            {"M3-2": [self._record(results)]}, history)
        self.assertEqual(coverage["edited_old_missing"], [])

        noise = run_eval.assess_history_coverage(
            {"M3-2": [self._record(results, {("sha256:other", "y", None)})]}, history)
        self.assertEqual(len(noise["edited_old_missing"]), 3)

    def test_rename_requires_old_and_new_snapshot_paths_with_current_alias(self):
        history = self._history()
        responses = []
        for entry in history["renamed"]:
            raw_hash = "sha256:" + entry["raw_sha256"]
            results = []
            for path_at_commit in (entry["old_file"], entry["new_file"]):
                result = _pointer(raw_hash, section_id="x/y")
                result["evidence_pointer"]["path_at_commit"] = path_at_commit
                result["current_paths"] = [entry["new_file"]]
                result["current_path"] = entry["new_file"]
                results.append(result)
            responses.append(self._record(results))
        coverage = run_eval.assess_history_coverage(
            {"M3-2": responses}, history)
        self.assertEqual(coverage["rename_failures"], [])

        responses[0]["response"]["results"][0]["current_paths"] = [
            history["renamed"][0]["old_file"]]
        stale = run_eval.assess_history_coverage(
            {"M3-2": responses}, history)
        self.assertTrue(stale["rename_failures"])

    def test_every_deleted_identity_is_required(self):
        history = self._history()
        results = [
            _pointer("sha256:" + entry["raw_sha256"], section_id="x/y")
            for entry in history["deleted"]
        ]
        coverage = run_eval.assess_history_coverage(
            {"M3-3": [self._record(results)]}, history)
        self.assertEqual(coverage["deleted_missing"], [])
        self.assertTrue(coverage["passes_m3_3"])

        incomplete = run_eval.assess_history_coverage(
            {"M3-3": [self._record(results[:-1])]}, history)
        self.assertEqual(len(incomplete["deleted_missing"]), 1)
        self.assertFalse(incomplete["passes_m3_3"])

    def test_evidence_fields(self):
        bad = {"results": [_pointer("sha256:a", section_id="x/y")]}
        self.assertTrue(run_eval.evidence_problems(bad))
        pointer = {
            "schema_version": 1,
            "commit": "sha256:c",
            "raw_hash": "sha256:r",
            "tool_profile_hash": "sha256:t",
            "chunk_hash": "sha256:h",
            "scope_id": "scope_1",
        }
        self.assertEqual(run_eval.evidence_problems(
            {"results": [{"evidence_pointer": pointer}]}), [])

    def test_scenario_specific_latency_boundaries(self):
        self.assertEqual(run_eval.percentile_nearest_rank([1, 2, 3, 4, 5], .95), 5)
        self.assertEqual(run_eval.LATENCY_TARGET_MS, {
            "M3-1": 5_000.0,
            "M3-2": 7_000.0,
            "M3-3": 7_000.0,
        })
        self.assertTrue(run_eval.passes_latency_target("M3-1", 4_999.9))
        self.assertFalse(run_eval.passes_latency_target("M3-1", 5_000.0))
        for scenario in ("M3-2", "M3-3"):
            self.assertTrue(run_eval.passes_latency_target(scenario, 6_999.9))
            self.assertFalse(run_eval.passes_latency_target(scenario, 7_000.0))
        self.assertFalse(run_eval.passes_latency_target("M3-1", None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
