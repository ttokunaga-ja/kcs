"""Bounded ID-free text feasibility renderer for persona-PC v2.

This is deliberately a narrow vertical slice.  It proves deterministic byte
and structural formulas for nine contributor variants, but it does not accept
persona, scope, source, intent, materialization, or final-source identifiers.
It therefore cannot allocate a source plan or write a fixture tree.  Observed
KCS chunks remain a later attestation concern.

The v1 renderer is intentionally not imported: its payload identity and digest
embedding semantics are incompatible with the v2 source-recipe boundary.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kcs.persona.pc-id-free-text-renderer/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-text-renderer"
RENDERER_ID = "persona-v2-id-free-text-feasibility-renderer"
RENDERER_SCHEMA_VERSION = 2
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
        "expected_kcs_path_media_type": "text/x-code",
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
        "expected_kcs_path_media_type": "text/x-code",
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
        "expected_kcs_path_media_type": "text/x-code",
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
        "expected_kcs_path_media_type": "text/markdown",
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
        "expected_kcs_path_media_type": "text/markdown",
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
        "expected_kcs_path_media_type": "text/x-code",
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
        "expected_kcs_path_media_type": "text/x-code",
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
        "expected_kcs_path_media_type": "text/x-code",
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
        "expected_kcs_path_media_type": "text/plain",
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


class PersonaV2TextRendererError(ValueError):
    """Raised when the narrow v2 text renderer contract is violated."""


@dataclass(frozen=True)
class TextRenderRequest:
    """An intentionally identity-free feasibility request."""

    schema_version: int
    variant: str
    target_complexity: int


@dataclass(frozen=True)
class RenderedText:
    """Rendered bytes and non-authoritative format/complexity metadata."""

    data: bytes
    extension: str
    content_media_type: str
    expected_kcs_path_media_type: str
    expected_offline_disposition: str
    target_complexity: int
    target_bytes: int
    renderer_id: str = RENDERER_ID
    renderer_schema_version: int = RENDERER_SCHEMA_VERSION


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        raise PersonaV2TextRendererError(f"unsupported text variant: {variant!r}")
    return _VARIANT_ROWS[variant]


def validate_request(request):
    """Reject all but the exact three-field, identity-free request shape."""

    if type(request) is not TextRenderRequest:
        raise PersonaV2TextRendererError("request must be an exact TextRenderRequest")
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2TextRendererError("renderer request schema version must be exact 2")
    _profile(request.variant)
    if (
        type(request.target_complexity) is not int
        or not MIN_TARGET_COMPLEXITY
        <= request.target_complexity
        <= MAX_TARGET_COMPLEXITY
    ):
        raise PersonaV2TextRendererError(
            "target complexity must be an integer from 1 through 70"
        )
    if tuple(TextRenderRequest.__dataclass_fields__) != REQUEST_FIELDS:
        raise PersonaV2TextRendererError("renderer request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        raise PersonaV2TextRendererError("renderer request exposes an identity field")
    return True


def target_bytes_for(variant, target_complexity):
    """Evaluate the exact affine raw-byte formula for one supported variant."""

    profile = _profile(variant)
    if (
        type(target_complexity) is not int
        or not MIN_TARGET_COMPLEXITY <= target_complexity <= MAX_TARGET_COMPLEXITY
    ):
        raise PersonaV2TextRendererError(
            "target complexity must be an integer from 1 through 70"
        )
    target = profile["formula_base_bytes_at_complexity_one"] + (
        target_complexity - 1
    ) * profile["formula_increment_bytes_per_additional_complexity"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        raise PersonaV2TextRendererError("target-byte formula exceeds renderer cap")
    return target


def _repeat_exact(phrase, byte_count):
    if type(phrase) is not str or not phrase or not phrase.isascii():
        raise PersonaV2TextRendererError("padding phrase must be non-empty ASCII")
    if type(byte_count) is not int or byte_count < 0:
        raise PersonaV2TextRendererError("padding byte count must be non-negative")
    repetitions, remainder = divmod(byte_count, len(phrase))
    return phrase * repetitions + phrase[:remainder]


def _render_heading_sections(variant, complexity, target_bytes):
    base, remainder = divmod(target_bytes, complexity)
    label = _HEADING_LABELS[variant]
    sections = []
    for ordinal in range(1, complexity + 1):
        section_bytes = base + (1 if ordinal <= remainder else 0)
        prefix = f"## {label} {ordinal:03d}\n\n"
        suffix = "\n"
        padding_bytes = section_bytes - len(prefix) - len(suffix)
        if padding_bytes < len(_HEADING_FILL):
            raise PersonaV2TextRendererError("heading section target is too small")
        section = prefix + _repeat_exact(_HEADING_FILL, padding_bytes) + suffix
        if len(section) != section_bytes or len(section) > CHUNKING_MAX_CHARS:
            raise PersonaV2TextRendererError(
                "heading section does not satisfy exact one-section bound"
            )
        sections.append(section)
    data = "".join(sections).encode("ascii")
    if len(data) != target_bytes:
        raise PersonaV2TextRendererError("heading target-byte formula drifted")
    return data


def _render_comment_code(variant, complexity, target_bytes):
    profile = _VARIANT_ROWS[variant]
    comment = profile["comment_prefix"]
    header = f"{comment}bounded {variant} feasibility text\n"
    body_prefix = f"{comment}"
    padding_bytes = target_bytes - len(header) - len(body_prefix) - 1
    if padding_bytes < len(_CODE_FILL):
        raise PersonaV2TextRendererError("code target is too small")
    text = header + body_prefix + _repeat_exact(_CODE_FILL, padding_bytes) + "\n"
    data = text.encode("ascii")
    if len(data) != target_bytes:
        raise PersonaV2TextRendererError("code target-byte formula drifted")

    normalized = f"```{variant}\n{text.rstrip(chr(10))}\n```\n"
    expected_normalized_chars = (
        complexity - 1
    ) * CHUNKING_MAX_CHARS + CODE_LAST_NORMALIZED_CHARS
    if "\n\n" in normalized or len(normalized) != expected_normalized_chars:
        raise PersonaV2TextRendererError("code normalized-span formula drifted")
    return data


def render_text(request):
    """Render one deterministic feasibility exemplar without source identity."""

    validate_request(request)
    profile = _VARIANT_ROWS[request.variant]
    target_bytes = target_bytes_for(request.variant, request.target_complexity)
    if profile["render_template"] == "bounded-h2-sections-v2":
        data = _render_heading_sections(
            request.variant,
            request.target_complexity,
            target_bytes,
        )
    elif profile["render_template"] == "comment-only-code-v2":
        data = _render_comment_code(
            request.variant,
            request.target_complexity,
            target_bytes,
        )
    else:  # pragma: no cover - the frozen table prevents this branch.
        raise PersonaV2TextRendererError("unknown text render template")
    return RenderedText(
        data=data,
        extension=profile["filename_extension"],
        content_media_type=profile["content_media_type"],
        expected_kcs_path_media_type=profile["expected_kcs_path_media_type"],
        expected_offline_disposition=profile["expected_offline_disposition"],
        target_complexity=request.target_complexity,
        target_bytes=target_bytes,
    )


def _contract_variant_row(variant):
    profile = _VARIANT_ROWS[variant]
    return {
        "complexity": {
            "inclusive_maximum": MAX_TARGET_COMPLEXITY,
            "inclusive_minimum": MIN_TARGET_COMPLEXITY,
            "measure": profile["complexity_measure"],
        },
        "content_media_type": profile["content_media_type"],
        "expected_kcs_path_media_type": profile["expected_kcs_path_media_type"],
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
            "maximum_rendered_bytes": target_bytes_for(
                variant, MAX_TARGET_COMPLEXITY
            ),
            "minimum_rendered_bytes": target_bytes_for(
                variant, MIN_TARGET_COMPLEXITY
            ),
        },
        "render_template": profile["render_template"],
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
            "kcs_execution_attested": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "nine-id-free-text-feasibility-variants-only-not-source-materialization"
        ),
        "payload_identity_policy": {
            "content_digest_embedded": False,
            "final_source_identifier_embedded": False,
            "intent_identifier_embedded": False,
            "materialization_identifier_embedded": False,
            "persona_identifier_embedded": False,
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
    }


def build_renderer_contract():
    """Return a detached, non-authorizing renderer contract descriptor."""

    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free text renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2TextRendererError(str(error)) from None


def validate_renderer_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free text renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2TextRendererError(str(error)) from None


def renderer_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free text renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2TextRendererError(str(error)) from None
