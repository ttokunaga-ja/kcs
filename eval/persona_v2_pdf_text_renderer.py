"""Bounded identity-free text-layer PDF feasibility renderer for persona-PC v2.

This module proves one deliberately narrow vertical slice for ``pdf-text``.
It accepts no persona, scope, source, digest, intent, materialization, or query
identity and does not authorize a source plan, a physical fixture write, or a
KCS chunk claim.  The v1 renderer is intentionally not imported; only its PDF
encoding shape was consulted while defining this independent v2 contract.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kcs.persona.pc-id-free-pdf-text-renderer/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-pdf-text-renderer"
RENDERER_ID = "persona-v2-id-free-pdf-text-feasibility-renderer"
RENDERER_SCHEMA_VERSION = 2
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

_PDF_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
_PADDING_BYTE = b"."


class PersonaV2PdfTextRendererError(ValueError):
    """Raised when the narrow v2 text-layer PDF contract is violated."""


@dataclass(frozen=True, slots=True)
class PdfTextRenderRequest:
    """An exact three-field request with no fixture or evaluation identity."""

    schema_version: int
    variant: str
    target_complexity: int


@dataclass(frozen=True, slots=True)
class RenderedPdfText:
    """Rendered PDF bytes plus non-authoritative local format metadata."""

    data: bytes
    extension: str
    content_media_type: str
    expected_kcs_path_media_type: str
    expected_offline_disposition: str
    target_complexity: int
    target_bytes: int
    renderer_id: str = RENDERER_ID
    renderer_schema_version: int = RENDERER_SCHEMA_VERSION


def validate_request(request):
    """Reject all but the exact bounded, identity-free request shape."""

    if type(request) is not PdfTextRenderRequest:
        raise PersonaV2PdfTextRendererError(
            "request must be an exact PdfTextRenderRequest"
        )
    if tuple(PdfTextRenderRequest.__dataclass_fields__) != REQUEST_FIELDS:
        raise PersonaV2PdfTextRendererError("renderer request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        raise PersonaV2PdfTextRendererError(
            "renderer request exposes an identity field"
        )
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2PdfTextRendererError(
            "renderer request schema version must be exact 2"
        )
    if type(request.variant) is not str or request.variant != VARIANT_ID:
        raise PersonaV2PdfTextRendererError(
            "renderer supports only exact pdf-text"
        )
    if (
        type(request.target_complexity) is not int
        or not MIN_TARGET_COMPLEXITY
        <= request.target_complexity
        <= MAX_TARGET_COMPLEXITY
    ):
        raise PersonaV2PdfTextRendererError(
            "target complexity must be an integer from 1 through 72"
        )
    return True


def target_bytes_for(target_complexity):
    """Evaluate the exact affine raw-byte formula for one page count."""

    if (
        type(target_complexity) is not int
        or not MIN_TARGET_COMPLEXITY
        <= target_complexity
        <= MAX_TARGET_COMPLEXITY
    ):
        raise PersonaV2PdfTextRendererError(
            "target complexity must be an integer from 1 through 72"
        )
    target = FORMULA_BASE_BYTES_AT_COMPLEXITY_ONE + (
        target_complexity - 1
    ) * FORMULA_INCREMENT_BYTES_PER_ADDITIONAL_COMPLEXITY
    if not 1 <= target <= MAX_RENDERED_BYTES:
        raise PersonaV2PdfTextRendererError(
            "target-byte formula exceeds renderer cap"
        )
    return target


def _pdf_objects(page_count):
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


def _padding_comments(length):
    if type(length) is not int or length < 2:
        raise PersonaV2PdfTextRendererError(
            "PDF padding comment must be at least two bytes"
        )
    # PDF 1.4 limits non-stream lines to 255 characters.  Each complete
    # record below is therefore at most 256 bytes including LF.  A remainder
    # of one byte is represented by shortening one full record and appending
    # the two-byte empty comment ``%\n``.
    full_records, remainder = divmod(length, MAX_PDF_NON_STREAM_LINE_BYTES + 1)
    record_lengths = [MAX_PDF_NON_STREAM_LINE_BYTES + 1] * full_records
    if remainder == 1:
        if not record_lengths:
            raise PersonaV2PdfTextRendererError(
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


def _assemble_pdf(objects, padding_length):
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
        output.extend(_padding_comments(padding_length))
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        if offset > 9_999_999_999:
            raise PersonaV2PdfTextRendererError("PDF object offset exceeds xref width")
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _render_exact_pdf(page_count, target_bytes):
    objects = _pdf_objects(page_count)
    unpadded = _assemble_pdf(objects, 0)
    padding_length = target_bytes - len(unpadded)
    if padding_length < 2:
        raise PersonaV2PdfTextRendererError(
            "affine target leaves no valid PDF padding comment"
        )
    # ``startxref`` contains the padding-adjusted decimal offset.  Its digit
    # width can change at a power-of-ten boundary, so converge on the exact
    # byte target instead of assuming the unpadded width is unchanged.
    for _ in range(8):
        data = _assemble_pdf(objects, padding_length)
        delta = target_bytes - len(data)
        if delta == 0:
            return data
        padding_length += delta
        if padding_length < 2:
            break
    raise PersonaV2PdfTextRendererError(
        "could not satisfy exact affine PDF byte formula"
    )


def render_pdf_text(request):
    """Render one deterministic local PDF exemplar without source identity."""

    validate_request(request)
    target_bytes = target_bytes_for(request.target_complexity)
    data = _render_exact_pdf(request.target_complexity, target_bytes)
    if len(data) != target_bytes:
        raise PersonaV2PdfTextRendererError("rendered PDF byte formula drifted")
    return RenderedPdfText(
        data=data,
        extension=FILENAME_EXTENSION,
        content_media_type=CONTENT_MEDIA_TYPE,
        expected_kcs_path_media_type=EXPECTED_KCS_PATH_MEDIA_TYPE,
        expected_offline_disposition=EXPECTED_OFFLINE_DISPOSITION,
        target_complexity=request.target_complexity,
        target_bytes=target_bytes,
    )


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
            "maximum_rendered_bytes": target_bytes_for(MAX_TARGET_COMPLEXITY),
            "minimum_rendered_bytes": target_bytes_for(MIN_TARGET_COMPLEXITY),
        },
        "render_template": "bounded-text-layer-pdf-v2",
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
            "max_pdf_non_stream_line_bytes": MAX_PDF_NON_STREAM_LINE_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "one-id-free-ascii-uncompressed-pdf-text-feasibility-variant-only-"
            "not-source-materialization-not-multilingual"
        ),
        "language_coverage": {
            "content_profile": "ascii-uncompressed-literal-text-only",
            "locale_language_query_coverage_proved": False,
            "multilingual_text_layer_proved": False,
        },
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
        "renderer_id": RENDERER_ID,
        "renderer_schema_version": RENDERER_SCHEMA_VERSION,
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "variant_count": 1,
        "variant_rows": [_variant_row()],
        "vertical_slice_implementation_available": True,
    }


def build_renderer_contract():
    """Return a detached, non-authorizing renderer descriptor."""

    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free PDF-text renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2PdfTextRendererError(str(error)) from None


def validate_renderer_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free PDF-text renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2PdfTextRendererError(str(error)) from None


def renderer_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free PDF-text renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2PdfTextRendererError(str(error)) from None
