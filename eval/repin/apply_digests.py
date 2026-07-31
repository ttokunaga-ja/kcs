#!/usr/bin/env python3
"""old->new の digest 対応をリポジトリ全体へ適用する。

同じ artifact の digest は、それを pin する下流モジュールすべてに同じ 64 桁
文字列として現れる。したがって置換は 1 対 1 の全域置換でよく、どのファイルの
どの行かを個別に追う必要はない。

引数は `old:new` の並び、または `--from-json <path>` で
`{"name": {"sha256": "..."}}` 形式と現行 pin の差分から自動抽出する。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(".")
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


def main() -> int:
    pairs: dict[str, str] = {}
    for argument in sys.argv[1:]:
        old, _, new = argument.partition(":")
        if not (HEX64.fullmatch(old) and HEX64.fullmatch(new)):
            print(f"[stop] not a digest pair: {argument}", file=sys.stderr)
            return 1
        pairs[old] = new
    if not pairs:
        print("[stop] no pairs given", file=sys.stderr)
        return 1

    files = subprocess.run(
        ["git", "grep", "-Il", "--", *pairs.keys()],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    # `git grep -l -- a b` は OR ではないので、素直に全テキストを走査する。
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()

    touched = 0
    per_pair = dict.fromkeys(pairs, 0)
    for relative in files:
        # 自分の記録は書き換えない。`before.json` は追跡下のテキストなので全域置換の
        # 対象に入っており、ラウンドごとに「改名前の実測値」が「適用後の値」へ静かに
        # 上書きされていた。記録が失われるだけでなく、`before == after` になった
        # artifact の対応が**見つからなくなる** — ラウンドが早々に「新規 0」で終わる
        # のは収束ではなく、比較対象が消えたためだった。74 件が一度も再 pin されずに
        # 残っていたのはこれが原因である。
        if relative.startswith("eval/repin/"):
            continue
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        updated = text
        for old, new in pairs.items():
            if old in updated:
                per_pair[old] += updated.count(old)
                updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            touched += 1

    replacements = sum(per_pair.values())
    print(f"  {len(pairs)} pair -> {replacements} occurrences in {touched} files")

    # 0 箇所置換の対応は合算では見えない。452 対応のうち 1 件が空振りしても
    # 「N occurrences in M files」は大きな数を出し続ける。converge は `old` が
    # repo に実在することを確かめてから対応を採るので、直後の適用が 0 箇所に
    # なるのは矛盾であり、**ソースが old でも new でもない第三の値を持っている**
    # ことを意味する。2026-07-30 に見つけた `c1ae7e10…` はこれだった —
    # 早いラウンドが `--allow-fail` 下の候補を焼き、依存を直した後のラウンドが
    # 作った正しい対応が、ソースがもう old を含まないので空振りしていた。
    # 気付いたのはツールではなくテストスイートで、4 時間の走行を 1 回無駄にした。
    empty = [old for old, count in per_pair.items() if count == 0]
    if empty:
        print(f"[stop] {len(empty)} pair replaced nothing:", file=sys.stderr)
        for old in empty:
            print(f"  {old} -> {pairs[old]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
