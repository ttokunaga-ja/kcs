"""Independent bounded validator for persona-PC v2 raw domain binaries.

The module intentionally does not import the renderer, source/variant catalogs,
the persona contract, or planning modules.  It duplicates the two frozen format
profiles and validates classic PCAP plus a fixed DICOM Part 10 Explicit VR
Little Endian subset using bounded standard-library parsing.  A successful
receipt proves local bytes and structure only and grants no source, write, KCS,
history, solver, renderer-execution, or G0 authority.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
import struct

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kcs.persona.pc-id-free-raw-domain-validator/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-domain-validator"
VALIDATOR_ID = "persona-v2-id-free-raw-domain-standalone-validator"
VALIDATOR_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 64 * 1024
MAX_RENDERED_BYTES = 512 * 1024

READY_VARIANTS = ("dicom-part10", "pcap")
REQUEST_FIELDS = (
    "schema_version",
    "variant",
    "target_complexity",
    "data",
    "extension",
    "content_media_type",
    "expected_kcs_path_media_type",
    "expected_offline_disposition",
)
PROHIBITED_IDENTITY_FIELDS = (
    "digest",
    "final_source_id",
    "intent_key",
    "materialization_id",
    "path",
    "persona_id",
    "query_id",
    "scope_key",
    "source_id",
)

PCAP_GLOBAL_HEADER_BYTES = 24
PCAP_PACKET_PAYLOAD_BYTES = 64
PCAP_CAPTURED_FRAME_BYTES = 106
PCAP_RECORD_BYTES = 122
PCAP_MAX_PACKETS = 4_096
PCAP_SNAPLEN = 65_535

DICOM_ROWS = 64
DICOM_COLUMNS = 64
DICOM_BYTES_PER_FRAME = 4_096
DICOM_MAX_FRAMES = 64
DICOM_PRIVATE_PADDING_BYTES = 256
DICOM_PAGE_VECTOR_BYTES_PER_FRAME = 4
DICOM_FIXED_BYTES = 1_108

_PCAP_MAGIC = 0xA1B2C3D4
_PCAP_LINKTYPE_ETHERNET = 1
_PCAP_SOURCE_MAC = b"\x02\x00\x00\x00\x00\x01"
_PCAP_DESTINATION_MAC = b"\x02\x00\x00\x00\x00\x02"
_PCAP_SOURCE_IP = b"\xc0\x00\x02\x01"
_PCAP_DESTINATION_IP = b"\xc6\x33\x64\x02"
_PCAP_UDP_DESTINATION_PORT = 41_000

_DICOM_SOP_CLASS_UID = b"1.2.840.10008.5.1.4.1.1.7.2\x00"
_DICOM_STUDY_INSTANCE_UID = b"2.25.210000000000000000000000000000000000001"
_DICOM_SERIES_INSTANCE_UID = b"2.25.220000000000000000000000000000000000001"
_DICOM_SOP_INSTANCE_UID_PREFIX = "2.25.2000000000000000000000000000000000000"
_DICOM_TRANSFER_SYNTAX_UID = b"1.2.840.10008.1.2.1\x00"
_DICOM_IMPLEMENTATION_CLASS_UID = b"2.25.2"
_DICOM_IMPLEMENTATION_VERSION = b"KCSRAW_2"
_DICOM_PRIVATE_CREATOR = b"KCS_BOUNDED "
_DICOM_LONG_VRS = frozenset(
    (b"OB", b"OD", b"OF", b"OL", b"OW", b"SQ", b"UC", b"UN", b"UR", b"UT")
)
_DICOM_SHORT_VRS = frozenset(
    (
        b"AE",
        b"AS",
        b"AT",
        b"CS",
        b"DA",
        b"DS",
        b"DT",
        b"FD",
        b"FL",
        b"IS",
        b"LO",
        b"LT",
        b"PN",
        b"SH",
        b"SL",
        b"SS",
        b"ST",
        b"TM",
        b"UI",
        b"UL",
        b"US",
    )
)

_VARIANT_ROWS = {
    "dicom-part10": {
        "base_bytes": 5_208,
        "complexity_measure": "frames",
        "content_media_type": "application/dicom",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "family": "domain_binary",
        "filename_extension": "dcm",
        "inclusive_maximum": 64,
        "inclusive_minimum": 1,
        "increment_bytes": 4_100,
        "render_template": (
            "dicom-part10-multiframe-grayscale-byte-sc-explicit-vr-little-"
            "endian-v3"
        ),
    },
    "pcap": {
        "base_bytes": 146,
        "complexity_measure": "packets",
        "content_media_type": "application/vnd.tcpdump.pcap",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "family": "domain_binary",
        "filename_extension": "pcap",
        "inclusive_maximum": 4_096,
        "inclusive_minimum": 1,
        "increment_bytes": 122,
        "render_template": "classic-pcap-ethernet-ipv4-udp-fixed-record-v2",
    },
}

_COMPLEXITY_COUNTING_RULES = {
    "dicom-part10": "number-of-frames-and-contiguous-native-pixel-frames",
    "pcap": "classic-pcap-packet-records",
}

_FORBIDDEN_IDENTITY_PATTERN = re.compile(
    rb"(?:"
    rb"\bp[0-9]{2}-src-[0-9]{6}\b|"
    rb"\b(?:persona|scope|source|intent|materialization|query|final[_-]?source)"
    rb"[_-]?(?:id|key)\s*[:=]|"
    rb"\b(?:sha256|digest)\s*[:=]|"
    rb"\b[0-9a-f]{64}\b"
    rb")",
    re.IGNORECASE,
)

_EXPECTED_DICOM_TAGS = (
    ((0x0002, 0x0000), b"UL"),
    ((0x0002, 0x0001), b"OB"),
    ((0x0002, 0x0002), b"UI"),
    ((0x0002, 0x0003), b"UI"),
    ((0x0002, 0x0010), b"UI"),
    ((0x0002, 0x0012), b"UI"),
    ((0x0002, 0x0013), b"SH"),
    ((0x0008, 0x0016), b"UI"),
    ((0x0008, 0x0018), b"UI"),
    ((0x0008, 0x0020), b"DA"),
    ((0x0008, 0x0030), b"TM"),
    ((0x0008, 0x0050), b"SH"),
    ((0x0008, 0x0060), b"CS"),
    ((0x0008, 0x0064), b"CS"),
    ((0x0008, 0x0090), b"PN"),
    ((0x0010, 0x0010), b"PN"),
    ((0x0010, 0x0020), b"LO"),
    ((0x0010, 0x0030), b"DA"),
    ((0x0010, 0x0040), b"CS"),
    ((0x0011, 0x0010), b"LO"),
    ((0x0011, 0x1001), b"OB"),
    ((0x0018, 0x2001), b"IS"),
    ((0x0020, 0x000D), b"UI"),
    ((0x0020, 0x000E), b"UI"),
    ((0x0020, 0x0010), b"SH"),
    ((0x0020, 0x0011), b"IS"),
    ((0x0020, 0x0013), b"IS"),
    ((0x0020, 0x0020), b"CS"),
    ((0x0028, 0x0002), b"US"),
    ((0x0028, 0x0004), b"CS"),
    ((0x0028, 0x0008), b"IS"),
    ((0x0028, 0x0009), b"AT"),
    ((0x0028, 0x0010), b"US"),
    ((0x0028, 0x0011), b"US"),
    ((0x0028, 0x0100), b"US"),
    ((0x0028, 0x0101), b"US"),
    ((0x0028, 0x0102), b"US"),
    ((0x0028, 0x0103), b"US"),
    ((0x0028, 0x0301), b"CS"),
    ((0x0028, 0x1052), b"DS"),
    ((0x0028, 0x1053), b"DS"),
    ((0x0028, 0x1054), b"LO"),
    ((0x2050, 0x0020), b"CS"),
    ((0x7FE0, 0x0010), b"OB"),
)


class PersonaV2RawDomainValidatorError(ValueError):
    """Raised when raw-domain bytes violate the exact bounded contract."""


@dataclass(frozen=True, slots=True)
class RawDomainValidationRequest:
    schema_version: int
    variant: str
    target_complexity: int
    data: bytes
    extension: str
    content_media_type: str
    expected_kcs_path_media_type: str
    expected_offline_disposition: str


def _fail(message):
    raise PersonaV2RawDomainValidatorError(message)


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        _fail("unknown raw-domain variant")
    return _VARIANT_ROWS[variant]


def _complexity(variant, value):
    profile = _profile(variant)
    if type(value) is not int:
        _fail("target_complexity must be an exact integer")
    if not profile["inclusive_minimum"] <= value <= profile["inclusive_maximum"]:
        _fail(f"target_complexity is outside the bounded {variant} range")
    return value


def target_bytes_for(variant, target_complexity):
    profile = _profile(variant)
    complexity = _complexity(variant, target_complexity)
    target = profile["base_bytes"] + (
        complexity - profile["inclusive_minimum"]
    ) * profile["increment_bytes"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        _fail("raw-domain target exceeds the formal ordinary byte cap")
    return target


def _validate_request(request):
    if type(request) is not RawDomainValidationRequest:
        _fail("request must be the exact RawDomainValidationRequest type")
    if type(request.schema_version) is not int or request.schema_version != 2:
        _fail("unsupported request schema version")
    profile = _profile(request.variant)
    _complexity(request.variant, request.target_complexity)
    if type(request.data) is not bytes:
        _fail("data must be exact bytes")
    if len(request.data) > MAX_RENDERED_BYTES:
        _fail("raw-domain body exceeds the pre-parse byte cap")
    metadata = (
        (request.extension, profile["filename_extension"]),
        (request.content_media_type, profile["content_media_type"]),
        (
            request.expected_kcs_path_media_type,
            profile["expected_kcs_path_media_type"],
        ),
        (
            request.expected_offline_disposition,
            profile["expected_offline_disposition"],
        ),
    )
    if any(
        type(actual) is not str or actual != expected
        for actual, expected in metadata
    ):
        _fail("raw-domain extension or media/disposition metadata drifted")
    target = target_bytes_for(request.variant, request.target_complexity)
    if len(request.data) != target:
        _fail("raw-domain body length differs from the exact byte formula")
    if _FORBIDDEN_IDENTITY_PATTERN.search(request.data):
        _fail("raw-domain bytes contain a prohibited external identity token")
    return profile, target


def _internet_checksum(data):
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for offset in range(0, len(data), 2):
        total += (data[offset] << 8) | data[offset + 1]
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _expected_pcap_payload(packet_ordinal):
    return bytes(
        (packet_ordinal * 17 + payload_ordinal * 29 + 11) & 0xFF
        for payload_ordinal in range(PCAP_PACKET_PAYLOAD_BYTES)
    )


def _validate_pcap(data, packet_count):
    if len(data) < PCAP_GLOBAL_HEADER_BYTES:
        _fail("PCAP global header is truncated")
    global_header = struct.unpack_from("<IHHIIII", data, 0)
    if global_header != (
        _PCAP_MAGIC,
        2,
        4,
        0,
        0,
        PCAP_SNAPLEN,
        _PCAP_LINKTYPE_ETHERNET,
    ):
        _fail("PCAP global header or Ethernet linktype drifted")

    offset = PCAP_GLOBAL_HEADER_BYTES
    for packet_ordinal in range(1, packet_count + 1):
        if offset + 16 > len(data):
            _fail("PCAP packet record header is truncated")
        ts_sec, ts_usec, included_length, original_length = struct.unpack_from(
            "<IIII", data, offset
        )
        offset += 16
        if (
            ts_sec != 1_700_000_000 + packet_ordinal
            or ts_usec != (packet_ordinal * 7_919) % 1_000_000
            or included_length != PCAP_CAPTURED_FRAME_BYTES
            or original_length != PCAP_CAPTURED_FRAME_BYTES
            or included_length > PCAP_SNAPLEN
        ):
            _fail("PCAP packet timestamp or captured/original length drifted")
        end = offset + included_length
        if end > len(data):
            _fail("PCAP captured frame exceeds the bounded body")
        frame = data[offset:end]
        offset = end

        if (
            frame[:6] != _PCAP_DESTINATION_MAC
            or frame[6:12] != _PCAP_SOURCE_MAC
            or frame[12:14] != b"\x08\x00"
        ):
            _fail("PCAP Ethernet header drifted")
        ipv4 = frame[14:34]
        if len(ipv4) != 20:
            _fail("PCAP IPv4 header is truncated")
        (
            version_ihl,
            dscp_ecn,
            total_length,
            identification,
            flags_fragment,
            ttl,
            protocol,
            _header_checksum,
            source_ip,
            destination_ip,
        ) = struct.unpack(">BBHHHBBH4s4s", ipv4)
        if (
            version_ihl != 0x45
            or dscp_ecn != 0
            or total_length != 20 + 8 + PCAP_PACKET_PAYLOAD_BYTES
            or total_length != len(frame) - 14
            or identification != packet_ordinal
            or flags_fragment != 0x4000
            or ttl != 64
            or protocol != 17
            or source_ip != _PCAP_SOURCE_IP
            or destination_ip != _PCAP_DESTINATION_IP
            or _internet_checksum(ipv4) != 0
        ):
            _fail("PCAP IPv4 lengths, fields, or header checksum drifted")

        udp = frame[34:42]
        payload = frame[42:]
        source_port, destination_port, udp_length, udp_checksum = struct.unpack(
            ">HHHH", udp
        )
        if (
            source_port != 40_000 + (packet_ordinal % 1_000)
            or destination_port != _PCAP_UDP_DESTINATION_PORT
            or udp_length != 8 + PCAP_PACKET_PAYLOAD_BYTES
            or udp_length != len(frame) - 34
            or udp_checksum == 0
            or payload != _expected_pcap_payload(packet_ordinal)
        ):
            _fail("PCAP UDP lengths, ports, checksum presence, or payload drifted")
        pseudo_header = (
            source_ip
            + destination_ip
            + b"\x00\x11"
            + struct.pack(">H", udp_length)
        )
        if _internet_checksum(pseudo_header + udp + payload) != 0:
            _fail("PCAP UDP checksum is invalid")
    if offset != len(data):
        _fail("PCAP body has trailing bytes or a packet-count mismatch")


def _parse_dicom_elements(data):
    if data[:128] != b"\x00" * 128 or data[128:132] != b"DICM":
        _fail("DICOM Part 10 preamble or DICM prefix drifted")
    offset = 132
    elements = []
    while offset < len(data):
        start = offset
        if offset + 8 > len(data):
            _fail("DICOM explicit-VR element header is truncated")
        group, element = struct.unpack_from("<HH", data, offset)
        vr = data[offset + 4 : offset + 6]
        if vr in _DICOM_LONG_VRS:
            if offset + 12 > len(data) or data[offset + 6 : offset + 8] != b"\x00\x00":
                _fail("DICOM long-VR reserved bytes or header drifted")
            length = struct.unpack_from("<I", data, offset + 8)[0]
            value_offset = offset + 12
        elif vr in _DICOM_SHORT_VRS:
            length = struct.unpack_from("<H", data, offset + 6)[0]
            value_offset = offset + 8
        else:
            _fail("DICOM contains an unsupported or implicit VR")
        if length == 0xFFFFFFFF:
            _fail("DICOM undefined-length elements are prohibited")
        if length % 2:
            _fail("DICOM element value length must be even")
        end = value_offset + length
        if end > len(data):
            _fail("DICOM element exceeds the bounded body")
        elements.append(
            {
                "end": end,
                "length": length,
                "start": start,
                "tag": (group, element),
                "value": data[value_offset:end],
                "value_offset": value_offset,
                "vr": vr,
            }
        )
        offset = end
    if offset != len(data):
        _fail("DICOM parse did not consume the exact body")
    return elements


def _expected_private_padding():
    return bytes((ordinal * 13 + 7) & 0xFF for ordinal in range(256))


def _expected_pixel_data(frame_count):
    return bytes(
        (frame_ordinal * 17 + pixel_ordinal * 29 + 11) & 0xFF
        for frame_ordinal in range(frame_count)
        for pixel_ordinal in range(DICOM_BYTES_PER_FRAME)
    )


def _expected_sop_instance_uid(frame_count):
    value = f"{_DICOM_SOP_INSTANCE_UID_PREFIX}{frame_count:02d}".encode("ascii")
    if len(value) != 44:
        _fail("internal DICOM SOP Instance UID width drifted")
    return value


def _expected_page_number_vector(frame_count):
    value = b"\\".join(
        f"{frame_ordinal:03d}".encode("ascii")
        for frame_ordinal in range(1, frame_count + 1)
    )
    if len(value) % 2:
        value += b" "
    if len(value) != frame_count * DICOM_PAGE_VECTOR_BYTES_PER_FRAME:
        _fail("internal DICOM page vector width drifted")
    return value


def _validate_dicom(data, frame_count):
    elements = _parse_dicom_elements(data)
    identities = tuple((row["tag"], row["vr"]) for row in elements)
    if identities != _EXPECTED_DICOM_TAGS:
        _fail("DICOM fixed tag/VR subset or canonical order drifted")
    by_tag = {row["tag"]: row for row in elements}
    if len(by_tag) != len(elements):
        _fail("DICOM contains duplicate tags")

    group_length_value = by_tag[(0x0002, 0x0000)]["value"]
    if len(group_length_value) != 4:
        _fail("DICOM File Meta Information Group Length value size drifted")
    group_length = struct.unpack("<I", group_length_value)[0]
    first_dataset_start = by_tag[(0x0008, 0x0016)]["start"]
    if group_length != first_dataset_start - by_tag[(0x0002, 0x0000)]["end"]:
        _fail("DICOM File Meta Information Group Length drifted")
    sop_instance_uid = _expected_sop_instance_uid(frame_count)
    if len(
        {
            sop_instance_uid,
            _DICOM_STUDY_INSTANCE_UID,
            _DICOM_SERIES_INSTANCE_UID,
        }
    ) != 3:
        _fail("DICOM Study, Series, and SOP Instance UIDs must be distinct")
    exact_values = {
        (0x0002, 0x0001): b"\x00\x01",
        (0x0002, 0x0002): _DICOM_SOP_CLASS_UID,
        (0x0002, 0x0003): sop_instance_uid,
        (0x0002, 0x0010): _DICOM_TRANSFER_SYNTAX_UID,
        (0x0002, 0x0012): _DICOM_IMPLEMENTATION_CLASS_UID,
        (0x0002, 0x0013): _DICOM_IMPLEMENTATION_VERSION,
        (0x0008, 0x0016): _DICOM_SOP_CLASS_UID,
        (0x0008, 0x0018): sop_instance_uid,
        (0x0008, 0x0020): b"20260715",
        (0x0008, 0x0030): b"120000",
        (0x0008, 0x0050): b"",
        (0x0008, 0x0060): b"OT",
        (0x0008, 0x0064): b"SYN ",
        (0x0008, 0x0090): b"",
        (0x0010, 0x0010): b"",
        (0x0010, 0x0020): b"",
        (0x0010, 0x0030): b"",
        (0x0010, 0x0040): b"",
        (0x0011, 0x0010): _DICOM_PRIVATE_CREATOR,
        (0x0018, 0x2001): _expected_page_number_vector(frame_count),
        (0x0020, 0x000D): _DICOM_STUDY_INSTANCE_UID,
        (0x0020, 0x000E): _DICOM_SERIES_INSTANCE_UID,
        (0x0020, 0x0010): b"",
        (0x0020, 0x0011): b"1 ",
        (0x0020, 0x0013): b"1 ",
        (0x0020, 0x0020): b"",
        (0x0028, 0x0002): struct.pack("<H", 1),
        (0x0028, 0x0004): b"MONOCHROME2 ",
        (0x0028, 0x0008): f"{frame_count:02d}".encode("ascii"),
        (0x0028, 0x0009): struct.pack("<HH", 0x0018, 0x2001),
        (0x0028, 0x0010): struct.pack("<H", DICOM_ROWS),
        (0x0028, 0x0011): struct.pack("<H", DICOM_COLUMNS),
        (0x0028, 0x0100): struct.pack("<H", 8),
        (0x0028, 0x0101): struct.pack("<H", 8),
        (0x0028, 0x0102): struct.pack("<H", 7),
        (0x0028, 0x0103): struct.pack("<H", 0),
        (0x0028, 0x0301): b"NO",
        (0x0028, 0x1052): b"0 ",
        (0x0028, 0x1053): b"1 ",
        (0x0028, 0x1054): b"US",
        (0x2050, 0x0020): b"IDENTITY",
    }
    for tag, expected in exact_values.items():
        if by_tag[tag]["value"] != expected:
            _fail(f"DICOM fixed element value drifted: {tag!r}")
    private_padding = by_tag[(0x0011, 0x1001)]["value"]
    if (
        len(private_padding) != DICOM_PRIVATE_PADDING_BYTES
        or private_padding != _expected_private_padding()
    ):
        _fail("DICOM private padding length or bytes drifted")
    pixel_data = by_tag[(0x7FE0, 0x0010)]["value"]
    expected_pixel_bytes = frame_count * DICOM_BYTES_PER_FRAME
    if (
        len(pixel_data) != expected_pixel_bytes
        or expected_pixel_bytes > DICOM_MAX_FRAMES * DICOM_BYTES_PER_FRAME
        or pixel_data != _expected_pixel_data(frame_count)
    ):
        _fail("DICOM native pixel byte length, frame count, or bytes drifted")


def validate_raw_domain_payload(request):
    """Validate one payload and return a strictly negative-authority receipt."""

    profile, target = _validate_request(request)
    if request.variant == "pcap":
        _validate_pcap(request.data, request.target_complexity)
        packet_count = request.target_complexity
        frame_count = 0
        pixel_bytes = 0
        private_padding_bytes = 0
    else:
        _validate_dicom(request.data, request.target_complexity)
        packet_count = 0
        frame_count = request.target_complexity
        pixel_bytes = request.target_complexity * DICOM_BYTES_PER_FRAME
        private_padding_bytes = DICOM_PRIVATE_PADDING_BYTES
    return {
        "actual_chunks_attested": False,
        "byte_length": len(request.data),
        "frame_count": frame_count,
        "identity_tokens_absent": True,
        "kcs_execution_attested": False,
        "observed_complexity_measure": profile["complexity_measure"],
        "observed_local_complexity": request.target_complexity,
        "packet_count": packet_count,
        "pixel_bytes": pixel_bytes,
        "private_padding_bytes": private_padding_bytes,
        "structure_validated": True,
        "target_bytes": target,
    }


def _format_limits(variant):
    if variant == "pcap":
        return {
            "captured_frame_bytes": 106,
            "ethernet_linktype": 1,
            "ipv4_header_bytes": 20,
            "packet_payload_bytes": 64,
            "pcap_record_header_bytes": 16,
            "snaplen": 65_535,
            "udp_header_bytes": 8,
        }
    return {
        "bits_allocated": 8,
        "bytes_per_frame": 4_096,
        "columns": 64,
        "defined_lengths_only": True,
        "explicit_vr_little_endian_only": True,
        "max_pixel_bytes": 262_144,
        "frame_increment_pointer_tag": "0018,2001",
        "multiframe_grayscale_byte_sc_sop_class_uid": (
            "1.2.840.10008.5.1.4.1.1.7.2"
        ),
        "page_vector_bytes_per_frame": 4,
        "private_padding_bytes": 256,
        "rows": 64,
    }


def _contract_variant_row(variant):
    profile = _VARIANT_ROWS[variant]
    minimum = profile["inclusive_minimum"]
    maximum = profile["inclusive_maximum"]
    return {
        "complexity": {
            "counting_rule": _COMPLEXITY_COUNTING_RULES[variant],
            "inclusive_maximum": maximum,
            "inclusive_minimum": minimum,
            "measure": profile["complexity_measure"],
        },
        "content_media_type": profile["content_media_type"],
        "expected_kcs_path_media_type": profile["expected_kcs_path_media_type"],
        "expected_offline_disposition": profile["expected_offline_disposition"],
        "family": profile["family"],
        "filename_extension": profile["filename_extension"],
        "format_limits": _format_limits(variant),
        "gate_role": "raw_only",
        "raw_byte_formula": {
            "base_bytes_at_minimum_complexity": profile["base_bytes"],
            "increment_bytes_per_additional_complexity": profile[
                "increment_bytes"
            ],
            "maximum_rendered_bytes": target_bytes_for(variant, maximum),
            "minimum_complexity": minimum,
            "minimum_rendered_bytes": target_bytes_for(variant, minimum),
            "selection_phase": "solved-source-recipe-instance-not-this-contract",
        },
        "render_template": profile["render_template"],
        "validator_profile_id": (
            f"{variant}-standalone-id-free-raw-domain-validation-v2"
        ),
        "variant_id": variant,
    }


def _negative_authority():
    return {
        "actual_chunks_attested": False,
        "authorizes_final_source_identifiers": False,
        "authorizes_g0_freeze": False,
        "authorizes_history_mutation": False,
        "authorizes_physical_write": False,
        "authorizes_renderer_execution": False,
        "authorizes_source_intents": False,
        "authorizes_source_plan": False,
        "kcs_execution_attested": False,
    }


def _canonical_contract_value():
    return {
        "artifact_kind": CONTRACT_KIND,
        "artifact_schema": CONTRACT_SCHEMA,
        "artifact_schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "byte_stress_lane_implemented": False,
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "coverage_contract": {
            "archive_gzip_tar_zip_variants_in_scope": False,
            "document_variants_in_scope": False,
            "image_variants_in_scope": False,
            "media_variants_in_scope": False,
            "non_container_special_raw_domain_variants_complete": True,
        },
        "implementation_scope": (
            "two-id-free-formal-ordinary-raw-domain-binary-validation-variants-"
            "only-not-source-materialization-or-kcs-attestation"
        ),
        "independence_contract": {
            "imports_planning_modules": False,
            "imports_renderer_module": False,
            "imports_source_or_variant_catalog": False,
            "parses_each_format_with_bounded_standard_library_primitives": True,
            "recomputes_checksums_and_defined_lengths": True,
            "recomputes_expected_payload": True,
            "recomputes_format_metadata": True,
            "recomputes_target_byte_formula": True,
        },
        "payload_runtime_standard_library_only": True,
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


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free raw-domain validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDomainValidatorError(str(error)) from None


def validate_validator_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free raw-domain validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDomainValidatorError(str(error)) from None


def validator_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free raw-domain validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDomainValidatorError(str(error)) from None


__all__ = [
    "DICOM_BYTES_PER_FRAME",
    "DICOM_MAX_FRAMES",
    "DICOM_PRIVATE_PADDING_BYTES",
    "MAX_RENDERED_BYTES",
    "PCAP_CAPTURED_FRAME_BYTES",
    "PCAP_MAX_PACKETS",
    "PCAP_PACKET_PAYLOAD_BYTES",
    "PersonaV2RawDomainValidatorError",
    "READY_VARIANTS",
    "RawDomainValidationRequest",
    "VALIDATOR_ID",
    "build_validator_contract",
    "canonical_json_bytes",
    "target_bytes_for",
    "validate_raw_domain_payload",
    "validate_validator_contract",
    "validator_contract_sha256",
]
