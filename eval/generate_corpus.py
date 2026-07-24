#!/usr/bin/env python3
"""合成コーパス生成 (KIO 検索評価ハーネス, docs/09-mvp-scope.md §4.3).

決定論的に 200-500 ファイル規模・複数 scope の合成コーパスを生成する。
- 依存: Python3 標準ライブラリのみ。
- 乱数 seed は corpus_spec.SEED / hashlib 由来で固定 → 2 回実行で byte 同一。
- 各 scope 直下に flat 配置 (docs/03-data-model.md §3「直下のみ」規則)。
- anchor 文書 (固有名詞・数値付き) はゴールデンクエリの対象。filler は検索ノイズ。
- 生成後 <out>/corpus-manifest.json に全ファイルの {scope, file, sections} を記録する。

使い方:
    python3 eval/generate_corpus.py --out /tmp/kio-eval-corpus
    python3 eval/generate_corpus.py --out /tmp/kio-eval-corpus --force
"""

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_spec as spec  # noqa: E402


def _raw_sha256(raw_bytes):
    """ファイル bytes の sha256 hexdigest (run_eval の解決層が raw_hash に使う)."""
    return hashlib.sha256(raw_bytes).hexdigest()


def build_manifest():
    files = []
    # anchor 文書: sections は {slug, heading} (実見出しテキスト) を持つ。
    # run_eval の解決層が heading -> slugify(heading) -> section_id を導くため heading が必須。
    # raw_sha256 は render_anchor が書き出す bytes の sha256。run_eval が raw_hash に使う。
    for anchor in spec.ANCHORS:
        entry = spec.anchor_manifest_entry(anchor)
        entry["raw_sha256"] = _raw_sha256(spec.render_anchor(anchor).encode("utf-8"))
        files.append(entry)
    # filler 文書
    for scope in spec.SCOPES:
        for f in spec.filler_files(scope):
            raw = f["data"] if f["is_binary"] else f["text"].encode("utf-8")
            files.append({
                "scope": scope,
                "file": f["file"],
                "kind": f["kind"],
                "anchor": False,
                "role": "filler",
                "sections": f["sections"],
                "raw_sha256": _raw_sha256(raw),
            })
    files.sort(key=lambda e: (e["scope"], e["file"]))
    return {
        "generator": "eval/generate_corpus.py",
        "seed": spec.SEED,
        "scopes": spec.SCOPES,
        "file_count": len(files),
        "anchor_count": len(spec.ANCHORS),
        "files": files,
    }


def write_corpus(out_dir, force):
    if os.path.exists(out_dir):
        if not force and os.listdir(out_dir):
            raise SystemExit(
                f"[error] 出力先が空でない: {out_dir} (--force で上書き)")
    for scope in spec.SCOPES:
        os.makedirs(os.path.join(out_dir, scope), exist_ok=True)

    written = 0
    # anchor
    for anchor in spec.ANCHORS:
        path = os.path.join(out_dir, anchor["scope"], anchor["file"])
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(spec.render_anchor(anchor))
        written += 1
    # filler
    for scope in spec.SCOPES:
        for f in spec.filler_files(scope):
            path = os.path.join(out_dir, scope, f["file"])
            if f["is_binary"]:
                with open(path, "wb") as fh:
                    fh.write(f["data"])
            else:
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(f["text"])
            written += 1

    manifest = build_manifest()
    with open(os.path.join(out_dir, spec.CORPUS_MANIFEST_NAME),
              "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    return written, manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="KIO 合成コーパス生成 (決定論的)")
    ap.add_argument("--out", required=True, help="出力ディレクトリ")
    ap.add_argument("--force", action="store_true", help="非空ディレクトリでも上書き")
    args = ap.parse_args(argv)

    out_dir = os.path.abspath(args.out)
    written, manifest = write_corpus(out_dir, args.force)

    per_scope = {}
    for e in manifest["files"]:
        per_scope[e["scope"]] = per_scope.get(e["scope"], 0) + 1
    print(f"[ok] コーパス生成: {out_dir}")
    print(f"     files={written} anchors={manifest['anchor_count']} "
          f"scopes={len(spec.SCOPES)}")
    for scope in spec.SCOPES:
        print(f"       - {scope:12s}: {per_scope.get(scope, 0)} files")
    print(f"     manifest: {os.path.join(out_dir, spec.CORPUS_MANIFEST_NAME)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
