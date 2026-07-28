#!/usr/bin/env python3
"""改名前スナップショットを正として、対応の取れた digest だけを繰り返し適用する。

各ラウンドで改名後ツリーを組み直す。前ラウンドで上流 pin が直っている分だけ
新たに組めるようになり、その artifact の対応が新しく取れる。取れた対応だけを
適用して次へ進む。

**推測は 1 つも入らない。** old は「改名前に同じ builder が出した実測値」であり、
new は「改名後に同じ builder が出した実測値」である。old が repo に書かれている
ことも都度確認する — 書かれていなければ、その artifact の pin をこちらが取り違えて
いる証拠なので採用しない。

各ラウンドで **bytes の一致も必ず確認する**。`kcs` と `kio` は同長なので canonical
JSON の長さは動かないはずで、動いたら改名以外の変化が混じっている。その場合は
その artifact を採用せず報告する — 前回はここを見ていなかったために無関係な pin を
潰した。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = Path(".")
BEFORE = json.loads((HERE / "before.json").read_text())


def in_repo(digest: str) -> bool:
    return bool(subprocess.run(["git", "grep", "-Il", digest],
                               cwd=ROOT, capture_output=True, text=True).stdout.strip())


def snapshot(path: Path) -> dict:
    subprocess.run([sys.executable, str(HERE / "snapshot.py"),
                    "--out", str(path), "--allow-fail"],
                   cwd=ROOT, capture_output=True, text=True)
    return json.loads(path.read_text())


def main() -> int:
    # 記録は追記でなければならない。毎回まっさらから書き直すと、前の実行で適用した
    # 対応が記録から消える (実際に消した)。何を当てたかは後から検算する唯一の手掛かり
    # なので、既存の記録に積む。
    record = HERE / "applied.json"
    history: dict[str, str] = json.loads(record.read_text()) if record.exists() else {}
    applied: dict[str, str] = {}
    for round_number in range(1, 25):
        after = snapshot(HERE / f"after-{round_number}.json")
        built = sum(1 for v in after.values() if "sha256" in v)

        fresh: list[str] = []
        for name, before in sorted(BEFORE.items()):
            if "sha256" not in before or "sha256" not in after.get(name, {}):
                continue
            now = after[name]
            if before["bytes"] != now["bytes"]:
                print(f"[stop] {name}: bytes moved {before['bytes']} -> {now['bytes']}. "
                      "改名以外の変化が混じっている。", file=sys.stderr)
                return 1
            old, new = before["sha256"], now["sha256"]
            if old == new or old in applied:
                continue
            if not in_repo(old):
                continue  # この artifact の pin を取り違えている。採用しない
            fresh.append(f"{old}:{new}")
            applied[old] = new

        print(f"round {round_number}: built {built}/{len(after)}, new pairs {len(fresh)}",
              flush=True)
        if not fresh:
            print(f"\n[done] {len(applied)} pairs applied over {round_number - 1} rounds")
            break
        subprocess.run([sys.executable, str(HERE / "apply_digests.py"), *fresh],
                       cwd=ROOT, check=True)

    record.write_text(json.dumps({**history, **applied}, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
