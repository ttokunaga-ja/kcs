"""U7 受け入れ検査の純ロジック試験。

モデルもサーバも要らない部分だけを固定する。数値一致そのものは GPU 実機での
実行 (`eval/u7/README.md`) でしか確かめられないが、**判定の形**はここで守る。
"""

from __future__ import annotations

import base64
import importlib.util
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "u7_same_space", Path(__file__).parent / "u7" / "u7_same_space.py"
)
u7 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(u7)


class VerdictTests(unittest.TestCase):
    """`verdict` はモダリティごとに独立に結論を出す。"""

    def test_both_modalities_agree_is_adoptable(self):
        result = u7.verdict([0.9999, 0.99995], [0.9999, 0.9999], 0.999)
        self.assertTrue(result["adoptable"])
        self.assertEqual(result["reason"], "both-agree")

    def test_text_agrees_and_image_diverges_is_the_defect_u7_exists_for(self):
        # llama.cpp #14851 の実測そのもの: text は一致、image だけ乖離。
        result = u7.verdict([0.99999, 0.99998], [0.87, 0.91], 0.999)
        self.assertFalse(result["adoptable"])
        self.assertEqual(result["reason"], "image-diverged")
        # 判定文は「採用してはならない」と、既に埋めた分の再埋め込みが要ることに
        # 触れていなければならない — 互換ゲートが検知しないので、読み手がここで
        # 気付かないと誤った空間が恒久凍結される。
        self.assertIn("採用してはならない", result["detail"])
        self.assertIn("再埋め込み", result["detail"])

    def test_text_disagreeing_blames_the_harness_not_the_serving_path(self):
        # 対照群が落ちている以上、image の数字は経路の性質を表していない。
        result = u7.verdict([0.61], [0.60], 0.999)
        self.assertFalse(result["adoptable"])
        self.assertEqual(result["reason"], "harness-suspect")
        self.assertIn("参照ハーネス", result["detail"])
        # 経路の欠陥だと断定してはいけない。
        self.assertNotEqual(result["reason"], "image-diverged")

    def test_no_images_is_incomplete_not_a_pass(self):
        result = u7.verdict([0.9999], [], 0.999)
        self.assertFalse(result["adoptable"])
        self.assertEqual(result["reason"], "image-not-measured")

    def test_no_texts_is_unusable_because_the_control_is_missing(self):
        result = u7.verdict([], [0.9999], 0.999)
        self.assertFalse(result["adoptable"])
        self.assertEqual(result["reason"], "harness-unusable")

    def test_a_good_text_score_must_not_average_away_a_bad_image_score(self):
        """**この検査の設計の核**: モダリティを跨いで合算しない。

        合算すると、探している欠陥 (片方だけずれる) を計器が自分で消す。
        下記は全 6 件の平均が閾値を超えるのに image は落ちている構成で、
        平均を採る実装に変えると必ずここが落ちる。
        """
        text_scores = [1.0, 1.0, 1.0, 1.0]
        image_scores = [0.98]
        pooled = sum(text_scores + image_scores) / len(text_scores + image_scores)
        self.assertGreater(pooled, 0.99, "前提: 合算すると 0.99 を超える構成であること")
        result = u7.verdict(text_scores, image_scores, 0.99)
        self.assertFalse(result["adoptable"])
        self.assertEqual(result["reason"], "image-diverged")

    def test_the_worst_case_decides_not_the_average_within_a_modality(self):
        # モダリティ内でも平均ではなく最小で判定する。1 枚でも別空間なら、
        # その 1 枚のベクトルが凍結される。
        result = u7.verdict([0.9999], [0.9999, 0.9999, 0.5], 0.999)
        self.assertFalse(result["adoptable"])
        self.assertEqual(result["reason"], "image-diverged")


class WireTests(unittest.TestCase):
    """serving 側の wire は `local_embedding.rs` と同形でなければならない。"""

    def test_text_content_matches_the_adapter_shape(self):
        self.assertEqual(
            u7.text_content("こんにちは"),
            [{"type": "text", "text": "こんにちは"}],
        )

    def test_image_content_is_a_base64_data_uri_like_the_adapter_builds(self):
        with self.subTest("png"):
            path = Path(__file__).parent.parent / (
                "experiments/ocr-verification/fixtures/generated-images/g1_chat_03.png"
            )
            self.assertTrue(path.exists(), "fixture が消えている")
            content = u7.image_content(path)
            self.assertEqual(len(content), 1)
            self.assertEqual(content[0]["type"], "image_url")
            expected = base64.b64encode(path.read_bytes()).decode("ascii")
            self.assertEqual(
                content[0]["image_url"]["url"], f"data:image/png;base64,{expected}"
            )


class CosineTests(unittest.TestCase):
    def test_identical_vectors_are_one(self):
        self.assertAlmostEqual(u7.cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0)

    def test_orthogonal_vectors_are_zero(self):
        self.assertAlmostEqual(u7.cosine([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_a_zero_vector_does_not_divide_by_zero(self):
        self.assertEqual(u7.cosine([0.0, 0.0], [1.0, 1.0]), 0.0)


class SummarizeTests(unittest.TestCase):
    def test_empty_reports_a_zero_count_rather_than_absent_keys(self):
        self.assertEqual(u7.summarize([]), {"count": 0})

    def test_reports_min_so_the_worst_case_is_visible(self):
        summary = u7.summarize([0.5, 0.9, 1.0])
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["min"], 0.5)
        self.assertEqual(summary["max"], 1.0)


if __name__ == "__main__":
    unittest.main()
