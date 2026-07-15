"""Standalone validator for the persona-PC v2 identity-free PDF-text slice.

Independence is intentional: this module does not import the renderer and
duplicates the frozen PDF object layout, affine byte formula, and deterministic
padding algorithm it checks.  Validation proves local PDF bytes, text-layer
pages, xref/trailer integrity, and metadata only; it never attests KCS chunks.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kcs.persona.pc-id-free-pdf-text-validator/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-pdf-text-validator"
VALIDATOR_ID = "persona-v2-id-free-pdf-text-standalone-validator"
VALIDATOR_SCHEMA_VERSION = 2
MAX_CONTRACT_BYTES = 32 * 1024
MAX_RENDERED_BYTES = 160 * 1024
MIN_TARGET_COMPLEXITY = 1
MAX_TARGET_COMPLEXITY = 72
VARIANT_ID = "pdf-text"
FILENAME_EXTENSION = "pdf"
CONTENT_MEDIA_TYPE = "application/pdf"
EXPECTED_KCS_PATH_MEDIA_TYPE = "application/pdf"
EXPECTED_OFFLINE_DISPOSITION = "local_pdf_text"
COMPLEXITY_MEASURE = "text-pages"
FORMULA_BASE_BYTES_AT_COMPLEXITY_ONE = 4_096
FORMULA_INCREMENT_BYTES_PER_ADDITIONAL_COMPLEXITY = 2_048
MAX_PDF_NON_STREAM_LINE_BYTES = 255
MAX_DECIMAL_INTEGER_DIGITS = len(str(MAX_RENDERED_BYTES))
MAX_PDF_OBJECT_NUMBER_DIGITS = len(str(3 + 2 * MAX_TARGET_COMPLEXITY))

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

_PDF_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
_PADDING_BYTE = b"."
_STARTXREF_RE = re.compile(
    b"startxref\n([0-9]{1,"
    + str(MAX_DECIMAL_INTEGER_DIGITS).encode("ascii")
    + rb"})\n%%EOF\n\Z"
)
_XREF_ENTRY_RE = re.compile(rb"[0-9]{10} 00000 n \Z")
_OBJECT_HEADER_RE = re.compile(
    rb"(?m)^([1-9][0-9]{0,"
    + str(MAX_PDF_OBJECT_NUMBER_DIGITS - 1).encode("ascii")
    + rb"}) 0 obj\n"
)
_STREAM_RE = re.compile(
    rb"<< /Length ([0-9]{1,"
    + str(MAX_DECIMAL_INTEGER_DIGITS).encode("ascii")
    + rb"}) >>\nstream\n(.*)endstream",
    re.DOTALL,
)
_FORBIDDEN_IDENTITY_PATTERN = re.compile(
    rb"(?:"
    rb"\bp[0-9]{2}-src-[0-9]{6}\b|"
    rb"\b(?:persona|scope|source|intent|materialization|query|final[_-]?source)"
    rb"[_-]?(?:id|key)\s*[:=]|"
    rb"\bsha256:|"
    rb"\b[0-9a-f]{64}\b"
    rb")",
    re.IGNORECASE,
)


class PersonaV2PdfTextValidatorError(ValueError):
    """Raised when PDF bytes or metadata violate the standalone contract."""


@dataclass(frozen=True, slots=True)
class PdfTextValidationRequest:
    """The complete identity-free byte payload supplied to the validator."""

    schema_version: int
    variant: str
    target_complexity: int
    data: bytes
    extension: str
    content_media_type: str
    expected_kcs_path_media_type: str
    expected_offline_disposition: str


def _target_bytes_for(target_complexity):
    if (
        type(target_complexity) is not int
        or not MIN_TARGET_COMPLEXITY
        <= target_complexity
        <= MAX_TARGET_COMPLEXITY
    ):
        raise PersonaV2PdfTextValidatorError(
            "target complexity must be an integer from 1 through 72"
        )
    target = FORMULA_BASE_BYTES_AT_COMPLEXITY_ONE + (
        target_complexity - 1
    ) * FORMULA_INCREMENT_BYTES_PER_ADDITIONAL_COMPLEXITY
    if not 1 <= target <= MAX_RENDERED_BYTES:
        raise PersonaV2PdfTextValidatorError(
            "target-byte formula exceeds validator cap"
        )
    return target


def _expected_objects(page_count):
    kids = []
    objects = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for page_number in range(1, page_count + 1):
        page_object = 4 + (page_number - 1) * 2
        content_object = page_object + 1
        kids.append(f"{page_object} 0 R")
        text = f"Bounded local PDF feasibility page {page_number:03d}"
        stream = (
            "BT\n"
            "/F1 10 Tf\n"
            "72 720 Td\n"
            f"({text}) Tj\n"
            "ET\n"
        ).encode("ascii")
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_object} 0 R >>"
            ).encode("ascii")
        )
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"endstream"
        )
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (
        f"<< /Type /Pages\n/Count {page_count}\n/Kids [\n"
        + "\n".join(kids)
        + "\n] >>"
    ).encode("ascii")
    return objects


def _expected_padding_comments(length):
    if type(length) is not int or length < 2:
        raise PersonaV2PdfTextValidatorError(
            "PDF padding comment must be at least two bytes"
        )
    full_records, remainder = divmod(length, MAX_PDF_NON_STREAM_LINE_BYTES + 1)
    record_lengths = [MAX_PDF_NON_STREAM_LINE_BYTES + 1] * full_records
    if remainder == 1:
        if not record_lengths:
            raise PersonaV2PdfTextValidatorError(
                "PDF padding length cannot encode a one-byte comment"
            )
        record_lengths[-1] -= 1
        record_lengths.append(2)
    elif remainder:
        record_lengths.append(remainder)
    return b"".join(
        b"%" + _PADDING_BYTE * (record_length - 2) + b"\n"
        for record_length in record_lengths
    )


def _assemble_expected_pdf(objects, padding_length):
    output = bytearray(_PDF_HEADER)
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode("ascii"))
        output.extend(body)
        if not body.endswith(b"\n"):
            output.extend(b"\n")
        output.extend(b"endobj\n")
    if padding_length:
        output.extend(_expected_padding_comments(padding_length))
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        if offset > 9_999_999_999:
            raise PersonaV2PdfTextValidatorError(
                "PDF object offset exceeds xref width"
            )
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _expected_pdf(page_count, target_bytes):
    objects = _expected_objects(page_count)
    unpadded = _assemble_expected_pdf(objects, 0)
    padding_length = target_bytes - len(unpadded)
    if padding_length < 2:
        raise PersonaV2PdfTextValidatorError(
            "affine target leaves no valid PDF padding comment"
        )
    for _ in range(8):
        data = _assemble_expected_pdf(objects, padding_length)
        delta = target_bytes - len(data)
        if delta == 0:
            return data
        padding_length += delta
        if padding_length < 2:
            break
    raise PersonaV2PdfTextValidatorError(
        "could not reconstruct exact affine PDF bytes"
    )


def _validate_request_shape(request):
    if type(request) is not PdfTextValidationRequest:
        raise PersonaV2PdfTextValidatorError(
            "request must be an exact PdfTextValidationRequest"
        )
    if tuple(PdfTextValidationRequest.__dataclass_fields__) != REQUEST_FIELDS:
        raise PersonaV2PdfTextValidatorError("validator request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        raise PersonaV2PdfTextValidatorError(
            "validator request exposes an identity field"
        )
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2PdfTextValidatorError(
            "validator request schema version must be exact 2"
        )
    if type(request.variant) is not str or request.variant != VARIANT_ID:
        raise PersonaV2PdfTextValidatorError(
            "validator supports only exact pdf-text"
        )
    target_bytes = _target_bytes_for(request.target_complexity)
    if type(request.data) is not bytes:
        raise PersonaV2PdfTextValidatorError("validated payload must be exact bytes")
    if not request.data or len(request.data) > MAX_RENDERED_BYTES:
        raise PersonaV2PdfTextValidatorError(
            "validated payload exceeds byte bounds"
        )
    expected_metadata = (
        FILENAME_EXTENSION,
        CONTENT_MEDIA_TYPE,
        EXPECTED_KCS_PATH_MEDIA_TYPE,
        EXPECTED_OFFLINE_DISPOSITION,
    )
    actual_metadata = (
        request.extension,
        request.content_media_type,
        request.expected_kcs_path_media_type,
        request.expected_offline_disposition,
    )
    if any(type(value) is not str for value in actual_metadata):
        raise PersonaV2PdfTextValidatorError(
            "format metadata must be exact strings"
        )
    if actual_metadata != expected_metadata:
        raise PersonaV2PdfTextValidatorError(
            "extension/MIME/disposition metadata drifted"
        )
    if len(request.data) != target_bytes:
        raise PersonaV2PdfTextValidatorError(
            "payload violates exact affine target-byte formula"
        )
    return target_bytes


def _object_body(data, object_offset, object_number):
    marker = f"{object_number} 0 obj\n".encode("ascii")
    if not data.startswith(marker, object_offset):
        raise PersonaV2PdfTextValidatorError("xref points outside its PDF object")
    body_start = object_offset + len(marker)
    body_end = data.find(b"\nendobj\n", body_start)
    if body_end < 0:
        raise PersonaV2PdfTextValidatorError("PDF object has no exact endobj")
    return data[body_start:body_end], body_end + len(b"\nendobj\n")


def _validate_pdf_structure(data, page_count):
    if not data.startswith(_PDF_HEADER):
        raise PersonaV2PdfTextValidatorError("PDF header or binary marker drifted")
    if any(
        len(line) > MAX_PDF_NON_STREAM_LINE_BYTES
        for line in data.split(b"\n")
    ):
        raise PersonaV2PdfTextValidatorError(
            "PDF contains a non-stream line longer than 255 bytes"
        )
    startxref_matches = list(_STARTXREF_RE.finditer(data))
    if len(startxref_matches) != 1:
        raise PersonaV2PdfTextValidatorError(
            "PDF must end with one exact startxref/EOF trailer"
        )
    xref_offset = int(startxref_matches[0].group(1))
    if xref_offset < len(_PDF_HEADER) or not data.startswith(b"xref\n", xref_offset):
        raise PersonaV2PdfTextValidatorError(
            "startxref does not point to the xref table"
        )

    object_count = 3 + 2 * page_count
    xref_count = object_count + 1
    lines = data[xref_offset:].splitlines()
    trailer_index = 2 + xref_count
    if len(lines) != xref_count + 7:
        raise PersonaV2PdfTextValidatorError("xref/trailer line count drifted")
    if lines[0] != b"xref" or lines[1] != f"0 {xref_count}".encode("ascii"):
        raise PersonaV2PdfTextValidatorError("xref subsection shape drifted")
    if lines[2] != b"0000000000 65535 f ":
        raise PersonaV2PdfTextValidatorError("xref free entry drifted")

    offsets = []
    for object_number in range(1, object_count + 1):
        line = lines[2 + object_number]
        if not _XREF_ENTRY_RE.fullmatch(line):
            raise PersonaV2PdfTextValidatorError("xref in-use entry drifted")
        offset = int(line[:10])
        if offset >= xref_offset:
            raise PersonaV2PdfTextValidatorError("xref object offset is out of range")
        if offsets and offset <= offsets[-1]:
            raise PersonaV2PdfTextValidatorError(
                "xref object offsets must increase strictly"
            )
        marker = f"{object_number} 0 obj\n".encode("ascii")
        if not data.startswith(marker, offset):
            raise PersonaV2PdfTextValidatorError(
                "xref entry does not point to its numbered object"
            )
        offsets.append(offset)

    exact_trailer = (
        b"trailer",
        f"<< /Size {xref_count} /Root 1 0 R >>".encode("ascii"),
        b"startxref",
        str(xref_offset).encode("ascii"),
        b"%%EOF",
    )
    if tuple(lines[trailer_index:]) != exact_trailer:
        raise PersonaV2PdfTextValidatorError("PDF trailer dictionary drifted")

    observed_numbers = [
        int(match.group(1))
        for match in _OBJECT_HEADER_RE.finditer(data[:xref_offset])
    ]
    if observed_numbers != list(range(1, object_count + 1)):
        raise PersonaV2PdfTextValidatorError(
            "PDF indirect object sequence drifted"
        )
    if data[:xref_offset].count(b"\nendobj\n") != object_count:
        raise PersonaV2PdfTextValidatorError("PDF endobj count drifted")

    bodies = []
    object_ends = []
    for object_number, offset in enumerate(offsets, start=1):
        body, object_end = _object_body(data, offset, object_number)
        if object_number < object_count and object_end != offsets[object_number]:
            raise PersonaV2PdfTextValidatorError(
                "bytes occur between consecutive PDF objects"
            )
        bodies.append(body)
        object_ends.append(object_end)

    if bodies[0] != b"<< /Type /Catalog /Pages 2 0 R >>":
        raise PersonaV2PdfTextValidatorError("PDF catalog drifted")
    expected_kids = "\n".join(
        f"{4 + (page_number - 1) * 2} 0 R"
        for page_number in range(1, page_count + 1)
    )
    expected_pages = (
        f"<< /Type /Pages\n/Count {page_count}\n/Kids [\n{expected_kids}\n] >>"
    ).encode("ascii")
    if bodies[1] != expected_pages:
        raise PersonaV2PdfTextValidatorError("PDF page tree drifted")
    if bodies[2] != b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>":
        raise PersonaV2PdfTextValidatorError("PDF font resource drifted")

    for page_number in range(1, page_count + 1):
        page_object = 4 + (page_number - 1) * 2
        content_object = page_object + 1
        expected_page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_object} 0 R >>"
        ).encode("ascii")
        if bodies[page_object - 1] != expected_page:
            raise PersonaV2PdfTextValidatorError("PDF page object drifted")
        expected_stream = (
            "BT\n"
            "/F1 10 Tf\n"
            "72 720 Td\n"
            f"(Bounded local PDF feasibility page {page_number:03d}) Tj\n"
            "ET\n"
        ).encode("ascii")
        content_body = bodies[content_object - 1]
        stream_match = _STREAM_RE.fullmatch(content_body)
        if stream_match is None:
            raise PersonaV2PdfTextValidatorError(
                "PDF content stream framing drifted"
            )
        stream = stream_match.group(2)
        if (
            stream_match.group(1) != str(len(stream)).encode("ascii")
            or stream != expected_stream
        ):
            raise PersonaV2PdfTextValidatorError(
                "PDF text-layer stream or declared length drifted"
            )

    padding = data[object_ends[-1]:xref_offset]
    if not re.fullmatch(rb"(?:%[.]*\n)+", padding):
        raise PersonaV2PdfTextValidatorError(
            "PDF deterministic padding comment drifted"
        )
    if data.count(b"stream\nBT\n") != page_count:
        raise PersonaV2PdfTextValidatorError(
            "observed text-layer page count differs from target"
        )
    if any(
        token in data
        for token in (b"/Encrypt", b"/EmbeddedFile", b"/JavaScript", b"/OpenAction")
    ):
        raise PersonaV2PdfTextValidatorError(
            "active, encrypted, or embedded PDF content is forbidden"
        )
    return object_count, xref_offset


def validate_pdf_text_payload(request):
    """Validate exact PDF bytes and return a strictly negative-authority receipt."""

    target_bytes = _validate_request_shape(request)
    if _FORBIDDEN_IDENTITY_PATTERN.search(request.data):
        raise PersonaV2PdfTextValidatorError(
            "PDF payload contains an internal identity or digest token"
        )
    object_count, xref_offset = _validate_pdf_structure(
        request.data, request.target_complexity
    )
    expected = _expected_pdf(request.target_complexity, target_bytes)
    if request.data != expected:
        raise PersonaV2PdfTextValidatorError(
            "PDF differs from standalone deterministic regeneration"
        )
    return {
        "actual_chunks_attested": False,
        "byte_length": len(request.data),
        "identity_tokens_absent": True,
        "kcs_execution_attested": False,
        "object_count": object_count,
        "observed_complexity_measure": COMPLEXITY_MEASURE,
        "observed_local_complexity": request.target_complexity,
        "page_tree_validated": True,
        "pdf_header_validated": True,
        "structure_validated": True,
        "target_bytes": target_bytes,
        "text_layer_validated": True,
        "trailer_validated": True,
        "xref_offset": xref_offset,
        "xref_validated": True,
    }


def _variant_row():
    return {
        "complexity": {
            "inclusive_maximum": MAX_TARGET_COMPLEXITY,
            "inclusive_minimum": MIN_TARGET_COMPLEXITY,
            "measure": COMPLEXITY_MEASURE,
        },
        "content_media_type": CONTENT_MEDIA_TYPE,
        "expected_kcs_path_media_type": EXPECTED_KCS_PATH_MEDIA_TYPE,
        "expected_offline_disposition": EXPECTED_OFFLINE_DISPOSITION,
        "family": "pdf_text",
        "filename_extension": FILENAME_EXTENSION,
        "gate_role": "contract_contributor",
        "raw_byte_formula": {
            "base_bytes_at_complexity_one": FORMULA_BASE_BYTES_AT_COMPLEXITY_ONE,
            "increment_bytes_per_additional_complexity": (
                FORMULA_INCREMENT_BYTES_PER_ADDITIONAL_COMPLEXITY
            ),
            "maximum_rendered_bytes": _target_bytes_for(MAX_TARGET_COMPLEXITY),
            "minimum_rendered_bytes": _target_bytes_for(MIN_TARGET_COMPLEXITY),
        },
        "render_template": "bounded-text-layer-pdf-v2",
        "validator_profile_id": "pdf-text-standalone-id-free-validation-v2",
        "variant_id": VARIANT_ID,
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
            "authorizes_query_plan": False,
            "authorizes_source_intents": False,
            "authorizes_source_plan": False,
            "kcs_execution_attested": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_decimal_integer_digits": MAX_DECIMAL_INTEGER_DIGITS,
            "max_pdf_non_stream_line_bytes": MAX_PDF_NON_STREAM_LINE_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "one-id-free-ascii-uncompressed-pdf-text-feasibility-variant-only-"
            "not-kcs-attestation-not-multilingual"
        ),
        "independence_contract": {
            "imports_renderer_module": False,
            "recomputes_expected_payload": True,
            "recomputes_format_metadata": True,
            "recomputes_pdf_object_offsets": True,
            "recomputes_target_byte_formula": True,
            "validates_page_tree_and_text_streams": True,
            "validates_xref_and_trailer": True,
        },
        "language_coverage": {
            "content_profile": "ascii-uncompressed-literal-text-only",
            "locale_language_query_coverage_proved": False,
            "multilingual_text_layer_proved": False,
        },
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "validator_id": VALIDATOR_ID,
        "validator_schema_version": VALIDATOR_SCHEMA_VERSION,
        "variant_count": 1,
        "variant_rows": [_variant_row()],
        "vertical_slice_implementation_available": True,
    }


def build_validator_contract():
    """Return a detached, non-authorizing standalone-validator descriptor."""

    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free PDF-text validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2PdfTextValidatorError(str(error)) from None


def validate_validator_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free PDF-text validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2PdfTextValidatorError(str(error)) from None


def validator_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free PDF-text validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2PdfTextValidatorError(str(error)) from None
