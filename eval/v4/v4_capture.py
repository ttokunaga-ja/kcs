#!/usr/bin/env python3
"""V4 step 1: モデルディレクトリから chat template と重みハッシュを採取する。

GPU も vLLM も不要 — モデルファイルさえあれば動く。出力は `v4-capture.json`。

## この段階で「決め打ち」をしない理由

chat template の在り処は HF のリポジトリ規約が動いており、同じモデルに複数の
候補が同居することがある (`chat_template.jinja` / `tokenizer_config.json` の
`chat_template` / `chat_template.json` / processor 側)。**どれを vLLM が実際に
使うかは、ファイルを読んだだけでは断定できない。**

なので本スクリプトは「1 つに決める」ことをせず、**見つかった候補を全部、内容
ハッシュ付きで列挙する**。候補が 1 つならそれが答えで、複数あって中身が違うなら
それは V4 が暴くべき事実であり、`v4_probe.py` が実サーバの描画結果と突き合わせて
決着させる。ここで勝手に優先順位を付けると、その順位が間違っていたときに
**誤った profile identity が凍結される** — D3 が防ごうとしているのはまさにそれ。

## 重みハッシュ (D2) について

docs/03 §5.1 は offline_api + local の `model_version_pin` を「重みファイルの
sha256」と定める。単一 GGUF ならそれで一意だが、**shard された safetensors では
「重みファイル」が複数あり、規約が一意でない。** 本スクリプトは各 shard の
sha256 を個別に出したうえで、集約案を 1 つ提示する:

    aggregate = sha256(JCS({ "<相対パス>": "sha256:...", ... }))

パス順ではなく JCS の key 順で決まるので、ディレクトリ走査順に依存しない。
**これは提案であって確定規約ではない。** V4 の報告に載せて 03 §5.1 に追記する
まで、この値を profile に焼き付けないこと。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v4_identity import jcs_bytes, normalize_prompt_template, sha256_hex  # noqa: E402

WEIGHT_SUFFIXES = (".safetensors", ".gguf", ".bin", ".pt")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def collect_template_candidates(model_dir: Path) -> list[dict[str, Any]]:
    """chat template を名乗りうるものを全部集める。優先順位は付けない。"""
    candidates: list[dict[str, Any]] = []

    def add(source: str, template: Any, note: str = "") -> None:
        if not isinstance(template, str) or not template.strip():
            return
        candidates.append(
            {
                "source": source,
                "note": note,
                "raw_sha256": sha256_hex(template.encode("utf-8")),
                "normalized_sha256": sha256_hex(
                    normalize_prompt_template(template).encode("utf-8")
                ),
                "chars": len(template),
                "template": template,
            }
        )

    # 新しい HF 規約: 単独ファイル。
    for name in ("chat_template.jinja", "chat_template.j2"):
        path = model_dir / name
        if path.is_file():
            add(name, path.read_text(encoding="utf-8"))

    # 従来規約: config の中の文字列、または {name, template} の配列。
    for name in ("tokenizer_config.json", "processor_config.json", "chat_template.json"):
        path = model_dir / name
        if not path.is_file():
            continue
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            candidates.append({"source": name, "error": f"unparseable: {error}"})
            continue
        value = config.get("chat_template")
        if isinstance(value, str):
            add(f"{name}:chat_template", value)
        elif isinstance(value, list):
            # 複数テンプレート形式 ({"name": ..., "template": ...} の配列)。
            for entry in value:
                if isinstance(entry, dict):
                    add(
                        f"{name}:chat_template[{entry.get('name', '?')}]",
                        entry.get("template"),
                        note="named template — vLLM がどれを選ぶかは実測で決める",
                    )

    return candidates


def collect_weights(model_dir: Path) -> dict[str, Any]:
    files = sorted(
        path
        for path in model_dir.rglob("*")
        if path.is_file() and path.suffix in WEIGHT_SUFFIXES
    )
    per_file = {
        str(path.relative_to(model_dir)): file_sha256(path) for path in files
    }
    return {
        "files": per_file,
        "count": len(per_file),
        "total_bytes": sum((model_dir / name).stat().st_size for name in per_file),
        # 提案であって確定規約ではない — module docstring 参照。
        "proposed_aggregate": sha256_hex(jcs_bytes(per_file)) if per_file else None,
        "proposed_aggregate_rule": "sha256(JCS({relative_path: sha256, ...}))",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        required=True,
        type=Path,
        help="モデルの実体ディレクトリ (HF cache の snapshots/<rev> でよい)",
    )
    parser.add_argument("--out", type=Path, default=Path("v4-capture.json"))
    parser.add_argument(
        "--skip-weights",
        action="store_true",
        help="重み sha256 を飛ばす (数十 GB の読み出しを避けたいとき)",
    )
    args = parser.parse_args()

    if not args.model_dir.is_dir():
        print(f"not a directory: {args.model_dir}", file=sys.stderr)
        return 2

    templates = collect_template_candidates(args.model_dir)
    weights = {"skipped": True} if args.skip_weights else collect_weights(args.model_dir)

    distinct = {
        candidate["normalized_sha256"]
        for candidate in templates
        if "normalized_sha256" in candidate
    }
    capture = {
        "model_dir": str(args.model_dir),
        "template_candidates": templates,
        "distinct_normalized_templates": len(distinct),
        "weights": weights,
    }
    args.out.write_text(
        json.dumps(capture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"[ok] {args.out}")
    print(f"     template candidates: {len(templates)} (distinct after normalization: {len(distinct)})")
    for candidate in templates:
        if "error" in candidate:
            print(f"       - {candidate['source']}: {candidate['error']}")
        else:
            print(
                f"       - {candidate['source']}: {candidate['chars']} chars "
                f"{candidate['normalized_sha256'][:19]}…"
            )
    if not templates:
        print(
            "     [!] テンプレート候補がゼロ。vLLM は --chat-template を要求するはずで、\n"
            "         その場合 V4 の答えは「明示的に渡したファイルの中身」になる。",
            file=sys.stderr,
        )
    elif len(distinct) > 1:
        print(
            "     [!] 正規化後も内容の異なる候補が複数ある。どれを vLLM が使うかは\n"
            "         v4_probe.py の実測 (--tokenize) で決着させること。",
            file=sys.stderr,
        )
    if not args.skip_weights and weights.get("count"):
        print(f"     weight files: {weights['count']} ({weights['total_bytes'] / 1e9:.1f} GB)")
        print(f"     proposed aggregate pin: {weights['proposed_aggregate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
