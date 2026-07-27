#!/usr/bin/env python3
"""V4 step 2: 起動中の vLLM に対して、identity を左右する事実を実測する。

出力は `v4-probe.json`。stdlib のみ (urllib) — GPU 機に何も入れさせない。

## 何を確かめるのか

Stage 0 の D3 / D4 は「chat template と instruction は識別に含める」「wire は
`messages` に一本化する」と決めたが、その根拠は**一般論**だった。V4 はそれを
このモデル・このランタイムで確かめる。確認と反証の両方があり得る:

| 測る量 | D3/D4 が支持される | D3/D4 を見直すべき |
|---|---|---|
| `cos(input 経由, messages 経由)` | < 1 (空間が割れる) | == 1 (割れない) |
| `cos(instruction 有, 無)` | < 1 (文面が効く) | == 1 (効かない) |
| `cos(同一入力 2 回)` | == 1 (決定的) | < 1 (**identity 前提が崩れる**) |

3 行目は特に重要で、ここが 1 でなければ「ベクトルは content-addressed identity で
凍結できる」という前提そのものが成立しない。**その場合は D3 の文面調整では済まず、
Stage 2 の採用可否に戻る。**

2 行目が 1.0 だった場合、D4 が払っているコスト (1 リクエスト 1 アイテム、バッチ
不可) は**何も買っていない**ことになる。計測は裁定を追認するために回すのではない
ので、そう出たらそのまま報告すること。

## エンドポイントを決め打ちしない

pooling モデルの API 面 (`/v1/embeddings` が `messages` を受けるか、`/pooling` が
要るか) は vLLM の版で動く。本スクリプトは候補を順に試して**通ったものを記録**し、
通らなかったものは理由付きで記録する。「たぶんこれ」で書いて GPU セッションを
無駄にしない。
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v4_identity import prompt_template_hash, sha256_hex  # noqa: E402

# 1x1 PNG。画像経路が「通るか」を見るだけなので中身に意味は要らない。
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

PROBE_TEXT = "認証仕様のトークン TTL は 3600 秒です。"
PROBE_TEXT_B = "The retention window for audit logs is ninety days."
DEFAULT_INSTRUCTION = "Represent the user's input."


def post(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:600]
        return error.code, {"error": detail}
    except Exception as error:  # noqa: BLE001 — 到達性の問題も記録して続ける
        return 0, {"error": f"{type(error).__name__}: {error}"}


def get(url: str, timeout: float) -> tuple[int, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, {"error": error.read().decode("utf-8", "replace")[:600]}
    except Exception as error:  # noqa: BLE001
        return 0, {"error": f"{type(error).__name__}: {error}"}


def extract_vector(payload: Any) -> list[float] | None:
    """レスポンス形の差を吸収してベクトルを 1 本取り出す。"""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            for key in ("embedding", "data", "vector"):
                value = first.get(key)
                if isinstance(value, list) and value and isinstance(value[0], (int, float)):
                    return [float(x) for x in value]
    for key in ("embedding", "vector", "pooled"):
        value = payload.get(key)
        if isinstance(value, list) and value and isinstance(value[0], (int, float)):
            return [float(x) for x in value]
    return None


def cosine(a: list[float], b: list[float]) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return None
    return dot / (na * nb)


def vector_fingerprint(vector: list[float]) -> str:
    """ベクトルの同一性を報告に載せるための短い指紋。

    浮動小数をそのまま JSON へ流すと報告が読めなくなるので、bit 表現を
    そのまま hash する。`==` 判定と同義で、丸めによる取り違えがない。
    """
    import struct

    return sha256_hex(b"".join(struct.pack("<d", x) for x in vector))[:23]


class Probe:
    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.base = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.attempts: list[dict[str, Any]] = []

    def embed(self, label: str, path: str, payload: dict[str, Any]) -> list[float] | None:
        status, body = post(f"{self.base}{path}", payload, self.timeout)
        vector = extract_vector(body)
        record = {
            "label": label,
            "path": path,
            "request_keys": sorted(payload.keys()),
            "status": status,
            "ok": vector is not None,
            "dimensions": len(vector) if vector else None,
        }
        if vector is None:
            record["error"] = body.get("error") if isinstance(body, dict) else str(body)[:400]
        else:
            record["fingerprint"] = vector_fingerprint(vector)
            record["l2_norm"] = math.sqrt(sum(x * x for x in vector))
        self.attempts.append(record)
        return vector

    def text_as_input(self, text: str, label: str) -> list[float] | None:
        return self.embed(
            label, "/v1/embeddings", {"model": self.model, "input": [text]}
        )

    def text_as_messages(
        self, text: str, label: str, instruction: str | None = None
    ) -> list[float] | None:
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        messages: list[dict[str, Any]] = []
        if instruction:
            messages.append({"role": "system", "content": instruction})
        messages.append({"role": "user", "content": content})
        for path in ("/v1/embeddings", "/pooling", "/v1/pooling"):
            vector = self.embed(label, path, {"model": self.model, "messages": messages})
            if vector is not None:
                return vector
        return None

    def image_as_messages(self, label: str) -> list[float] | None:
        data_uri = "data:image/png;base64," + base64.b64encode(TINY_PNG).decode()
        messages = [
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": data_uri}}],
            }
        ]
        for path in ("/v1/embeddings", "/pooling", "/v1/pooling"):
            vector = self.embed(label, path, {"model": self.model, "messages": messages})
            if vector is not None:
                return vector
        return None

    def rendered_prompt(self, text: str, instruction: str | None) -> dict[str, Any]:
        """vLLM が実際に描画したプロンプト文字列を取りに行く。

        これが取れれば、`v4_capture.py` が挙げた候補のどれが本当に使われたかを
        **ファイルの読み比べではなく実測で**決められる。取れなければ取れないと
        記録する — 推測で埋めない。
        """
        messages: list[dict[str, Any]] = []
        if instruction:
            messages.append({"role": "system", "content": instruction})
        messages.append({"role": "user", "content": [{"type": "text", "text": text}]})
        results = []
        for payload in (
            {"model": self.model, "messages": messages, "return_token_strs": True},
            {"model": self.model, "messages": messages},
        ):
            status, body = post(f"{self.base}/tokenize", payload, self.timeout)
            entry: dict[str, Any] = {"status": status, "request_keys": sorted(payload)}
            if isinstance(body, dict):
                for key in ("prompt", "prompt_token_ids", "tokens", "token_strs", "count"):
                    if key in body:
                        value = body[key]
                        # vLLM 0.26 は return_token_strs を渡さないとき token_strs を
                        # null で返す。key の有無だけ見て len() すると落ちるので、
                        # null は null のまま記録する (記録内容の意味は変えない)。
                        if key in ("prompt", "count") or value is None:
                            entry[key] = value
                        else:
                            entry[key] = len(value)
                if "prompt" in body and isinstance(body["prompt"], str):
                    entry["prompt_sha256"] = sha256_hex(body["prompt"].encode("utf-8"))
                if "error" in body:
                    entry["error"] = body["error"]
            results.append(entry)
        return {"attempts": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", required=True, help="/v1/models が返す id")
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", type=Path, default=Path("v4-probe.json"))
    args = parser.parse_args()

    probe = Probe(args.base_url, args.model, args.timeout)
    status, models = get(f"{args.base_url.rstrip('/')}/v1/models", args.timeout)
    if status != 200:
        print(f"[!] /v1/models -> {status}: {models}", file=sys.stderr)
        print("    サーバが起動していないか URL が違う。", file=sys.stderr)
        return 2

    # --- 測定 ---------------------------------------------------------------
    a_input = probe.text_as_input(PROBE_TEXT, "A: text via input[]")
    b_msg = probe.text_as_messages(PROBE_TEXT, "B: text via messages")
    b_msg_again = probe.text_as_messages(PROBE_TEXT, "B': text via messages (repeat)")
    c_instr = probe.text_as_messages(
        PROBE_TEXT, "C: text via messages + instruction", instruction=args.instruction
    )
    d_image = probe.image_as_messages("D: image via messages")
    e_other = probe.text_as_messages(PROBE_TEXT_B, "E: unrelated text via messages")

    findings: dict[str, Any] = {}

    def note(key: str, left: list[float] | None, right: list[float] | None, verdict: dict[str, str]) -> None:
        value = cosine(left, right) if (left and right) else None
        entry: dict[str, Any] = {"cosine": value}
        if value is None:
            entry["conclusion"] = "measured=no — 上の attempts の error を見ること"
        elif value > 1.0 - 1e-9:
            entry["conclusion"] = verdict["same"]
        else:
            entry["conclusion"] = verdict["differs"]
        findings[key] = entry

    note(
        "d4_input_vs_messages",
        a_input,
        b_msg,
        {
            "same": "IDENTICAL — このモデルでは wire 形式が空間を割らない。"
            " D4 が払うコスト (バッチ不可) は何も買っていないので、07 §5.3 (2) を見直す根拠になる。",
            "differs": "DIFFERENT — D4 の前提が成立。messages 一本化は必要。",
        },
    )
    note(
        "d3_instruction_effect",
        b_msg,
        c_instr,
        {
            "same": "IDENTICAL — instruction が出力を動かさない。"
            " prompt_template_hash に畳む意味は薄く、D3 の instruction 側は再検討の余地。",
            "differs": "DIFFERENT — D3 の前提が成立。instruction は identity に含めるべき。",
        },
    )
    note(
        "determinism",
        b_msg,
        b_msg_again,
        {
            "same": "OK — 同一入力は同一ベクトル。content-addressed identity の前提が立つ。",
            "differs": "**STOP** — 同一入力が別ベクトルを返す。"
            " ベクトルを first-instance-wins で凍結する設計そのものが成立しない。"
            " Stage 2 の採用可否に戻ること。",
        },
    )
    note(
        "sanity_unrelated_text",
        b_msg,
        e_other,
        {
            "same": "**SUSPECT** — 無関係な 2 文が同一ベクトル。プーリングか"
            " エンドポイント選択が誤っている疑い。他の結論も信用できない。",
            "differs": "OK — 別の入力は別のベクトル。",
        },
    )

    # --- 実際に描画されたプロンプト -----------------------------------------
    rendered = {
        "without_instruction": probe.rendered_prompt(PROBE_TEXT, None),
        "with_instruction": probe.rendered_prompt(PROBE_TEXT, args.instruction),
    }

    report = {
        "base_url": args.base_url,
        "model": args.model,
        "models_endpoint": models,
        "instruction_under_test": args.instruction,
        "attempts": probe.attempts,
        "findings": findings,
        "rendered_prompt": rendered,
        "dimensions_observed": sorted(
            {a["dimensions"] for a in probe.attempts if a.get("dimensions")}
        ),
        "image_lane": "ok" if d_image else "FAILED — 画像経路が通っていない",
        # ここでは prompt_template_hash を **確定させない**。chat template の本文が
        # 確定するのは v4_capture.py の候補と rendered_prompt の突き合わせ後であり、
        # それは人間の判断を 1 回挟む。v4_finalize の入力になる値だけ置く。
        "next_step": "v4_capture.json の template 候補と rendered_prompt を突き合わせ、"
        "確定した template 本文と instruction を v4_finalize.py へ渡す",
    }
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"[ok] {args.out}\n")
    for key, entry in findings.items():
        value = entry["cosine"]
        shown = "n/a" if value is None else f"{value:.9f}"
        print(f"  {key:28s} cos={shown}\n      {entry['conclusion']}\n")
    print(f"  dimensions observed: {report['dimensions_observed']}")
    print(f"  image lane: {report['image_lane']}")

    hard_stop = findings.get("determinism", {}).get("conclusion", "").startswith("**STOP**")
    return 1 if hard_stop else 0


if __name__ == "__main__":
    raise SystemExit(main())
