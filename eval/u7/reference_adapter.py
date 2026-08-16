#!/usr/bin/env python3
"""U7's Python-native reference embedding adapter.

This program owns only PyTorch/Transformers loading and embedding. Rust owns
HTTP, verdicts, reports, and filesystem discovery. One versioned JSON object
enters stdin and one vector response leaves stdout for each line.
"""

import base64
import io
import json
import sys
import warnings
from hashlib import sha256
from pathlib import Path

REQUEST_SCHEMA = "kio.u7.reference-embedding-request/v1"
RESPONSE_SCHEMA = "kio.u7.reference-embedding-response/v1"
MAX_IMAGE_WIDTH = 8_192
MAX_IMAGE_HEIGHT = 8_192
MAX_IMAGE_PIXELS = 16_777_216
MAX_REQUEST_LINE_BYTES = 13 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REQUEST_ID_BYTES = 128


def load(model_id):
    # This adapter may execute model-provided trusted code, but only from a
    # caller-selected local canonical directory. Never resolve/download a hub ID.
    supplied = Path(model_id)
    if not supplied.is_absolute():
        raise ValueError("model must be an absolute local directory")
    model_path = supplied.resolve(strict=True)
    if model_path != supplied or not model_path.is_dir():
        raise ValueError("model must be an existing local directory")
    import torch
    from transformers import AutoModel, AutoProcessor

    return (
        torch,
        AutoProcessor.from_pretrained(model_path, local_files_only=True, trust_remote_code=True),
        AutoModel.from_pretrained(model_path, local_files_only=True, trust_remote_code=True).eval(),
    )


def decode_image(encoded):
    from PIL import Image

    warnings.simplefilter("error", Image.DecompressionBombWarning)
    raw = base64.b64decode(encoded, validate=True)
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image bytes exceed U7 adapter bound")
    image = Image.open(io.BytesIO(raw))
    if image.width > MAX_IMAGE_WIDTH or image.height > MAX_IMAGE_HEIGHT:
        raise ValueError("image dimensions exceed U7 adapter bound")
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError("image pixels exceed U7 adapter bound")
    image.verify()
    return Image.open(io.BytesIO(raw)), raw


def embed(torch, processor, model, request):
    modality = request["modality"]
    if modality == "text":
        allowed = {"schema", "request_id", "input_digest", "modality", "text"}
        text = request.get("text")
        if set(request) != allowed or not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("invalid text request")
        if request["input_digest"] != "sha256:" + sha256(text.encode("utf-8")).hexdigest():
            raise ValueError("text input digest mismatch")
        content = [{"type": "text", "text": text}]
    elif modality == "image":
        allowed = {"schema", "request_id", "input_digest", "modality", "image_base64", "mime"}
        if set(request) != allowed or not isinstance(request.get("image_base64"), str) or not isinstance(request.get("mime"), str):
            raise ValueError("invalid image request")
        image, raw = decode_image(request["image_base64"])
        if request["input_digest"] != "sha256:" + sha256(raw).hexdigest():
            raise ValueError("image input digest mismatch")
        content = [{"type": "image", "image": image}]
    else:
        raise ValueError("unsupported modality")
    inputs = processor.apply_chat_template(
        [{"role": "user", "content": content}],
        add_generation_prompt=False,
        tokenize=True,
        return_tensors="pt",
        return_dict=True,
    )
    with torch.no_grad():
        output = model(**inputs)
    hidden = output.last_hidden_state if hasattr(output, "last_hidden_state") else output[0]
    return [float(value) for value in hidden[0, -1]]


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: reference_adapter.py MODEL_ID")
    torch, processor, model = load(sys.argv[1])
    while True:
        line = sys.stdin.buffer.readline(MAX_REQUEST_LINE_BYTES + 1)
        if not line:
            break
        if len(line) > MAX_REQUEST_LINE_BYTES or not line.endswith(b"\n"):
            raise ValueError("reference request line exceeds its bound")
        request = json.loads(line)
        request_id = request.get("request_id")
        digest = request.get("input_digest")
        if (
            request.get("schema") != REQUEST_SCHEMA
            or not isinstance(request_id, str)
            or not request_id
            or len(request_id.encode("utf-8")) > MAX_REQUEST_ID_BYTES
            or not isinstance(digest, str)
            or len(digest) != 71
            or not digest.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in digest[7:])
        ):
            raise ValueError("unsupported request schema")
        vector = embed(torch, processor, model, request)
        response = {
            "schema": RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "input_digest": request["input_digest"],
            "modality": request["modality"],
            "dimensions": len(vector),
            "vector": vector,
        }
        sys.stdout.write(json.dumps(response, allow_nan=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
