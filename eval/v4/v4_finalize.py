#!/usr/bin/env python3
"""V4 step 3: 確定した template と instruction から profile identity を出す。

`v4_capture.py` の候補と `v4_probe.py` の rendered_prompt を突き合わせて
「vLLM が実際に使った template はこれ」と**人間が確定させた後**に走らせる。
自動化しないのは、ここで間違えると誤った空間のベクトルが恒久的に凍結される
(docs/07 §5.3 の冒頭が述べている通り) からで、その判断は人間が 1 回挟む価値がある。

出力は Rust に貼れる定数と、そのまま報告に載せられる JSON。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v4_identity import (  # noqa: E402
    normalize_prompt_template,
    prompt_template_hash,
    sha256_hex,
    tool_profile_hash,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chat-template-file",
        required=True,
        type=Path,
        help="確定した chat template の本文 (実測で裏の取れたもの)",
    )
    parser.add_argument(
        "--instruction",
        default="",
        help="タスク instruction。使わない構成では空文字を明示する (07 §5.3)",
    )
    parser.add_argument(
        "--model-version-pin",
        required=True,
        help="重みの sha256 (03 §5.1 / D2)。v4-capture.json の値を使う",
    )
    parser.add_argument("--model-family", default="qwen3-vl-embedding")
    parser.add_argument("--dimensions", type=int, default=768)
    parser.add_argument("--prompt-template-id", default="kio-local-embedding-v1")
    parser.add_argument("--out", type=Path, default=Path("v4-profile.json"))
    args = parser.parse_args()

    template = args.chat_template_file.read_text(encoding="utf-8")
    template_hash = prompt_template_hash(template, args.instruction)

    # local_embedding.rs::profile_value と同じ field 集合。`prompt_template_id` /
    # `prompt_template_hash` は cloud profile では未設定のままで、ローカル profile で
    # 初めて埋まる (07 §5.3)。
    profile = {
        "adapter_kind": "embedding",
        "adapter_role": "multimodal",
        "dimensions": args.dimensions,
        "distance": "cosine",
        "input_construction": "chunk_filename_context_v1",
        "modality": "multimodal",
        "model_or_tool_family": args.model_family,
        "model_version_pin": args.model_version_pin,
        "prompt_template_hash": template_hash,
        "prompt_template_id": args.prompt_template_id,
        "runtime_kind": "local",
        "spec_version": 1,
    }
    profile_hash = tool_profile_hash(profile)

    result = {
        "chat_template_raw_sha256": sha256_hex(template.encode("utf-8")),
        "chat_template_normalized_sha256": sha256_hex(
            normalize_prompt_template(template).encode("utf-8")
        ),
        "instruction": args.instruction,
        "prompt_template_hash": template_hash,
        "profile": profile,
        "tool_profile_hash": profile_hash,
    }
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"[ok] {args.out}\n")
    print(f"  prompt_template_hash : {template_hash}")
    print(f"  tool_profile_hash    : {profile_hash}\n")
    print("  crates/kio-adapter/src/local_embedding.rs へ:\n")
    print(f'      "model_version_pin": "{args.model_version_pin}",')
    print(f'      "prompt_template_hash": "{template_hash}",')
    print(f'      "prompt_template_id": "{args.prompt_template_id}",')
    print(
        "\n  この 2 つの hash が変わると既存ベクトルは全て非互換になる (03 §7)。\n"
        "  採用は再埋め込みを伴う決定として扱うこと。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
