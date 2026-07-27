#!/usr/bin/env python3
"""V3: MRL 切り詰め (native → 768) が検索品質をどれだけ落とすか測る。

`tasks/local-adapter-plan.md` の **V3**。決めるのは
`fts.rs::CHUNK_VEC_DIMENSIONS` / `local_embedding.rs::LOCAL_EMBEDDING_DIMENSIONS`
を 768 のままにするか native (実測 2048) へ動かすか。**動かすと `chunk_vec` の
DDL 改訂と全再埋め込みを伴う**ので、実測なしに動かさない。

## なぜこれが安く済むのか

**比べるのは同じ native ベクトルの 2 つの切り詰めである。** サーバへは 1 回しか
投げず、返ってきた 2048 次元から 768 版を導出する。したがって chunk の切り方も、
入力構築 (`chunk_filename_context_v1` の humanize) も、instruction も、**両側で
完全に相殺される**。V3 が答えるのは「幅を削ると近傍が壊れるか」だけであり、
その問いに対してこれらは交絡しない。

同じ理由で **Kio のビルドも fixture の再構築も要らない**。要るのは
「Kio が入れるような文章」と GPU 上の vLLM だけ。

## 2 つの計器

**(1) 近傍の一致率 (正解ラベル不要・常に測る)**
各 passage の上位 k 近傍を 2048 と 768 で出し、重なりを見る。
「幅を削ると誰の隣に誰が居るかが変わるか」を直接測る。**これが主計器**である
— ラベルが要らないので、どんなコーパスでも回せる。

**(2) recall@k (`--queries` を渡したときだけ)**
golden query の正解 passage が上位 k に入るかを両幅で測り、差を出す。
`eval/golden-queries-*.jsonl` の形式 (`query` と、正解を指す `expected` 系の
フィールド) を受ける。**こちらは正解ラベルのあるコーパスでしか回せない**。

## 判断の目安

近傍一致率 (k=10) が

- **0.95 以上** → 768 で問題ない。`dimensions` は動かさない
- **0.85 未満** → native への移行を検討する材料になる。ただし移行は全再埋め込みを
  伴うので、この時点で 24 問 fixture による recall 実測 (V3b、実費 $1.21) へ進む
- **その間** → 曖昧帯。同じく V3b へ

数字だけで決めない。**`dimensions` は `tool_profile_hash` の入力**なので、
動かした瞬間に既存ベクトルは全て 03 §7 の互換ゲートに弾かれる。

## 使い方

    vllm serve Qwen/Qwen3-VL-Embedding-2B --runner pooling --host 127.0.0.1 --port 8000

    python3 eval/v3/v3_mrl.py --corpus ~/kcs-baseline-corpus --out v3-mrl.json

`--corpus` には Kio が扱うような文章のディレクトリを渡す。24 問 fixture の
原本 (`~/kcs-baseline-corpus`) がそのまま使えるが、無ければ `docs/` でもよい —
測っているのは幅の効果であってコーパスの絶対性能ではない。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = (".md", ".txt", ".rst")
DEFAULT_MODEL = "Qwen/Qwen3-VL-Embedding-2B"


# --- 埋め込み ---------------------------------------------------------------


def embed_one(base_url: str, model: str, text: str, timeout: float) -> list[float]:
    """07 §5.3 (2) の `messages` 形式で 1 件送る。

    Kio の実装 (`local_embedding.rs`) と同じ形にしてある — system message は
    送らず、`content` は配列。V4 が実測したのはこの描画である。
    """
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
    data = body.get("data")
    if not isinstance(data, list) or len(data) != 1:
        raise RuntimeError(f"expected exactly 1 vector, got {data!r}")
    vector = data[0].get("embedding")
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("response entry carries no embedding")
    return [float(value) for value in vector]


def truncate_and_renormalize(vector: list[float], width: int) -> list[float]:
    """`local_embedding.rs::truncate_and_renormalize` と同じ処理。

    再正規化は飾りではない。サーバは native 幅で L2 ≈ 1 を返すので、先頭 width の
    prefix は**短い** — しかも短さの度合いはベクトルごとに違う。正規化せずに
    比べると cosine が「そのベクトルの質量が切り口より先にどれだけ乗っていたか」に
    依存し、それは文章の性質ではない。
    """
    if len(vector) < width:
        raise RuntimeError(f"vector is {len(vector)} wide, narrower than {width}")
    head = vector[:width]
    norm = math.sqrt(sum(value * value for value in head))
    if not math.isfinite(norm) or norm <= 0.0:
        raise RuntimeError("truncation produced a zero or non-finite vector")
    return [value / norm for value in head]


def cosine(left: list[float], right: list[float]) -> float:
    """両方とも単位ベクトルなので内積でよい。"""
    return sum(a * b for a, b in zip(left, right))


# --- 計器 (1) 近傍の一致率 ---------------------------------------------------


def top_k_neighbours(vectors: list[list[float]], index: int, k: int) -> list[int]:
    scored = [
        (cosine(vectors[index], vectors[other]), other)
        for other in range(len(vectors))
        if other != index
    ]
    # 同点は index 昇順で決め、幅を変えただけで順序が揺れないようにする。
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [other for _, other in scored[:k]]


def neighbour_agreement(
    native: list[list[float]], truncated: list[list[float]], k: int
) -> dict[str, Any]:
    overlaps: list[float] = []
    top1_same = 0
    for index in range(len(native)):
        wide = top_k_neighbours(native, index, k)
        narrow = top_k_neighbours(truncated, index, k)
        if not wide:
            continue
        overlaps.append(len(set(wide) & set(narrow)) / len(wide))
        if wide[0] == narrow[0]:
            top1_same += 1
    if not overlaps:
        return {"measured": False}
    return {
        "measured": True,
        "passages": len(overlaps),
        "k": k,
        "mean_overlap": sum(overlaps) / len(overlaps),
        "min_overlap": min(overlaps),
        "top1_agreement": top1_same / len(overlaps),
    }


# --- 計器 (2) recall@k -------------------------------------------------------


def load_queries(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def expected_paths(row: dict[str, Any]) -> list[str]:
    """golden query の正解 path を取り出す。

    `eval/golden-queries-*.jsonl` の `expected` は
    `[{"path": "...", "file": "..."}]` の形。素の文字列リストも受ける。
    """
    value = row.get("expected")
    if isinstance(value, str) and value:
        return [value]
    if not isinstance(value, list):
        return []
    paths = []
    for item in value:
        if isinstance(item, dict):
            path = item.get("path") or item.get("file")
            if path:
                paths.append(str(path))
        elif isinstance(item, str) and item:
            paths.append(item)
    return paths


def recall_at_k(
    vectors: list[list[float]],
    passage_paths: list[str],
    queries: list[tuple[str, list[str]]],
    query_vectors: list[list[float]],
    k: int,
) -> dict[str, Any]:
    # 正解 passage がそもそも収集対象に入っていない query を先に落とす。
    # 落とさないと「切り詰めのせいで当たらない」と「そもそも候補に無い」が
    # 同じ低い recall として出てきて、計器が黙って嘘をつく。
    answerable = [
        (pair, vector)
        for pair, vector in zip(queries, query_vectors)
        if pair[1] and any(any(want in path for path in passage_paths) for want in pair[1])
    ]
    if len(answerable) < max(1, len(queries) // 2):
        return {
            "measured": False,
            "answerable": len(answerable),
            "queries": len(queries),
            "note": "正解 passage の過半がコーパスに存在しない。golden query の正解は "
            "大半が .pdf/.docx/.pptx/.png で、OCR 済みの本文が要る — 生の "
            "コーパスではなく index 済み fixture から取り出した Markdown を "
            "--corpus に渡すこと。",
        }

    hits = 0
    scored_total = 0
    misses: list[str] = []
    for (text, expected), query_vector in answerable:
        scored_total += 1
        ranked = sorted(
            range(len(vectors)),
            key=lambda index: (-cosine(query_vector, vectors[index]), index),
        )[:k]
        found = {passage_paths[index] for index in ranked}
        # 正解は path の一部一致で判定する — golden query は
        # `<persona>/home/...` のような相対表記を持つため。
        if any(any(want in path for path in found) for want in expected):
            hits += 1
        else:
            misses.append(text)
    if scored_total == 0:
        return {"measured": False, "note": "no query carried an expected answer"}
    return {
        "measured": True,
        "queries": scored_total,
        "k": k,
        "recall": hits / scored_total,
        "misses": misses[:10],
    }


# --- 収集 -------------------------------------------------------------------


def collect_passages(corpus: Path, max_chars: int, limit: int) -> list[tuple[str, str]]:
    """1 ファイル = 1 passage。chunk 分割は**あえてしない**。

    V3 が比べるのは同じベクトルの 2 つの幅なので、分割規則は両側で相殺される。
    Kio の chunker を移植しても答えは変わらず、ずれる余地だけが増える。
    """
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--queries", type=Path, help="golden query の jsonl (任意)")
    parser.add_argument("--width", type=int, default=768, help="切り詰め後の幅")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=400, help="passage 数の上限")
    parser.add_argument("--max-chars", type=int, default=4000)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", type=Path, default=Path("v3-mrl.json"))
    args = parser.parse_args()

    passages = collect_passages(args.corpus, args.max_chars, args.limit)
    if len(passages) < 20:
        print(
            f"[stop] {args.corpus} からは {len(passages)} 件しか取れなかった。"
            "近傍の一致率は母数が要る。",
            file=sys.stderr,
        )
        return 1
    print(f"[1/3] {len(passages)} passages を埋め込む …", flush=True)

    native: list[list[float]] = []
    for index, (path, text) in enumerate(passages, start=1):
        try:
            native.append(embed_one(args.base_url, args.model, text, args.timeout))
        except (urllib.error.URLError, RuntimeError, TimeoutError) as error:
            print(f"[stop] {path}: {error}", file=sys.stderr)
            return 1
        if index % 25 == 0:
            print(f"      {index}/{len(passages)}", flush=True)

    native_width = len(native[0])
    if any(len(vector) != native_width for vector in native):
        print("[stop] サーバが幅の違うベクトルを返した", file=sys.stderr)
        return 1
    if native_width <= args.width:
        print(
            f"[stop] native 幅 {native_width} が切り詰め先 {args.width} 以下。"
            "測るものがない。",
            file=sys.stderr,
        )
        return 1

    # native 側も比較のため正規化しておく (サーバは L2≈1 で返すが、丸めを揃える)。
    native = [truncate_and_renormalize(vector, native_width) for vector in native]
    truncated = [truncate_and_renormalize(vector, args.width) for vector in native]

    print(f"[2/3] 近傍の一致率 (k={args.k}) …", flush=True)
    agreement = neighbour_agreement(native, truncated, args.k)

    recall: dict[str, Any] = {"measured": False, "note": "--queries が未指定"}
    if args.queries:
        print("[3/3] recall@k …", flush=True)
        rows = load_queries(args.queries)
        queries = [(str(row.get("query", "")), expected_paths(row)) for row in rows]
        queries = [pair for pair in queries if pair[0]]
        query_vectors = [
            truncate_and_renormalize(
                embed_one(args.base_url, args.model, text, args.timeout), native_width
            )
            for text, _ in queries
        ]
        paths = [path for path, _ in passages]
        native_recall = recall_at_k(native, paths, queries, query_vectors, args.k)
        narrow_vectors = [
            truncate_and_renormalize(vector, args.width) for vector in query_vectors
        ]
        truncated_recall = recall_at_k(
            truncated, paths, queries, narrow_vectors, args.k
        )
        recall = {
            "measured": native_recall.get("measured", False),
            f"native_{native_width}": native_recall,
            f"truncated_{args.width}": truncated_recall,
        }

    result = {
        "base_url": args.base_url,
        "model": args.model,
        "corpus": str(args.corpus),
        "passages": len(passages),
        "native_dimensions": native_width,
        "truncated_dimensions": args.width,
        "neighbour_agreement": agreement,
        "recall": recall,
    }
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n[ok] {args.out}\n")
    if agreement.get("measured"):
        mean = agreement["mean_overlap"]
        print(f"  近傍一致率 (k={args.k})  mean {mean:.4f}  min {agreement['min_overlap']:.4f}")
        print(f"  top-1 一致率            {agreement['top1_agreement']:.4f}\n")
        if mean >= 0.95:
            print("  → 768 で問題ない。dimensions は動かさない。")
        elif mean < 0.85:
            print("  → 近傍が崩れている。24 問 fixture での recall 実測 (V3b) へ進む。")
        else:
            print("  → 曖昧帯。24 問 fixture での recall 実測 (V3b) へ進む。")
    if recall.get("measured"):
        wide = recall[f"native_{native_width}"]["recall"]
        narrow = recall[f"truncated_{args.width}"]["recall"]
        print(f"\n  recall@{args.k}  native {wide:.4f}  →  {args.width} {narrow:.4f}"
              f"  (差 {narrow - wide:+.4f})")
    print(
        "\n  dimensions は tool_profile_hash の入力である。動かすと既存ベクトルは\n"
        "  全て 03 §7 の互換ゲートに弾かれる — 採用は再埋め込みを伴う決定として扱うこと。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
