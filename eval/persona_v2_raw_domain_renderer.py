"""Deterministic ID-free feasibility renderer for raw domain binaries.

This bounded vertical slice covers only the two non-container special
``raw_only`` variants in the persona-PC v2 dictionary: classic PCAP and DICOM
Part 10.  It accepts no persona, path, source, scope, query, digest, or planning
identity.  Successful rendering proves local format and byte feasibility only;
it grants no filesystem, source-plan, KIO, history, or G0 authority.

Payload construction uses only Python's standard library.  The shared artifact
helper is used solely to canonicalize the small, non-authorizing descriptor.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import struct

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kio.persona.pc-id-free-raw-domain-renderer/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-domain-renderer"
RENDERER_ID = "persona-v2-id-free-raw-domain-feasibility-renderer"
RENDERER_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 64 * 1024
MAX_RENDERED_BYTES = 512 * 1024

READY_VARIANTS = ("dicom-part10", "pcap")
REQUEST_FIELDS = ("schema_version", "variant", "target_complexity")
PROHIBITED_IDENTITY_FIELDS = (
    "digest",
    "final_source_id",
    "fixture_nonce",
    "intent_key",
    "materialization_id",
    "path",
    "persona_id",
    "query",
    "raw_hash",
    "scope_key",
    "source_id",
)

PCAP_GLOBAL_HEADER_BYTES = 24
PCAP_PACKET_PAYLOAD_BYTES = 64
PCAP_CAPTURED_FRAME_BYTES = 14 + 20 + 8 + PCAP_PACKET_PAYLOAD_BYTES
PCAP_RECORD_BYTES = 16 + PCAP_CAPTURED_FRAME_BYTES
PCAP_MAX_PACKETS = 4_096
PCAP_SNAPLEN = 65_535

DICOM_ROWS = 64
DICOM_COLUMNS = 64
DICOM_BYTES_PER_FRAME = DICOM_ROWS * DICOM_COLUMNS
DICOM_MAX_FRAMES = 64
DICOM_PRIVATE_PADDING_BYTES = 256
DICOM_PAGE_VECTOR_BYTES_PER_FRAME = 4
DICOM_FIXED_BYTES = 1_108

_PCAP_MAGIC = 0xA1B2C3D4
_PCAP_LINKTYPE_ETHERNET = 1
_PCAP_SOURCE_MAC = b"\x02\x00\x00\x00\x00\x01"
_PCAP_DESTINATION_MAC = b"\x02\x00\x00\x00\x00\x02"
_PCAP_SOURCE_IP = b"\xc0\x00\x02\x01"  # RFC 5737 TEST-NET-1.
_PCAP_DESTINATION_IP = b"\xc6\x33\x64\x02"  # RFC 5737 TEST-NET-2.
_PCAP_UDP_DESTINATION_PORT = 41_000

_DICOM_SOP_CLASS_UID = b"1.2.840.10008.5.1.4.1.1.7.2"
_DICOM_STUDY_INSTANCE_UID = b"2.25.210000000000000000000000000000000000001"
_DICOM_SERIES_INSTANCE_UID = b"2.25.220000000000000000000000000000000000001"
_DICOM_SOP_INSTANCE_UID_PREFIX = "2.25.2000000000000000000000000000000000000"
_DICOM_TRANSFER_SYNTAX_UID = b"1.2.840.10008.1.2.1"
_DICOM_IMPLEMENTATION_CLASS_UID = b"2.25.2"
_DICOM_IMPLEMENTATION_VERSION = b"KIORAW_2"
_DICOM_PRIVATE_CREATOR = b"KIO_BOUNDED"
_DICOM_LONG_VRS = frozenset(
    (b"OB", b"OD", b"OF", b"OL", b"OW", b"SQ", b"UC", b"UN", b"UR", b"UT")
)

_VARIANT_ROWS = {
    "dicom-part10": {
        "base_bytes": (
            DICOM_FIXED_BYTES
            + DICOM_PAGE_VECTOR_BYTES_PER_FRAME
            + DICOM_BYTES_PER_FRAME
        ),
        "complexity_measure": "frames",
        "content_media_type": "application/dicom",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "family": "domain_binary",
        "filename_extension": "dcm",
        "inclusive_maximum": DICOM_MAX_FRAMES,
        "inclusive_minimum": 1,
        "increment_bytes": (
            DICOM_PAGE_VECTOR_BYTES_PER_FRAME + DICOM_BYTES_PER_FRAME
        ),
        "render_template": (
            "dicom-part10-multiframe-grayscale-byte-sc-explicit-vr-little-"
            "endian-v3"
        ),
    },
    "pcap": {
        "base_bytes": PCAP_GLOBAL_HEADER_BYTES + PCAP_RECORD_BYTES,
        "complexity_measure": "packets",
        "content_media_type": "application/vnd.tcpdump.pcap",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "family": "domain_binary",
        "filename_extension": "pcap",
        "inclusive_maximum": PCAP_MAX_PACKETS,
        "inclusive_minimum": 1,
        "increment_bytes": PCAP_RECORD_BYTES,
        "render_template": "classic-pcap-ethernet-ipv4-udp-fixed-record-v2",
    },
}

_COMPLEXITY_COUNTING_RULES = {
    "dicom-part10": "number-of-frames-and-contiguous-native-pixel-frames",
    "pcap": "classic-pcap-packet-records",
}


class PersonaV2RawDomainRendererError(ValueError):
    """Raised when a raw-domain render request or descriptor is invalid."""


@dataclass(frozen=True, slots=True)
class RawDomainRenderRequest:
    schema_version: int
    variant: str
    target_complexity: int


@dataclass(frozen=True, slots=True)
class RenderedRawDomain:
    data: bytes
    extension: str
    content_media_type: str
    expected_kio_path_media_type: str
    expected_offline_disposition: str
    target_complexity: int
    target_bytes: int


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        raise PersonaV2RawDomainRendererError("unknown raw-domain variant")
    return _VARIANT_ROWS[variant]


def _complexity(variant, value):
    profile = _profile(variant)
    if type(value) is not int:
        raise PersonaV2RawDomainRendererError(
            "target_complexity must be an exact integer"
        )
    if not profile["inclusive_minimum"] <= value <= profile["inclusive_maximum"]:
        raise PersonaV2RawDomainRendererError(
            f"target_complexity is outside the bounded {variant} range"
        )
    return value


def target_bytes_for(variant, target_complexity):
    profile = _profile(variant)
    complexity = _complexity(variant, target_complexity)
    target = profile["base_bytes"] + (
        complexity - profile["inclusive_minimum"]
    ) * profile["increment_bytes"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        raise PersonaV2RawDomainRendererError(
            "raw-domain target exceeds the formal ordinary byte cap"
        )
    return target


def validate_request(request):
    if type(request) is not RawDomainRenderRequest:
        raise PersonaV2RawDomainRendererError(
            "request must be the exact RawDomainRenderRequest type"
        )
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2RawDomainRendererError("unsupported request schema version")
    _complexity(request.variant, request.target_complexity)
    return True


def _internet_checksum(data):
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for offset in range(0, len(data), 2):
        total += (data[offset] << 8) | data[offset + 1]
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _pcap_payload(packet_ordinal):
    return bytes(
        (packet_ordinal * 17 + payload_ordinal * 29 + 11) & 0xFF
        for payload_ordinal in range(PCAP_PACKET_PAYLOAD_BYTES)
    )


def _pcap_frame(packet_ordinal):
    payload = _pcap_payload(packet_ordinal)
    udp_length = 8 + len(payload)
    source_port = 40_000 + (packet_ordinal % 1_000)
    udp_without_checksum = struct.pack(
        ">HHHH", source_port, _PCAP_UDP_DESTINATION_PORT, udp_length, 0
    )
    pseudo_header = (
        _PCAP_SOURCE_IP
        + _PCAP_DESTINATION_IP
        + b"\x00\x11"
        + struct.pack(">H", udp_length)
    )
    udp_checksum = _internet_checksum(pseudo_header + udp_without_checksum + payload)
    if udp_checksum == 0:
        udp_checksum = 0xFFFF
    udp = struct.pack(
        ">HHHH",
        source_port,
        _PCAP_UDP_DESTINATION_PORT,
        udp_length,
        udp_checksum,
    ) + payload

    total_length = 20 + len(udp)
    ipv4_without_checksum = struct.pack(
        ">BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        packet_ordinal & 0xFFFF,
        0x4000,
        64,
        17,
        0,
        _PCAP_SOURCE_IP,
        _PCAP_DESTINATION_IP,
    )
    ipv4_checksum = _internet_checksum(ipv4_without_checksum)
    ipv4 = struct.pack(
        ">BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        packet_ordinal & 0xFFFF,
        0x4000,
        64,
        17,
        ipv4_checksum,
        _PCAP_SOURCE_IP,
        _PCAP_DESTINATION_IP,
    )
    ethernet = (
        _PCAP_DESTINATION_MAC + _PCAP_SOURCE_MAC + struct.pack(">H", 0x0800)
    )
    frame = ethernet + ipv4 + udp
    if len(frame) != PCAP_CAPTURED_FRAME_BYTES:
        raise PersonaV2RawDomainRendererError("internal PCAP frame length drifted")
    return frame


def _render_pcap(packet_count):
    parts = [
        struct.pack(
            "<IHHIIII",
            _PCAP_MAGIC,
            2,
            4,
            0,
            0,
            PCAP_SNAPLEN,
            _PCAP_LINKTYPE_ETHERNET,
        )
    ]
    for packet_ordinal in range(1, packet_count + 1):
        frame = _pcap_frame(packet_ordinal)
        parts.append(
            struct.pack(
                "<IIII",
                1_700_000_000 + packet_ordinal,
                (packet_ordinal * 7_919) % 1_000_000,
                len(frame),
                len(frame),
            )
        )
        parts.append(frame)
    return b"".join(parts)


def _even_value(vr, value):
    if type(value) is not bytes:
        raise PersonaV2RawDomainRendererError("DICOM values must be exact bytes")
    if len(value) % 2:
        value += b"\x00" if vr == b"UI" else b" "
    return value


def _dicom_element(group, element, vr, value):
    value = _even_value(vr, value)
    tag_and_vr = struct.pack("<HH", group, element) + vr
    if vr in _DICOM_LONG_VRS:
        return tag_and_vr + b"\x00\x00" + struct.pack("<I", len(value)) + value
    if len(value) > 0xFFFF:
        raise PersonaV2RawDomainRendererError("short-VR DICOM value is too large")
    return tag_and_vr + struct.pack("<H", len(value)) + value


def _dicom_us(group, element, value):
    return _dicom_element(group, element, b"US", struct.pack("<H", value))


def _dicom_at(group, element, target_group, target_element):
    return _dicom_element(
        group,
        element,
        b"AT",
        struct.pack("<HH", target_group, target_element),
    )


def _dicom_sop_instance_uid(frame_count):
    value = f"{_DICOM_SOP_INSTANCE_UID_PREFIX}{frame_count:02d}".encode("ascii")
    if len(value) != 44:
        raise PersonaV2RawDomainRendererError(
            "internal DICOM SOP Instance UID width drifted"
        )
    return value


def _dicom_meta_information(sop_instance_uid):
    body = b"".join(
        (
            _dicom_element(0x0002, 0x0001, b"OB", b"\x00\x01"),
            _dicom_element(0x0002, 0x0002, b"UI", _DICOM_SOP_CLASS_UID),
            _dicom_element(0x0002, 0x0003, b"UI", sop_instance_uid),
            _dicom_element(0x0002, 0x0010, b"UI", _DICOM_TRANSFER_SYNTAX_UID),
            _dicom_element(
                0x0002, 0x0012, b"UI", _DICOM_IMPLEMENTATION_CLASS_UID
            ),
            _dicom_element(
                0x0002, 0x0013, b"SH", _DICOM_IMPLEMENTATION_VERSION
            ),
        )
    )
    return _dicom_element(0x0002, 0x0000, b"UL", struct.pack("<I", len(body))) + body


def _dicom_private_padding():
    return bytes((ordinal * 13 + 7) & 0xFF for ordinal in range(256))


def _dicom_pixel_data(frame_count):
    return bytes(
        (frame_ordinal * 17 + pixel_ordinal * 29 + 11) & 0xFF
        for frame_ordinal in range(frame_count)
        for pixel_ordinal in range(DICOM_BYTES_PER_FRAME)
    )


def _dicom_page_number_vector(frame_count):
    # Three ASCII digits plus the following separator (or final even-length
    # padding) make the encoded value exactly four bytes per frame.  This keeps
    # the formal byte formula affine while supplying the required SC
    # multi-frame vector target for every frame, including a one-frame object.
    return b"\\".join(
        f"{frame_ordinal:03d}".encode("ascii")
        for frame_ordinal in range(1, frame_count + 1)
    )


def _render_dicom(frame_count):
    sop_instance_uid = _dicom_sop_instance_uid(frame_count)
    dataset = b"".join(
        (
            _dicom_element(0x0008, 0x0016, b"UI", _DICOM_SOP_CLASS_UID),
            _dicom_element(0x0008, 0x0018, b"UI", sop_instance_uid),
            _dicom_element(0x0008, 0x0020, b"DA", b"20260715"),
            _dicom_element(0x0008, 0x0030, b"TM", b"120000"),
            _dicom_element(0x0008, 0x0050, b"SH", b""),
            _dicom_element(0x0008, 0x0060, b"CS", b"OT"),
            _dicom_element(0x0008, 0x0064, b"CS", b"SYN"),
            _dicom_element(0x0008, 0x0090, b"PN", b""),
            _dicom_element(0x0010, 0x0010, b"PN", b""),
            _dicom_element(0x0010, 0x0020, b"LO", b""),
            _dicom_element(0x0010, 0x0030, b"DA", b""),
            _dicom_element(0x0010, 0x0040, b"CS", b""),
            _dicom_element(0x0011, 0x0010, b"LO", _DICOM_PRIVATE_CREATOR),
            _dicom_element(
                0x0011, 0x1001, b"OB", _dicom_private_padding()
            ),
            _dicom_element(
                0x0018,
                0x2001,
                b"IS",
                _dicom_page_number_vector(frame_count),
            ),
            _dicom_element(0x0020, 0x000D, b"UI", _DICOM_STUDY_INSTANCE_UID),
            _dicom_element(0x0020, 0x000E, b"UI", _DICOM_SERIES_INSTANCE_UID),
            _dicom_element(0x0020, 0x0010, b"SH", b""),
            _dicom_element(0x0020, 0x0011, b"IS", b"1"),
            _dicom_element(0x0020, 0x0013, b"IS", b"1"),
            _dicom_element(0x0020, 0x0020, b"CS", b""),
            _dicom_us(0x0028, 0x0002, 1),
            _dicom_element(0x0028, 0x0004, b"CS", b"MONOCHROME2"),
            _dicom_element(
                0x0028, 0x0008, b"IS", f"{frame_count:02d}".encode("ascii")
            ),
            _dicom_at(0x0028, 0x0009, 0x0018, 0x2001),
            _dicom_us(0x0028, 0x0010, DICOM_ROWS),
            _dicom_us(0x0028, 0x0011, DICOM_COLUMNS),
            _dicom_us(0x0028, 0x0100, 8),
            _dicom_us(0x0028, 0x0101, 8),
            _dicom_us(0x0028, 0x0102, 7),
            _dicom_us(0x0028, 0x0103, 0),
            _dicom_element(0x0028, 0x0301, b"CS", b"NO"),
            _dicom_element(0x0028, 0x1052, b"DS", b"0"),
            _dicom_element(0x0028, 0x1053, b"DS", b"1"),
            _dicom_element(0x0028, 0x1054, b"LO", b"US"),
            _dicom_element(0x2050, 0x0020, b"CS", b"IDENTITY"),
            _dicom_element(
                0x7FE0, 0x0010, b"OB", _dicom_pixel_data(frame_count)
            ),
        )
    )
    result = (
        b"\x00" * 128
        + b"DICM"
        + _dicom_meta_information(sop_instance_uid)
        + dataset
    )
    expected = DICOM_FIXED_BYTES + frame_count * (
        DICOM_PAGE_VECTOR_BYTES_PER_FRAME + DICOM_BYTES_PER_FRAME
    )
    if len(result) != expected:
        raise PersonaV2RawDomainRendererError(
            f"internal DICOM byte formula drifted: {len(result)} != {expected}"
        )
    return result


def render_raw_domain(request):
    """Render one bounded deterministic binary exemplar without source identity."""

    validate_request(request)
    profile = _profile(request.variant)
    if request.variant == "pcap":
        data = _render_pcap(request.target_complexity)
    else:
        data = _render_dicom(request.target_complexity)
    target = target_bytes_for(request.variant, request.target_complexity)
    if type(data) is not bytes or len(data) != target:
        raise PersonaV2RawDomainRendererError(
            "rendered raw-domain bytes differ from the exact byte formula"
        )
    return RenderedRawDomain(
        data=data,
        extension=profile["filename_extension"],
        content_media_type=profile["content_media_type"],
        expected_kio_path_media_type=profile["expected_kio_path_media_type"],
        expected_offline_disposition=profile["expected_offline_disposition"],
        target_complexity=request.target_complexity,
        target_bytes=target,
    )


def _format_limits(variant):
    if variant == "pcap":
        return {
            "captured_frame_bytes": PCAP_CAPTURED_FRAME_BYTES,
            "ethernet_linktype": _PCAP_LINKTYPE_ETHERNET,
            "ipv4_header_bytes": 20,
            "packet_payload_bytes": PCAP_PACKET_PAYLOAD_BYTES,
            "pcap_record_header_bytes": 16,
            "snaplen": PCAP_SNAPLEN,
            "udp_header_bytes": 8,
        }
    return {
        "bits_allocated": 8,
        "bytes_per_frame": DICOM_BYTES_PER_FRAME,
        "columns": DICOM_COLUMNS,
        "defined_lengths_only": True,
        "explicit_vr_little_endian_only": True,
        "max_pixel_bytes": DICOM_MAX_FRAMES * DICOM_BYTES_PER_FRAME,
        "frame_increment_pointer_tag": "0018,2001",
        "multiframe_grayscale_byte_sc_sop_class_uid": (
            _DICOM_SOP_CLASS_UID.decode("ascii")
        ),
        "page_vector_bytes_per_frame": DICOM_PAGE_VECTOR_BYTES_PER_FRAME,
        "private_padding_bytes": DICOM_PRIVATE_PADDING_BYTES,
        "rows": DICOM_ROWS,
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
        "expected_kio_path_media_type": profile["expected_kio_path_media_type"],
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
        "kio_execution_attested": False,
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
            "two-id-free-formal-ordinary-raw-domain-binary-feasibility-variants-"
            "only-not-source-materialization-or-kio-attestation"
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
        "payload_runtime_standard_library_only": True,
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


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free raw-domain renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDomainRendererError(str(error)) from None


def validate_renderer_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free raw-domain renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDomainRendererError(str(error)) from None


def renderer_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free raw-domain renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDomainRendererError(str(error)) from None


__all__ = [
    "DICOM_BYTES_PER_FRAME",
    "DICOM_MAX_FRAMES",
    "DICOM_PRIVATE_PADDING_BYTES",
    "MAX_RENDERED_BYTES",
    "PCAP_CAPTURED_FRAME_BYTES",
    "PCAP_MAX_PACKETS",
    "PCAP_PACKET_PAYLOAD_BYTES",
    "PersonaV2RawDomainRendererError",
    "READY_VARIANTS",
    "RENDERER_ID",
    "RawDomainRenderRequest",
    "RenderedRawDomain",
    "build_renderer_contract",
    "canonical_json_bytes",
    "render_raw_domain",
    "renderer_contract_sha256",
    "target_bytes_for",
    "validate_renderer_contract",
    "validate_request",
]
