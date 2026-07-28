"""Deterministic ID-free feasibility renderer for raw image/media variants.

This module implements only bounded format encoding.  Requests contain no
persona, path, source, query, digest, solution, or fixture identity.  Returned
bytes do not authorize source planning, physical writes, KIO execution, chunk
claims, history mutation, or G0.  The encoders use only the Python standard
library and emit deliberately narrow, canonical subsets of seven formats.
"""

from __future__ import annotations

import binascii
import copy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
import struct

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kio.persona.pc-id-free-raw-image-media-renderer/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-image-media-renderer"
RENDERER_ID = "persona-v2-id-free-raw-image-media-feasibility-renderer"
RENDERER_SCHEMA_VERSION = 2
MAX_CONTRACT_BYTES = 96 * 1024
MAX_CONTRACT_JSON_DEPTH = 64
MAX_CONTRACT_JSON_NODES = 32_768
MAX_RENDERED_BYTES = 100 * 2**20
FORMAL_ORDINARY_MIN_BYTES = 4 * 1024
FORMAL_ORDINARY_MAX_BYTES = 512 * 1024
FORMAL_TAIL_MIN_BYTES = 1 * 2**20
FORMAL_TAIL_MAX_BYTES = 4 * 2**20
MIN_RASTER_PIXELS = 4_096
MAX_RASTER_PIXELS = 16_777_216
MAX_RASTER_DIMENSION = 65_535
MIN_MEDIA_UNITS = 1
MAX_MEDIA_UNITS = 4_800_000

READY_VARIANTS = ("aiff", "bmp", "jpg", "mid", "png", "tif", "wav")
IMAGE_VARIANTS = frozenset(("bmp", "jpg", "png", "tif"))
MEDIA_VARIANTS = frozenset(("aiff", "mid", "wav"))

REQUEST_FIELDS = (
    "schema_version",
    "variant",
    "width",
    "height",
    "frame_or_event_count",
)

PROHIBITED_IDENTITY_FIELDS = (
    "answer",
    "chunk",
    "digest",
    "final_source_id",
    "fixture_nonce",
    "intent_key",
    "materialization_id",
    "oracle",
    "path",
    "persona_id",
    "query",
    "raw_hash",
    "scope_key",
    "solution",
    "source_id",
)

_VARIANT_ROWS = {
    "aiff": {
        "family": "media",
        "filename_extension": "aiff",
        "content_media_type": "audio/aiff",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "complexity_measure": "frames-or-events",
        "counting_rule": "mono-pcm-sample-frames",
        "render_template": "canonical-aiff-8bit-mono-pcm-v2",
        "raw_byte_formula": "54+frames+(frames-mod-2)",
    },
    "bmp": {
        "family": "image",
        "filename_extension": "bmp",
        "content_media_type": "image/bmp",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "complexity_measure": "pixels",
        "counting_rule": "decoded-width-times-height",
        "render_template": "canonical-bmp-infoheader-1bit-v2",
        "raw_byte_formula": "62+4*ceil(width/32)*height",
    },
    "jpg": {
        "family": "image",
        "filename_extension": "jpg",
        "content_media_type": "image/jpeg",
        "expected_kio_path_media_type": "image/jpeg",
        "expected_offline_disposition": "awaiting_ocr",
        "complexity_measure": "pixels",
        "counting_rule": "decoded-width-times-height",
        "render_template": "canonical-jfif-baseline-grayscale-zero-dct-v2",
        "raw_byte_formula": "154+ceil(ceil(width/8)*ceil(height/8)/4)",
    },
    "mid": {
        "family": "media",
        "filename_extension": "mid",
        "content_media_type": "audio/midi",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "complexity_measure": "frames-or-events",
        "counting_rule": "note-on-channel-events-excluding-end-of-track",
        "render_template": "canonical-smf0-running-status-note-events-v2",
        "raw_byte_formula": "27+3*events",
    },
    "png": {
        "family": "image",
        "filename_extension": "png",
        "content_media_type": "image/png",
        "expected_kio_path_media_type": "image/png",
        "expected_offline_disposition": "awaiting_ocr",
        "complexity_measure": "pixels",
        "counting_rule": "decoded-width-times-height",
        "render_template": "canonical-png-1bit-gray-stored-deflate-v2",
        "raw_byte_formula": (
            "63+(ceil(width/8)+1)*height+"
            "5*ceil(((ceil(width/8)+1)*height)/65535)"
        ),
    },
    "tif": {
        "family": "image",
        "filename_extension": "tif",
        "content_media_type": "image/tiff",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "complexity_measure": "pixels",
        "counting_rule": "decoded-width-times-height",
        "render_template": "canonical-tiff-le-single-strip-1bit-v2",
        "raw_byte_formula": "110+ceil(width/8)*height",
    },
    "wav": {
        "family": "media",
        "filename_extension": "wav",
        "content_media_type": "audio/wav",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "complexity_measure": "frames-or-events",
        "counting_rule": "mono-pcm-sample-frames",
        "render_template": "canonical-wave-8bit-mono-pcm-v2",
        "raw_byte_formula": "44+frames+(frames-mod-2)",
    },
}


