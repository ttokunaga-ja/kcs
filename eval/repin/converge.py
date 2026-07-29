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

# bytes が動くことに**説明がついた** artifact だけ、バイト一致の検査を外す。
# 番人ごと外さないのは、これが実際に仕事をしたからである — 43 artifact しか
# 測っていなかったときは静かだったが、81 builder に広げた最初のラウンドで
# 下記の salt を捕まえた。理由を書かずにここへ足さないこと。
BYTES_MAY_MOVE = {
    "persona_v2_query_history_semantic_resolution_feasibility"
    "::build_query_history_semantic_resolution_feasibility_audit": (
        "改名で `_domain_key` の前置詞が変わり domain-separated-sha256-order の "
        "DFS 探索順が動いた。この artifact は上流の canonical_bytes をデータとして"
        "記録しているので、その差が自身のバイト数に出る "
        "(8312760 -> 8313318 を記録して 40947 -> 40949)。"
    ),
}


def in_repo(digest: str) -> bool:
    """その digest を pin している箇所が repo にあるか。

    `eval/repin/` は数えない。`before.json` は改名前の実測値を持っているので、
    そこを数えると **自分の記録を「repo にある証拠」として扱う**ことになり、
    既に再 pin し終えた artifact にも幻の対応が立つ (74 件の対応が成立して
    置換対象 0 件、という形で現れた)。置換側だけ除外して検査側を残していた。
    """
    completed = subprocess.run(
        ["git", "grep", "-Il", digest, "--", ".", ":(exclude)eval/repin"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return bool(completed.stdout.strip())


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
    held: dict[str, str] = {}
    for round_number in range(1, 25):
        after = snapshot(HERE / f"after-{round_number}.json")
        built = sum(1 for v in after.values() if "sha256" in v)

        fresh: list[str] = []
        for name, before in sorted(BEFORE.items()):
            if "sha256" not in before or "sha256" not in after.get(name, {}):
                continue
            now = after[name]
            if before["bytes"] != now["bytes"] and name not in BYTES_MAY_MOVE:
                # その対応を採らない。全体を止めるのではない — 番人の役割は
                # 「この対応は信用しない」であって「他も測るな」ではない。
                # 引数を取らない builder を全部測るようにしてから、凍結 artifact
                # ではない診断的な builder も混ざるようになった。1 件で止めると
                # 前進しないので、外して最後にまとめて報告する。
                held[name] = f"bytes moved {before['bytes']} -> {now['bytes']}"
                continue
            # 上流が直るたびに下流の digest はもう一度動く。`old` を一度使ったら
            # 打ち切る書き方だと、その二度目以降を取りこぼす — 実際に
            # `corpus_input_closure_v3` が round 1 の中間値で止まり、46 件の
            # エラーとして残っていた。適用済みの鎖を辿って **いま repo にある値**
            # と対応を取る。
            old, new = before["sha256"], now["sha256"]
            current = old
            while current in applied:
                current = applied[current]
            if current == new:
                continue
            if not in_repo(current):
                continue  # この artifact の pin を取り違えている。採用しない
            fresh.append(f"{current}:{new}")
            applied[current] = new

        print(f"round {round_number}: built {built}/{len(after)}, new pairs {len(fresh)}",
              flush=True)
        if not fresh:
            print(f"\n[done] {len(applied)} pairs applied over {round_number - 1} rounds")
            break
        subprocess.run([sys.executable, str(HERE / "apply_digests.py"), *fresh],
                       cwd=ROOT, check=True)

    record.write_text(json.dumps({**history, **applied}, indent=2, sort_keys=True) + "\n")
    for name, why in sorted(held.items()):
        print(f"[held] {name}: {why}", file=sys.stderr)
    if held:
        print(f"\n{len(held)} 件は採用していない。改名以外で動いているので、"
              "凍結 artifact なのか診断なのかを確かめること。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
