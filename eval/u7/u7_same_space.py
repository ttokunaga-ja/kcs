#!/usr/bin/env python3
"""U7: serving 経路が image と text を**同じ空間**へ埋め込んでいるかを、参照実装との
数値一致で確かめる受け入れ検査。

出力は `u7-same-space.json`。

## なぜ互換ゲートでは足りないのか

llama.cpp Discussion #14851 (jina-embeddings-v4) の実測は

> text embeddings matched perfectly, **image embeddings diverged significantly**

だった。この失敗モードは **[03 §7](../../docs/03-data-model.md) の互換ゲートが原理的に
検知できない** — 次元も distance metric も modality も `profile_hash` も、すべて一致
するからである。しかも embedding は content-addressed identity を持ち
first-instance-wins で永続化されるので、**誤った空間の画像ベクトルが恒久的に凍結
される**。取り消すには再埋め込みしかない。

したがって serving 経路の採用条件は「動くこと」ではなく **参照実装との数値一致**である
(`tasks/local-adapter-plan.md` §2 / Stage 2 の U7)。vLLM は公式サポートなので優先度が
下がるが、**llama.cpp 経路を採るなら必須**。

## text は対照群である — ここが本検査の設計の核

報告された失敗は「text は合う・image だけずれる」だった。したがって:

- **text が一致 かつ image が一致** → 採用してよい
- **text が一致 かつ image が不一致** → **これが探している欠陥**。採用しない
- **text が不一致** → serving 経路の判定ではなく、**この計器の側が壊れている**。
  参照ハーネスの描画・pooling・正規化が serving 側と揃っていない疑いを先に潰すこと。
  この状態で image の数字を読んではいけない

3 つ目を独立した結論として出すのが重要である。参照実装を組むときに chat template の
描画や pooling を取り違えるのは容易で (V4 は `/tokenize` の `add_generation_prompt`
で実際に踏んだ)、それを「serving 経路が壊れている」と誤診すると、健全な経路を捨てるか、
壊れた経路を通してしまう。

## serving 側は Kio と同一の wire で送る

`crates/kio-adapter/src/local_embedding.rs` と同形にしてある:

    POST {base_url}/v1/embeddings
    {"model": …, "encoding_format": "float", "messages": [{"role":"user","content":[…]}]}

    text  → [{"type":"text","text": …}]
    image → [{"type":"image_url","image_url":{"url":"data:{mime};base64,{…}"}}]

**ここを変えると測る意味が無くなる。** V4 は wire 形式を変えるだけで
`cos(input[] 経由, messages 経由) = 0.4740` になることを実測しており、これは無関係な
2 文の 0.5966 より遠い。計器が本番と違う形で送れば、serving 経路ではなく wire の差を
測ることになる。

## MRL 切り詰めは判定に使わない

Kio は 768 へ切り詰めて再正規化するが、本検査は **native 次元のまま**比較する。
切り詰めは決定的な後処理であって、空間が違うことを直せないし作りもしない。
切り詰め後の一致は参考として併記する。
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import mimetypes
import statistics
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "Qwen/Qwen3-VL-Embedding-2B"

# U2 は同一ランタイム内での参照計算に対し cos 0.999999994 (最大絶対差 7e-9 = f32 の
# 丸め) を実測した。本検査はランタイムをまたぐので、カーネルの違いでそこまでは寄らない。
# 一方で捕まえたい欠陥は「significantly diverged」と表現された水準である。
# 0.999 はその間に置いた既定値であって、実測された境界ではない。
#
# **0.99〜0.999 に着地したら「惜しい」ではなく裁定対象である。** 参照ハーネスの
# 不一致なのか経路の欠陥なのかを切り分けるまで、採用の可否を決めないこと。
DEFAULT_THRESHOLD = 0.999


def cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


# --- 判定 (純関数。モデル無しで試験できる) ----------------------------------


def verdict(
    text_scores: list[float], image_scores: list[float], threshold: float
) -> dict[str, Any]:
    """モダリティごとに独立に判定する。

    **合算した 1 つの数字を出してはいけない。** 探している欠陥は片方だけがずれる
    形なので、平均すると text の良さが image の悪さを薄めて隠す — 検知したい当の
    ものを、計器が自分で消すことになる。
    """
    if not text_scores:
        return {
            "adoptable": False,
            "reason": "harness-unusable",
            "detail": "text の対照群が空。判定できない",
        }

    text_min = min(text_scores)
    text_ok = text_min >= threshold
    image_min = min(image_scores) if image_scores else None
    image_ok = bool(image_scores) and image_min >= threshold

    if not text_ok:
        # serving 経路の判定を出さない。対照群が落ちている以上、image の数字は
        # 経路の性質を表していない。
        return {
            "adoptable": False,
            "reason": "harness-suspect",
            "detail": (
                f"text の一致が閾値を下回った (min {text_min:.6f} < {threshold})。"
                "報告されている失敗モードは text が合って image がずれる形なので、"
                "text が合わないのは参照ハーネス側の疑いが濃い。描画・pooling・"
                "正規化が serving 側と揃っているかを先に確かめること。"
                "**この状態で image の数字を読まない。**"
            ),
        }

    if not image_scores:
        return {
            "adoptable": False,
            "reason": "image-not-measured",
            "detail": "text は一致したが image を 1 件も測っていない。判定は未完了",
        }

    if not image_ok:
        return {
            "adoptable": False,
            "reason": "image-diverged",
            "detail": (
                f"text は一致 (min {text_min:.6f}) しているのに image が閾値を"
                f"下回った (min {image_min:.6f} < {threshold})。"
                "**これが U7 が存在する理由の欠陥そのものである** — 互換ゲートは "
                "次元も distance も profile_hash も一致するため検知しない。"
                "この経路を採用してはならない。既に埋めたベクトルがあれば、"
                "first-instance-wins で凍結されているので再埋め込みが要る。"
            ),
        }

    return {
        "adoptable": True,
        "reason": "both-agree",
        "detail": (
            f"text min {text_min:.6f} / image min {image_min:.6f}、"
            f"いずれも閾値 {threshold} 以上"
        ),
    }


def summarize(scores: list[float]) -> dict[str, Any]:
    if not scores:
        return {"count": 0}
    return {
        "count": len(scores),
        "min": min(scores),
        "mean": statistics.fmean(scores),
        "max": max(scores),
    }


# --- serving 側 (Kio と同一の wire) ------------------------------------------


def text_content(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]


def image_content(path: Path) -> list[dict[str, Any]]:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return [{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}]


def embed_served(
    base_url: str, model: str, content: list[dict[str, Any]], timeout: float
) -> list[float]:
    payload = {
        "model": model,
        "encoding_format": "float",
        "messages": [{"role": "user", "content": content}],
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["data"][0]["embedding"]


# --- 参照側 (PyTorch) ---------------------------------------------------------


def load_reference(model_id: str):
    """transformers の参照実装を読む。

    ここが「serving 経路が正しいか」を決める基準になるので、**読めなかったことを
    黙って握り潰さない**。落ちた理由をそのまま呼出元へ返す。
    """
    try:
        import torch  # noqa: F401
        from transformers import AutoModel, AutoProcessor
    except ImportError as error:
        raise SystemExit(
            f"[stop] 参照実装に torch / transformers が要る: {error}\n"
            "       U7 は『参照実装との数値一致』が採用条件なので、"
            "参照が無いままでは判定できない。"
        ) from error
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModel.from_pretrained(model_id, trust_remote_code=True).eval()
    return processor, model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--images",
        type=Path,
        default=Path("experiments/ocr-verification/fixtures/generated-images"),
        help="画像 fixture のディレクトリ",
    )
    parser.add_argument(
        "--texts",
        type=Path,
        default=None,
        help="1 行 1 passage のテキスト。既定は下記の内蔵 5 本",
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", type=Path, default=Path("u7-same-space.json"))
    parser.add_argument(
        "--served-only",
        action="store_true",
        help="参照実装を読まず serving 側だけ取る (配線確認用。判定は出ない)",
    )
    args = parser.parse_args()

    texts = (
        [line for line in args.texts.read_text(encoding="utf-8").splitlines() if line.strip()]
        if args.texts
        else [
            "四半期の設計レビューで決まった保持期間の方針",
            "The invoice total did not match the purchase order.",
            "ホワイトボードに書いた移行手順の下書き",
            "Terminal output showing a failed migration step.",
            "会議で合意した次のマイルストーンの締め切り",
        ]
    )
    images = sorted(p for p in args.images.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
    if not images:
        print(f"[stop] {args.images} に画像が無い", file=sys.stderr)
        return 1
    print(f"[1/3] text {len(texts)} 本 / image {len(images)} 枚", flush=True)

    served_text = [embed_served(args.base_url, args.model, text_content(t), args.timeout) for t in texts]
    served_image = [embed_served(args.base_url, args.model, image_content(p), args.timeout) for p in images]
    print(f"[2/3] serving 側を取得 (native {len(served_text[0])} 次元)", flush=True)

    result: dict[str, Any] = {
        "base_url": args.base_url,
        "model": args.model,
        "threshold": args.threshold,
        "native_dimensions": len(served_text[0]),
        "texts": len(texts),
        "images": [p.name for p in images],
    }

    if args.served_only:
        result["verdict"] = {
            "adoptable": False,
            "reason": "reference-not-run",
            "detail": "--served-only は配線確認のためのもので、採用判定ではない",
        }
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[3/3] {args.out} (判定なし)")
        return 0

    processor, model = load_reference(args.model)
    print("[3/3] 参照実装と比較 …", flush=True)
    reference_text = [reference_embed(processor, model, text=t) for t in texts]
    reference_image = [reference_embed(processor, model, image=p) for p in images]

    text_scores = [cosine(a, b) for a, b in zip(served_text, reference_text)]
    image_scores = [cosine(a, b) for a, b in zip(served_image, reference_image)]
    result["text_agreement"] = summarize(text_scores)
    result["image_agreement"] = summarize(image_scores)
    result["verdict"] = verdict(text_scores, image_scores, args.threshold)

    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["verdict"], ensure_ascii=False, indent=2))
    return 0 if result["verdict"]["adoptable"] else 2


def reference_embed(processor, model, *, text: str | None = None, image: Path | None = None) -> list[float]:
    """参照実装で 1 件埋め込む。

    **描画は serving 側と揃えること。** ここがずれていると、経路の欠陥ではなく
    ハーネスの差を測ることになる。揃っているかは text の一致率が答える
    (揃っていなければ text も落ちる) ので、`verdict` はそれを独立した結論として扱う。
    """
    import torch

    if (text is None) == (image is None):
        raise ValueError("text か image のどちらか一方を渡すこと")
    if text is not None:
        messages = [{"role": "user", "content": [{"type": "text", "text": text}]}]
        inputs = processor.apply_chat_template(
            messages, add_generation_prompt=False, tokenize=True, return_tensors="pt",
            return_dict=True,
        )
    else:
        messages = [{"role": "user", "content": [{"type": "image", "image": str(image)}]}]
        inputs = processor.apply_chat_template(
            messages, add_generation_prompt=False, tokenize=True, return_tensors="pt",
            return_dict=True,
        )
    with torch.no_grad():
        output = model(**inputs)
    vector = output.last_hidden_state[0, -1] if hasattr(output, "last_hidden_state") else output[0][0, -1]
    return [float(v) for v in vector]


if __name__ == "__main__":
    raise SystemExit(main())
