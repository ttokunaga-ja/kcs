#!/usr/bin/env python3
"""index 済み fixture から、正規化済み本文だけを取り出して恒久化する。

## なぜこれが要るのか

V3b (MRL 768 の recall 実測) には **OCR 済みの本文**が要る。golden query の正解は
24 問中 20 問が `.pdf` / `.docx` / `.pptx` / `.png` で、生のコーパスを読んでも
本文が出てこないからである。その OCR は実費 $1.21 を払って既に済んでおり、
結果は `~/kio-dogfood/corpus-v1/corpus` 配下の index に入っている。

**だが index は 1.9 GB あり、`.kio` の内部構造 (object store・sqlite・manifest)
に依存する。** V3 が要るのは本文だけなので、本文だけを取り出せば

- 5 MB 程度のテキストになり **commit して恒久化できる**
- 以後の V3 再測定は GPU さえあれば**無料**になる
- 同じ OCR 費用を 3 度目に払う事故が構造的に起きなくなる
  (1 度目は 2026-07-24、2 度目は 07-27 に払っている)

## 取り出す形

golden query の `expected[].path` は `corpus/p01/home/.../latency-review.docx`
の形。これに一致させるため、**scope の位置 + `chunks.raw_path`** から相対パスを
組み立て、拡張子を `.md` に替えた 1 ファイルへ、その文書の chunk を
`byte_start` 順に連結して書く。

    corpus/p01/home/work/.../latency-review.docx  →  p01/home/work/.../latency-review.docx.md

元の拡張子を**消さずに残す**のは、`v3_mrl.py` の recall 判定が
`expected[].path` の部分一致で当てているため。消すと当たらなくなる。

## 使い方

    python3 eval/v3/extract_normalized_corpus.py \
      --fixture ~/kio-dogfood/corpus-v1/corpus \
      --out eval/v3/corpus-normalized
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def scope_dirs(fixture: Path) -> list[Path]:
    """`.kio` を直接持つディレクトリ = 1 scope。"""
    return sorted(p.parent for p in fixture.rglob(".kio") if p.is_dir())


def chunks_of(scope: Path) -> list[tuple[str, int, str]]:
    """(raw_path, byte_start, text) を返す。index が無ければ空。

    `gen` は最新だけを採る — 同じ文書の複数世代を連結すると本文が重複する。
    """
    db = scope / ".kio" / "index" / "sqlite.db"
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return list(
            con.execute(
                """
                SELECT c.raw_path, c.byte_start, c.text
                  FROM chunks c
                  JOIN (SELECT raw_path, MAX(gen) AS gen
                          FROM chunks GROUP BY raw_path) latest
                    ON c.raw_path = latest.raw_path AND c.gen = latest.gen
                 ORDER BY c.raw_path, c.byte_start
                """
            )
        )
    except sqlite3.DatabaseError as error:
        print(f"  [skip] {scope}: {error}", file=sys.stderr)
        return []
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--path-prefix",
        help="書き出すパスの先頭に付ける。既定は fixture ディレクトリ自身の名前 — "
        "golden query の `expected[].path` が `corpus/p01/…` の形で、その `corpus` が "
        "fixture ディレクトリ名だからである。これを外すと recall 判定が 0/24 になる",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="書き出したファイルの一覧と由来を JSON で残す (既定: <out>/EXTRACT.json)",
    )
    args = parser.parse_args()

    fixture = args.fixture.expanduser().resolve()
    scopes = scope_dirs(fixture)
    if not scopes:
        print(f"[stop] {fixture} に .kio scope が無い", file=sys.stderr)
        return 1
    print(f"[1/2] {len(scopes)} scope を走査 …", flush=True)

    documents: dict[str, list[tuple[int, str]]] = {}
    empty_scopes = 0
    for scope in scopes:
        rows = chunks_of(scope)
        if not rows:
            empty_scopes += 1
            continue
        prefix = Path(args.path_prefix or fixture.name) / scope.relative_to(fixture)
        for raw_path, byte_start, text in rows:
            documents.setdefault(str(prefix / raw_path), []).append((byte_start, text))

    if not documents:
        print("[stop] chunk が 1 件も取れなかった", file=sys.stderr)
        return 1

    print(f"[2/2] {len(documents)} 文書を書き出す …", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    written = 0
    total_bytes = 0
    for relative, parts in sorted(documents.items()):
        parts.sort()
        body = "\n\n".join(text for _, text in parts if text)
        if not body.strip():
            continue
        # 元の拡張子は残したまま `.md` を足す (recall の部分一致判定のため)。
        target = args.out / f"{relative}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written += 1
        total_bytes += len(body.encode("utf-8"))

    manifest = args.manifest or (args.out / "EXTRACT.json")
    manifest.write_text(
        json.dumps(
            {
                "fixture": str(fixture),
                "scopes_seen": len(scopes),
                "scopes_without_index": empty_scopes,
                "documents": written,
                "bytes": total_bytes,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\n[ok] {written} 文書 / {total_bytes / 1_000_000:.1f} MB → {args.out}")
    if empty_scopes:
        print(f"     index の無い scope: {empty_scopes} (未 index なら想定内)")
    print(
        "\n  これを commit すれば V3b は GPU だけで回る。OCR の実費は再度発生しない。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
