"""Standalone validator for persona-PC v2 raw ZIP feasibility bytes.

The frozen metadata, ZIP grammar, byte formulas, and canonical payload
templates are intentionally duplicated here.  A successful receipt proves
only bounded local structure and bytes; it never attests source identity,
placement, observed chunks, history mutation, or KCS execution.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
import struct
import zlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kcs.persona.pc-id-free-raw-zip-validator/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-zip-validator"
VALIDATOR_ID = "persona-v2-id-free-raw-zip-standalone-validator"
VALIDATOR_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 128 * 1024
MAX_RENDERED_BYTES = 4 * 2**20
MAX_EXPANDED_CONTAINER_BYTES = 8 * 2**20
MAX_CONTAINER_MEMBERS = 64
MAX_MEMBER_NAME_BYTES = 192

ZIP_COMPRESSION_METHOD = 0
ZIP_CREATOR_VERSION = 20
ZIP_EXTRACT_VERSION = 20
ZIP_DOS_TIME = 0
ZIP_DOS_DATE = 33
ZIP_EXTERNAL_ATTRIBUTES = 0x20

READY_VARIANTS = (
    "archive-zip",
    "ats-zip",
    "cde-zip",
    "close-package-zip",
    "course-package-zip",
    "crm-zip",
    "data-room-zip",
    "dms-zip",
    "edc-zip",
    "evidence-zip",
    "foia-zip",
    "ifczip",
    "instrument-export-zip",
    "model-metadata-zip",
    "npz",
    "product-export-zip",
    "qms-zip",
    "recording-project-zip",
    "source-export-zip",
    "ticket-zip",
    "warehouse-zip",
)

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

_GENERIC_VARIANTS = frozenset(
    variant for variant in READY_VARIANTS if variant not in {"ifczip", "npz"}
)


def _generic_row():
    return {
        "complexity_measure": "members",
        "content_media_type": "application/zip",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "family": "domain_binary",
        "filename_extension": "zip",
        "formula_base_bytes_at_minimum": 4_096,
        "formula_increment_bytes": 4_096,
        "inclusive_maximum": 64,
        "inclusive_minimum": 1,
        "render_template": "bounded-stored-zip-record-members-v2",
        "safety_profile_id": "bounded-archive-v2",
    }


_VARIANT_ROWS = {variant: _generic_row() for variant in _GENERIC_VARIANTS}
_VARIANT_ROWS.update(
    {
        "ifczip": {
            "complexity_measure": "spf-members",
            "content_media_type": "application/zip",
            "expected_kcs_path_media_type": "application/octet-stream",
            "expected_offline_disposition": "unsupported_binary",
            "family": "domain_binary",
            "filename_extension": "ifczip",
            "formula_base_bytes_at_minimum": 4_096,
            "formula_increment_bytes": 0,
            "inclusive_maximum": 1,
            "inclusive_minimum": 1,
            "render_template": "bounded-stored-ifc4-spf-zip-v2",
            "safety_profile_id": "bounded-ifczip-v2",
        },
        "npz": {
            "complexity_measure": "array-elements",
            "content_media_type": "application/zip",
            "expected_kcs_path_media_type": "application/octet-stream",
            "expected_offline_disposition": "unsupported_binary",
            "family": "domain_binary",
            "filename_extension": "npz",
            "inclusive_maximum": 1_000_000,
            "inclusive_minimum": 1,
            "render_template": "bounded-stored-npy-array-zip-v2",
            "safety_profile_id": "bounded-npz-v2",
        },
    }
)

_COMPLEXITY_COUNTING_RULES = {
    **{
        variant: "non-directory-stored-members"
        for variant in _GENERIC_VARIANTS
    },
    "ifczip": "ifc-spf-members",
    "npz": "elements-in-the-single-canonical-array",
}

_LOCAL_FILE_HEADER = struct.Struct("<IHHHHHIIIHH")
_CENTRAL_DIRECTORY_HEADER = struct.Struct("<IHHHHHHIIIHHHHHII")
_END_OF_CENTRAL_DIRECTORY = struct.Struct("<IHHHHIIH")
_LOCAL_FILE_SIGNATURE = 0x04034B50
_CENTRAL_DIRECTORY_SIGNATURE = 0x02014B50
_END_OF_CENTRAL_DIRECTORY_SIGNATURE = 0x06054B50
_WINDOWS_RESERVED_STEMS = frozenset(
    {"aux", "con", "nul", "prn"}
    | {f"com{ordinal}" for ordinal in range(1, 10)}
    | {f"lpt{ordinal}" for ordinal in range(1, 10)}
)

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


class PersonaV2RawZipValidatorError(ValueError):
    """Raised when raw ZIP bytes or metadata violate the exact contract."""


@dataclass(frozen=True, slots=True)
class RawZipValidationRequest:
    """Identity-free bytes and metadata presented for local validation."""

    schema_version: int
    variant: str
    target_complexity: int
    data: bytes
    extension: str
    content_media_type: str
    expected_kcs_path_media_type: str
    expected_offline_disposition: str


@dataclass(frozen=True, slots=True)
class _ParsedMember:
    name: str
    payload: bytes
    checksum: int
    local_offset: int


def _fail(message):
    raise PersonaV2RawZipValidatorError(message)


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        _fail("unsupported raw ZIP variant")
    return _VARIANT_ROWS[variant]


def _npy_header(target_complexity):
    dictionary = (
        "{'descr': '<f4', 'fortran_order': False, "
        f"'shape': ({target_complexity},), }}"
    ).encode("ascii")
    preamble_bytes = 10
    padding = (64 - ((preamble_bytes + len(dictionary) + 1) % 64)) % 64
    header = dictionary + b" " * padding + b"\n"
    if len(header) > 0xFFFF:
        _fail("canonical NPY v1 header is too large")
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header


def _single_member_zip_overhead(name):
    try:
        name_bytes = name.encode("ascii")
    except (AttributeError, UnicodeEncodeError):
        _fail("canonical ZIP member name is not ASCII")
    return (
        _LOCAL_FILE_HEADER.size
        + len(name_bytes)
        + _CENTRAL_DIRECTORY_HEADER.size
        + len(name_bytes)
        + _END_OF_CENTRAL_DIRECTORY.size
    )


def target_bytes_for(variant, target_complexity):
    profile = _profile(variant)
    if (
        type(target_complexity) is not int
        or not profile["inclusive_minimum"]
        <= target_complexity
        <= profile["inclusive_maximum"]
    ):
        _fail("target complexity is outside the exact variant domain")
    if variant in _GENERIC_VARIANTS:
        target = 4_096 * target_complexity
    elif variant == "ifczip":
        target = 4_096
    else:
        target = (
            len(_npy_header(target_complexity))
            + 4 * target_complexity
            + _single_member_zip_overhead("array.npy")
        )
    if not 1 <= target <= MAX_RENDERED_BYTES:
        _fail("target-byte formula exceeds the validator cap")
    return target


def validate_request(request):
    if type(request) is not RawZipValidationRequest:
        _fail("request must be an exact RawZipValidationRequest")
    if tuple(RawZipValidationRequest.__dataclass_fields__) != REQUEST_FIELDS:
        _fail("validator request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        _fail("validator request exposes an identity field")
    if type(request.schema_version) is not int or request.schema_version != 2:
        _fail("validator request schema version must be exact 2")
    profile = _profile(request.variant)
    if (
        type(request.target_complexity) is not int
        or not profile["inclusive_minimum"]
        <= request.target_complexity
        <= profile["inclusive_maximum"]
    ):
        _fail("target complexity is outside the exact variant domain")
    if type(request.data) is not bytes:
        _fail("data must be exact bytes")
    expected_metadata = {
        "extension": profile["filename_extension"],
        "content_media_type": profile["content_media_type"],
        "expected_kcs_path_media_type": profile[
            "expected_kcs_path_media_type"
        ],
        "expected_offline_disposition": profile[
            "expected_offline_disposition"
        ],
    }
    for field, expected in expected_metadata.items():
        actual = getattr(request, field)
        if type(actual) is not str or actual != expected:
            _fail(f"{field} differs from the frozen variant metadata")
    target_bytes = target_bytes_for(request.variant, request.target_complexity)
    if len(request.data) != target_bytes:
        _fail("payload length differs from the exact target-byte formula")
    if _FORBIDDEN_IDENTITY_PATTERN.search(request.data):
        _fail("payload contains a prohibited identity token")
    return True


def _safe_member_name(name_bytes):
    if not 1 <= len(name_bytes) <= MAX_MEMBER_NAME_BYTES:
        _fail("ZIP member name length is out of bounds")
    try:
        name = name_bytes.decode("ascii")
    except UnicodeDecodeError:
        _fail("ZIP member name must be ASCII")
    if name.startswith(("/", "\\")) or "\\" in name or name.endswith("/"):
        _fail("ZIP member path is unsafe")
    components = name.split("/")
    for component in components:
        if (
            not component
            or component in {".", ".."}
            or component.endswith(".")
            or len(component) > 64
            or not component[0].isalnum()
            or component.split(".", 1)[0] in _WINDOWS_RESERVED_STEMS
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789._-"
                for character in component
            )
        ):
            _fail("ZIP member path is unsafe")
    return name


def _parse_stored_zip(data):
    if type(data) is not bytes or not 1 <= len(data) <= MAX_RENDERED_BYTES:
        _fail("ZIP byte length is out of bounds")
    if len(data) < _END_OF_CENTRAL_DIRECTORY.size:
        _fail("ZIP is shorter than its end record")
    eocd_offset = len(data) - _END_OF_CENTRAL_DIRECTORY.size
    (
        signature,
        disk_number,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_offset,
        archive_comment_length,
    ) = _END_OF_CENTRAL_DIRECTORY.unpack_from(data, eocd_offset)
    if signature != _END_OF_CENTRAL_DIRECTORY_SIGNATURE:
        _fail("ZIP end record is not at the exact end")
    if data.count(b"PK\x05\x06") != 1:
        _fail("ZIP must contain one unambiguous end record")
    if (
        disk_number != 0
        or central_disk != 0
        or disk_entries != total_entries
        or archive_comment_length != 0
    ):
        _fail("ZIP multi-disk or archive comments are prohibited")
    if not 1 <= total_entries <= MAX_CONTAINER_MEMBERS:
        _fail("ZIP member count is out of bounds")
    if 0xFFFF in {disk_entries, total_entries} or 0xFFFFFFFF in {
        central_size,
        central_offset,
    }:
        _fail("ZIP64 is prohibited")
    if central_offset + central_size != eocd_offset:
        _fail("ZIP central-directory bounds are not canonical")

    local_members = []
    offset = 0
    expanded_bytes = 0
    while offset < central_offset:
        if offset + _LOCAL_FILE_HEADER.size > central_offset:
            _fail("ZIP local header is truncated")
        fields = _LOCAL_FILE_HEADER.unpack_from(data, offset)
        (
            local_signature,
            extract_version,
            flags,
            compression,
            dos_time,
            dos_date,
            checksum,
            compressed_size,
            uncompressed_size,
            name_length,
            extra_length,
        ) = fields
        if local_signature != _LOCAL_FILE_SIGNATURE:
            _fail("ZIP local record signature is invalid")
        if extract_version != ZIP_EXTRACT_VERSION:
            _fail("ZIP extraction version is not canonical")
        if flags != 0:
            _fail("ZIP flags prohibit encryption and data descriptors")
        if compression != ZIP_COMPRESSION_METHOD:
            _fail("ZIP members must use ZIP_STORED")
        if dos_time != ZIP_DOS_TIME or dos_date != ZIP_DOS_DATE:
            _fail("ZIP member timestamp is not the fixed epoch")
        if extra_length != 0:
            _fail("ZIP local extra fields are prohibited")
        if compressed_size == 0xFFFFFFFF or uncompressed_size == 0xFFFFFFFF:
            _fail("ZIP64 member sizes are prohibited")
        if compressed_size != uncompressed_size:
            _fail("stored ZIP member sizes differ")
        name_start = offset + _LOCAL_FILE_HEADER.size
        name_end = name_start + name_length
        payload_end = name_end + compressed_size
        if name_end > central_offset or payload_end > central_offset:
            _fail("ZIP local member bounds are invalid")
        name = _safe_member_name(data[name_start:name_end])
        payload = data[name_end:payload_end]
        if zlib.crc32(payload) & 0xFFFFFFFF != checksum:
            _fail("ZIP member CRC differs from its payload")
        expanded_bytes += uncompressed_size
        if expanded_bytes > MAX_EXPANDED_CONTAINER_BYTES:
            _fail("ZIP expanded bytes exceed the cap")
        local_members.append(
            _ParsedMember(
                name=name,
                payload=payload,
                checksum=checksum,
                local_offset=offset,
            )
        )
        if len(local_members) > total_entries:
            _fail("ZIP local member count exceeds the end record")
        offset = payload_end
    if offset != central_offset or len(local_members) != total_entries:
        _fail("ZIP local records do not match the end record")

    central_cursor = central_offset
    for ordinal, local in enumerate(local_members):
        if central_cursor + _CENTRAL_DIRECTORY_HEADER.size > eocd_offset:
            _fail("ZIP central-directory entry is truncated")
        fields = _CENTRAL_DIRECTORY_HEADER.unpack_from(data, central_cursor)
        (
            central_signature,
            creator_version,
            extract_version,
            flags,
            compression,
            dos_time,
            dos_date,
            checksum,
            compressed_size,
            uncompressed_size,
            name_length,
            extra_length,
            member_comment_length,
            disk_start,
            internal_attributes,
            external_attributes,
            local_offset,
        ) = fields
        if central_signature != _CENTRAL_DIRECTORY_SIGNATURE:
            _fail("ZIP central-directory signature is invalid")
        if creator_version != ZIP_CREATOR_VERSION:
            _fail("ZIP creator version is not canonical")
        if extract_version != ZIP_EXTRACT_VERSION:
            _fail("ZIP extraction version is not canonical")
        if flags != 0:
            _fail("ZIP central flags prohibit encryption and data descriptors")
        if compression != ZIP_COMPRESSION_METHOD:
            _fail("ZIP central method must be ZIP_STORED")
        if dos_time != ZIP_DOS_TIME or dos_date != ZIP_DOS_DATE:
            _fail("ZIP central timestamp is not the fixed epoch")
        if extra_length != 0 or member_comment_length != 0:
            _fail("ZIP central extra fields and comments are prohibited")
        if disk_start != 0:
            _fail("ZIP multi-disk members are prohibited")
        if internal_attributes != 0 or external_attributes != ZIP_EXTERNAL_ATTRIBUTES:
            _fail("ZIP member attributes are not canonical")
        if compressed_size == 0xFFFFFFFF or uncompressed_size == 0xFFFFFFFF:
            _fail("ZIP64 member sizes are prohibited")
        name_start = central_cursor + _CENTRAL_DIRECTORY_HEADER.size
        name_end = name_start + name_length
        entry_end = name_end + extra_length + member_comment_length
        if entry_end > eocd_offset:
            _fail("ZIP central-directory entry bounds are invalid")
        name = _safe_member_name(data[name_start:name_end])
        if (
            name != local.name
            or checksum != local.checksum
            or compressed_size != len(local.payload)
            or uncompressed_size != len(local.payload)
            or local_offset != local.local_offset
        ):
            _fail("ZIP central directory differs from its local record")
        if ordinal >= total_entries:
            _fail("ZIP central member count exceeds the end record")
        central_cursor = entry_end
    if central_cursor != eocd_offset:
        _fail("ZIP central-directory size differs from the end record")

    names = [member.name for member in local_members]
    if names != sorted(names) or len(names) != len(set(names)):
        _fail("ZIP member names must be unique ascending ASCII")
    return local_members, expanded_bytes


def _build_stored_zip(members):
    """Independent exact regeneration; structural validation is above."""

    if type(members) is not list or not 1 <= len(members) <= MAX_CONTAINER_MEMBERS:
        _fail("expected ZIP member count is out of bounds")
    local_records = []
    central_records = []
    offset = 0
    for name, payload in members:
        try:
            name_bytes = name.encode("ascii")
        except (AttributeError, UnicodeEncodeError):
            _fail("expected ZIP member name is not ASCII")
        _safe_member_name(name_bytes)
        if type(payload) is not bytes:
            _fail("expected ZIP payload must be bytes")
        checksum = zlib.crc32(payload) & 0xFFFFFFFF
        local = (
            _LOCAL_FILE_HEADER.pack(
                _LOCAL_FILE_SIGNATURE,
                ZIP_EXTRACT_VERSION,
                0,
                ZIP_COMPRESSION_METHOD,
                ZIP_DOS_TIME,
                ZIP_DOS_DATE,
                checksum,
                len(payload),
                len(payload),
                len(name_bytes),
                0,
            )
            + name_bytes
            + payload
        )
        central = (
            _CENTRAL_DIRECTORY_HEADER.pack(
                _CENTRAL_DIRECTORY_SIGNATURE,
                ZIP_CREATOR_VERSION,
                ZIP_EXTRACT_VERSION,
                0,
                ZIP_COMPRESSION_METHOD,
                ZIP_DOS_TIME,
                ZIP_DOS_DATE,
                checksum,
                len(payload),
                len(payload),
                len(name_bytes),
                0,
                0,
                0,
                0,
                ZIP_EXTERNAL_ATTRIBUTES,
                offset,
            )
            + name_bytes
        )
        local_records.append(local)
        central_records.append(central)
        offset += len(local)
    central = b"".join(central_records)
    eocd = _END_OF_CENTRAL_DIRECTORY.pack(
        _END_OF_CENTRAL_DIRECTORY_SIGNATURE,
        0,
        0,
        len(members),
        len(members),
        len(central),
        offset,
        0,
    )
    result = b"".join(local_records) + central + eocd
    if len(result) > MAX_RENDERED_BYTES:
        _fail("expected ZIP bytes exceed the cap")
    return result


def _generic_member_payload(variant, ordinal, padding_bytes):
    prefix = (
        "bounded raw ZIP feasibility record\n"
        f"variant={variant}\n"
        f"ordinal={ordinal:04d}\n"
        "padding="
    ).encode("ascii")
    return prefix + b"x" * padding_bytes + b"\n"


def _expected_generic_zip(variant, complexity):
    members = [
        (
            f"records/record-{ordinal:04d}.txt",
            _generic_member_payload(variant, ordinal, 0),
        )
        for ordinal in range(1, complexity + 1)
    ]
    target = target_bytes_for(variant, complexity)
    padding = target - len(_build_stored_zip(members))
    if padding < 0:
        _fail("generic ZIP skeleton exceeds its exact target")
    last_name, _ = members[-1]
    members[-1] = (
        last_name,
        _generic_member_payload(variant, complexity, padding),
    )
    return _build_stored_zip(members)


def _ifc_payload(padding_bytes):
    prefix = (
        "ISO-10303-21;\n"
        "HEADER;\n"
        "FILE_DESCRIPTION(('Bounded IFC feasibility model'),'2;1');\n"
        "FILE_NAME('model.ifc','2026-07-15T00:00:00',"
        "('Synthetic'),('KCS'),'KCS','KCS','');\n"
        "FILE_SCHEMA(('IFC4'));\n"
        "ENDSEC;\n"
        "DATA;\n"
        "/*bounded-padding:"
    ).encode("ascii")
    suffix = (
        "*/\n"
        "#1=IFCPROJECT('0000000000000000000000',$,'Bounded Project',"
        "$,$,$,$,$,$);\n"
        "ENDSEC;\n"
        "END-ISO-10303-21;\n"
    ).encode("ascii")
    return prefix + b"x" * padding_bytes + suffix


def _expected_ifczip():
    target = target_bytes_for("ifczip", 1)
    padding = target - len(_build_stored_zip([("model.ifc", _ifc_payload(0))]))
    if padding < 0:
        _fail("IFCZIP skeleton exceeds its exact target")
    return _build_stored_zip([("model.ifc", _ifc_payload(padding))])


def _expected_npz(complexity):
    payload = _npy_header(complexity) + b"\x00\x00\x00\x00" * complexity
    return _build_stored_zip([("array.npy", payload)])


def _validate_generic_members(variant, complexity, members):
    expected_names = [
        f"records/record-{ordinal:04d}.txt"
        for ordinal in range(1, complexity + 1)
    ]
    if [member.name for member in members] != expected_names:
        _fail("generic ZIP member set differs from its exact complexity")
    for ordinal, member in enumerate(members, 1):
        prefix = (
            "bounded raw ZIP feasibility record\n"
            f"variant={variant}\n"
            f"ordinal={ordinal:04d}\n"
            "padding="
        ).encode("ascii")
        if not member.payload.startswith(prefix) or not member.payload.endswith(b"\n"):
            _fail("generic ZIP member framing is invalid")
        padding = member.payload[len(prefix) : -1]
        if padding != b"x" * len(padding):
            _fail("generic ZIP member padding is non-canonical")


def _validate_ifc_member(complexity, members):
    if complexity != 1 or len(members) != 1 or members[0].name != "model.ifc":
        _fail("IFCZIP must contain exactly one model.ifc SPF member")
    payload = members[0].payload
    if not payload.isascii():
        _fail("IFC SPF member must be ASCII")
    if not payload.startswith(b"ISO-10303-21;\nHEADER;\n"):
        _fail("IFC SPF exchange header is invalid")
    if payload.count(b"FILE_SCHEMA(('IFC4'));") != 1:
        _fail("IFCZIP canonical subset requires IFC4")
    if payload.count(b"#1=IFCPROJECT(") != 1:
        _fail("IFCZIP canonical subset requires one project entity")
    if not payload.endswith(b"ENDSEC;\nEND-ISO-10303-21;\n"):
        _fail("IFC SPF exchange trailer is invalid")


def _validate_npy_member(complexity, members):
    if len(members) != 1 or members[0].name != "array.npy":
        _fail("NPZ must contain exactly one array.npy member")
    payload = members[0].payload
    if len(payload) < 10 or payload[:8] != b"\x93NUMPY\x01\x00":
        _fail("NPY magic or version is not canonical v1.0")
    header_length = struct.unpack_from("<H", payload, 8)[0]
    header_end = 10 + header_length
    if header_end > len(payload) or header_end % 64 != 0:
        _fail("NPY header bounds or alignment are invalid")
    if header_length == 0 or payload[header_end - 1 : header_end] != b"\n":
        _fail("NPY header must end in one newline")
    expected_header = _npy_header(complexity)
    if payload[:header_end] != expected_header:
        _fail("NPY dtype, order, shape, or header padding is non-canonical")
    array_bytes = payload[header_end:]
    if len(array_bytes) != 4 * complexity:
        _fail("NPY array byte count differs from its shape")
    if array_bytes != b"\x00\x00\x00\x00" * complexity:
        _fail("NPY canonical float32 array must contain positive zeros")


def validate_raw_zip_payload(request):
    """Validate bounded bytes and return a negative-authority receipt."""

    validate_request(request)
    members, expanded_bytes = _parse_stored_zip(request.data)
    if request.variant in _GENERIC_VARIANTS:
        _validate_generic_members(
            request.variant, request.target_complexity, members
        )
        expected = _expected_generic_zip(
            request.variant, request.target_complexity
        )
    elif request.variant == "ifczip":
        _validate_ifc_member(request.target_complexity, members)
        expected = _expected_ifczip()
    else:
        _validate_npy_member(request.target_complexity, members)
        expected = _expected_npz(request.target_complexity)
    if request.data != expected:
        _fail("payload differs from independent exact-byte regeneration")
    return {
        "actual_chunks_attested": False,
        "byte_length": len(request.data),
        "expanded_bytes": expanded_bytes,
        "identity_tokens_absent": True,
        "kcs_execution_attested": False,
        "member_count": len(members),
        "observed_complexity_measure": _profile(request.variant)[
            "complexity_measure"
        ],
        "observed_local_complexity": request.target_complexity,
        "structure_validated": True,
        "target_bytes": target_bytes_for(
            request.variant, request.target_complexity
        ),
        "zip_subset_validated": True,
    }


def _raw_byte_formula(variant, minimum, maximum):
    common = {
        "maximum_rendered_bytes": target_bytes_for(variant, maximum),
        "minimum_complexity": minimum,
        "minimum_rendered_bytes": target_bytes_for(variant, minimum),
        "selection_phase": "solved-source-recipe-instance-not-this-contract",
    }
    if variant in _GENERIC_VARIANTS:
        return {
            **common,
            "base_bytes_at_minimum_complexity": 4_096,
            "formula_kind": "affine",
            "increment_bytes_per_additional_complexity": 4_096,
        }
    if variant == "ifczip":
        return {
            **common,
            "base_bytes_at_minimum_complexity": 4_096,
            "formula_kind": "affine",
            "increment_bytes_per_additional_complexity": 0,
        }
    return {
        **common,
        "array_element_width_bytes": 4,
        "base_bytes_at_minimum_complexity": 248,
        "formula_kind": "affine",
        "increment_bytes_per_additional_complexity": 4,
        "npy_header_alignment_bytes": 64,
        "npy_member_count": 1,
        "zip_fixed_overhead_bytes": _single_member_zip_overhead("array.npy"),
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
        "compound_suffix_parts": [profile["filename_extension"]],
        "content_media_type": profile["content_media_type"],
        "expected_kcs_path_media_type": profile[
            "expected_kcs_path_media_type"
        ],
        "expected_offline_disposition": profile[
            "expected_offline_disposition"
        ],
        "family": profile["family"],
        "filename_extension": profile["filename_extension"],
        "gate_role": "raw_only",
        "raw_byte_formula": _raw_byte_formula(variant, minimum, maximum),
        "render_template": profile["render_template"],
        "safety_profile_id": profile["safety_profile_id"],
        "validator_profile_id": (
            f"{variant}-standalone-id-free-raw-zip-validation-v2"
        ),
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
            "kcs_execution_attested": False,
        },
        "byte_stress_lane_implemented": False,
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_container_members": MAX_CONTAINER_MEMBERS,
            "max_expanded_container_bytes": MAX_EXPANDED_CONTAINER_BYTES,
            "max_member_name_bytes": MAX_MEMBER_NAME_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "twenty-one-id-free-formal-ordinary-raw-zip-format-validation-"
            "variants-only-excluding-ooxml-not-source-materialization-or-kcs-attestation"
        ),
        "independence_contract": {
            "imports_planning_modules": False,
            "imports_renderer_module": False,
            "imports_source_or_variant_catalog": False,
            "parses_zip_and_npy_with_bounded_standard_library_primitives": True,
            "recomputes_expected_payload": True,
            "recomputes_format_metadata": True,
            "recomputes_target_byte_formula": True,
        },
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
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "validator_id": VALIDATOR_ID,
        "validator_schema_version": VALIDATOR_SCHEMA_VERSION,
        "variant_count": len(READY_VARIANTS),
        "variant_rows": [
            _contract_variant_row(variant) for variant in READY_VARIANTS
        ],
        "vertical_slice_implementation_available": True,
        "zip_subset": {
            "archive_comment_bytes": 0,
            "central_comment_bytes_per_member": 0,
            "compression_method": "stored",
            "data_descriptors_allowed": False,
            "encryption_allowed": False,
            "extra_field_bytes_per_member": 0,
            "fixed_dos_date": ZIP_DOS_DATE,
            "fixed_dos_time": ZIP_DOS_TIME,
            "member_order": "ascending-ascii-name",
            "zip64_allowed": False,
        },
    }


def build_validator_contract():
    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free raw ZIP validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawZipValidatorError(str(error)) from None


def validate_validator_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free raw ZIP validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawZipValidatorError(str(error)) from None


def validator_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free raw ZIP validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawZipValidatorError(str(error)) from None


__all__ = [
    "MAX_CONTAINER_MEMBERS",
    "MAX_EXPANDED_CONTAINER_BYTES",
    "MAX_MEMBER_NAME_BYTES",
    "MAX_RENDERED_BYTES",
    "PersonaV2RawZipValidatorError",
    "READY_VARIANTS",
    "RawZipValidationRequest",
    "VALIDATOR_ID",
    "build_validator_contract",
    "canonical_json_bytes",
    "target_bytes_for",
    "validate_raw_zip_payload",
    "validate_request",
    "validate_validator_contract",
    "validator_contract_sha256",
]
