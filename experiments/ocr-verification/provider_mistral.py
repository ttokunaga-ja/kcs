#!/usr/bin/env python3
"""The Python-native Mistral OCR adapter.

Reads exactly one versioned JSON request from stdin and writes exactly one
versioned JSON response to stdout.  It deliberately owns no evaluation,
threshold, report, output-path, or fixture-discovery policy.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from hashlib import sha256
from typing import Any

REQUEST_SCHEMA = "kio.ocr.provider-request/v1"
RESPONSE_SCHEMA = "kio.ocr.provider-response/v1"
MAX_REQUEST_BYTES = 24 * 1024 * 1024
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024


def read_request() -> dict[str, Any]:
    line = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
    if not line or len(line) > MAX_REQUEST_BYTES or not line.endswith(b"\n"):
        raise ValueError("expected one bounded JSONL request")
    if sys.stdin.buffer.read(1):
        raise ValueError("expected exactly one JSONL request")
    request = json.loads(line)
    required = {"schema", "request_id", "model", "media_type", "document_bytes", "document_sha256", "document_base64", "include_image_base64"}
    if set(request) != required or request["schema"] != REQUEST_SCHEMA:
        raise ValueError("unsupported provider request schema")
    if not isinstance(request["request_id"], str) or not request["request_id"] or len(request["request_id"]) > 256:
        raise ValueError("request_id is invalid")
    if not isinstance(request["model"], str) or not request["model"] or len(request["model"]) > 256:
        raise ValueError("model is invalid")
    if request["media_type"] != "application/pdf":
        raise ValueError("only application/pdf is supported")
    if not isinstance(request["document_bytes"], int) or request["document_bytes"] < 0 or request["document_bytes"] > MAX_DOCUMENT_BYTES:
        raise ValueError("document_bytes is out of bounds")
    if (
        not isinstance(request["document_sha256"], str)
        or len(request["document_sha256"]) != 64
        or any(char not in "0123456789abcdef" for char in request["document_sha256"])
    ):
        raise ValueError("document_sha256 is invalid")
    if not isinstance(request["document_base64"], str) or len(request["document_base64"]) > MAX_REQUEST_BYTES:
        raise ValueError("document_base64 is invalid")
    return request


def plain_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    raise TypeError("Mistral SDK returned an unsupported response type")


def main() -> None:
    request = read_request()
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is required")
    from mistralai import Mistral

    payload_bytes = base64.b64decode(request["document_base64"], validate=True)
    if len(payload_bytes) != request["document_bytes"] or sha256(payload_bytes).hexdigest() != request["document_sha256"]:
        raise ValueError("document identity changed or mismatched request binding")
    payload = base64.b64encode(payload_bytes).decode("ascii")
    client = Mistral(api_key=api_key)
    response = client.ocr.process(
        model=request["model"],
        document={"type": "document_url", "document_url": f"data:application/pdf;base64,{payload}"},
        include_image_base64=bool(request["include_image_base64"]),
        table_format=None,
    )
    output = {"schema": RESPONSE_SCHEMA, "request_id": request["request_id"], "document_sha256": request["document_sha256"], "response": plain_data(response)}
    sys.stdout.write(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # Errors intentionally go only to bounded stderr.
        print(f"provider_mistral: {error}", file=sys.stderr)
        raise SystemExit(1)
