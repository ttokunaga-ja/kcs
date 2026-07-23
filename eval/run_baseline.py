#!/usr/bin/env python3
"""Q_hard baseline 比較 (09 §4.1 / M3-1 完了条件の「ベースライン優位」).

対象クエリ = eval/golden-queries-fixture-b.jsonl (24 問、hard1/2/3 × 8。
測定前凍結)。3 エンジンの Recall@10 を同一人格サブツリーで比較する:

- kcs:    登録済み fixture 環境 (register_fixture) に対する `kcs search
          --all-scopes`。--online-query で検索時 query embedding を許可
          (hard 系自然文の正規解答経路 — run_qhard と同じ裁定)。
- mdfind: Spotlight ネイティブのクエリ意味論をそのまま使う
          (`mdfind -onlyin <corpus>/<persona> "<query全文>"`)。
- rga:    ripgrep-all。全文 literal は自然文でほぼ必ず 0 件になるため、
          クエリをスクリプト種別の断片 (ascii 語 / 数値 / カタカナ連 /
          漢字連) に分解し、断片ごとの `rga -l` 一致数でファイルを採点する
          「上振れ寄りの丁寧な使い方」を採用 (baseline への generosity は
          KCS 優位主張を保守側に倒す)。

ゲート: KCS >= 0.8 かつ (KCS - mdfind) >= 0.3 かつ (KCS - rga) >= 0.3。

前提: baseline コーパスは Spotlight が索引する場所に置いた PRISTINE 複製
(.kcs なし — KCS 派生物を baseline に見せない公平性)。
"""
import argparse
import json
import os
import re
import subprocess
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))


def env_for(fixture_root: Path, persona: str, online_query: bool):
    base = fixture_root / "env" / persona
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith("KCS_TEST_"):
            env.pop(name, None)
        elif name in ("MISTRAL_API_KEY", "GEMINI_API_KEY") and not online_query:
            env.pop(name, None)
    env["XDG_CONFIG_HOME"] = str(base / "xdg-config")
    env["XDG_DATA_HOME"] = str(base / "xdg-data")
    env["XDG_CACHE_HOME"] = str(base / "xdg-cache")
    return env


def first_scope_dir(fixture_root: Path, persona: str) -> Path:
    for kcs_dir in sorted((fixture_root / persona).rglob(".kcs")):
        return kcs_dir.parent
    raise SystemExit(f"no registered scope for {persona}")


def kcs_top10(bin_path, fixture_root, persona, query, online_query):
    proc = subprocess.run(
        [bin_path, "--json", "search", query, "--all-scopes"],
        cwd=first_scope_dir(fixture_root, persona),
        env=env_for(fixture_root, persona, online_query),
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return [], proc.returncode
    try:
        results = json.loads(proc.stdout).get("results") or []
    except json.JSONDecodeError:
        return [], proc.returncode
    return [r.get("title") for r in results][:10], 0


def mdfind_top10(corpus: Path, persona: str, query: str):
    proc = subprocess.run(
        ["mdfind", "-onlyin", str(corpus / persona), query],
        capture_output=True, text=True,
    )
    names = [Path(line).name for line in proc.stdout.splitlines() if line.strip()]
    return names[:10]


def query_fragments(query: str):
    normalized = unicodedata.normalize("NFKC", query)
    fragments = set()
    fragments.update(m.lower() for m in re.findall(r"[A-Za-z][A-Za-z0-9_+\-]{1,}", normalized))
    fragments.update(re.findall(r"\d+(?:\.\d+)?", normalized))
    fragments.update(re.findall(r"[ァ-ヶー]{2,}", normalized))
    fragments.update(re.findall(r"[一-鿿]{2,}", normalized))
    return sorted(fragments)


def rga_top10(corpus: Path, persona: str, query: str):
    scores = defaultdict(int)
    for fragment in query_fragments(query):
        proc = subprocess.run(
            ["rga", "-l", "--no-messages", "--ignore-case", "--fixed-strings",
             fragment, str(corpus / persona)],
            capture_output=True, text=True, timeout=300,
        )
        for line in set(proc.stdout.splitlines()):
            if line.strip():
                scores[line] += 1
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [Path(path).name for path, _ in ranked[:10]]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=os.path.join(HERE, "golden-queries-fixture-b.jsonl"))
    ap.add_argument("--fixture-root", default="/private/tmp/kcs-fixture-run")
    ap.add_argument("--baseline-corpus", default=os.path.expanduser("~/kcs-baseline-corpus"))
    ap.add_argument("--bin", default="target/release/kcs")
    ap.add_argument("--out", default=os.path.join(HERE, "baseline-results.json"))
    ap.add_argument("--online-query", action="store_true")
    args = ap.parse_args(argv)

    fixture_root = Path(args.fixture_root)
    corpus = Path(args.baseline_corpus)
    bin_path = os.path.abspath(args.bin)
    goldens = [json.loads(l) for l in open(args.golden, encoding="utf-8") if l.strip()]

    rows = []
    for q in goldens:
        persona = q["persona"]
        expected = {e["file"] for e in q["expected"]}
        kcs_titles, kcs_rc = kcs_top10(bin_path, fixture_root, persona, q["query"],
                                       args.online_query)
        md_names = mdfind_top10(corpus, persona, q["query"])
        rga_names = rga_top10(corpus, persona, q["query"])
        row = {
            "query_id": q["query_id"],
            "class": q["class"],
            "persona": persona,
            "kcs_hit": any(t in expected for t in kcs_titles),
            "mdfind_hit": any(n in expected for n in md_names),
            "rga_hit": any(n in expected for n in rga_names),
            "kcs_rc": kcs_rc,
            "kcs_top3": kcs_titles[:3],
            "mdfind_top3": md_names[:3],
            "rga_top3": rga_names[:3],
            "expected": sorted(expected),
        }
        rows.append(row)
        print(f"  {q['query_id']} ({q['class']}): kcs={'o' if row['kcs_hit'] else 'x'} "
              f"mdfind={'o' if row['mdfind_hit'] else 'x'} rga={'o' if row['rga_hit'] else 'x'}",
              flush=True)

    n = len(rows)
    recall = {
        "kcs": sum(r["kcs_hit"] for r in rows) / n,
        "mdfind": sum(r["mdfind_hit"] for r in rows) / n,
        "rga": sum(r["rga_hit"] for r in rows) / n,
    }
    gate = {
        "kcs_ge_0_8": recall["kcs"] >= 0.8,
        "margin_mdfind_ge_0_3": recall["kcs"] - recall["mdfind"] >= 0.3,
        "margin_rga_ge_0_3": recall["kcs"] - recall["rga"] >= 0.3,
    }
    gate["pass"] = all(gate.values())
    by_class = {}
    for klass in ("hard1", "hard2", "hard3"):
        sub = [r for r in rows if r["class"] == klass]
        by_class[klass] = {
            "kcs": sum(r["kcs_hit"] for r in sub),
            "mdfind": sum(r["mdfind_hit"] for r in sub),
            "rga": sum(r["rga_hit"] for r in sub),
            "n": len(sub),
        }
    result = {"queries": rows, "recall_at_10": recall, "gate": gate,
              "by_class": by_class, "n": n,
              "note": "09 §4.1 ベースライン優位 — KCS>=0.8 かつ各差>=0.3"}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({"recall_at_10": recall, "gate": gate, "by_class": by_class},
                     ensure_ascii=False, indent=1))
    return 0 if gate["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
