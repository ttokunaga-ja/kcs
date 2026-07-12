#!/usr/bin/env python3
"""Harmless in-memory probe for the Mistral OCR response-boundary bug.

The source-equivalent path intentionally mirrors the relevant behavior in
`mistral_ocr.rs`: materialize the complete JSON value, collect every page and
image, decode every base64 image, and account every unique image as a would-be
CAS write.  It never performs HTTP or filesystem I/O.

The bounded path applies deliberately small demonstration limits so boundary
failures are reproducible without consuming meaningful resources.  These
constants are test values, not recommended production policy values.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Limits:
    max_virtual_tick: int = 4
    max_body_bytes: int = 8 * 1024
    max_pages: int = 4
    max_markdown_bytes_per_page: int = 1024
    max_markdown_bytes_total: int = 2048
    max_images_per_page: int = 2
    max_images_total: int = 4
    max_image_bytes: int = 1024
    max_decoded_image_bytes_total: int = 2048
    max_unique_persist_bytes: int = 1536


LIMITS = Limits()


class Rejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Observation:
    pages: int
    images: int
    decoded_bytes: int
    unique_persist_bytes: int


def split_data_uri(value: str) -> str:
    if value.startswith("data:") and ";base64," in value:
        return value.split(";base64,", 1)[1]
    return value


def source_equivalent_parse(chunks: Iterable[tuple[int, bytes]]) -> Observation:
    """Model the current unbounded allocation/decode/persistence sequence."""
    # Virtual ticks are ignored here because the current transport has no read
    # or overall deadline once it is connected.
    body = b"".join(chunk for _tick, chunk in chunks)
    value = json.loads(body)
    pages = value.get("pages")
    if not isinstance(pages, list):
        raise ValueError("OCR response missing pages")

    decoded: list[bytes] = []
    image_count = 0
    for page in pages:
        images = page.get("images") if isinstance(page, dict) else None
        if not isinstance(images, list):
            images = []
        for image in images:
            image_count += 1
            raw = ""
            if isinstance(image, dict):
                candidate = image.get("image_base64", image.get("base64", ""))
                if isinstance(candidate, str):
                    raw = candidate
            decoded.append(base64.b64decode(split_data_uri(raw), validate=True))

    # `persist_images` hashes each image and writes it if the CAS path does not
    # already exist.  We calculate the same unique-byte exposure in memory.
    unique: dict[str, bytes] = {}
    for payload in decoded:
        unique.setdefault(hashlib.sha256(payload).hexdigest(), payload)

    return Observation(
        pages=len(pages),
        images=image_count,
        decoded_bytes=sum(map(len, decoded)),
        unique_persist_bytes=sum(len(payload) for payload in unique.values()),
    )


def bounded_parse(
    chunks: Iterable[tuple[int, bytes]], limits: Limits = LIMITS
) -> Observation:
    """Apply time, body, shape, decode, and pre-persistence budgets."""
    body = bytearray()
    for virtual_tick, chunk in chunks:
        if virtual_tick > limits.max_virtual_tick:
            raise Rejected("deadline")
        if len(body) + len(chunk) > limits.max_body_bytes:
            raise Rejected("body_bytes")
        body.extend(chunk)

    value = json.loads(body)
    pages = value.get("pages")
    if not isinstance(pages, list):
        raise Rejected("pages_shape")
    if len(pages) > limits.max_pages:
        raise Rejected("pages")

    markdown_total = 0
    image_total = 0
    decoded_total = 0
    decoded: list[bytes] = []

    for page in pages:
        if not isinstance(page, dict):
            raise Rejected("page_shape")
        markdown = page.get("markdown", "")
        if not isinstance(markdown, str):
            raise Rejected("markdown_shape")
        markdown_bytes = len(markdown.encode("utf-8"))
        if markdown_bytes > limits.max_markdown_bytes_per_page:
            raise Rejected("markdown_page")
        markdown_total += markdown_bytes
        if markdown_total > limits.max_markdown_bytes_total:
            raise Rejected("markdown_total")

        images = page.get("images", [])
        if not isinstance(images, list):
            raise Rejected("images_shape")
        if len(images) > limits.max_images_per_page:
            raise Rejected("images_page")
        image_total += len(images)
        if image_total > limits.max_images_total:
            raise Rejected("images_total")

        for image in images:
            if not isinstance(image, dict):
                raise Rejected("image_shape")
            raw = image.get("image_base64", image.get("base64", ""))
            if not isinstance(raw, str):
                raise Rejected("base64_shape")
            encoded = split_data_uri(raw)

            # Bound encoded input before decode.  The small rounding allowance
            # means at most two bytes beyond the final cap can be allocated;
            # the exact decoded length is checked immediately afterward.
            max_encoded = 4 * ((limits.max_image_bytes + 2) // 3)
            if len(encoded) > max_encoded:
                raise Rejected("image_encoded_bytes")
            try:
                payload = base64.b64decode(encoded, validate=True)
            except ValueError as error:
                raise Rejected("base64_invalid") from error
            if len(payload) > limits.max_image_bytes:
                raise Rejected("image_bytes")
            decoded_total += len(payload)
            if decoded_total > limits.max_decoded_image_bytes_total:
                raise Rejected("decoded_total")
            decoded.append(payload)

    unique: dict[str, bytes] = {}
    for payload in decoded:
        unique.setdefault(hashlib.sha256(payload).hexdigest(), payload)
    unique_persist_bytes = sum(len(payload) for payload in unique.values())
    if unique_persist_bytes > limits.max_unique_persist_bytes:
        raise Rejected("persist_total")

    return Observation(
        pages=len(pages),
        images=image_total,
        decoded_bytes=decoded_total,
        unique_persist_bytes=unique_persist_bytes,
    )


def encoded_image(size: int, marker: int) -> dict[str, str]:
    payload = bytes([marker]) * size
    return {
        "image_base64": "data:image/png;base64,"
        + base64.b64encode(payload).decode("ascii")
    }


def page(
    markdown: str = "ok", images: list[dict[str, str]] | None = None
) -> dict[str, object]:
    return {"markdown": markdown, "images": images or []}


def response_bytes(
    pages: list[dict[str, object]], padding: str = ""
) -> bytes:
    return json.dumps(
        {"pages": pages, "padding": padding}, separators=(",", ":")
    ).encode("utf-8")


def chunks_at(body: bytes, ticks: list[int]) -> list[tuple[int, bytes]]:
    width = max(1, (len(body) + len(ticks) - 1) // len(ticks))
    parts = [body[offset : offset + width] for offset in range(0, len(body), width)]
    return list(zip(ticks, parts, strict=True))


@dataclass(frozen=True)
class Case:
    name: str
    chunks: list[tuple[int, bytes]]
    expected_rejection: str | None


def cases() -> list[Case]:
    baseline = response_bytes([page(images=[encoded_image(200, 0x41)])])
    duplicate = encoded_image(800, 0x44)
    return [
        Case("baseline", [(1, baseline)], None),
        Case("virtual_slow_read", chunks_at(baseline, [1, 3, 5]), "deadline"),
        Case(
            "body_over_limit",
            [(1, response_bytes([], "X" * LIMITS.max_body_bytes))],
            "body_bytes",
        ),
        Case(
            "page_cardinality",
            [(1, response_bytes([page() for _ in range(LIMITS.max_pages + 1)]))],
            "pages",
        ),
        Case(
            "markdown_per_page",
            [(1, response_bytes([page("M" * (LIMITS.max_markdown_bytes_per_page + 1))]))],
            "markdown_page",
        ),
        Case(
            "image_cardinality",
            [
                (
                    1,
                    response_bytes(
                        [
                            page(
                                images=[
                                    encoded_image(16, 0x31),
                                    encoded_image(16, 0x32),
                                    encoded_image(16, 0x33),
                                ]
                            )
                        ]
                    ),
                )
            ],
            "images_page",
        ),
        Case(
            "decoded_image_size",
            [(1, response_bytes([page(images=[encoded_image(1025, 0x45)])]))],
            "image_bytes",
        ),
        Case(
            "decoded_aggregate",
            [
                (
                    1,
                    response_bytes(
                        [
                            page(
                                images=[
                                    encoded_image(800, 0x51),
                                    encoded_image(800, 0x52),
                                ]
                            ),
                            page(images=[encoded_image(800, 0x53)]),
                        ]
                    ),
                )
            ],
            "decoded_total",
        ),
        Case(
            "unique_persistence_budget",
            [
                (
                    1,
                    response_bytes(
                        [
                            page(
                                images=[
                                    encoded_image(800, 0x61),
                                    encoded_image(800, 0x62),
                                ]
                            )
                        ]
                    ),
                )
            ],
            "persist_total",
        ),
        Case(
            "cas_dedup_control",
            [(1, response_bytes([page(images=[duplicate, duplicate])]))],
            None,
        ),
    ]


def main() -> int:
    failures = 0
    for case in cases():
        # Every case is syntactically valid and modest in size, so the current
        # source-equivalent model accepts it.  The observation reports how many
        # bytes would reach the decode and unique-image persistence stages.
        current = source_equivalent_parse(case.chunks)
        try:
            bounded = bounded_parse(case.chunks)
            rejection = None
            bounded_text = (
                f"accepted(decoded={bounded.decoded_bytes},"
                f" unique_persist={bounded.unique_persist_bytes})"
            )
        except Rejected as error:
            rejection = error.code
            bounded_text = f"rejected[{error.code}]"

        ok = rejection == case.expected_rejection
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} {case.name}: current=accepted("
            f"pages={current.pages}, images={current.images}, "
            f"decoded={current.decoded_bytes}, "
            f"would_persist={current.unique_persist_bytes}); "
            f"bounded={bounded_text}"
        )
        failures += int(not ok)

    if failures:
        print(f"{failures} case(s) failed", file=sys.stderr)
        return 1
    print("All cases passed; no network, credentials, sleeps, or file writes were used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
