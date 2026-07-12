#!/usr/bin/env python3
"""Offline, allocation-capped regression oracle for model-catalog reads.

This program never opens a socket, reads a credential, or imports KCS.  It uses
small in-memory byte strings and a logical clock to demonstrate the invariants
that a repaired model-catalog reader should enforce before JSON parsing.
"""

from __future__ import annotations

import gzip
import io
import json
from dataclasses import dataclass
from typing import Iterable


DEMO_BODY_BYTES = 128 * 1024
MODEL_CATALOG_BYTES = 4 * 1024
WIRE_BYTES = 2 * 1024
DEADLINE_MS = 1_000


class BodyTooLarge(ValueError):
    """The response exceeded an explicit byte ceiling."""


class DeadlineExceeded(TimeoutError):
    """The response exceeded an explicit logical deadline."""


@dataclass(frozen=True)
class TimedChunk:
    at_ms: int
    data: bytes


def make_catalog(exact_size: int) -> bytes:
    """Build valid JSON of exactly ``exact_size`` bytes, within the demo cap."""
    if exact_size > DEMO_BODY_BYTES:
        raise ValueError("demo allocation cap exceeded")
    prefix = b'{"data":[{"id":"mistral-ocr-2505","padding":"'
    suffix = b'"}]}'
    padding = exact_size - len(prefix) - len(suffix)
    if padding < 0:
        raise ValueError("requested catalog is too small")
    body = prefix + (b"A" * padding) + suffix
    assert len(body) == exact_size
    return body


def select_model_after_full_parse(body: bytes) -> str:
    """Mirror the vulnerable ordering: materialize JSON, then filter IDs."""
    value = json.loads(body)
    candidates = [
        model["id"]
        for model in value["data"]
        if model.get("id", "").startswith("mistral-ocr")
        and not model["id"].endswith("-latest")
    ]
    return max(candidates)


def read_scripted(
    chunks: Iterable[TimedChunk], *, max_bytes: int, deadline_ms: int
) -> bytes:
    """Read scripted decoded chunks with deterministic size/time bounds."""
    output = bytearray()
    for chunk in chunks:
        if chunk.at_ms > deadline_ms:
            raise DeadlineExceeded(
                f"chunk arrived at {chunk.at_ms} ms; deadline is {deadline_ms} ms"
            )
        if len(output) + len(chunk.data) > max_bytes:
            raise BodyTooLarge(
                f"decoded body exceeds {max_bytes} bytes"
            )
        output.extend(chunk.data)
    return bytes(output)


def decode_gzip_capped(payload: bytes, *, max_wire: int, max_decoded: int) -> bytes:
    """Apply separate wire and decoded ceilings to an in-memory gzip body."""
    if len(payload) > max_wire:
        raise BodyTooLarge(f"wire body exceeds {max_wire} bytes")
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
        decoded = stream.read(max_decoded + 1)
    if len(decoded) > max_decoded:
        raise BodyTooLarge(f"decoded body exceeds {max_decoded} bytes")
    return decoded


def main() -> None:
    # The vulnerable ordering is demonstrated only at a fixed, harmless size.
    demo = make_catalog(DEMO_BODY_BYTES)
    selected = select_model_after_full_parse(demo)
    print(
        f"[+] vulnerable ordering: materialized {len(demo)} bytes "
        f"before selecting {selected} (demo hard-capped)"
    )

    try:
        read_scripted(
            [TimedChunk(0, b"A" * (MODEL_CATALOG_BYTES + 1))],
            max_bytes=MODEL_CATALOG_BYTES,
            deadline_ms=DEADLINE_MS,
        )
    except BodyTooLarge as error:
        print(f"[+] decoded-byte regression: rejected: {error}")
    else:
        raise AssertionError("decoded-byte ceiling was not enforced")

    compressed = gzip.compress(make_catalog(MODEL_CATALOG_BYTES + 1))
    try:
        decode_gzip_capped(
            compressed,
            max_wire=WIRE_BYTES,
            max_decoded=MODEL_CATALOG_BYTES,
        )
    except BodyTooLarge as error:
        print(f"[+] gzip-expansion regression: rejected: {error}")
    else:
        raise AssertionError("decoded gzip ceiling was not enforced")

    try:
        read_scripted(
            [TimedChunk(0, b'{"data":['), TimedChunk(1_001, b"]}")],
            max_bytes=MODEL_CATALOG_BYTES,
            deadline_ms=DEADLINE_MS,
        )
    except DeadlineExceeded as error:
        print(f"[+] deadline regression: rejected: {error}")
    else:
        raise AssertionError("deadline was not enforced")

    valid = b'{"data":[{"id":"mistral-ocr-2505"}]}'
    bounded = read_scripted(
        [TimedChunk(0, valid)],
        max_bytes=MODEL_CATALOG_BYTES,
        deadline_ms=DEADLINE_MS,
    )
    assert select_model_after_full_parse(bounded) == "mistral-ocr-2505"
    print("[+] valid-catalog regression: selected mistral-ocr-2505")
    print("[+] PASS: offline byte, decompression, and deadline invariants hold")


if __name__ == "__main__":
    main()
