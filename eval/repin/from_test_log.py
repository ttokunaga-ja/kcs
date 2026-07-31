#!/usr/bin/env python3
"""テストが計算した値と、テストに書かれた古い値との対応をその場で採る。

artifact 単位の差分 (`snapshot.py` + `converge.py`) では届かない digest がある —
`assertEqual(module.f(x), "<64 hex>")` のように **テストの中に直接書かれている**
もので、どの builder の出力とも一致しないため前後比較の対象にできない。

`AssertionError` はそれ自体が計器である。失敗した比較の両辺は「今このツリーで
計算した値」と「凍結されていた値」であり、どちらがどちらかは **repo に実在するか**
で決まる。凍結値はソースに書かれているから grep に当たり、計算値は当たらない。
`assertEqual` の引数順はテストごとに違うので、順序では判定しない。

## なぜテストの実行までこのスクリプトが持つのか

「repo にあるほうが old」は **ログがいまのツリーと同期しているときにだけ**正しい。
一度 digest を当てた後の repo に古いログを当てると、新しい値のほうが repo に実在
するので対応が反転し、正しく直した分を巻き戻す。実際に空撃ちで再現した。

ログを引数で受け取る限りこの取り違えは避けられないので、**このスクリプトが自分で
テストを走らせる**。ログとツリーがずれる余地を無くすのが唯一の確実な防ぎ方である。

上流 pin が壊れたままだと計算値も汚染されるので、**必ず収束ループを終えてから**
使うこと。適用後は同じテストを流し直して緑になることが対応の検算になる
(対応が反転していれば元の失敗に戻るので、この再実行が反転も捕まえる)。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
BLOCK = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)


def in_repo(digest: str) -> bool:
    return bool(subprocess.run(["git", "grep", "-Il", digest],
                               cwd=ROOT, capture_output=True, text=True).stdout.strip())


def run_tests(modules: list[str], log: Path) -> str:
    """テストを走らせ、**進行中もログを読める形で**書き出す。

    出力をまとめて受け取って最後に書く版は、CI の 91 モジュールで 3 時間以上
    「ログが空でプロセスは生きている」状態が続き、進んでいるのか止まっている
    のか判断できなかった。長い測定では途中が見えることが結果と同じくらい重要
    なので、`unittest` の出力を直接ログへ流す。進行はドットで見える。

    `-v` は付けない。下の `blocks()` はこのログを解析するので、検証済みの出力
    形式を進捗を見るためだけに変えたくない。
    """
    print(f"[run] {len(modules)} modules -> {log}", flush=True)
    with log.open("w", encoding="utf-8") as sink:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", *modules],
            cwd=ROOT, stdout=sink, stderr=subprocess.STDOUT, text=True,
        )
    text = log.read_text(encoding="utf-8", errors="replace")
    tail = [line for line in text.splitlines() if line.startswith(("Ran ", "OK", "FAILED"))]
    print(f"  exit={completed.returncode}  " + " / ".join(tail[-2:]), flush=True)
    return text


def blocks(log: str) -> list[tuple[str, str]]:
    """(見出し, 本文) に切り分ける。区切りは unittest の `=====` 行。"""
    found = []
    for chunk in re.split(r"^={60,}$", log, flags=re.M):
        head = BLOCK.search(chunk)
        if head:
            found.append((head.group(1), chunk))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules", required=True, type=Path,
                        help="1 行 1 モジュールのリスト。これを走らせてログを採る")
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    modules = [m for m in args.modules.read_text().split() if m]
    log = run_tests(modules, args.log)

    pairs: dict[str, str] = {}
    skipped: list[tuple[str, str]] = []
    for name, chunk in blocks(log):
        digests = list(dict.fromkeys(HEX64.findall(chunk)))
        old = [d for d in digests if in_repo(d)]
        new = [d for d in digests if not in_repo(d)]
        if len(old) != 1 or len(new) != 1:
            skipped.append((name, f"{len(old)} in repo / {len(new)} fresh"))
            continue
        if pairs.get(old[0], new[0]) != new[0]:
            skipped.append((name, f"conflicting mapping for {old[0][:12]}…"))
            continue
        pairs[old[0]] = new[0]
        print(f"  {old[0][:12]}… -> {new[0][:12]}…  {name}", flush=True)

    args.out.write_text("".join(f"{o}:{n}\n" for o, n in pairs.items()), encoding="utf-8")
    print(f"\n[ok] {len(pairs)} pairs -> {args.out}")
    if skipped:
        print(f"[left] {len(skipped)} blocks need a look:", file=sys.stderr)
        for name, why in skipped:
            print(f"  {name}: {why}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
