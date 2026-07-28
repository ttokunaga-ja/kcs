"""Deterministic ID-free renderer for persona-PC v2 raw ZIP variants.

This module is a deliberately narrow feasibility primitive for the nineteen
generic raw ZIP variants plus NPZ and IFCZIP.  It does not accept source,
persona, placement, query, digest, or history identity and grants no authority
to materialize a source or attest KIO execution.  OOXML containers are outside
this slice.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import struct
import zlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kio.persona.pc-id-free-raw-zip-renderer/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-zip-renderer"
RENDERER_ID = "persona-v2-id-free-raw-zip-feasibility-renderer"
RENDERER_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 128 * 1024
MAX_RENDERED_BYTES = 4 * 2**20
MAX_EXPANDED_CONTAINER_BYTES = 8 * 2**20
MAX_CONTAINER_MEMBERS = 64
MAX_MEMBER_NAME_BYTES = 192

ZIP_COMPRESSION_METHOD = 0  # ZIP_STORED
ZIP_CREATOR_VERSION = 20
ZIP_EXTRACT_VERSION = 20
ZIP_DOS_TIME = 0
ZIP_DOS_DATE = 33  # 1980-01-01
ZIP_EXTERNAL_ATTRIBUTES = 0x20  # MS-DOS archive bit.

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

_GENERIC_VARIANTS = frozenset(
    variant for variant in READY_VARIANTS if variant not in {"ifczip", "npz"}
)


def _generic_row():
    return {
        "complexity_measure": "members",
        "content_media_type": "application/zip",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "unsupported_binary",
        "family": "domain_binary",
        "filename_extension": "zip",
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
            "expected_kio_path_media_type": "application/octet-stream",
            "expected_offline_disposition": "unsupported_binary",
            "family": "domain_binary",
            "filename_extension": "ifczip",
            "inclusive_maximum": 1,
            "inclusive_minimum": 1,
            "render_template": "bounded-stored-ifc4-spf-zip-v2",
            "safety_profile_id": "bounded-ifczip-v2",
        },
        "npz": {
            "complexity_measure": "array-elements",
            "content_media_type": "application/zip",
            "expected_kio_path_media_type": "application/octet-stream",
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


class PersonaV2RawZipRendererError(ValueError):
    """Raised when the raw ZIP renderer contract is violated."""


@dataclass(frozen=True, slots=True)
class RawZipRenderRequest:
    """An intentionally identity-free local feasibility request."""

    schema_version: int
    variant: str
    target_complexity: int


@dataclass(frozen=True, slots=True)
class RenderedRawZip:
    """Rendered ZIP bytes and non-authoritative format metadata."""

    data: bytes
    extension: str
    content_media_type: str
    expected_kio_path_media_type: str
    expected_offline_disposition: str
    target_complexity: int
    target_bytes: int
    renderer_id: str = RENDERER_ID
    renderer_schema_version: int = RENDERER_SCHEMA_VERSION


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        raise PersonaV2RawZipRendererError("unsupported raw ZIP variant")
    return _VARIANT_ROWS[variant]


def validate_request(request):
    if type(request) is not RawZipRenderRequest:
        raise PersonaV2RawZipRendererError(
            "request must be an exact RawZipRenderRequest"
        )
    if tuple(RawZipRenderRequest.__dataclass_fields__) != REQUEST_FIELDS:
        raise PersonaV2RawZipRendererError("renderer request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        raise PersonaV2RawZipRendererError(
            "renderer request exposes an identity field"
        )
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2RawZipRendererError(
            "renderer request schema version must be exact 2"
        )
    profile = _profile(request.variant)
    if (
        type(request.target_complexity) is not int
        or not profile["inclusive_minimum"]
        <= request.target_complexity
        <= profile["inclusive_maximum"]
    ):
        raise PersonaV2RawZipRendererError(
            "target complexity is outside the exact variant domain"
        )
    return True


def _npy_header(target_complexity):
    dictionary = (
        "{'descr': '<f4', 'fortran_order': False, "
        f"'shape': ({target_complexity},), }}"
    ).encode("ascii")
    preamble_bytes = 10  # magic, version, and uint16 header length.
    padding = (64 - ((preamble_bytes + len(dictionary) + 1) % 64)) % 64
    header = dictionary + b" " * padding + b"\n"
    if len(header) > 0xFFFF:
        raise PersonaV2RawZipRendererError("canonical NPY v1 header is too large")
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header


def _single_member_zip_overhead(name):
    name_bytes = name.encode("ascii")
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
        raise PersonaV2RawZipRendererError(
            "target complexity is outside the exact variant domain"
        )
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
        raise PersonaV2RawZipRendererError(
            "target-byte formula exceeds the renderer cap"
        )
    return target


def _safe_member_name(name):
    if type(name) is not str or not name or not name.isascii():
        return False
    encoded = name.encode("ascii")
    if len(encoded) > MAX_MEMBER_NAME_BYTES or name.startswith(("/", "\\")):
        return False
    if "\\" in name or name.endswith("/"):
        return False
    components = name.split("/")
    if any(
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
        for component in components
    ):
        return False
    return True


def _build_stored_zip(members):
    if type(members) is not list or not 1 <= len(members) <= MAX_CONTAINER_MEMBERS:
        raise PersonaV2RawZipRendererError("ZIP member count is out of bounds")
    names = [member[0] for member in members]
    if names != sorted(names) or len(names) != len(set(names)):
        raise PersonaV2RawZipRendererError(
            "ZIP member names must be unique ASCII order"
        )
    if any(not _safe_member_name(name) for name in names):
        raise PersonaV2RawZipRendererError("ZIP member path is unsafe")
    if any(type(payload) is not bytes for _, payload in members):
        raise PersonaV2RawZipRendererError("ZIP member payload must be bytes")
    expanded_bytes = sum(len(payload) for _, payload in members)
    if expanded_bytes > MAX_EXPANDED_CONTAINER_BYTES:
        raise PersonaV2RawZipRendererError("ZIP expanded bytes exceed the cap")

    local_records = []
    central_records = []
    offset = 0
    for name, payload in members:
        name_bytes = name.encode("ascii")
        if len(payload) > 0xFFFFFFFF or offset > 0xFFFFFFFF:
            raise PersonaV2RawZipRendererError("ZIP64 is prohibited")
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

    central_directory = b"".join(central_records)
    if offset > 0xFFFFFFFF or len(central_directory) > 0xFFFFFFFF:
        raise PersonaV2RawZipRendererError("ZIP64 is prohibited")
    eocd = _END_OF_CENTRAL_DIRECTORY.pack(
        _END_OF_CENTRAL_DIRECTORY_SIGNATURE,
        0,
        0,
        len(members),
        len(members),
        len(central_directory),
        offset,
        0,
    )
    result = b"".join(local_records) + central_directory + eocd
    if len(result) > MAX_RENDERED_BYTES:
        raise PersonaV2RawZipRendererError("ZIP bytes exceed the renderer cap")
    return result


def _generic_member_payload(variant, ordinal, padding_bytes):
    prefix = (
        "bounded raw ZIP feasibility record\n"
        f"variant={variant}\n"
        f"ordinal={ordinal:04d}\n"
        "padding="
    ).encode("ascii")
    return prefix + b"x" * padding_bytes + b"\n"


def _render_generic_zip(variant, complexity):
    members = [
        (
            f"records/record-{ordinal:04d}.txt",
            _generic_member_payload(variant, ordinal, 0),
        )
        for ordinal in range(1, complexity + 1)
    ]
    target = target_bytes_for(variant, complexity)
    skeleton = _build_stored_zip(members)
    padding = target - len(skeleton)
    if padding < 0:
        raise PersonaV2RawZipRendererError(
            "generic ZIP skeleton exceeds its exact target"
        )
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
        "('Synthetic'),('KIO'),'KIO','KIO','');\n"
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


def _render_ifczip():
    target = target_bytes_for("ifczip", 1)
    skeleton = _build_stored_zip([("model.ifc", _ifc_payload(0))])
    padding = target - len(skeleton)
    if padding < 0:
        raise PersonaV2RawZipRendererError(
            "IFCZIP skeleton exceeds its exact target"
        )
    return _build_stored_zip([("model.ifc", _ifc_payload(padding))])


def _render_npz(complexity):
    payload = _npy_header(complexity) + b"\x00\x00\x00\x00" * complexity
    return _build_stored_zip([("array.npy", payload)])


def _render_payload(variant, complexity):
    if variant in _GENERIC_VARIANTS:
        return _render_generic_zip(variant, complexity)
    if variant == "ifczip":
        return _render_ifczip()
    if variant == "npz":
        return _render_npz(complexity)
    raise PersonaV2RawZipRendererError("unknown raw ZIP render template")


def render_raw_zip(request):
    """Render one deterministic local exemplar without source identity."""

    validate_request(request)
    profile = _profile(request.variant)
    data = _render_payload(request.variant, request.target_complexity)
    target_bytes = target_bytes_for(request.variant, request.target_complexity)
    if type(data) is not bytes or len(data) != target_bytes:
        raise PersonaV2RawZipRendererError(
            "rendered payload differs from exact byte formula"
        )
    return RenderedRawZip(
        data=data,
        extension=profile["filename_extension"],
        content_media_type=profile["content_media_type"],
        expected_kio_path_media_type=profile["expected_kio_path_media_type"],
        expected_offline_disposition=profile["expected_offline_disposition"],
        target_complexity=request.target_complexity,
        target_bytes=target_bytes,
    )


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
        "expected_kio_path_media_type": profile[
            "expected_kio_path_media_type"
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
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_container_members": MAX_CONTAINER_MEMBERS,
            "max_expanded_container_bytes": MAX_EXPANDED_CONTAINER_BYTES,
            "max_member_name_bytes": MAX_MEMBER_NAME_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "twenty-one-id-free-formal-ordinary-raw-zip-format-feasibility-"
            "variants-only-excluding-ooxml-not-source-materialization-or-kio-attestation"
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


def build_renderer_contract():
    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free raw ZIP renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawZipRendererError(str(error)) from None


def validate_renderer_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free raw ZIP renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawZipRendererError(str(error)) from None


def renderer_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free raw ZIP renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawZipRendererError(str(error)) from None


__all__ = [
    "MAX_CONTAINER_MEMBERS",
    "MAX_EXPANDED_CONTAINER_BYTES",
    "MAX_MEMBER_NAME_BYTES",
    "MAX_RENDERED_BYTES",
    "PersonaV2RawZipRendererError",
    "READY_VARIANTS",
    "RENDERER_ID",
    "RawZipRenderRequest",
    "RenderedRawZip",
    "build_renderer_contract",
    "canonical_json_bytes",
    "render_raw_zip",
    "renderer_contract_sha256",
    "target_bytes_for",
    "validate_renderer_contract",
    "validate_request",
]
