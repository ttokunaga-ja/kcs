#!/usr/bin/env python3
"""V3a の補助計器: 近傍一致率の低下が「劣化」なのか「同点の入れ替わり」なのか。

[`v3_mrl.py`](v3_mrl.py) の主計器は上位 k 近傍の **集合の重なり**を数える。これは
集合が変わったことは検出できるが、**変わったことの重み**を区別できない —

- 10 位と 11 位が cos 0.30 と 0.05 で離れているのに入れ替わった (本物の劣化)
- 10 位と 11 位が cos 0.3004 と 0.3001 で並んでいて入れ替わった (同点の揺れ)

の 2 つが同じ「overlap 0.9」になる。判断表の 0.95 / 0.85 という閾値は暗黙に
**近傍が分離しているコーパス**を前提しているので、その前提が成り立っているかを
測っておかないと、閾値を割った数字が何を意味するのか決まらない。

## 測る 2 つ

**(a) native 側の上位 k 境界のギャップ** — `cos@k - cos@k+1`。
これが小さいコーパスでは、幅を変えなくても (たとえば f32 の丸めだけでも)
集合は揺れる。**コーパスの性質であって切り詰めの効果ではない。**

**(b) 実際に失った類似度** — native 空間で測った
`mean(cos(i, native の上位k)) - mean(cos(i, 768 の上位k))`。
「768 が選んだ 10 件は、native が選んだ 10 件よりどれだけ悪いか」を
**native 空間を正として**問う。(a) が小さく (b) も小さいなら、集合は
入れ替わっているが取ってくるものの質は変わっていない。

`--cache` は `v3_mrl.py` と同じ埋め込みを使い回すためのもの。無ければ作る。
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = (".md", ".txt", ".rst")
DEFAULT_MODEL = "Qwen/Qwen3-VL-Embedding-2B"


def embed_one(base_url: str, model: str, text: str, timeout: float) -> list[float]:
    """`v3_mrl.py::embed_one` と同一。07 §5.3 (2) の `messages` 形式。"""
    payload = {
        "model": model,
        "encoding_format": "float",
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    return [float(value) for value in body["data"][0]["embedding"]]


def truncate_and_renormalize(vector: list[float], width: int) -> list[float]:
    head = vector[:width]
    norm = math.sqrt(sum(value * value for value in head))
    if not math.isfinite(norm) or norm <= 0.0:
        raise RuntimeError("truncation produced a zero or non-finite vector")
    return [value / norm for value in head]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def collect_passages(corpus: Path, max_chars: int, limit: int) -> list[tuple[str, str]]:
    """`v3_mrl.py::collect_passages` と同一の収集規則 (1 ファイル = 1 passage)。"""
    passages: list[tuple[str, str]] = []
    for path in sorted(corpus.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        text = text.strip()
        if len(text) < 40:
            continue
        passages.append((str(path.relative_to(corpus)), text[:max_chars]))
        if len(passages) >= limit:
            break
    return passages


def ranked_neighbours(vectors: list[list[float]], index: int) -> list[tuple[float, int]]:
    scored = [
        (cosine(vectors[index], vectors[other]), other)
        for other in range(len(vectors))
        if other != index
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return scored


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--max-chars", type=int, default=4000)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--cache", type=Path, help="native ベクトルの使い回し先")
    parser.add_argument("--out", type=Path, default=Path("v3-tie-diagnostic.json"))
    args = parser.parse_args()

    passages = collect_passages(args.corpus, args.max_chars, args.limit)
    if len(passages) < 20:
        print(f"[stop] {args.corpus} からは {len(passages)} 件しか取れなかった。", file=sys.stderr)
        return 1

    if args.cache and args.cache.exists():
        raw = json.loads(args.cache.read_text(encoding="utf-8"))
        if len(raw) != len(passages):
            print("[stop] cache の件数がコーパスと一致しない。", file=sys.stderr)
            return 1
        print(f"[1/2] cache から {len(raw)} passages …", flush=True)
    else:
        print(f"[1/2] {len(passages)} passages を埋め込む …", flush=True)
        raw = []
        for index, (path, text) in enumerate(passages, start=1):
            try:
                raw.append(embed_one(args.base_url, args.model, text, args.timeout))
            except (urllib.error.URLError, RuntimeError, TimeoutError) as error:
                print(f"[stop] {path}: {error}", file=sys.stderr)
                return 1
            if index % 25 == 0:
                print(f"      {index}/{len(passages)}", flush=True)
        if args.cache:
            args.cache.write_text(json.dumps(raw), encoding="utf-8")

    native_width = len(raw[0])
    if native_width <= args.width:
        print(f"[stop] native 幅 {native_width} が切り詰め先以下。", file=sys.stderr)
        return 1

    native = [truncate_and_renormalize(vector, native_width) for vector in raw]
    narrow = [truncate_and_renormalize(vector, args.width) for vector in raw]

    print(f"[2/2] 同点性の診断 (k={args.k}) …", flush=True)
    k = args.k
    gaps: list[float] = []
    forfeited: list[float] = []
    overlaps: list[float] = []
    for index in range(len(native)):
        wide_ranked = ranked_neighbours(native, index)
        thin_ranked = ranked_neighbours(narrow, index)
        wide = [other for _, other in wide_ranked[:k]]
        thin = [other for _, other in thin_ranked[:k]]
        overlaps.append(len(set(wide) & set(thin)) / k)
        gaps.append(wide_ranked[k - 1][0] - wide_ranked[k][0])
        # 「768 が選んだ集合は native 空間でどれだけ劣るか」。正は native 空間。
        native_cos = {other: value for value, other in wide_ranked}
        forfeited.append(
            sum(native_cos[other] for other in wide) / k
            - sum(native_cos[other] for other in thin) / k
        )

    def stats(values: list[float]) -> dict[str, float]:
        ordered = sorted(values)
        return {
            "median": statistics.median(values),
            "mean": statistics.mean(values),
            "p90": ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))],
            "max": max(values),
        }

    tight = sum(1 for gap in gaps if gap < 0.01)
    result: dict[str, Any] = {
        "base_url": args.base_url,
        "model": args.model,
        "corpus": str(args.corpus),
        "passages": len(passages),
        "native_dimensions": native_width,
        "truncated_dimensions": args.width,
        "k": k,
        "mean_overlap": statistics.mean(overlaps),
        "native_boundary_gap": stats(gaps),
        "similarity_forfeited": stats(forfeited),
        "tied_passages": {
            "threshold": 0.01,
            "count": tight,
            "of": len(passages),
            "ratio": tight / len(passages),
        },
    }
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n[ok] {args.out}\n")
    print(f"  近傍一致率 (k={k})            mean {result['mean_overlap']:.4f}")
    print(
        f"  native 上位{k}境界のギャップ    median {result['native_boundary_gap']['median']:.5f}"
        f"  p90 {result['native_boundary_gap']['p90']:.5f}"
    )
    print(
        f"  失った類似度 (native 空間)   median {result['similarity_forfeited']['median']:.5f}"
        f"  max {result['similarity_forfeited']['max']:.5f}"
    )
    print(
        f"  境界ギャップ < 0.01 の passage  {tight}/{len(passages)}"
        f" ({100 * tight / len(passages):.0f}%)\n"
    )
    print(
        "  境界ギャップと失った類似度がともに小さいなら、overlap の低下は\n"
        "  同点の入れ替わりであって近傍構造の破壊ではない。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
