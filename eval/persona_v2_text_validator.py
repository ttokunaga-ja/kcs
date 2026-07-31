"""Standalone validator for the persona-PC v2 ID-free text slice.

Independence is intentional: this module does not import the renderer and
duplicates the frozen formulas and templates it checks.  A renderer bug cannot
make validation succeed merely by changing a shared rendering helper.  The
receipt proves only local bytes/structure; it never attests KIO chunk output.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kio.persona.pc-id-free-text-validator/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-text-validator"
VALIDATOR_ID = "persona-v2-id-free-text-standalone-validator"
VALIDATOR_SCHEMA_VERSION = 2
MAX_CONTRACT_BYTES = 64 * 1024
MAX_RENDERED_BYTES = 512 * 1024
MIN_TARGET_COMPLEXITY = 1
MAX_TARGET_COMPLEXITY = 70
CHUNKING_MAX_CHARS = 6_000
CODE_LAST_NORMALIZED_CHARS = 512

READY_VARIANTS = (
    "cpp",
    "go",
    "js",
    "markdown",
    "md",
    "py",
    "rs",
    "ts",
    "txt",
)

REQUEST_FIELDS = (
    "schema_version",
    "variant",
    "target_complexity",
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
    "scope_id",
    "scope_key",
    "source_id",
)

_VARIANT_ROWS = {
    "cpp": {
        "comment_prefix": "// ",
        "complexity_measure": "normalized-hard-split-spans",
        "content_media_type": "text/x-c++src",
        "expected_kio_path_media_type": "text/x-code",
        "expected_offline_disposition": "local_text",
        "family": "code",
        "filename_extension": "cpp",
        "formula_base_bytes_at_complexity_one": 501,
        "formula_increment_bytes_per_additional_complexity": 6_000,
        "render_template": "comment-only-code-v2",
    },
    "go": {
        "comment_prefix": "// ",
        "complexity_measure": "normalized-hard-split-spans",
        "content_media_type": "text/x-go",
        "expected_kio_path_media_type": "text/x-code",
        "expected_offline_disposition": "local_text",
        "family": "code",
        "filename_extension": "go",
        "formula_base_bytes_at_complexity_one": 502,
        "formula_increment_bytes_per_additional_complexity": 6_000,
        "render_template": "comment-only-code-v2",
    },
    "js": {
        "comment_prefix": "// ",
        "complexity_measure": "normalized-hard-split-spans",
        "content_media_type": "text/javascript",
        "expected_kio_path_media_type": "text/x-code",
        "expected_offline_disposition": "local_text",
        "family": "code",
        "filename_extension": "js",
        "formula_base_bytes_at_complexity_one": 502,
        "formula_increment_bytes_per_additional_complexity": 6_000,
        "render_template": "comment-only-code-v2",
    },
    "markdown": {
        "comment_prefix": "not-applicable",
        "complexity_measure": "atx-h2-sections",
        "content_media_type": "text/markdown",
        "expected_kio_path_media_type": "text/markdown",
        "expected_offline_disposition": "local_text",
        "family": "md",
        "filename_extension": "markdown",
        "formula_base_bytes_at_complexity_one": 1_053,
        "formula_increment_bytes_per_additional_complexity": 1_024,
        "render_template": "bounded-h2-sections-v2",
    },
    "md": {
        "comment_prefix": "not-applicable",
        "complexity_measure": "atx-h2-sections",
        "content_media_type": "text/markdown",
        "expected_kio_path_media_type": "text/markdown",
        "expected_offline_disposition": "local_text",
        "family": "md",
        "filename_extension": "md",
        "formula_base_bytes_at_complexity_one": 1_041,
        "formula_increment_bytes_per_additional_complexity": 1_024,
        "render_template": "bounded-h2-sections-v2",
    },
    "py": {
        "comment_prefix": "# ",
        "complexity_measure": "normalized-hard-split-spans",
        "content_media_type": "text/x-python",
        "expected_kio_path_media_type": "text/x-code",
        "expected_offline_disposition": "local_text",
        "family": "code",
        "filename_extension": "py",
        "formula_base_bytes_at_complexity_one": 502,
        "formula_increment_bytes_per_additional_complexity": 6_000,
        "render_template": "comment-only-code-v2",
    },
    "rs": {
        "comment_prefix": "// ",
        "complexity_measure": "normalized-hard-split-spans",
        "content_media_type": "text/x-rust",
        "expected_kio_path_media_type": "text/x-code",
        "expected_offline_disposition": "local_text",
        "family": "code",
        "filename_extension": "rs",
        "formula_base_bytes_at_complexity_one": 502,
        "formula_increment_bytes_per_additional_complexity": 6_000,
        "render_template": "comment-only-code-v2",
    },
    "ts": {
        "comment_prefix": "// ",
        "complexity_measure": "normalized-hard-split-spans",
        "content_media_type": "text/typescript",
        "expected_kio_path_media_type": "text/x-code",
        "expected_offline_disposition": "local_text",
        "family": "code",
        "filename_extension": "ts",
        "formula_base_bytes_at_complexity_one": 502,
        "formula_increment_bytes_per_additional_complexity": 6_000,
        "render_template": "comment-only-code-v2",
    },
    "txt": {
        "comment_prefix": "not-applicable",
        "complexity_measure": "atx-h2-sections",
        "content_media_type": "text/plain",
        "expected_kio_path_media_type": "text/plain",
        "expected_offline_disposition": "local_text",
        "family": "txt_log",
        "filename_extension": "txt",
        "formula_base_bytes_at_complexity_one": 1_065,
        "formula_increment_bytes_per_additional_complexity": 1_024,
        "render_template": "bounded-h2-sections-v2",
    },
}

_HEADING_LABELS = {
    "markdown": "Long markdown topic",
    "md": "Markdown topic",
    "txt": "Plain text topic",
}
_HEADING_FILL = (
    "context evidence decision outcome review note remains bounded and local "
)
_CODE_FILL = "bounded context evidence decision outcome review note "

_FORBIDDEN_IDENTITY_PATTERN = re.compile(
    r"(?:"
    r"\bp[0-9]{2}-src-[0-9]{6}\b|"
    r"\b(?:persona|scope|source|intent|materialization|final[_-]?source)"
    r"[_-]?(?:id|key)\s*[:=]|"
    r"\bsha256:|"
    r"\b[0-9a-f]{64}\b"
    r")",
    re.IGNORECASE,
)


class PersonaV2TextValidatorError(ValueError):
    """Raised when bytes or metadata violate the standalone contract."""


@dataclass(frozen=True, slots=True)
class TextValidationRequest:
    """The complete identity-free payload supplied to the validator."""

    schema_version: int
    variant: str
    target_complexity: int
    data: bytes
    extension: str
    content_media_type: str
    expected_kio_path_media_type: str
    expected_offline_disposition: str


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        raise PersonaV2TextValidatorError("unsupported text variant")
    return _VARIANT_ROWS[variant]


def _target_bytes_for(variant, target_complexity):
    profile = _profile(variant)
    if (
        type(target_complexity) is not int
        or not MIN_TARGET_COMPLEXITY <= target_complexity <= MAX_TARGET_COMPLEXITY
    ):
        raise PersonaV2TextValidatorError(
            "target complexity must be an integer from 1 through 70"
        )
    target = profile["formula_base_bytes_at_complexity_one"] + (
        target_complexity - 1
    ) * profile["formula_increment_bytes_per_additional_complexity"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        raise PersonaV2TextValidatorError("target-byte formula exceeds validator cap")
    return target


def _repeat_exact(phrase, byte_count):
    repetitions, remainder = divmod(byte_count, len(phrase))
    return phrase * repetitions + phrase[:remainder]


def _expected_heading_bytes(variant, complexity, target_bytes):
    base, remainder = divmod(target_bytes, complexity)
    label = _HEADING_LABELS[variant]
    sections = []
    for ordinal in range(1, complexity + 1):
        section_bytes = base + (1 if ordinal <= remainder else 0)
        prefix = f"## {label} {ordinal:03d}\n\n"
        suffix = "\n"
        padding_bytes = section_bytes - len(prefix) - len(suffix)
        if padding_bytes < len(_HEADING_FILL):
            raise PersonaV2TextValidatorError("heading formula is infeasible")
        sections.append(
            prefix + _repeat_exact(_HEADING_FILL, padding_bytes) + suffix
        )
    return "".join(sections).encode("ascii")


def _expected_code_bytes(variant, target_bytes):
    comment = _VARIANT_ROWS[variant]["comment_prefix"]
    header = f"{comment}bounded {variant} feasibility text\n"
    body_prefix = comment
    padding_bytes = target_bytes - len(header) - len(body_prefix) - 1
    if padding_bytes < len(_CODE_FILL):
        raise PersonaV2TextValidatorError("code formula is infeasible")
    return (
        header + body_prefix + _repeat_exact(_CODE_FILL, padding_bytes) + "\n"
    ).encode("ascii")


def _validate_request_shape(request):
    if type(request) is not TextValidationRequest:
        raise PersonaV2TextValidatorError(
            "request must be an exact TextValidationRequest"
        )
    if tuple(TextValidationRequest.__dataclass_fields__) != REQUEST_FIELDS:
        raise PersonaV2TextValidatorError("validator request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        raise PersonaV2TextValidatorError("validator request exposes an identity field")
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2TextValidatorError(
            "validator request schema version must be exact 2"
        )
    profile = _profile(request.variant)
    target_bytes = _target_bytes_for(
        request.variant, request.target_complexity
    )
    if type(request.data) is not bytes:
        raise PersonaV2TextValidatorError("validated payload must be exact bytes")
    if not request.data or len(request.data) > MAX_RENDERED_BYTES:
        raise PersonaV2TextValidatorError("validated payload exceeds byte bounds")
    expected_metadata = (
        profile["filename_extension"],
        profile["content_media_type"],
        profile["expected_kio_path_media_type"],
        profile["expected_offline_disposition"],
    )
    actual_metadata = (
        request.extension,
        request.content_media_type,
        request.expected_kio_path_media_type,
        request.expected_offline_disposition,
    )
    if any(type(value) is not str for value in actual_metadata):
        raise PersonaV2TextValidatorError("format metadata must be exact strings")
    if actual_metadata != expected_metadata:
        raise PersonaV2TextValidatorError("extension/MIME/disposition metadata drifted")
    if len(request.data) != target_bytes:
        raise PersonaV2TextValidatorError("payload violates exact target-byte formula")
    return profile, target_bytes


def _validate_text_encoding_and_identity(data):
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise PersonaV2TextValidatorError("payload must be strict UTF-8") from None
    if not text.isascii():
        raise PersonaV2TextValidatorError("feasibility payload must be ASCII")
    if unicodedata.normalize("NFC", text) != text:
        raise PersonaV2TextValidatorError("payload must be NFC")
    if not text.endswith("\n") or "\r" in text or "\x00" in text:
        raise PersonaV2TextValidatorError("payload must use one terminal LF and no CR/NUL")
    if text.endswith("\n\n"):
        raise PersonaV2TextValidatorError("payload must end with exactly one LF")
    if _FORBIDDEN_IDENTITY_PATTERN.search(text):
        raise PersonaV2TextValidatorError(
            "payload contains an internal identity or digest token"
        )
    return text


def _validate_heading_structure(variant, complexity, text):
    label = _HEADING_LABELS[variant]
    starts = []
    offset = 0
    heading_ordinal = 0
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("## "):
            heading_ordinal += 1
            if line != f"## {label} {heading_ordinal:03d}\n":
                raise PersonaV2TextValidatorError("heading order or label drifted")
            if index + 1 >= len(lines) or lines[index + 1] != "\n":
                raise PersonaV2TextValidatorError("heading must be followed by one blank line")
            starts.append(offset)
        offset += len(line)
    if heading_ordinal != complexity:
        raise PersonaV2TextValidatorError("observed H2 complexity differs from target")
    boundaries = starts + [len(text)]
    if any(
        not 1 <= boundaries[index + 1] - boundaries[index] <= CHUNKING_MAX_CHARS
        for index in range(len(starts))
    ):
        raise PersonaV2TextValidatorError("heading section exceeds one-section bound")


def _validate_code_structure(variant, complexity, text):
    comment = _VARIANT_ROWS[variant]["comment_prefix"]
    lines = text.splitlines()
    if len(lines) != 2 or any(not line.startswith(comment) for line in lines):
        raise PersonaV2TextValidatorError("code exemplar must contain two comment-only lines")
    normalized = f"```{variant}\n{text.rstrip(chr(10))}\n```\n"
    expected_normalized_chars = (
        complexity - 1
    ) * CHUNKING_MAX_CHARS + CODE_LAST_NORMALIZED_CHARS
    if "\n\n" in normalized or len(normalized) != expected_normalized_chars:
        raise PersonaV2TextValidatorError("normalized hard-split formula drifted")
    cursor = 0
    observed_spans = 0
    while cursor < len(normalized):
        observed_spans += 1
        limit = min(cursor + CHUNKING_MAX_CHARS, len(normalized))
        if limit == len(normalized):
            break
        cursor = limit
        while cursor < len(normalized) and normalized[cursor].isspace():
            cursor += 1
    if observed_spans != complexity:
        raise PersonaV2TextValidatorError("observed hard-split span count drifted")


def validate_text_payload(request):
    """Validate exact bytes independently and return a negative-authority receipt."""

    profile, target_bytes = _validate_request_shape(request)
    text = _validate_text_encoding_and_identity(request.data)
    if profile["render_template"] == "bounded-h2-sections-v2":
        expected = _expected_heading_bytes(
            request.variant,
            request.target_complexity,
            target_bytes,
        )
        _validate_heading_structure(
            request.variant, request.target_complexity, text
        )
        observed_measure = "atx-h2-sections"
    elif profile["render_template"] == "comment-only-code-v2":
        expected = _expected_code_bytes(request.variant, target_bytes)
        _validate_code_structure(
            request.variant, request.target_complexity, text
        )
        observed_measure = "normalized-hard-split-spans"
    else:  # pragma: no cover - the frozen table prevents this branch.
        raise PersonaV2TextValidatorError("unknown text validation template")
    if request.data != expected:
        raise PersonaV2TextValidatorError("payload differs from standalone regeneration")
    return {
        "actual_chunks_attested": False,
        "byte_length": len(request.data),
        "identity_tokens_absent": True,
        "kio_execution_attested": False,
        "observed_complexity_measure": observed_measure,
        "observed_local_complexity": request.target_complexity,
        "structure_validated": True,
        "target_bytes": target_bytes,
        "utf8_validated": True,
    }


def _contract_variant_row(variant):
    profile = _VARIANT_ROWS[variant]
    return {
        "complexity": {
            "inclusive_maximum": MAX_TARGET_COMPLEXITY,
            "inclusive_minimum": MIN_TARGET_COMPLEXITY,
            "measure": profile["complexity_measure"],
        },
        "content_media_type": profile["content_media_type"],
        "expected_kio_path_media_type": profile["expected_kio_path_media_type"],
        "expected_offline_disposition": profile["expected_offline_disposition"],
        "family": profile["family"],
        "filename_extension": profile["filename_extension"],
        "gate_role": "contract_contributor",
        "raw_byte_formula": {
            "base_bytes_at_complexity_one": profile[
                "formula_base_bytes_at_complexity_one"
            ],
            "increment_bytes_per_additional_complexity": profile[
                "formula_increment_bytes_per_additional_complexity"
            ],
            "maximum_rendered_bytes": _target_bytes_for(
                variant, MAX_TARGET_COMPLEXITY
            ),
            "minimum_rendered_bytes": _target_bytes_for(
                variant, MIN_TARGET_COMPLEXITY
            ),
        },
        "render_template": profile["render_template"],
        "validator_profile_id": f"{variant}-standalone-id-free-text-validation-v2",
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
            "authorizes_source_intents": False,
            "authorizes_source_plan": False,
            "kio_execution_attested": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "nine-id-free-text-feasibility-variants-only-not-kio-attestation"
        ),
        "independence_contract": {
            "imports_renderer_module": False,
            "recomputes_expected_payload": True,
            "recomputes_format_metadata": True,
            "recomputes_target_byte_formula": True,
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
    }


def build_validator_contract():
    """Return a detached, non-authorizing standalone-validator descriptor."""

    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free text validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2TextValidatorError(str(error)) from None


def validate_validator_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free text validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2TextValidatorError(str(error)) from None


def validator_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free text validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2TextValidatorError(str(error)) from None
