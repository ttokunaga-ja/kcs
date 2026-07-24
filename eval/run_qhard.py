#!/usr/bin/env python3
"""Q_hard 増補分 (eval/golden-queries-qhard.jsonl) の専用ランナー.

09 §5.5 #5 (2026-07-23 再凍結) の別ファイル方式: 増補 8 問は実データ fixture
(raster PDF / PPTX 図表 / 画像) を正解担体とするため合成コーパスの
run_eval.py には載らない。本ランナーが fixture 環境 (register_fixture 系で
登録済みの qhard 環境) に対して Recall@10 を計測し、M3-1 の Done 判定は
run_eval.py の M3-1 (18 問) と本結果の合算 26 問 >= 0.8 (= 21 問) で行う。

前提: 増補ファイルの正解は OCR 強化パス (Mistral Batch) 完了後にのみ索引に
載る (hard1 = raster、hard3 = 図表画像)。OCR 未実行の環境では recall 0 が
期待値であり、それは計測の失敗ではなく enrichment 未了の事実を示す。
"""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))


def env_for(fixture_root: Path, env_name: str, online_query: bool):
    base = fixture_root / "env" / env_name
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith("KIO_TEST_"):
            env.pop(name, None)
        elif name in ("MISTRAL_API_KEY", "GEMINI_API_KEY") and not online_query:
            # hard1/hard3 の自然文クエリは字句非一致が設計そのもの — 検索時
            # query embedding (vector レーン) が正規の解答経路なので、
            # --online-query では資格情報を素通しする。
            env.pop(name, None)
    env["XDG_CONFIG_HOME"] = str(base / "xdg-config")
    env["XDG_DATA_HOME"] = str(base / "xdg-data")
    env["XDG_CACHE_HOME"] = str(base / "xdg-cache")
    return env


def first_scope_dir(fixture_root: Path, tree: str) -> Path:
    root = fixture_root / tree
    for kio_dir in sorted(root.rglob(".kio")):
        return kio_dir.parent
    raise SystemExit(f"no registered scope found under {root}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=os.path.join(HERE, "golden-queries-qhard.jsonl"))
    ap.add_argument("--fixture-root", default="/private/tmp/kio-fixture-run")
    ap.add_argument("--tree", default="qhard", help="fixture-root 直下の対象ツリー名")
    ap.add_argument("--env-name", default="qhard", help="fixture-root/env/ 配下の環境名")
    ap.add_argument("--bin", default="target/release/kio")
    ap.add_argument("--out", default=os.path.join(HERE, "qhard-results.json"))
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--online-query", action="store_true",
                    help="検索時の query embedding を許可 (GEMINI_API_KEY を環境から素通し)")
    args = ap.parse_args(argv)

    fixture_root = Path(args.fixture_root)
    goldens = [json.loads(l) for l in open(args.golden, encoding="utf-8") if l.strip()]
    cwd = first_scope_dir(fixture_root, args.tree)
    env = env_for(fixture_root, args.env_name, args.online_query)
    bin_path = os.path.abspath(args.bin)

    rows = []
    for q in goldens:
        started = time.monotonic()
        proc = subprocess.run(
            [bin_path, "--json", "search", q["query"], "--all-scopes"],
            cwd=cwd, env=env, capture_output=True, text=True,
        )
        duration_ms = (time.monotonic() - started) * 1000.0
        titles = []
        if proc.returncode == 0:
            try:
                response = json.loads(proc.stdout)
                titles = [r.get("title") for r in (response.get("results") or [])][: args.k]
            except json.JSONDecodeError:
                pass
        expected_titles = {Path(e["path"]).name for e in q["expected"]}
        hit = any(t in expected_titles for t in titles)
        rows.append({
            "query_id": q["query_id"],
            "class": q["class"],
            "hit": hit,
            "top": titles[:5],
            "expected": sorted(expected_titles),
            "returncode": proc.returncode,
            "duration_ms": round(duration_ms, 1),
        })

    hits = sum(1 for r in rows if r["hit"])
    result = {
        "golden": os.path.abspath(args.golden),
        "queries": rows,
        "hits": hits,
        "total": len(rows),
        "recall_fraction": round(hits / len(rows), 4) if rows else 0.0,
        "note": ("M3-1 Done 判定は run_eval.py の M3-1 18 問との合算 26 問 >= 21 "
                 "(09 §5.5 #5, 2026-07-23 再凍結)"),
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"[qhard] {hits}/{len(rows)} hits -> {args.out}")
    for r in rows:
        mark = "o" if r["hit"] else "x"
        print(f"  {mark} {r['query_id']} ({r['class']}) top={r['top'][:2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