class PersonaV2RawImageMediaRendererError(ValueError):
    """Raised when a bounded raw image/media request is invalid."""


@dataclass(frozen=True, slots=True)
class RawImageMediaRenderRequest:
    """Identity-free request; unused dimensional axes must be exact zero."""

    schema_version: int
    variant: str
    width: int
    height: int
    frame_or_event_count: int


@dataclass(frozen=True, slots=True)
class RenderedRawImageMedia:
    """Canonical bytes plus non-authoritative format metadata."""

    data: bytes
    extension: str
    content_media_type: str
    expected_kio_path_media_type: str
    expected_offline_disposition: str
    width: int
    height: int
    frame_or_event_count: int
    target_complexity: int
    target_bytes: int
    size_lane: str
    renderer_id: str = RENDERER_ID
    renderer_schema_version: int = RENDERER_SCHEMA_VERSION


def _fail(message):
    raise PersonaV2RawImageMediaRendererError(message)


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        _fail("unsupported raw image/media variant")
    return _VARIANT_ROWS[variant]


def validate_request(request):
    if type(request) is not RawImageMediaRenderRequest:
        _fail("request must be an exact RawImageMediaRenderRequest")
    if tuple(RawImageMediaRenderRequest.__dataclass_fields__) != REQUEST_FIELDS:
        _fail("renderer request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        _fail("renderer request exposes an identity field")
    if type(request.schema_version) is not int or request.schema_version != 2:
        _fail("renderer request schema version must be exact 2")
    _profile(request.variant)
    if request.variant in IMAGE_VARIANTS:
        if (
            type(request.width) is not int
            or type(request.height) is not int
            or not 1 <= request.width <= MAX_RASTER_DIMENSION
            or not 1 <= request.height <= MAX_RASTER_DIMENSION
        ):
            _fail("raster width and height must be exact bounded integers")
        pixels = request.width * request.height
        if not MIN_RASTER_PIXELS <= pixels <= MAX_RASTER_PIXELS:
            _fail("width times height is outside the upstream pixel domain")
        if type(request.frame_or_event_count) is not int or request.frame_or_event_count != 0:
            _fail("image frame_or_event_count must be exact zero")
    else:
        if type(request.width) is not int or request.width != 0:
            _fail("media width must be exact zero")
        if type(request.height) is not int or request.height != 0:
            _fail("media height must be exact zero")
        if (
            type(request.frame_or_event_count) is not int
            or not MIN_MEDIA_UNITS
            <= request.frame_or_event_count
            <= MAX_MEDIA_UNITS
        ):
            _fail("media frame/event count is outside the upstream domain")
    target = target_bytes_for(
        request.variant,
        request.width,
        request.height,
        request.frame_or_event_count,
    )
    if target > MAX_RENDERED_BYTES:
        _fail("request exceeds the absolute renderer byte cap")
    return True


def target_complexity_for(variant, width, height, frame_or_event_count):
    target_bytes_for(variant, width, height, frame_or_event_count)
    if variant in IMAGE_VARIANTS:
        return width * height
    return frame_or_event_count


def target_bytes_for(variant, width, height, frame_or_event_count):
    """Return the exact canonical file length without allocating the payload."""

    _profile(variant)
    if variant in IMAGE_VARIANTS:
        if (
            type(width) is not int
            or type(height) is not int
            or type(frame_or_event_count) is not int
            or frame_or_event_count != 0
            or not 1 <= width <= MAX_RASTER_DIMENSION
            or not 1 <= height <= MAX_RASTER_DIMENSION
            or not MIN_RASTER_PIXELS <= width * height <= MAX_RASTER_PIXELS
        ):
            _fail("invalid raster dimensions for byte formula")
        if variant == "bmp":
            target = 62 + 4 * ((width + 31) // 32) * height
        elif variant == "jpg":
            blocks = ((width + 7) // 8) * ((height + 7) // 8)
            target = 154 + (blocks + 3) // 4
        elif variant == "png":
            raw_length = (((width + 7) // 8) + 1) * height
            blocks = (raw_length + 65_534) // 65_535
            target = 63 + raw_length + 5 * blocks
        else:
            target = 110 + ((width + 7) // 8) * height
    else:
        if (
            type(width) is not int
            or type(height) is not int
            or width != 0
            or height != 0
            or type(frame_or_event_count) is not int
            or not MIN_MEDIA_UNITS <= frame_or_event_count <= MAX_MEDIA_UNITS
        ):
            _fail("invalid media axes for byte formula")
        if variant == "aiff":
            target = 54 + frame_or_event_count + (frame_or_event_count & 1)
        elif variant == "mid":
            target = 27 + 3 * frame_or_event_count
        else:
            target = 44 + frame_or_event_count + (frame_or_event_count & 1)
    if not 1 <= target <= MAX_RENDERED_BYTES:
        _fail("canonical byte formula exceeds the absolute cap")
    return target


def classify_size_lane(byte_length):
    if type(byte_length) is not int or not 1 <= byte_length <= MAX_RENDERED_BYTES:
        _fail("byte length is outside the renderer domain")
    if FORMAL_ORDINARY_MIN_BYTES <= byte_length <= FORMAL_ORDINARY_MAX_BYTES:
        return "formal-ordinary"
    if FORMAL_TAIL_MIN_BYTES <= byte_length <= FORMAL_TAIL_MAX_BYTES:
        return "formal-tail"
    return "feasibility-only"


@lru_cache(maxsize=None)
def _maximum_rendered_bytes_for_valid_variant(variant):
    if variant in MEDIA_VARIANTS:
        return target_bytes_for(variant, 0, 0, MAX_MEDIA_UNITS)
    maximum = 0
    for width in range(1, MAX_RASTER_DIMENSION + 1):
        height = min(MAX_RASTER_DIMENSION, MAX_RASTER_PIXELS // width)
        if width * height < MIN_RASTER_PIXELS:
            continue
        maximum = max(maximum, target_bytes_for(variant, width, height, 0))
    if maximum == 0:  # pragma: no cover - frozen domains always have values.
        _fail("variant has no reachable request in its upstream domain")
    return maximum


def maximum_rendered_bytes_for(variant):
    """Exhaustively derive the largest file reachable in the legal domain."""

    _profile(variant)
    return _maximum_rendered_bytes_for_valid_variant(variant)


def _render_bmp(width, height):
    stride = 4 * ((width + 31) // 32)
    image_bytes = stride * height
    file_bytes = 62 + image_bytes
    header = struct.pack("<2sIHHI", b"BM", file_bytes, 0, 0, 62)
    dib = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        1,
        0,
        image_bytes,
        2_835,
        2_835,
        2,
        2,
    )
    palette = b"\x00\x00\x00\x00\xff\xff\xff\x00"
    return header + dib + palette + bytes(image_bytes)


def _jpeg_segment(marker, payload):
    if type(marker) is not int or not 0 <= marker <= 255 or len(payload) > 65_533:
        _fail("invalid canonical JPEG segment")
    return b"\xff" + bytes((marker,)) + struct.pack(">H", len(payload) + 2) + payload


def _render_jpg(width, height):
    app0 = _jpeg_segment(
        0xE0,
        b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00",
    )
    dqt = _jpeg_segment(0xDB, b"\x00" + b"\x01" * 64)
    sof0 = _jpeg_segment(
        0xC0,
        b"\x08" + struct.pack(">HH", height, width) + b"\x01\x01\x11\x00",
    )
    single_code_counts = b"\x01" + b"\x00" * 15
    dht = _jpeg_segment(
        0xC4,
        b"\x00" + single_code_counts + b"\x00"
        + b"\x10" + single_code_counts + b"\x00",
    )
    sos = _jpeg_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    blocks = ((width + 7) // 8) * ((height + 7) // 8)
    full_bytes, remaining_blocks = divmod(blocks, 4)
    scan = bytearray(full_bytes)
    if remaining_blocks:
        scan.append((1 << (8 - 2 * remaining_blocks)) - 1)
    return b"\xff\xd8" + app0 + dqt + sof0 + dht + sos + bytes(scan) + b"\xff\xd9"


def _png_chunk(chunk_type, payload):
    body = chunk_type + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)


def _render_png(width, height):
    row_bytes = (width + 7) // 8
    raw_length = (row_bytes + 1) * height
    deflate = bytearray(b"\x78\x01")
    remaining = raw_length
    while remaining:
        block_length = min(remaining, 65_535)
        remaining -= block_length
        deflate.append(1 if remaining == 0 else 0)
        deflate.extend(struct.pack("<HH", block_length, block_length ^ 0xFFFF))
        deflate.extend(bytes(block_length))
    adler32_of_zeros = ((raw_length % 65_521) << 16) | 1
    deflate.extend(struct.pack(">I", adler32_of_zeros))
    ihdr = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", bytes(deflate))
        + _png_chunk(b"IEND", b"")
    )


def _tiff_entry(tag, field_type, count, value):
    if field_type == 3 and count == 1:
        encoded_value = struct.pack("<H", value) + b"\x00\x00"
    elif field_type == 4 and count == 1:
        encoded_value = struct.pack("<I", value)
    else:  # pragma: no cover - only the frozen table calls this helper.
        _fail("unsupported canonical TIFF entry")
    return struct.pack("<HHI", tag, field_type, count) + encoded_value


def _render_tif(width, height):
    strip_bytes = ((width + 7) // 8) * height
    entries = (
        _tiff_entry(256, 4, 1, width)
        + _tiff_entry(257, 4, 1, height)
        + _tiff_entry(258, 3, 1, 1)
        + _tiff_entry(259, 3, 1, 1)
        + _tiff_entry(262, 3, 1, 1)
        + _tiff_entry(273, 4, 1, 110)
        + _tiff_entry(278, 4, 1, height)
        + _tiff_entry(279, 4, 1, strip_bytes)
    )
    return b"II\x2a\x00\x08\x00\x00\x00" + struct.pack("<H", 8) + entries + b"\x00\x00\x00\x00" + bytes(strip_bytes)


def _render_wav(frames):
    pad = frames & 1
    file_length = 44 + frames + pad
    return (
        b"RIFF"
        + struct.pack("<I", file_length - 8)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 8_000, 8_000, 1, 8)
        + b"data"
        + struct.pack("<I", frames)
        + b"\x80" * frames
        + bytes(pad)
    )


def _render_aiff(frames):
    pad = frames & 1
    file_length = 54 + frames + pad
    sample_rate_8000 = b"\x40\x0b\xfa\x00\x00\x00\x00\x00\x00\x00"
    comm = struct.pack(">hIh", 1, frames, 8) + sample_rate_8000
    ssnd = struct.pack(">II", 0, 0) + bytes(frames)
    return (
        b"FORM"
        + struct.pack(">I", file_length - 8)
        + b"AIFFCOMM"
        + struct.pack(">I", len(comm))
        + comm
        + b"SSND"
        + struct.pack(">I", len(ssnd))
        + ssnd
        + bytes(pad)
    )


def _render_mid(events):
    track_length = 3 * events + 5
    track = b"\x00\x90\x3c\x01" + b"\x00\x3c\x01" * (events - 1) + b"\x00\xff\x2f\x00"
    return (
        b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x01\xe0"
        + b"MTrk"
        + struct.pack(">I", track_length)
        + track
    )


def _render_payload(request):
    if request.variant == "bmp":
        return _render_bmp(request.width, request.height)
    if request.variant == "jpg":
        return _render_jpg(request.width, request.height)
    if request.variant == "png":
        return _render_png(request.width, request.height)
    if request.variant == "tif":
        return _render_tif(request.width, request.height)
    if request.variant == "wav":
        return _render_wav(request.frame_or_event_count)
    if request.variant == "aiff":
        return _render_aiff(request.frame_or_event_count)
    if request.variant == "mid":
        return _render_mid(request.frame_or_event_count)
    _fail("unknown canonical raw image/media render template")


def render_raw_image_media(request):
    """Render one bounded canonical exemplar without any source identity."""

    validate_request(request)
    profile = _profile(request.variant)
    target_bytes = target_bytes_for(
        request.variant,
        request.width,
        request.height,
        request.frame_or_event_count,
    )
    data = _render_payload(request)
    if type(data) is not bytes or len(data) != target_bytes:
        _fail("rendered bytes differ from the exact structural formula")
    complexity = target_complexity_for(
        request.variant,
        request.width,
        request.height,
        request.frame_or_event_count,
    )
    return RenderedRawImageMedia(
        data=data,
        extension=profile["filename_extension"],
        content_media_type=profile["content_media_type"],
        expected_kio_path_media_type=profile["expected_kio_path_media_type"],
        expected_offline_disposition=profile["expected_offline_disposition"],
        width=request.width,
        height=request.height,
        frame_or_event_count=request.frame_or_event_count,
        target_complexity=complexity,
        target_bytes=target_bytes,
        size_lane=classify_size_lane(target_bytes),
    )


def _contract_variant_row(variant):
    profile = _VARIANT_ROWS[variant]
    image = variant in IMAGE_VARIANTS
    return {
        "complexity": {
            "counting_rule": profile["counting_rule"],
            "inclusive_maximum": MAX_RASTER_PIXELS if image else MAX_MEDIA_UNITS,
            "inclusive_minimum": MIN_RASTER_PIXELS if image else MIN_MEDIA_UNITS,
            "measure": profile["complexity_measure"],
            "raster_dimension_inclusive_maximum": MAX_RASTER_DIMENSION if image else 0,
            "request_binding": (
                "exact-width-times-height" if image else "exact-frame-or-event-count"
            ),
        },
        "content_media_type": profile["content_media_type"],
        "expected_kio_path_media_type": profile["expected_kio_path_media_type"],
        "expected_offline_disposition": profile["expected_offline_disposition"],
        "family": profile["family"],
        "filename_extension": profile["filename_extension"],
        "gate_role": "raw_only",
        "raw_byte_formula": {
            "exact_formula": profile["raw_byte_formula"],
            "formal_ordinary_inclusive_bytes": [
                FORMAL_ORDINARY_MIN_BYTES,
                FORMAL_ORDINARY_MAX_BYTES,
            ],
            "formal_tail_inclusive_bytes": [
                FORMAL_TAIL_MIN_BYTES,
                FORMAL_TAIL_MAX_BYTES,
            ],
            "maximum_rendered_bytes": maximum_rendered_bytes_for(variant),
            "quantization": "exact-integer-structural-fields-no-target-byte-padding",
            "selection_phase": "solved-source-recipe-instance-not-this-contract",
        },
        "render_template": profile["render_template"],
        "variant_id": variant,
    }


def _canonical_contract_value():
    return {
        "artifact_kind": CONTRACT_KIND,
        "artifact_schema": CONTRACT_SCHEMA,
        "artifact_schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_final_source_identifiers": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_renderer_execution": False,
            "authorizes_source_intents": False,
            "authorizes_source_plan": False,
            "kio_execution_attested": False,
        },
        "byte_stress_lane_implemented": False,
        "canonical_limits": {
            "absolute_max_rendered_bytes": MAX_RENDERED_BYTES,
            "formal_ordinary_inclusive_bytes": [
                FORMAL_ORDINARY_MIN_BYTES,
                FORMAL_ORDINARY_MAX_BYTES,
            ],
            "formal_tail_inclusive_bytes": [
                FORMAL_TAIL_MIN_BYTES,
                FORMAL_TAIL_MAX_BYTES,
            ],
            "max_media_frames_or_events": MAX_MEDIA_UNITS,
            "max_raster_dimension": MAX_RASTER_DIMENSION,
            "max_raster_pixels": MAX_RASTER_PIXELS,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "seven-id-free-raw-only-image-media-format-feasibility-variants-"
            "not-source-materialization-or-kio-attestation"
        ),
        "payload_identity_policy": {
            "content_digest_embedded": False,
            "final_source_identifier_embedded": False,
            "intent_identifier_embedded": False,
            "materialization_identifier_embedded": False,
            "persona_identifier_embedded": False,
            "query_or_oracle_content_embedded": False,
            "scope_identifier_embedded": False,
            "source_identifier_embedded": False,
        },
        "renderer_id": RENDERER_ID,
        "renderer_schema_version": RENDERER_SCHEMA_VERSION,
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "variant_count": len(READY_VARIANTS),
        "variant_rows": [_contract_variant_row(variant) for variant in READY_VARIANTS],
        "vertical_slice_implementation_available": True,
    }


def build_renderer_contract():
    return copy.deepcopy(_canonical_contract_value())


def _json_string_upper_bound(value):
    size = 2
    for character in value:
        codepoint = ord(character)
        if character in '"\\' or character in "\b\f\n\r\t":
            size += 2
        elif codepoint < 0x20 or codepoint <= 0xFFFF and codepoint > 0x7F:
            size += 6
        elif codepoint > 0xFFFF:
            size += 12
        else:
            size += 1
        if size > MAX_CONTRACT_BYTES:
            _fail("JSON string exceeds the pre-serialization byte cap")
    return size


def _prevalidate_json_tree(value):
    stack = [(value, 0)]
    nodes = 0
    size_upper_bound = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_CONTRACT_JSON_NODES:
            _fail("contract JSON exceeds the pre-serialization node cap")
        if depth > MAX_CONTRACT_JSON_DEPTH:
            _fail("contract JSON exceeds the pre-serialization depth cap")
        current_type = type(current)
        if current_type is dict:
            if len(current) > MAX_CONTRACT_JSON_NODES:
                _fail("contract JSON object exceeds the node cap")
            size_upper_bound += 2 + max(0, len(current) - 1)
            for key, child in current.items():
                if type(key) is not str:
                    _fail("contract JSON object keys must be exact strings")
                size_upper_bound += _json_string_upper_bound(key) + 1
                if size_upper_bound > MAX_CONTRACT_BYTES:
                    _fail("contract JSON exceeds the pre-serialization byte cap")
                stack.append((child, depth + 1))
        elif current_type is list:
            if len(current) > MAX_CONTRACT_JSON_NODES:
                _fail("contract JSON array exceeds the node cap")
            size_upper_bound += 2 + max(0, len(current) - 1)
            stack.extend((child, depth + 1) for child in current)
        elif current_type is str:
            size_upper_bound += _json_string_upper_bound(current)
        elif current_type is bool:
            size_upper_bound += 4 if current else 5
        elif current is None:
            size_upper_bound += 4
        elif current_type is int:
            bits = abs(current).bit_length()
            digits = 1 if bits == 0 else (bits * 30_103) // 100_000 + 1
            size_upper_bound += digits + (1 if current < 0 else 0)
        elif current_type is float:
            if not math.isfinite(current):
                _fail("contract JSON floats must be finite")
            size_upper_bound += 32
        else:
            _fail("contract JSON contains a non-exact JSON value type")
        if size_upper_bound > MAX_CONTRACT_BYTES:
            _fail("contract JSON exceeds the pre-serialization byte cap")


def canonical_json_bytes(value):
    _prevalidate_json_tree(value)
    try:
        data = artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free raw image/media renderer contract",
            max_bytes=MAX_CONTRACT_BYTES - 1,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    if not data.isascii():
        _fail("raw image/media renderer contract must be canonical ASCII")
    return data + b"\n"


def validate_renderer_contract(value):
    if type(value) is not dict:
        _fail("renderer contract must be an exact object")
    if canonical_json_bytes(value) != canonical_json_bytes(_canonical_contract_value()):
        _fail("renderer contract differs from exact regeneration")
    return True


def renderer_contract_sha256(value=None):
    contract = _canonical_contract_value() if value is None else value
    validate_renderer_contract(contract)
    return hashlib.sha256(canonical_json_bytes(contract)).hexdigest()


__all__ = [
    "FORMAL_ORDINARY_MAX_BYTES",
    "FORMAL_ORDINARY_MIN_BYTES",
    "FORMAL_TAIL_MAX_BYTES",
    "FORMAL_TAIL_MIN_BYTES",
    "IMAGE_VARIANTS",
    "MAX_MEDIA_UNITS",
    "MAX_RASTER_DIMENSION",
    "MAX_RASTER_PIXELS",
    "MAX_RENDERED_BYTES",
    "MEDIA_VARIANTS",
    "PersonaV2RawImageMediaRendererError",
    "READY_VARIANTS",
    "RENDERER_ID",
    "RawImageMediaRenderRequest",
    "RenderedRawImageMedia",
    "build_renderer_contract",
    "canonical_json_bytes",
    "classify_size_lane",
    "maximum_rendered_bytes_for",
    "render_raw_image_media",
    "renderer_contract_sha256",
    "target_bytes_for",
    "target_complexity_for",
    "validate_renderer_contract",
    "validate_request",
]
