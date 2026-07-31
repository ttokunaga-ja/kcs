"""Independent bounded validator for canonical raw image/media feasibility.

The validator imports neither the renderer nor any source/catalog/planning
module.  It duplicates the seven frozen metadata rows and parses every binary
container itself.  Header lengths and structural formulas are checked before
payload-sized work.  A successful receipt is strictly local and negative-
authority: it is not a source, KIO, chunk, history, publication, or G0 claim.
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


CONTRACT_SCHEMA = "kio.persona.pc-id-free-raw-image-media-validator/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-image-media-validator"
VALIDATOR_ID = "persona-v2-id-free-raw-image-media-standalone-validator"
VALIDATOR_SCHEMA_VERSION = 2
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
    "data",
    "extension",
    "content_media_type",
    "expected_kio_path_media_type",
    "expected_offline_disposition",
)

PROHIBITED_IDENTITY_FIELDS = (
    "digest",
    "final_id",
    "final_source_id",
    "intent_id",
    "materialization_id",
    "payload_seed",
    "persona_id",
    "query_id",
    "query_key",
    "scope_id",
    "scope_key",
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


class PersonaV2RawImageMediaValidatorError(ValueError):
    """Raised when bytes or metadata violate the standalone contract."""


@dataclass(frozen=True, slots=True)
class RawImageMediaValidationRequest:
    """Complete identity-free payload supplied to the standalone validator."""

    schema_version: int
    variant: str
    width: int
    height: int
    frame_or_event_count: int
    data: bytes
    extension: str
    content_media_type: str
    expected_kio_path_media_type: str
    expected_offline_disposition: str


def _fail(message):
    raise PersonaV2RawImageMediaValidatorError(message)


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        _fail("unsupported raw image/media variant")
    return _VARIANT_ROWS[variant]


def target_bytes_for(variant, width, height, frame_or_event_count):
    """Independently evaluate the exact canonical structural byte formula."""

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
            _fail("invalid raster axes for standalone byte formula")
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
            _fail("invalid media axes for standalone byte formula")
        if variant == "aiff":
            target = 54 + frame_or_event_count + (frame_or_event_count & 1)
        elif variant == "mid":
            target = 27 + 3 * frame_or_event_count
        else:
            target = 44 + frame_or_event_count + (frame_or_event_count & 1)
    if not 1 <= target <= MAX_RENDERED_BYTES:
        _fail("canonical byte formula exceeds the absolute validator cap")
    return target


def classify_size_lane(byte_length):
    if type(byte_length) is not int or not 1 <= byte_length <= MAX_RENDERED_BYTES:
        _fail("byte length is outside the validator domain")
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
    """Independently derive the maximum file reachable in the legal domain."""

    _profile(variant)
    return _maximum_rendered_bytes_for_valid_variant(variant)


def _validate_request_shape(request):
    if type(request) is not RawImageMediaValidationRequest:
        _fail("request must be an exact RawImageMediaValidationRequest")
    if tuple(RawImageMediaValidationRequest.__dataclass_fields__) != REQUEST_FIELDS:
        _fail("validator request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        _fail("validator request exposes an identity field")
    if type(request.schema_version) is not int or request.schema_version != 2:
        _fail("validator request schema version must be exact 2")
    profile = _profile(request.variant)
    if type(request.data) is not bytes:
        _fail("payload must be exact immutable bytes")
    if not 1 <= len(request.data) <= MAX_RENDERED_BYTES:
        _fail("payload length exceeds the absolute cap before parsing")
    target = target_bytes_for(
        request.variant,
        request.width,
        request.height,
        request.frame_or_event_count,
    )
    if len(request.data) != target:
        _fail("payload length differs from the independent structural formula")
    for field_name, profile_key in (
        ("extension", "filename_extension"),
        ("content_media_type", "content_media_type"),
        ("expected_kio_path_media_type", "expected_kio_path_media_type"),
        ("expected_offline_disposition", "expected_offline_disposition"),
    ):
        value = getattr(request, field_name)
        if type(value) is not str or value != profile[profile_key]:
            _fail(f"{field_name} differs from the frozen variant metadata")
    return profile, target


def _all_equal(view, expected):
    return all(value == expected for value in view)


def _validate_bmp(data, width, height):
    if len(data) < 62:
        _fail("BMP is truncated before its bounded headers")
    signature, file_size, reserved1, reserved2, pixel_offset = struct.unpack_from(
        "<2sIHHI", data, 0
    )
    if (signature, file_size, reserved1, reserved2, pixel_offset) != (
        b"BM", len(data), 0, 0, 62
    ):
        _fail("BMP file header is not canonical")
    dib = struct.unpack_from("<IiiHHIIiiII", data, 14)
    stride = 4 * ((width + 31) // 32)
    image_bytes = stride * height
    if dib != (40, width, height, 1, 1, 0, image_bytes, 2_835, 2_835, 2, 2):
        _fail("BMP dimensions or INFOHEADER fields are not canonical")
    if data[54:62] != b"\x00\x00\x00\x00\xff\xff\xff\x00":
        _fail("BMP monochrome palette is not canonical")
    if not _all_equal(memoryview(data)[62:], 0):
        _fail("BMP raster or row padding is not canonical zero")


def _read_jpeg_segment(data, offset, marker):
    if offset + 4 > len(data):
        _fail("JPEG is truncated before a bounded segment header")
    if data[offset:offset + 2] != b"\xff" + bytes((marker,)):
        _fail("JPEG marker order differs from the canonical baseline subset")
    segment_length = struct.unpack_from(">H", data, offset + 2)[0]
    if segment_length < 2 or segment_length > 65_535:
        _fail("JPEG segment has an invalid bounded length")
    end = offset + 2 + segment_length
    if end > len(data):
        _fail("JPEG segment length crosses the bounded payload")
    return memoryview(data)[offset + 4:end], end


def _validate_jpg(data, width, height):
    if len(data) < 154 or data[:2] != b"\xff\xd8":
        _fail("JPEG SOI is missing or the stream is too short")
    app0, offset = _read_jpeg_segment(data, 2, 0xE0)
    if bytes(app0) != b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00":
        _fail("JPEG JFIF APP0 segment is not canonical")
    dqt, offset = _read_jpeg_segment(data, offset, 0xDB)
    if len(dqt) != 65 or dqt[0] != 0 or not _all_equal(dqt[1:], 1):
        _fail("JPEG 8-bit quantization table is not canonical")
    sof0, offset = _read_jpeg_segment(data, offset, 0xC0)
    if len(sof0) != 9:
        _fail("JPEG SOF0 length is not canonical")
    precision, parsed_height, parsed_width, components = struct.unpack_from(
        ">BHHB", sof0, 0
    )
    if (precision, parsed_height, parsed_width, components) != (8, height, width, 1):
        _fail("JPEG SOF0 dimensions or precision differ from the request")
    if bytes(sof0[6:]) != b"\x01\x11\x00":
        _fail("JPEG grayscale component descriptor is not canonical")
    dht, offset = _read_jpeg_segment(data, offset, 0xC4)
    counts = b"\x01" + b"\x00" * 15
    expected_dht = b"\x00" + counts + b"\x00" + b"\x10" + counts + b"\x00"
    if bytes(dht) != expected_dht:
        _fail("JPEG DC/AC Huffman tables are not canonical")
    sos, offset = _read_jpeg_segment(data, offset, 0xDA)
    if bytes(sos) != b"\x01\x01\x00\x00\x3f\x00":
        _fail("JPEG sequential scan parameters are not canonical")
    blocks = ((width + 7) // 8) * ((height + 7) // 8)
    scan_length = (blocks + 3) // 4
    if offset + scan_length + 2 != len(data) or data[-2:] != b"\xff\xd9":
        _fail("JPEG entropy span or EOI position differs from dimensions")
    full_bytes, remaining_blocks = divmod(blocks, 4)
    scan = memoryview(data)[offset:offset + scan_length]
    if not _all_equal(scan[:full_bytes], 0):
        _fail("JPEG entropy-coded zero-DCT blocks are not canonical")
    if remaining_blocks:
        expected_last = (1 << (8 - 2 * remaining_blocks)) - 1
        if scan[-1] != expected_last:
            _fail("JPEG entropy fill bits are not canonical all-ones padding")


def _read_png_chunk(data, offset, expected_type):
    if offset + 12 > len(data):
        _fail("PNG is truncated before a bounded chunk header")
    length = struct.unpack_from(">I", data, offset)[0]
    if length > MAX_RENDERED_BYTES or offset + 12 + length > len(data):
        _fail("PNG chunk length crosses the bounded payload")
    chunk_type = data[offset + 4:offset + 8]
    if chunk_type != expected_type:
        _fail("PNG chunk order or type is not canonical")
    payload_start = offset + 8
    payload_end = payload_start + length
    expected_crc = struct.unpack_from(">I", data, payload_end)[0]
    actual_crc = binascii.crc32(chunk_type)
    actual_crc = binascii.crc32(memoryview(data)[payload_start:payload_end], actual_crc) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        _fail("PNG chunk CRC does not validate")
    return memoryview(data)[payload_start:payload_end], payload_end + 4


def _validate_png(data, width, height):
    if len(data) < 68 or data[:8] != b"\x89PNG\r\n\x1a\n":
        _fail("PNG signature is missing or the stream is truncated")
    ihdr, offset = _read_png_chunk(data, 8, b"IHDR")
    if len(ihdr) != 13:
        _fail("PNG IHDR length is not canonical")
    fields = struct.unpack(">IIBBBBB", ihdr)
    if fields != (width, height, 1, 0, 0, 0, 0):
        _fail("PNG IHDR dimensions or one-bit grayscale mode differ")
    idat, offset = _read_png_chunk(data, offset, b"IDAT")
    iend, offset = _read_png_chunk(data, offset, b"IEND")
    if len(iend) != 0 or offset != len(data):
        _fail("PNG IEND or trailing-byte policy differs")
    row_bytes = (width + 7) // 8
    raw_length = (row_bytes + 1) * height
    deflate_blocks = (raw_length + 65_534) // 65_535
    if len(idat) != raw_length + 5 * deflate_blocks + 6:
        _fail("PNG IDAT length differs from stored-DEFLATE formula")
    if bytes(idat[:2]) != b"\x78\x01":
        _fail("PNG zlib header is not the canonical stored-block profile")
    cursor = 2
    remaining = raw_length
    for block_index in range(deflate_blocks):
        if cursor + 5 > len(idat) - 4:
            _fail("PNG stored block is truncated before LEN/NLEN")
        block_length = min(remaining, 65_535)
        remaining -= block_length
        expected_header = 1 if remaining == 0 else 0
        header = idat[cursor]
        length, inverse = struct.unpack_from("<HH", idat, cursor + 1)
        if header != expected_header or length != block_length or inverse != (block_length ^ 0xFFFF):
            _fail("PNG stored-DEFLATE block framing is not canonical")
        cursor += 5
        block_end = cursor + block_length
        if block_end > len(idat) - 4:
            _fail("PNG stored block length crosses the zlib payload")
        if not _all_equal(idat[cursor:block_end], 0):
            _fail("PNG filters, pixels, or row padding are not canonical zero")
        cursor = block_end
    if remaining != 0 or cursor + 4 != len(idat):
        _fail("PNG stored blocks do not cover the exact decoded raster")
    expected_adler = ((raw_length % 65_521) << 16) | 1
    if struct.unpack_from(">I", idat, cursor)[0] != expected_adler:
        _fail("PNG zlib Adler-32 does not validate")


def _parse_tiff_inline_value(entry):
    tag, field_type, count = struct.unpack_from("<HHI", entry, 0)
    if count != 1:
        _fail("TIFF canonical IFD entries must have count one")
    if field_type == 3:
        if bytes(entry[10:12]) != b"\x00\x00":
            _fail("TIFF SHORT inline padding is not canonical")
        value = struct.unpack_from("<H", entry, 8)[0]
    elif field_type == 4:
        value = struct.unpack_from("<I", entry, 8)[0]
    else:
        _fail("TIFF canonical IFD uses only SHORT and LONG fields")
    return tag, field_type, value


def _validate_tif(data, width, height):
    if len(data) < 110 or data[:8] != b"II\x2a\x00\x08\x00\x00\x00":
        _fail("TIFF byte order, magic, or first IFD offset is invalid")
    count = struct.unpack_from("<H", data, 8)[0]
    if count != 8:
        _fail("TIFF canonical IFD must contain exactly eight entries")
    parsed = []
    for index in range(count):
        start = 10 + 12 * index
        parsed.append(_parse_tiff_inline_value(memoryview(data)[start:start + 12]))
    strip_bytes = ((width + 7) // 8) * height
    expected = [
        (256, 4, width),
        (257, 4, height),
        (258, 3, 1),
        (259, 3, 1),
        (262, 3, 1),
        (273, 4, 110),
        (278, 4, height),
        (279, 4, strip_bytes),
    ]
    if parsed != expected or data[106:110] != b"\x00\x00\x00\x00":
        _fail("TIFF IFD dimensions, strip bounds, or next-IFD value differ")
    if not _all_equal(memoryview(data)[110:], 0):
        _fail("TIFF single-strip pixels or row padding are not canonical zero")


def _validate_wav(data, frames):
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:16] != b"WAVEfmt ":
        _fail("WAVE RIFF or fmt framing is invalid")
    riff_size = struct.unpack_from("<I", data, 4)[0]
    if riff_size != len(data) - 8:
        _fail("WAVE RIFF size does not cover the bounded file")
    fmt = struct.unpack_from("<IHHIIHH", data, 16)
    if fmt != (16, 1, 1, 8_000, 8_000, 1, 8):
        _fail("WAVE PCM format, channel count, or sample rate differs")
    if data[36:40] != b"data" or struct.unpack_from("<I", data, 40)[0] != frames:
        _fail("WAVE data chunk size differs from the requested frame count")
    if not _all_equal(memoryview(data)[44:44 + frames], 0x80):
        _fail("WAVE unsigned 8-bit silence samples are not canonical")
    if (frames & 1) and data[-1] != 0:
        _fail("WAVE odd-size chunk pad byte is not canonical zero")


def _validate_aiff(data, frames):
    if len(data) < 54 or data[:4] != b"FORM" or data[8:16] != b"AIFFCOMM":
        _fail("AIFF FORM or COMM framing is invalid")
    form_size = struct.unpack_from(">I", data, 4)[0]
    if form_size != len(data) - 8:
        _fail("AIFF FORM size does not cover the bounded file")
    if struct.unpack_from(">I", data, 16)[0] != 18:
        _fail("AIFF COMM chunk length is not canonical")
    channels, parsed_frames, sample_bits = struct.unpack_from(">hIh", data, 20)
    rate = data[28:38]
    if (channels, parsed_frames, sample_bits) != (1, frames, 8):
        _fail("AIFF channel, frame, or sample-size fields differ")
    if rate != b"\x40\x0b\xfa\x00\x00\x00\x00\x00\x00\x00":
        _fail("AIFF 80-bit 8000 Hz sample rate is not canonical")
    if data[38:42] != b"SSND" or struct.unpack_from(">I", data, 42)[0] != frames + 8:
        _fail("AIFF SSND chunk length differs from the requested frames")
    if data[46:54] != b"\x00" * 8:
        _fail("AIFF SSND offset or block size is not canonical zero")
    if not _all_equal(memoryview(data)[54:54 + frames], 0):
        _fail("AIFF signed 8-bit silence samples are not canonical")
    if (frames & 1) and data[-1] != 0:
        _fail("AIFF odd-size chunk pad byte is not canonical zero")


def _validate_mid(data, events):
    if len(data) < 30 or data[:14] != b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x01\xe0":
        _fail("MIDI header must be SMF format 0, one track, division 480")
    if data[14:18] != b"MTrk":
        _fail("MIDI track chunk is missing")
    track_length = struct.unpack_from(">I", data, 18)[0]
    if track_length != 3 * events + 5 or track_length + 22 != len(data):
        _fail("MIDI bounded track length differs from the event formula")
    cursor = 22
    if data[cursor:cursor + 4] != b"\x00\x90\x3c\x01":
        _fail("MIDI first note-on event or status is not canonical")
    cursor += 4
    observed_events = 1
    while observed_events < events:
        if cursor + 3 > len(data):
            _fail("MIDI running-status event is truncated")
        if data[cursor] != 0 or data[cursor + 1] != 0x3C or data[cursor + 2] != 1:
            _fail("MIDI delta, note, velocity, or running status differs")
        cursor += 3
        observed_events += 1
    if data[cursor:cursor + 4] != b"\x00\xff\x2f\x00" or cursor + 4 != len(data):
        _fail("MIDI mandatory end-of-track event or trailing policy differs")
    if observed_events != events:
        _fail("MIDI observed note-on event count differs from the request")


def _validate_structure(request):
    if request.variant == "bmp":
        _validate_bmp(request.data, request.width, request.height)
    elif request.variant == "jpg":
        _validate_jpg(request.data, request.width, request.height)
    elif request.variant == "png":
        _validate_png(request.data, request.width, request.height)
    elif request.variant == "tif":
        _validate_tif(request.data, request.width, request.height)
    elif request.variant == "wav":
        _validate_wav(request.data, request.frame_or_event_count)
    elif request.variant == "aiff":
        _validate_aiff(request.data, request.frame_or_event_count)
    elif request.variant == "mid":
        _validate_mid(request.data, request.frame_or_event_count)
    else:  # pragma: no cover - exact metadata table prevents this branch.
        _fail("unknown standalone raw image/media parser")


def validate_raw_image_media_payload(request):
    """Parse canonical bytes and return a strictly negative-authority receipt."""

    profile, target = _validate_request_shape(request)
    _validate_structure(request)
    complexity = (
        request.width * request.height
        if request.variant in IMAGE_VARIANTS
        else request.frame_or_event_count
    )
    return {
        "actual_chunks_attested": False,
        "byte_length": len(request.data),
        "checksum_fields_validated": request.variant == "png",
        "height": request.height,
        "identity_tokens_absent": True,
        "kio_execution_attested": False,
        "observed_complexity_measure": profile["complexity_measure"],
        "observed_local_complexity": complexity,
        "size_lane": classify_size_lane(target),
        "structure_validated": True,
        "target_bytes": target,
        "width": request.width,
    }


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
        "validator_profile_id": f"{variant}-standalone-id-free-raw-image-media-validation-v2",
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
            "seven-id-free-raw-only-image-media-format-validation-variants-"
            "not-source-materialization-or-kio-attestation"
        ),
        "independence_contract": {
            "checks_bounded_headers_before_payload_work": True,
            "imports_planning_modules": False,
            "imports_renderer_module": False,
            "imports_source_or_variant_catalog": False,
            "parses_each_binary_format_with_standard_library_primitives": True,
            "recomputes_structural_byte_formula": True,
            "validates_checksums_where_the_format_defines_them": True,
            "validates_dimensions_frames_or_events": True,
        },
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "validator_id": VALIDATOR_ID,
        "validator_schema_version": VALIDATOR_SCHEMA_VERSION,
        "variant_count": len(READY_VARIANTS),
        "variant_rows": [_contract_variant_row(variant) for variant in READY_VARIANTS],
        "vertical_slice_implementation_available": True,
    }


def build_validator_contract():
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
            label="persona v2 ID-free raw image/media validator contract",
            max_bytes=MAX_CONTRACT_BYTES - 1,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    if not data.isascii():
        _fail("raw image/media validator contract must be canonical ASCII")
    return data + b"\n"


def validate_validator_contract(value):
    if type(value) is not dict:
        _fail("validator contract must be an exact object")
    if canonical_json_bytes(value) != canonical_json_bytes(_canonical_contract_value()):
        _fail("validator contract differs from exact regeneration")
    return True


def validator_contract_sha256(value=None):
    contract = _canonical_contract_value() if value is None else value
    validate_validator_contract(contract)
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
    "PersonaV2RawImageMediaValidatorError",
    "READY_VARIANTS",
    "RawImageMediaValidationRequest",
    "VALIDATOR_ID",
    "build_validator_contract",
    "canonical_json_bytes",
    "classify_size_lane",
    "maximum_rendered_bytes_for",
    "target_bytes_for",
    "validate_raw_image_media_payload",
    "validate_validator_contract",
    "validator_contract_sha256",
]
