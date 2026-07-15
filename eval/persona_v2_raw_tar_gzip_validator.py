"""Independent bounded validator for persona-PC v2 raw USTAR/GZIP bytes.

The exact sixteen-variant matrix and byte grammar are duplicated here on
purpose.  This module imports no producer, catalog, or planning code.  It
parses USTAR headers/checksums and stored-DEFLATE GZIP framing directly before
returning a non-authorizing receipt.
"""

from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
import io
import json
import zlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kcs.persona.pc-id-free-raw-tar-gzip-validator/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-tar-gzip-validator"
VALIDATOR_ID = "persona-v2-id-free-raw-tar-gzip-independent-validator"
VALIDATOR_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 128 * 1024
MAX_RENDERED_BYTES = 512 * 1024
MAX_CANONICAL_DEPTH = 64
MAX_CANONICAL_STRING_BYTES = 4_096

USTAR_BLOCK_BYTES = 512
USTAR_MEMBER_PAYLOAD_BYTES = 256
USTAR_MEMBER_STORED_BYTES = 1_024
USTAR_TERMINAL_ZERO_BLOCKS = 2
USTAR_MIN_MEMBERS = 1
USTAR_MAX_MEMBERS = 64
USTAR_BASE_BYTES_AT_COMPLEXITY_ONE = 2_048
USTAR_INCREMENT_BYTES = 1_024
USTAR_MAX_EXPANDED_BYTES = 16_384

GZIP_HEADER_BYTES = bytes((0x1F, 0x8B, 0x08, 0x00, 0, 0, 0, 0, 0, 0xFF))
GZIP_TRAILER_BYTES = 8
GZIP_STORED_BLOCK_HEADER_BYTES = 5
GZIP_RECORD_BYTES = 64
GZIP_MIN_RECORDS = 1
GZIP_MAX_RECORDS = 4_096
GZIP_BASE_BYTES_AT_COMPLEXITY_ONE = 87
GZIP_INCREMENT_BYTES = 69
GZIP_MAX_EXPANDED_BYTES = 262_144

PROFILE_ORDER = ("tiny-smoke", "pilot", "full")
PROFILE_TOTALS = {"full": 2_120, "pilot": 210, "tiny-smoke": 38}

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
    "data",
    "extension",
    "content_media_type",
    "expected_kcs_path_media_type",
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

