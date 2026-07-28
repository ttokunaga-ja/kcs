"""Bounded identity-free raw USTAR/GZIP renderer for persona-PC v2.

This module is a deliberately narrow, non-authorizing feasibility slice for
the raw-only ``*-ustar`` and ``*-gzip`` variants.  It has no dependency on the
variant catalog, planning code, a validator, or a filesystem writer.  USTAR
archives are assembled from fixed regular-file headers and GZIP members use
manual byte-aligned stored DEFLATE blocks, so every output length follows an
exact affine formula.

The rendered bytes establish only local container syntax.  They do not
authorize a source plan, fixture writes, KIO execution, history mutation, or
any chunk claim.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import zlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kio.persona.pc-id-free-raw-tar-gzip-renderer/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-tar-gzip-renderer"
RENDERER_ID = "persona-v2-id-free-raw-tar-gzip-feasibility-renderer"
RENDERER_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 128 * 1024
MAX_RENDERED_BYTES = 512 * 1024
MAX_CANONICAL_DEPTH = 64
MAX_CANONICAL_STRING_BYTES = 4_096

USTAR_BLOCK_BYTES = 512
USTAR_MEMBER_PAYLOAD_BYTES = 256
USTAR_MEMBER_STORED_BYTES = 2 * USTAR_BLOCK_BYTES
USTAR_TERMINAL_ZERO_BLOCKS = 2
USTAR_MIN_MEMBERS = 1
USTAR_MAX_MEMBERS = 64
USTAR_BASE_BYTES_AT_COMPLEXITY_ONE = 2_048
USTAR_INCREMENT_BYTES = 1_024
USTAR_MAX_EXPANDED_BYTES = USTAR_MEMBER_PAYLOAD_BYTES * USTAR_MAX_MEMBERS

GZIP_HEADER_BYTES = bytes((0x1F, 0x8B, 0x08, 0x00, 0, 0, 0, 0, 0, 0xFF))
GZIP_TRAILER_BYTES = 8
GZIP_STORED_BLOCK_HEADER_BYTES = 5
GZIP_RECORD_BYTES = 64
GZIP_MIN_RECORDS = 1
GZIP_MAX_RECORDS = 4_096
GZIP_BASE_BYTES_AT_COMPLEXITY_ONE = 87
GZIP_INCREMENT_BYTES = 69
GZIP_MAX_EXPANDED_BYTES = GZIP_RECORD_BYTES * GZIP_MAX_RECORDS

PROFILE_ORDER = ("tiny-smoke", "pilot", "full")
PROFILE_TOTALS = {
    "full": 2_120,
    "pilot": 210,
    "tiny-smoke": 38,
}

USTAR_VARIANTS = (
    "legal-hold-ustar",
    "lms-ustar",
    "maildir-ustar",
    "plm-ustar",
    "session-ustar",
    "snapshot-ustar",
    "source-drop-ustar",
    "source-ustar",
    "team-export-ustar",
    "tiff-ustar",
)

GZIP_VARIANTS = (
    "assay-csv-gzip",
    "crm-jsonl-gzip",
    "csv-gzip",
    "erp-csv-gzip",
    "hris-jsonl-gzip",
    "jsonl-gzip",
)

READY_VARIANTS = tuple(sorted(USTAR_VARIANTS + GZIP_VARIANTS))

REQUEST_FIELDS = (
    "schema_version",
    "variant",
    "target_complexity",
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

AUTHORITY_FIELDS = (
    "actual_chunks_attested",
    "authorizes_final_source_identifiers",
    "authorizes_g0_freeze",
    "authorizes_history_mutation",
    "authorizes_kio_execution",
    "authorizes_physical_write",
    "authorizes_renderer_execution",
    "authorizes_source_intents",
    "authorizes_source_plan",
    "filesystem_writer_available",
    "formal_capacity_gate_satisfied",
    "kio_execution_attested",
)

_PROFILE_COUNTS = {
    "assay-csv-gzip": {"tiny-smoke": 2, "pilot": 10, "full": 96},
    "crm-jsonl-gzip": {"tiny-smoke": 1, "pilot": 10, "full": 96},
    "csv-gzip": {"tiny-smoke": 5, "pilot": 29, "full": 288},
    "erp-csv-gzip": {"tiny-smoke": 4, "pilot": 23, "full": 234},
    "hris-jsonl-gzip": {"tiny-smoke": 2, "pilot": 6, "full": 64},
    "jsonl-gzip": {"tiny-smoke": 7, "pilot": 52, "full": 525},
    "legal-hold-ustar": {"tiny-smoke": 2, "pilot": 6, "full": 63},
    "lms-ustar": {"tiny-smoke": 1, "pilot": 5, "full": 54},
    "maildir-ustar": {"tiny-smoke": 2, "pilot": 8, "full": 80},
    "plm-ustar": {"tiny-smoke": 5, "pilot": 29, "full": 288},
    "session-ustar": {"tiny-smoke": 1, "pilot": 5, "full": 54},
    "snapshot-ustar": {"tiny-smoke": 1, "pilot": 4, "full": 44},
    "source-drop-ustar": {"tiny-smoke": 1, "pilot": 6, "full": 60},
    "source-ustar": {"tiny-smoke": 2, "pilot": 11, "full": 108},
    "team-export-ustar": {"tiny-smoke": 1, "pilot": 2, "full": 24},
    "tiff-ustar": {"tiny-smoke": 1, "pilot": 4, "full": 42},
}

_GZIP_TAGS = {
    "assay-csv-gzip": "assaycsv",
    "crm-jsonl-gzip": "crmjsonl",
    "csv-gzip": "csvplain",
    "erp-csv-gzip": "erpcsv00",
    "hris-jsonl-gzip": "hrisjson",
    "jsonl-gzip": "jsonline",
}


def _variant_row(variant):
    if type(variant) is not str:
        raise PersonaV2RawTarGzipRendererError(
            "raw tar/gzip variant must be an exact built-in string"
        )
    variant = next(
        (candidate for candidate in READY_VARIANTS if candidate == variant),
        None,
    )
    if variant is None:
        raise PersonaV2RawTarGzipRendererError(
            "unsupported raw tar/gzip variant"
        )
    if variant in USTAR_VARIANTS:
        return {
            "archive_format": "ustar",
            "complexity_maximum": USTAR_MAX_MEMBERS,
            "complexity_measure": "members",
            "complexity_minimum": USTAR_MIN_MEMBERS,
            "content_media_type": "application/x-tar",
            "expected_kio_path_media_type": "application/octet-stream",
            "expected_offline_disposition": "unsupported_binary",
            "family": "domain_binary",
            "filename_extension": "tar",
            "formula_base_bytes_at_complexity_one": (
                USTAR_BASE_BYTES_AT_COMPLEXITY_ONE
            ),
            "formula_increment_bytes_per_additional_complexity": (
                USTAR_INCREMENT_BYTES
            ),
            "gate_role": "raw_only",
            "profile_counts": _PROFILE_COUNTS[variant],
            "render_template": "manual-ustar-regular-members-v2",
            "size_quantum_bytes": USTAR_BLOCK_BYTES,
        }
    if variant in GZIP_VARIANTS:
        return {
            "archive_format": "gzip-stored-deflate",
            "complexity_maximum": GZIP_MAX_RECORDS,
            "complexity_measure": "records",
            "complexity_minimum": GZIP_MIN_RECORDS,
            "content_media_type": "application/gzip",
            "expected_kio_path_media_type": "application/octet-stream",
            "expected_offline_disposition": "unsupported_binary",
            "family": "domain_binary",
            "filename_extension": (
                "jsonl.gz" if "jsonl" in variant else "csv.gz"
            ),
            "formula_base_bytes_at_complexity_one": (
                GZIP_BASE_BYTES_AT_COMPLEXITY_ONE
            ),
            "formula_increment_bytes_per_additional_complexity": (
                GZIP_INCREMENT_BYTES
            ),
            "gate_role": "raw_only",
            "profile_counts": _PROFILE_COUNTS[variant],
            "record_format": "jsonl" if "jsonl" in variant else "csv",
            "record_tag": _GZIP_TAGS[variant],
            "render_template": "manual-gzip-stored-records-v2",
            "size_quantum_bytes": 1,
        }
    raise PersonaV2RawTarGzipRendererError("unsupported raw tar/gzip variant")


class PersonaV2RawTarGzipRendererError(ValueError):
    """Raised when the raw USTAR/GZIP renderer contract is violated."""


@dataclass(frozen=True, slots=True)
class RawTarGzipRenderRequest:
    """An exact three-field request with no fixture or evaluation identity."""

    schema_version: int
    variant: str
    target_complexity: int


@dataclass(frozen=True, slots=True)
class RenderedRawTarGzip:
    """Rendered bytes plus deterministic, non-authorizing format metadata."""

    data: bytes
    extension: str
    content_media_type: str
    expected_kio_path_media_type: str
    expected_offline_disposition: str
    archive_format: str
    complexity_measure: str
    target_complexity: int
    target_bytes: int
    expanded_bytes: int
    size_quantum_bytes: int
    renderer_id: str = RENDERER_ID
    renderer_schema_version: int = RENDERER_SCHEMA_VERSION


def validate_request(request):
    """Reject all but the exact identity-free request and per-variant range."""

    if type(request) is not RawTarGzipRenderRequest:
        raise PersonaV2RawTarGzipRendererError(
            "request must be an exact RawTarGzipRenderRequest"
        )
    if tuple(RawTarGzipRenderRequest.__dataclass_fields__) != REQUEST_FIELDS:
        raise PersonaV2RawTarGzipRendererError("renderer request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        raise PersonaV2RawTarGzipRendererError(
            "renderer request exposes an identity field"
        )
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2RawTarGzipRendererError(
            "renderer request schema version must be exact 2"
        )
    profile = _variant_row(request.variant)
    if (
        type(request.target_complexity) is not int
        or not profile["complexity_minimum"]
        <= request.target_complexity
        <= profile["complexity_maximum"]
    ):
        raise PersonaV2RawTarGzipRendererError(
            "target complexity is outside the exact variant range"
        )
    return True


def target_bytes_for(variant, target_complexity):
    """Return the exact affine rendered-byte target for one request."""

    profile = _variant_row(variant)
    if (
        type(target_complexity) is not int
        or not profile["complexity_minimum"]
        <= target_complexity
        <= profile["complexity_maximum"]
    ):
        raise PersonaV2RawTarGzipRendererError(
            "target complexity is outside the exact variant range"
        )
    target = profile["formula_base_bytes_at_complexity_one"] + (
        target_complexity - 1
    ) * profile["formula_increment_bytes_per_additional_complexity"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        raise PersonaV2RawTarGzipRendererError(
            "target-byte formula exceeds renderer cap"
        )
    return target


def expanded_bytes_for(variant, target_complexity):
    """Return the exact logical member/record bytes before container framing."""

    profile = _variant_row(variant)
    target_bytes_for(variant, target_complexity)
    if profile["archive_format"] == "ustar":
        expanded = target_complexity * USTAR_MEMBER_PAYLOAD_BYTES
        cap = USTAR_MAX_EXPANDED_BYTES
    else:
        expanded = target_complexity * GZIP_RECORD_BYTES
        cap = GZIP_MAX_EXPANDED_BYTES
    if expanded > cap or expanded > MAX_RENDERED_BYTES:
        raise PersonaV2RawTarGzipRendererError("expanded-byte cap exceeded")
    return expanded


def _octal_field(value, width):
    if type(value) is not int or value < 0 or type(width) is not int or width < 2:
        raise PersonaV2RawTarGzipRendererError("invalid USTAR octal field")
    digits = f"{value:0{width - 1}o}"
    if len(digits) != width - 1:
        raise PersonaV2RawTarGzipRendererError("USTAR octal field overflow")
    return digits.encode("ascii") + b"\0"


def _ustar_member_name(variant, ordinal):
    name = f"entries/{variant}/item-{ordinal:04d}.dat"
    encoded = name.encode("ascii")
    if len(encoded) > 100 or name.startswith("/") or ".." in name.split("/"):
        raise PersonaV2RawTarGzipRendererError("USTAR member name is not portable")
    return encoded


def _ustar_member_payload(variant, ordinal):
    prefix = (
        f"variant={variant}\n"
        f"member={ordinal:04d}\n"
        "kind=bounded-ustar-regular\n"
    ).encode("ascii")
    padding = USTAR_MEMBER_PAYLOAD_BYTES - len(prefix) - 1
    if padding < 0:
        raise PersonaV2RawTarGzipRendererError("USTAR payload prefix overflow")
    return prefix + b"x" * padding + b"\n"


def _ustar_header(variant, ordinal):
    header = bytearray(USTAR_BLOCK_BYTES)
    name = _ustar_member_name(variant, ordinal)
    header[0 : len(name)] = name
    header[100:108] = _octal_field(0o644, 8)
    header[108:116] = _octal_field(0, 8)
    header[116:124] = _octal_field(0, 8)
    header[124:136] = _octal_field(USTAR_MEMBER_PAYLOAD_BYTES, 12)
    header[136:148] = _octal_field(0, 12)
    header[148:156] = b"        "
    header[156:157] = b"0"
    header[257:263] = b"ustar\0"
    header[263:265] = b"00"
    header[329:337] = _octal_field(0, 8)
    header[337:345] = _octal_field(0, 8)
    checksum = sum(header)
    encoded_checksum = f"{checksum:06o}\0 ".encode("ascii")
    if len(encoded_checksum) != 8:
        raise PersonaV2RawTarGzipRendererError("USTAR checksum overflow")
    header[148:156] = encoded_checksum
    return bytes(header)


def _render_ustar(variant, member_count):
    parts = []
    for ordinal in range(1, member_count + 1):
        payload = _ustar_member_payload(variant, ordinal)
        parts.extend(
            (
                _ustar_header(variant, ordinal),
                payload,
                bytes(USTAR_BLOCK_BYTES - len(payload)),
            )
        )
    parts.append(bytes(USTAR_TERMINAL_ZERO_BLOCKS * USTAR_BLOCK_BYTES))
    data = b"".join(parts)
    if len(data) != target_bytes_for(variant, member_count):
        raise PersonaV2RawTarGzipRendererError("USTAR byte formula drifted")
    return data


def _gzip_record(profile, ordinal):
    ordinal_text = f"{ordinal:04d}"
    if len(ordinal_text) != 4:
        raise PersonaV2RawTarGzipRendererError("GZIP record ordinal overflow")
    if profile["record_format"] == "csv":
        prefix = f"{ordinal_text},{profile['record_tag']},".encode("ascii")
        padding = GZIP_RECORD_BYTES - len(prefix) - 1
        if padding < 1:
            raise PersonaV2RawTarGzipRendererError("CSV record prefix overflow")
        record = prefix + b"x" * padding + b"\n"
    else:
        empty = {
            "kind": profile["record_tag"],
            "note": "",
            "ordinal": ordinal_text,
        }
        empty_bytes = json.dumps(
            empty,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        padding = GZIP_RECORD_BYTES - len(empty_bytes) - 1
        if padding < 1:
            raise PersonaV2RawTarGzipRendererError("JSONL record prefix overflow")
        value = dict(empty)
        value["note"] = "x" * padding
        record = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii") + b"\n"
    if len(record) != GZIP_RECORD_BYTES:
        raise PersonaV2RawTarGzipRendererError("GZIP record width drifted")
    return record


def _render_gzip(variant, record_count):
    profile = _variant_row(variant)
    records = [_gzip_record(profile, ordinal) for ordinal in range(1, record_count + 1)]
    blocks = []
    for index, record in enumerate(records):
        final = index == len(records) - 1
        length = len(record)
        blocks.append(
            bytes((1 if final else 0,))
            + length.to_bytes(2, "little")
            + ((~length) & 0xFFFF).to_bytes(2, "little")
            + record
        )
    expanded = b"".join(records)
    trailer = (
        (zlib.crc32(expanded) & 0xFFFFFFFF).to_bytes(4, "little")
        + (len(expanded) & 0xFFFFFFFF).to_bytes(4, "little")
    )
    data = GZIP_HEADER_BYTES + b"".join(blocks) + trailer
    if len(expanded) != expanded_bytes_for(variant, record_count):
        raise PersonaV2RawTarGzipRendererError("GZIP expanded-byte formula drifted")
    if len(data) != target_bytes_for(variant, record_count):
        raise PersonaV2RawTarGzipRendererError("GZIP byte formula drifted")
    return data


def render_raw_tar_gzip(request):
    """Render one deterministic raw-only USTAR or GZIP feasibility exemplar."""

    validate_request(request)
    profile = _variant_row(request.variant)
    if profile["archive_format"] == "ustar":
        data = _render_ustar(request.variant, request.target_complexity)
    else:
        data = _render_gzip(request.variant, request.target_complexity)
    target_bytes = target_bytes_for(request.variant, request.target_complexity)
    return RenderedRawTarGzip(
        data=data,
        extension=profile["filename_extension"],
        content_media_type=profile["content_media_type"],
        expected_kio_path_media_type=profile["expected_kio_path_media_type"],
        expected_offline_disposition=profile["expected_offline_disposition"],
        archive_format=profile["archive_format"],
        complexity_measure=profile["complexity_measure"],
        target_complexity=request.target_complexity,
        target_bytes=target_bytes,
        expanded_bytes=expanded_bytes_for(
            request.variant, request.target_complexity
        ),
        size_quantum_bytes=profile["size_quantum_bytes"],
    )


def _contract_variant_row(variant):
    profile = _variant_row(variant)
    minimum = profile["complexity_minimum"]
    maximum = profile["complexity_maximum"]
    size_quantization = (
        {
            "member_data_bytes": USTAR_MEMBER_PAYLOAD_BYTES,
            "member_header_bytes": USTAR_BLOCK_BYTES,
            "member_stored_bytes": USTAR_MEMBER_STORED_BYTES,
            "raw_size_quantum_bytes": USTAR_BLOCK_BYTES,
            "terminal_zero_block_count": USTAR_TERMINAL_ZERO_BLOCKS,
        }
        if profile["archive_format"] == "ustar"
        else {
            "expanded_record_bytes": GZIP_RECORD_BYTES,
            "fixed_gzip_envelope_bytes": len(GZIP_HEADER_BYTES)
            + GZIP_TRAILER_BYTES,
            "raw_size_quantum_bytes": 1,
            "stored_block_header_bytes_per_record": (
                GZIP_STORED_BLOCK_HEADER_BYTES
            ),
        }
    )
    return {
        "archive_format": profile["archive_format"],
        "complexity": {
            "inclusive_maximum": maximum,
            "inclusive_minimum": minimum,
            "measure": profile["complexity_measure"],
        },
        "content_media_type": profile["content_media_type"],
        "expected_kio_path_media_type": profile[
            "expected_kio_path_media_type"
        ],
        "expected_offline_disposition": profile[
            "expected_offline_disposition"
        ],
        "family": profile["family"],
        "filename_extension": profile["filename_extension"],
        "gate_role": profile["gate_role"],
        "profile_counts": copy.deepcopy(profile["profile_counts"]),
        "raw_byte_formula": {
            "base_bytes_at_complexity_one": profile[
                "formula_base_bytes_at_complexity_one"
            ],
            "increment_bytes_per_additional_complexity": profile[
                "formula_increment_bytes_per_additional_complexity"
            ],
            "maximum_rendered_bytes": target_bytes_for(variant, maximum),
            "minimum_rendered_bytes": target_bytes_for(variant, minimum),
        },
        "render_template": profile["render_template"],
        "size_quantization": size_quantization,
        "variant_id": variant,
    }


def _negative_authority():
    return {field: False for field in AUTHORITY_FIELDS}


def _canonical_contract_value():
    return {
        "artifact_kind": CONTRACT_KIND,
        "artifact_schema": CONTRACT_SCHEMA,
        "artifact_schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_canonical_depth": MAX_CANONICAL_DEPTH,
            "max_canonical_string_bytes": MAX_CANONICAL_STRING_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "sixteen-id-free-raw-only-ustar-gzip-feasibility-variants"
        ),
        "payload_identity_policy": {
            "content_digest_embedded": False,
            "final_source_identifier_embedded": False,
            "intent_identifier_embedded": False,
            "materialization_identifier_embedded": False,
            "persona_identifier_embedded": False,
            "query_identifier_embedded": False,
            "scope_identifier_embedded": False,
            "source_identifier_embedded": False,
        },
        "profile_count_totals": copy.deepcopy(PROFILE_TOTALS),
        "profile_order": list(PROFILE_ORDER),
        "proof_boundaries": {
            "P1_ustar_structure": (
                "manual-512-byte-regular-member-headers-and-data-padding-"
                "with-two-terminal-zero-blocks"
            ),
            "P2_gzip_expansion": (
                "single-member-fixed-header-stored-deflate-record-blocks-"
                "with-crc32-isize-and-262144-byte-expansion-cap"
            ),
            "actual_raw_only_zero_chunks_attested": False,
        },
        "renderer_id": RENDERER_ID,
        "renderer_schema_version": RENDERER_SCHEMA_VERSION,
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "variant_count": len(READY_VARIANTS),
        "variant_rows": [
            _contract_variant_row(variant) for variant in READY_VARIANTS
        ],
        "vertical_slice_implementation_available": True,
    }


def build_renderer_contract():
    """Return a detached, exact, non-authorizing renderer contract."""

    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    """Encode one strict bounded canonical contract value."""

    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free raw USTAR/GZIP renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawTarGzipRendererError(str(error)) from None


def validate_renderer_contract(value):
    """Require exact regeneration of the frozen renderer contract."""

    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free raw USTAR/GZIP renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawTarGzipRendererError(str(error)) from None


def renderer_contract_sha256(value=None):
    """Return the canonical SHA-256 without embedding it in the contract."""

    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free raw USTAR/GZIP renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawTarGzipRendererError(str(error)) from None
