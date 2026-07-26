#!/usr/bin/env python3
"""V4: `prompt_template_hash` の算出 (docs/07 §5.3 D3 + docs/03 §5.1)。

このファイルだけは **GPU 機でなくても動く**し、動かなければ他の V4 スクリプトの
出力はすべて無意味になる。したがって `python3 v4_identity.py` は自己テストであり、
計測の前に必ず 1 回通すこと。

## なぜ Python で書き直すのか

正本の実装は `crates/kio-adapter/src/identity.rs` の `normalize_prompt_template` /
`jcs_bytes` にある。計測は GPU 機で走り、その機械に Kio のビルド環境がある保証は
ないので Python 版を置くが、**移植は仕様の再解釈ではなく写経**である。ずれていない
ことは下の SELF_TESTS が凍結ベクタで示す — 1 つでも落ちたら移植が壊れている。

## 算出規約 (docs/07 §5.3)

    prompt_template_hash
      = "sha256:" + hex(sha256(JCS({"chat_template": P(T), "instruction": P(I)})))

P() は docs/03 §5.1 の前処理:

    1. 行末の ASCII 空白 (U+0020) と TAB (U+0009) のみ除去
       (全角空白・\\f・\\v は除去しない)
    2. 改行を \\n へ正規化 (CRLF / 単独 CR も行区切り)
    3. NFC 正規化
    4. 末尾の空行を削除

instruction を使わない構成でも `"instruction": ""` を **明示する** (key 省略と
空文字を識別しない)。
"""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from typing import Any


def normalize_prompt_template(raw: str) -> str:
    """docs/03 §5.1 の前処理。`identity.rs::normalize_prompt_template` の写し。

    NFC は行を join した **後** に掛ける (Rust 側が `.join("\\n").nfc()` の順序で
    あるため)。順序を入れ替えると結合文字が行境界をまたぐ入力で差が出る。
    """
    normalized_newlines = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized_newlines.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return unicodedata.normalize("NFC", "\n".join(lines))


def jcs_bytes(value: Any) -> bytes:
    """RFC 8785 JCS の byte 列。

    `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` は
    この用途では JCS と一致する:

    - key 順: JCS は UTF-16 code unit 順、Python は code point 順。BMP 内では
      同一で、Kio の profile / template key はすべて ASCII なので差は出ない
    - 制御文字: 双方 `\\b \\t \\n \\f \\r` の短縮形、それ以外は小文字 `\\u00xx`
    - 非 ASCII: 双方エスケープせず UTF-8 のまま出す
    - 数値: JCS は ECMAScript 数値書式。Kio が hash 入力に載せる数値は
      `spec_version` / `dimensions` のような小さな整数だけで、双方一致する

    **浮動小数を載せる用途には使えない** (JCS の数値書式は Python の repr と
    一般には一致しない)。V4 が hash するのは文字列 2 個なので範囲内。
    """
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def prompt_template_hash(chat_template: str, instruction: str) -> str:
    """D3 の 2-key object から `prompt_template_hash` を出す。"""
    return sha256_hex(
        jcs_bytes(
            {
                "chat_template": normalize_prompt_template(chat_template),
                "instruction": normalize_prompt_template(instruction),
            }
        )
    )


def tool_profile_hash(profile: dict[str, Any]) -> str:
    """docs/03 §5.1 の `tool_profile_hash`。null は hash 入力から除く。"""
    return sha256_hex(jcs_bytes({k: v for k, v in profile.items() if v is not None}))


# --- 自己テスト: すべて Kio 本体に凍結済みのベクタ ------------------------------


def _selftest() -> int:
    failures: list[str] = []

    def check(name: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            failures.append(f"{name}\n    expected: {expected!r}\n    actual:   {actual!r}")

    # 1. 前処理。identity.rs::prompt_template_hash_vector_matches_step2a
    raw = (
        "You are a markdownize adapter.  \r\n"
        "Process the café unchánged unit.\t\t\r\n\r\n"
    )
    check(
        "normalize_prompt_template",
        normalize_prompt_template(raw).encode("utf-8"),
        b"You are a markdownize adapter.\nProcess the caf\xc3\xa9 unch\xc3\xa1nged unit.",
    )
    check(
        "prompt_template_hash (single-string form)",
        sha256_hex(normalize_prompt_template(raw).encode("utf-8")),
        "sha256:3f5200e929d23e1f113f605fb528b1b7b75e183d226064d319f57fb3e467d238",
    )

    # 2. JCS。bbox_annotation.rs の凍結 byte 列と BBOX_ANNOTATION_FORMAT_HASH。
    #    入れ子 object / 配列 / boolean を含むので、平坦な 2-key より強い検査。
    bbox = {
        "type": "json_schema",
        "json_schema": {
            "name": "kio_bbox_annotation_v1",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "short_description": {
                        "type": "string",
                        "description": "Describe the figure briefly in plain text. Do not use Markdown or HTML.",
                    },
                    "transcribed_text": {
                        "type": "string",
                        "description": "Transcribe all visible text verbatim in plain text. Do not use Markdown or HTML.",
                    },
                },
                "required": ["short_description", "transcribed_text"],
            },
        },
    }
    check(
        "jcs_bytes (bbox schema)",
        jcs_bytes(bbox),
        br'{"json_schema":{"name":"kio_bbox_annotation_v1","schema":{"additionalProperties":false,"properties":{"short_description":{"description":"Describe the figure briefly in plain text. Do not use Markdown or HTML.","type":"string"},"transcribed_text":{"description":"Transcribe all visible text verbatim in plain text. Do not use Markdown or HTML.","type":"string"}},"required":["short_description","transcribed_text"],"type":"object"},"strict":true},"type":"json_schema"}',
    )
    check(
        "BBOX_ANNOTATION_FORMAT_HASH",
        sha256_hex(jcs_bytes(bbox)),
        "sha256:79443071238e373b41e34818e91d52ea69d2bba70a30169cda2cf98bfd8bea76",
    )

    # 3. tool_profile_hash。identity.rs::profile_hash_vectors_match_step2a
    #    整数 (`spec_version`) が混ざる形。
    mistral = {
        "adapter_kind": "markdownize",
        "adapter_role": "multimodal",
        "model_or_tool_family": "mistral-ocr",
        "model_version_pin": "mistral-ocr-2505",
        "output_schema": "kio-markdown-v1",
        "runtime_kind": "cloud",
        "spec_version": 1,
    }
    check(
        "tool_profile_hash (mistral)",
        tool_profile_hash(mistral),
        "sha256:393d7b062ec1fd573c0a061455bef3f3ee16367378ca4122a0684045178e974c",
    )

    if failures:
        print("V4 identity self-test FAILED:\n", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}\n", file=sys.stderr)
        print(
            "この移植は Kio 本体と一致していない。計測を進めても算出される\n"
            "prompt_template_hash は誤りになるので、ここで止めること。",
            file=sys.stderr,
        )
        return 1

    print("V4 identity self-test OK (4 frozen vectors from kio-adapter)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