AUTHORITY_FIELDS = (
    "actual_chunks_attested",
    "authorizes_final_source_identifiers",
    "authorizes_g0_freeze",
    "authorizes_history_mutation",
    "authorizes_kcs_execution",
    "authorizes_physical_write",
    "authorizes_renderer_execution",
    "authorizes_source_intents",
    "authorizes_source_plan",
    "filesystem_writer_available",
    "formal_capacity_gate_satisfied",
    "kcs_execution_attested",
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


class PersonaV2RawTarGzipValidatorError(ValueError):
    """Raised when raw USTAR/GZIP bytes fail the independent contract."""


@dataclass(frozen=True, slots=True)
class RawTarGzipValidationRequest:
    """Exact payload plus public format metadata, without internal identity."""

    schema_version: int
    variant: str
    target_complexity: int
    data: bytes
    extension: str
    content_media_type: str
    expected_kcs_path_media_type: str
    expected_offline_disposition: str


def _profile(variant):
    if type(variant) is not str:
        raise PersonaV2RawTarGzipValidatorError(
            "raw tar/gzip variant must be an exact built-in string"
        )
    variant = next(
        (candidate for candidate in READY_VARIANTS if candidate == variant),
        None,
    )
    if variant is None:
        raise PersonaV2RawTarGzipValidatorError(
            "unsupported raw tar/gzip variant"
        )
    if variant in USTAR_VARIANTS:
        return {
            "archive_format": "ustar",
            "canonical_variant": variant,
            "complexity_maximum": USTAR_MAX_MEMBERS,
            "complexity_measure": "members",
            "complexity_minimum": USTAR_MIN_MEMBERS,
            "content_media_type": "application/x-tar",
            "expected_kcs_path_media_type": "application/octet-stream",
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
            "canonical_variant": variant,
            "complexity_maximum": GZIP_MAX_RECORDS,
            "complexity_measure": "records",
            "complexity_minimum": GZIP_MIN_RECORDS,
            "content_media_type": "application/gzip",
            "expected_kcs_path_media_type": "application/octet-stream",
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
    raise PersonaV2RawTarGzipValidatorError("unsupported raw tar/gzip variant")


def _target_bytes_for(variant, target_complexity):
    profile = _profile(variant)
    if (
        type(target_complexity) is not int
        or not profile["complexity_minimum"]
        <= target_complexity
        <= profile["complexity_maximum"]
    ):
        raise PersonaV2RawTarGzipValidatorError(
            "target complexity is outside the exact variant range"
        )
    target = profile["formula_base_bytes_at_complexity_one"] + (
        target_complexity - 1
    ) * profile["formula_increment_bytes_per_additional_complexity"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        raise PersonaV2RawTarGzipValidatorError("rendered-byte cap exceeded")
    return target


def _expanded_bytes_for(profile, target_complexity):
    if profile["archive_format"] == "ustar":
        expanded = target_complexity * USTAR_MEMBER_PAYLOAD_BYTES
        cap = USTAR_MAX_EXPANDED_BYTES
    else:
        expanded = target_complexity * GZIP_RECORD_BYTES
        cap = GZIP_MAX_EXPANDED_BYTES
    if expanded > cap or expanded > MAX_RENDERED_BYTES:
        raise PersonaV2RawTarGzipValidatorError("expanded-byte cap exceeded")
    return expanded


def validate_request(request):
    """Validate the exact request shape, metadata, range, and input cap."""

    if type(request) is not RawTarGzipValidationRequest:
        raise PersonaV2RawTarGzipValidatorError(
            "request must be an exact RawTarGzipValidationRequest"
        )
    if tuple(RawTarGzipValidationRequest.__dataclass_fields__) != REQUEST_FIELDS:
        raise PersonaV2RawTarGzipValidatorError("validator request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        raise PersonaV2RawTarGzipValidatorError(
            "validator request exposes an identity field"
        )
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2RawTarGzipValidatorError(
            "validator request schema version must be exact 2"
        )
    profile = _profile(request.variant)
    _target_bytes_for(request.variant, request.target_complexity)
    if type(request.data) is not bytes:
        raise PersonaV2RawTarGzipValidatorError("payload data must be exact bytes")
    if len(request.data) > MAX_RENDERED_BYTES:
        raise PersonaV2RawTarGzipValidatorError("payload exceeds pre-parse cap")
    exact_metadata = (
        ("extension", "filename_extension"),
        ("content_media_type", "content_media_type"),
        ("expected_kcs_path_media_type", "expected_kcs_path_media_type"),
        ("expected_offline_disposition", "expected_offline_disposition"),
    )
    for request_name, profile_name in exact_metadata:
        value = getattr(request, request_name)
        if type(value) is not str or value != profile[profile_name]:
            raise PersonaV2RawTarGzipValidatorError(
                f"payload {request_name} metadata drifted"
            )
    return True


def _expected_ustar_name(variant, ordinal):
    return f"entries/{variant}/item-{ordinal:04d}.dat".encode("ascii")


def _expected_ustar_payload(variant, ordinal):
    prefix = (
        f"variant={variant}\n"
        f"member={ordinal:04d}\n"
        "kind=bounded-ustar-regular\n"
    ).encode("ascii")
    padding = USTAR_MEMBER_PAYLOAD_BYTES - len(prefix) - 1
    if padding < 0:
        raise PersonaV2RawTarGzipValidatorError("expected USTAR payload overflow")
    return prefix + b"x" * padding + b"\n"


def _exact_octal(value, width):
    digits = f"{value:0{width - 1}o}"
    if len(digits) != width - 1:
        raise PersonaV2RawTarGzipValidatorError("expected octal field overflow")
    return digits.encode("ascii") + b"\0"


def _decode_name(field):
    if len(field) != 100:
        raise PersonaV2RawTarGzipValidatorError("USTAR name field width drifted")
    end = field.find(b"\0")
    if end < 0:
        raise PersonaV2RawTarGzipValidatorError("USTAR name lacks NUL padding")
    if any(field[end:]):
        raise PersonaV2RawTarGzipValidatorError("USTAR name padding is nonzero")
    try:
        return field[:end].decode("ascii")
    except UnicodeDecodeError as error:
        raise PersonaV2RawTarGzipValidatorError(
            "USTAR name must be ASCII"
        ) from error


def _validate_ustar_header(header, variant, ordinal):
    if len(header) != USTAR_BLOCK_BYTES or not any(header):
        raise PersonaV2RawTarGzipValidatorError("USTAR member header is missing")
    name = _decode_name(header[:100])
    expected_name = _expected_ustar_name(variant, ordinal).decode("ascii")
    components = name.split("/")
    if name.startswith("/") or not components or any(
        component in {"", ".", ".."} for component in components
    ):
        raise PersonaV2RawTarGzipValidatorError("USTAR member path is unsafe")
    if name != expected_name:
        raise PersonaV2RawTarGzipValidatorError("USTAR member path drifted")
    if header[100:108] != _exact_octal(0o644, 8):
        raise PersonaV2RawTarGzipValidatorError("USTAR mode drifted")
    if header[108:116] != _exact_octal(0, 8) or header[116:124] != _exact_octal(0, 8):
        raise PersonaV2RawTarGzipValidatorError("USTAR uid/gid drifted")
    if header[124:136] != _exact_octal(USTAR_MEMBER_PAYLOAD_BYTES, 12):
        raise PersonaV2RawTarGzipValidatorError("USTAR member size drifted")
    if header[136:148] != _exact_octal(0, 12):
        raise PersonaV2RawTarGzipValidatorError("USTAR mtime drifted")
    checksum_field = header[148:156]
    if (
        len(checksum_field) != 8
        or checksum_field[6:] != b"\0 "
        or any(byte not in b"01234567" for byte in checksum_field[:6])
    ):
        raise PersonaV2RawTarGzipValidatorError("USTAR checksum field malformed")
    checksum_view = bytearray(header)
    checksum_view[148:156] = b"        "
    observed_checksum = int(checksum_field[:6], 8)
    if observed_checksum != sum(checksum_view):
        raise PersonaV2RawTarGzipValidatorError("USTAR checksum mismatch")
    if header[156:157] != b"0":
        raise PersonaV2RawTarGzipValidatorError("USTAR member type is not regular")
    if any(header[157:257]):
        raise PersonaV2RawTarGzipValidatorError("USTAR link field must be empty")
    if header[257:263] != b"ustar\0" or header[263:265] != b"00":
        raise PersonaV2RawTarGzipValidatorError("USTAR magic/version drifted")
    if any(header[265:329]):
        raise PersonaV2RawTarGzipValidatorError("USTAR uname/gname must be empty")
    if header[329:337] != _exact_octal(0, 8) or header[337:345] != _exact_octal(0, 8):
        raise PersonaV2RawTarGzipValidatorError("USTAR device fields drifted")
    if any(header[345:]):
        raise PersonaV2RawTarGzipValidatorError("USTAR prefix/padding must be zero")


def _validate_ustar(data, variant, member_count):
    if len(data) % USTAR_BLOCK_BYTES:
        raise PersonaV2RawTarGzipValidatorError("USTAR length is not 512-byte quantized")
    terminal_size = USTAR_TERMINAL_ZERO_BLOCKS * USTAR_BLOCK_BYTES
    if data[-terminal_size:] != bytes(terminal_size):
        raise PersonaV2RawTarGzipValidatorError("USTAR terminal zero blocks drifted")
    offset = 0
    names = set()
    for ordinal in range(1, member_count + 1):
        header = data[offset : offset + USTAR_BLOCK_BYTES]
        _validate_ustar_header(header, variant, ordinal)
        name = _decode_name(header[:100])
        if name in names:
            raise PersonaV2RawTarGzipValidatorError("USTAR member path duplicated")
        names.add(name)
        offset += USTAR_BLOCK_BYTES
        payload_block = data[offset : offset + USTAR_BLOCK_BYTES]
        expected_payload = _expected_ustar_payload(variant, ordinal)
        if payload_block[:USTAR_MEMBER_PAYLOAD_BYTES] != expected_payload:
            raise PersonaV2RawTarGzipValidatorError("USTAR member payload drifted")
        if any(payload_block[USTAR_MEMBER_PAYLOAD_BYTES:]):
            raise PersonaV2RawTarGzipValidatorError("USTAR data padding is nonzero")
        offset += USTAR_BLOCK_BYTES
    if offset + terminal_size != len(data):
        raise PersonaV2RawTarGzipValidatorError("USTAR member count drifted")
    return member_count * USTAR_MEMBER_PAYLOAD_BYTES


def _expected_gzip_record(profile, ordinal):
    ordinal_text = f"{ordinal:04d}"
    if len(ordinal_text) != 4:
        raise PersonaV2RawTarGzipValidatorError("GZIP record ordinal overflow")
    if profile["record_format"] == "csv":
        prefix = f"{ordinal_text},{profile['record_tag']},".encode("ascii")
        record = prefix + b"x" * (GZIP_RECORD_BYTES - len(prefix) - 1) + b"\n"
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
        value = dict(empty)
        value["note"] = "x" * (GZIP_RECORD_BYTES - len(empty_bytes) - 1)
        record = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii") + b"\n"
    if len(record) != GZIP_RECORD_BYTES:
        raise PersonaV2RawTarGzipValidatorError("expected GZIP record width drifted")
    return record


def _validate_expanded_records(expanded, profile, record_count):
    if len(expanded) != record_count * GZIP_RECORD_BYTES:
        raise PersonaV2RawTarGzipValidatorError("expanded GZIP length drifted")
    lines = expanded.splitlines(keepends=True)
    if len(lines) != record_count or any(len(line) != GZIP_RECORD_BYTES for line in lines):
        raise PersonaV2RawTarGzipValidatorError("expanded GZIP record framing drifted")
    if profile["record_format"] == "csv":
        parsed = list(csv.reader(io.StringIO(expanded.decode("ascii"))))
        if len(parsed) != record_count or any(len(row) != 3 for row in parsed):
            raise PersonaV2RawTarGzipValidatorError("expanded CSV grammar drifted")
    else:
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise PersonaV2RawTarGzipValidatorError(
                    "expanded JSONL grammar drifted"
                ) from error
            canonical = json.dumps(
                value,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii") + b"\n"
            if canonical != line:
                raise PersonaV2RawTarGzipValidatorError(
                    "expanded JSONL row is not canonical compact JSON"
                )


def _validate_gzip(data, variant, record_count):
    profile = _profile(variant)
    if data[: len(GZIP_HEADER_BYTES)] != GZIP_HEADER_BYTES:
        raise PersonaV2RawTarGzipValidatorError("GZIP fixed header drifted")
    offset = len(GZIP_HEADER_BYTES)
    records = []
    for index in range(record_count):
        if offset + GZIP_STORED_BLOCK_HEADER_BYTES > len(data) - GZIP_TRAILER_BYTES:
            raise PersonaV2RawTarGzipValidatorError("GZIP stored block truncated")
        control = data[offset]
        expected_control = 1 if index == record_count - 1 else 0
        if control != expected_control:
            raise PersonaV2RawTarGzipValidatorError(
                "GZIP stored block final/type bits drifted"
            )
        length = int.from_bytes(data[offset + 1 : offset + 3], "little")
        inverse = int.from_bytes(data[offset + 3 : offset + 5], "little")
        if length != GZIP_RECORD_BYTES or inverse != ((~length) & 0xFFFF):
            raise PersonaV2RawTarGzipValidatorError("GZIP LEN/NLEN drifted")
        offset += GZIP_STORED_BLOCK_HEADER_BYTES
        record = data[offset : offset + length]
        if len(record) != length:
            raise PersonaV2RawTarGzipValidatorError("GZIP stored payload truncated")
        expected = _expected_gzip_record(profile, index + 1)
        if record != expected:
            raise PersonaV2RawTarGzipValidatorError("GZIP record payload drifted")
        records.append(record)
        offset += length
    if offset + GZIP_TRAILER_BYTES != len(data):
        raise PersonaV2RawTarGzipValidatorError("GZIP block count drifted")
    expanded = b"".join(records)
    if len(expanded) > GZIP_MAX_EXPANDED_BYTES:
        raise PersonaV2RawTarGzipValidatorError("GZIP expansion cap exceeded")
    observed_crc = int.from_bytes(data[offset : offset + 4], "little")
    observed_isize = int.from_bytes(data[offset + 4 : offset + 8], "little")
    if observed_crc != (zlib.crc32(expanded) & 0xFFFFFFFF):
        raise PersonaV2RawTarGzipValidatorError("GZIP CRC32 mismatch")
    if observed_isize != len(expanded):
        raise PersonaV2RawTarGzipValidatorError("GZIP ISIZE mismatch")
    try:
        standard_expanded = zlib.decompress(data, wbits=31)
    except zlib.error as error:
        raise PersonaV2RawTarGzipValidatorError(
            "GZIP is not accepted by the standard inflater"
        ) from error
    if standard_expanded != expanded:
        raise PersonaV2RawTarGzipValidatorError("GZIP standard expansion drifted")
    _validate_expanded_records(expanded, profile, record_count)
    return len(expanded)


def _negative_authority():
    return {field: False for field in AUTHORITY_FIELDS}


def validate_raw_tar_gzip_payload(request):
    """Parse and validate one bounded payload and return a negative receipt."""

    validate_request(request)
    profile = _profile(request.variant)
    target_bytes = _target_bytes_for(request.variant, request.target_complexity)
    if len(request.data) != target_bytes:
        raise PersonaV2RawTarGzipValidatorError("payload byte formula drifted")
    if profile["archive_format"] == "ustar":
        expanded_bytes = _validate_ustar(
            request.data, request.variant, request.target_complexity
        )
    else:
        expanded_bytes = _validate_gzip(
            request.data, request.variant, request.target_complexity
        )
    if expanded_bytes != _expanded_bytes_for(profile, request.target_complexity):
        raise PersonaV2RawTarGzipValidatorError("expanded-byte formula drifted")
    return {
        "archive_format": profile["archive_format"],
        "authority": _negative_authority(),
        "observed_complexity": request.target_complexity,
        "observed_complexity_measure": profile["complexity_measure"],
        "observed_expanded_bytes": expanded_bytes,
        "raw_only_zero_chunks_attested": False,
        "size_quantum_bytes": profile["size_quantum_bytes"],
        "target_bytes": target_bytes,
        "variant_id": profile["canonical_variant"],
    }


def _contract_variant_row(variant):
    profile = _profile(variant)
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
        "expected_kcs_path_media_type": profile[
            "expected_kcs_path_media_type"
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
            "maximum_rendered_bytes": _target_bytes_for(variant, maximum),
            "minimum_rendered_bytes": _target_bytes_for(variant, minimum),
        },
        "render_template": profile["render_template"],
        "size_quantization": size_quantization,
        "validator_profile_id": (
            "manual-ustar-header-checksum-member-validator-v2"
            if profile["archive_format"] == "ustar"
            else "manual-gzip-stored-deflate-crc-validator-v2"
        ),
        "variant_id": profile["canonical_variant"],
    }


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
            "sixteen-id-free-raw-only-ustar-gzip-independent-validations"
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
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "validator_id": VALIDATOR_ID,
        "validator_is_independent": True,
        "validator_schema_version": VALIDATOR_SCHEMA_VERSION,
        "variant_count": len(READY_VARIANTS),
        "variant_rows": [
            _contract_variant_row(variant) for variant in READY_VARIANTS
        ],
        "vertical_slice_implementation_available": True,
    }


def build_validator_contract():
    """Return a detached, exact, non-authorizing validator contract."""

    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    """Encode one strict bounded canonical contract value."""

    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free raw USTAR/GZIP validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawTarGzipValidatorError(str(error)) from None


def validate_validator_contract(value):
    """Require exact regeneration of the frozen validator contract."""

    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free raw USTAR/GZIP validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawTarGzipValidatorError(str(error)) from None


def validator_contract_sha256(value=None):
    """Return the canonical SHA-256 without embedding it in the contract."""

    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free raw USTAR/GZIP validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawTarGzipValidatorError(str(error)) from None
