"""Deterministic ID-free feasibility renderer for all incidental v2 formats.

The eleven variants in this module account for every ``incidental_searchable``
physical source in the persona-PC v2 envelope.  This is deliberately a local
format/byte feasibility primitive: it accepts no persona, source, query,
solution, path, or digest identity and grants no write, KCS, solver, or G0
authority.  Formal source recipes and solved per-source values remain separate
downstream artifacts.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kcs.persona.pc-id-free-incidental-text-renderer/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-incidental-text-renderer"
RENDERER_ID = "persona-v2-id-free-incidental-text-feasibility-renderer"
RENDERER_SCHEMA_VERSION = 2
MAX_CONTRACT_BYTES = 96 * 1024
MAX_RENDERED_BYTES = 512 * 1024
MAX_EML_LINE_OCTETS = 78

READY_VARIANTS = (
    "csv",
    "eml",
    "html",
    "ipynb",
    "json",
    "jsonl",
    "log",
    "sql",
    "tsv",
    "xml",
    "yaml",
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

_BOUNDARY = "bounded-mixed-boundary"
_LF = "\n"
_CRLF = "\r\n"

_VARIANT_ROWS = {
    "csv": {
        "complexity_measure": "tabular-rows",
        "inclusive_minimum": 1,
        "inclusive_maximum": 10_000,
        "base_bytes": 512,
        "increment_bytes": 48,
        "content_media_type": "text/csv",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "csv_tsv",
        "filename_extension": "csv",
        "render_template": "canonical-comma-table-v2",
    },
    "eml": {
        "complexity_measure": "attachments",
        "inclusive_minimum": 0,
        "inclusive_maximum": 5,
        "base_bytes": 8_192,
        "increment_bytes": 16_384,
        "content_media_type": "message/rfc822",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "html_eml",
        "filename_extension": "eml",
        "render_template": "canonical-crlf-multipart-mixed-v2",
    },
    "html": {
        "complexity_measure": "html-sections",
        "inclusive_minimum": 1,
        "inclusive_maximum": 256,
        "base_bytes": 2_048,
        "increment_bytes": 1_024,
        "content_media_type": "text/html",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "html_eml",
        "filename_extension": "html",
        "render_template": "canonical-html-sections-v2",
    },
    "ipynb": {
        "complexity_measure": "notebook-cells",
        "inclusive_minimum": 1,
        "inclusive_maximum": 256,
        "base_bytes": 2_048,
        "increment_bytes": 1_024,
        "content_media_type": "application/x-ipynb+json",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "ipynb",
        "filename_extension": "ipynb",
        "render_template": "canonical-nbformat-4-5-v2",
    },
    "json": {
        "complexity_measure": "json-nodes",
        "inclusive_minimum": 1,
        "inclusive_maximum": 1_024,
        "base_bytes": 1_024,
        "increment_bytes": 256,
        "content_media_type": "application/json",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "structured_text",
        "filename_extension": "json",
        "render_template": "canonical-json-node-array-v2",
    },
    "jsonl": {
        "complexity_measure": "jsonl-records",
        "inclusive_minimum": 1,
        "inclusive_maximum": 4_096,
        "base_bytes": 512,
        "increment_bytes": 96,
        "content_media_type": "application/x-ndjson",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "txt_log",
        "filename_extension": "jsonl",
        "render_template": "canonical-json-lines-v2",
    },
    "log": {
        "complexity_measure": "log-records",
        "inclusive_minimum": 1,
        "inclusive_maximum": 4_096,
        "base_bytes": 512,
        "increment_bytes": 96,
        "content_media_type": "text/plain",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "txt_log",
        "filename_extension": "log",
        "render_template": "canonical-fixed-log-records-v2",
    },
    "sql": {
        "complexity_measure": "sql-statements",
        "inclusive_minimum": 1,
        "inclusive_maximum": 256,
        "base_bytes": 2_048,
        "increment_bytes": 1_024,
        "content_media_type": "application/sql",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "structured_text",
        "filename_extension": "sql",
        "render_template": "canonical-select-statements-v2",
    },
    "tsv": {
        "complexity_measure": "tabular-rows",
        "inclusive_minimum": 1,
        "inclusive_maximum": 10_000,
        "base_bytes": 512,
        "increment_bytes": 48,
        "content_media_type": "text/tab-separated-values",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "csv_tsv",
        "filename_extension": "tsv",
        "render_template": "canonical-tab-table-v2",
    },
    "xml": {
        "complexity_measure": "xml-elements",
        "inclusive_minimum": 1,
        "inclusive_maximum": 1_024,
        "base_bytes": 1_024,
        "increment_bytes": 256,
        "content_media_type": "application/xml",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "structured_text",
        "filename_extension": "xml",
        "render_template": "canonical-xml-items-v2",
    },
    "yaml": {
        "complexity_measure": "yaml-nodes",
        "inclusive_minimum": 1,
        "inclusive_maximum": 1_024,
        "base_bytes": 1_024,
        "increment_bytes": 256,
        "content_media_type": "application/yaml",
        "expected_kcs_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "structured_text",
        "filename_extension": "yaml",
        "render_template": "canonical-yaml-block-sequence-v2",
    },
}

_COMPLEXITY_COUNTING_RULES = {
    "csv": "data-rows-excluding-header",
    "eml": "attachment-parts-excluding-primary-body",
    "html": "section-elements",
    "ipynb": "notebook-cells",
    "json": "top-level-array-items-excluding-root-object-and-array",
    "jsonl": "physical-json-records",
    "log": "physical-log-records",
    "sql": "select-statements",
    "tsv": "data-rows-excluding-header",
    "xml": "direct-item-elements-excluding-root-element",
    "yaml": "block-sequence-items-excluding-sequence-container",
}


class PersonaV2IncidentalTextRendererError(ValueError):
    """Raised when the incidental renderer contract is violated."""


@dataclass(frozen=True, slots=True)
class IncidentalTextRenderRequest:
    """An intentionally identity-free local feasibility request."""

    schema_version: int
    variant: str
    target_complexity: int


@dataclass(frozen=True, slots=True)
class RenderedIncidentalText:
    """Rendered bytes and non-authoritative format metadata."""

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
        raise PersonaV2IncidentalTextRendererError(
            "unsupported incidental text variant"
        )
    return _VARIANT_ROWS[variant]


def validate_request(request):
    if type(request) is not IncidentalTextRenderRequest:
        raise PersonaV2IncidentalTextRendererError(
            "request must be an exact IncidentalTextRenderRequest"
        )
    if tuple(IncidentalTextRenderRequest.__dataclass_fields__) != REQUEST_FIELDS:
        raise PersonaV2IncidentalTextRendererError(
            "renderer request schema drifted"
        )
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        raise PersonaV2IncidentalTextRendererError(
            "renderer request exposes an identity field"
        )
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2IncidentalTextRendererError(
            "renderer request schema version must be exact 2"
        )
    profile = _profile(request.variant)
    if (
        type(request.target_complexity) is not int
        or not profile["inclusive_minimum"]
        <= request.target_complexity
        <= profile["inclusive_maximum"]
    ):
        raise PersonaV2IncidentalTextRendererError(
            "target complexity is outside the exact variant domain"
        )
    return True


def target_bytes_for(variant, target_complexity):
    profile = _profile(variant)
    if (
        type(target_complexity) is not int
        or not profile["inclusive_minimum"]
        <= target_complexity
        <= profile["inclusive_maximum"]
    ):
        raise PersonaV2IncidentalTextRendererError(
            "target complexity is outside the exact variant domain"
        )
    target = profile["base_bytes"] + (
        target_complexity - profile["inclusive_minimum"]
    ) * profile["increment_bytes"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        raise PersonaV2IncidentalTextRendererError(
            "target-byte formula exceeds the renderer cap"
        )
    return target


def _filled(prefix, suffix, target_length, *, fill="x"):
    if not all(type(value) is str and value.isascii() for value in (prefix, suffix, fill)):
        raise PersonaV2IncidentalTextRendererError("fill components must be ASCII")
    if not fill:
        raise PersonaV2IncidentalTextRendererError("fill token must be non-empty")
    remaining = target_length - len(prefix) - len(suffix)
    if remaining < 0:
        raise PersonaV2IncidentalTextRendererError(
            "format skeleton exceeds its target length"
        )
    repetitions, remainder = divmod(remaining, len(fill))
    result = prefix + fill * repetitions + fill[:remainder] + suffix
    if len(result) != target_length:
        raise PersonaV2IncidentalTextRendererError("exact fill length drifted")
    return result


def _filled_crlf_lines(prefix, suffix, target_length):
    """Fill an EML body exactly while keeping every wire line bounded."""

    if not all(type(value) is str and value.isascii() for value in (prefix, suffix)):
        raise PersonaV2IncidentalTextRendererError(
            "EML fill components must be ASCII"
        )
    if not suffix.startswith(_CRLF):
        raise PersonaV2IncidentalTextRendererError(
            "EML fill suffix must begin with CRLF framing"
        )
    remaining = target_length - len(prefix) - len(suffix)
    current_width = len(prefix.rsplit(_CRLF, 1)[-1])
    if remaining < 1 or not 0 <= current_width < MAX_EML_LINE_OCTETS:
        raise PersonaV2IncidentalTextRendererError(
            "EML body skeleton cannot satisfy its exact line-bound target"
        )
    for break_count in range(remaining // len(_CRLF) + 1):
        filler_octets = remaining - break_count * len(_CRLF)
        capacities = [MAX_EML_LINE_OCTETS - current_width] + [
            MAX_EML_LINE_OCTETS
        ] * break_count
        if not len(capacities) <= filler_octets <= sum(capacities):
            continue
        widths = [1] * len(capacities)
        unassigned = filler_octets - len(widths)
        for ordinal, capacity in enumerate(capacities):
            addition = min(capacity - 1, unassigned)
            widths[ordinal] += addition
            unassigned -= addition
        if unassigned:
            continue
        filler = _CRLF.join("x" * width for width in widths)
        result = prefix + filler + suffix
        if len(result) != target_length:
            raise PersonaV2IncidentalTextRendererError(
                "EML exact fill length drifted"
            )
        if max(len(line) for line in result.split(_CRLF)) > MAX_EML_LINE_OCTETS:
            raise PersonaV2IncidentalTextRendererError(
                "EML exact fill exceeded its wire line bound"
            )
        return result
    raise PersonaV2IncidentalTextRendererError(
        "EML exact target has no bounded-line representation"
    )


def _render_log(complexity):
    rows = []
    for ordinal in range(1, complexity + 1):
        length = 512 if ordinal == 1 else 96
        prefix = (
            f"2026-07-15T00:00:00Z INFO ordinal={ordinal:04d} "
            "message=bounded-"
        )
        rows.append(_filled(prefix, _LF, length))
    return "".join(rows).encode("ascii")


def _jsonl_line(ordinal, target_length):
    row = {"kind": "bounded-record", "ordinal": f"{ordinal:04d}", "padding": ""}
    empty = json.dumps(row, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    padding = target_length - len(empty) - 1
    if padding < 0:
        raise PersonaV2IncidentalTextRendererError("JSONL skeleton is too large")
    row["padding"] = "x" * padding
    encoded = json.dumps(
        row, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ) + _LF
    if len(encoded) != target_length:
        raise PersonaV2IncidentalTextRendererError("JSONL formula drifted")
    return encoded


def _render_jsonl(complexity):
    return "".join(
        _jsonl_line(ordinal, 512 if ordinal == 1 else 96)
        for ordinal in range(1, complexity + 1)
    ).encode("ascii")


def _json_string(prefix, serialized_length):
    content_length = serialized_length - 2
    if content_length < len(prefix):
        raise PersonaV2IncidentalTextRendererError("JSON string target is too small")
    return json.dumps(prefix + "x" * (content_length - len(prefix)))


def _render_json(complexity):
    prefix = '{"nodes":['
    suffix = "]}\n"
    first_length = 1_024 - len(prefix) - len(suffix)
    items = [_json_string("bounded-node-0001-", first_length)]
    for ordinal in range(2, complexity + 1):
        items.append(_json_string(f"bounded-node-{ordinal:04d}-", 255))
    data = (prefix + ",".join(items) + suffix).encode("ascii")
    if len(data) != target_bytes_for("json", complexity):
        raise PersonaV2IncidentalTextRendererError("JSON formula drifted")
    return data


def _render_yaml(complexity):
    rows = []
    for ordinal in range(1, complexity + 1):
        length = 1_024 if ordinal == 1 else 256
        rows.append(_filled(f"- bounded-node-{ordinal:04d}-", _LF, length))
    return "".join(rows).encode("ascii")


def _render_xml(complexity):
    prefix = '<?xml version="1.0" encoding="UTF-8"?>\n<items>\n'
    suffix = "</items>\n"
    first_length = 1_024 - len(prefix) - len(suffix)
    items = [
        _filled('<item ordinal="0001">bounded-node-', "</item>\n", first_length)
    ]
    for ordinal in range(2, complexity + 1):
        items.append(
            _filled(
                f'<item ordinal="{ordinal:04d}">bounded-node-',
                "</item>\n",
                256,
            )
        )
    data = (prefix + "".join(items) + suffix).encode("ascii")
    if len(data) != target_bytes_for("xml", complexity):
        raise PersonaV2IncidentalTextRendererError("XML formula drifted")
    return data


def _render_sql(complexity):
    statements = []
    for ordinal in range(1, complexity + 1):
        length = 2_048 if ordinal == 1 else 1_024
        prefix = f"SELECT 'bounded-statement-{ordinal:03d}-"
        statements.append(_filled(prefix, "' AS note;\n", length))
    return "".join(statements).encode("ascii")


def _table_row(delimiter, ordinal, target_length):
    prefix = f"{ordinal:05d}{delimiter}bounded{delimiter}"
    return _filled(prefix, _LF, target_length)


def _render_table(variant, complexity):
    delimiter = "," if variant == "csv" else "\t"
    header = f"ordinal{delimiter}label{delimiter}note\n"
    first_length = 512 - len(header)
    rows = [_table_row(delimiter, 1, first_length)]
    rows.extend(
        _table_row(delimiter, ordinal, 48)
        for ordinal in range(2, complexity + 1)
    )
    data = (header + "".join(rows)).encode("ascii")
    if len(data) != target_bytes_for(variant, complexity):
        raise PersonaV2IncidentalTextRendererError("table formula drifted")
    return data


def _render_html(complexity):
    prefix = '<!doctype html>\n<html><head><meta charset="utf-8"><title>Bounded</title></head><body>\n'
    suffix = "</body></html>\n"
    first_length = 2_048 - len(prefix) - len(suffix)
    sections = [
        _filled(
            '<section data-ordinal="001"><h2>Bounded section</h2><p>',
            "</p></section>\n",
            first_length,
        )
    ]
    for ordinal in range(2, complexity + 1):
        sections.append(
            _filled(
                f'<section data-ordinal="{ordinal:03d}"><h2>Bounded section</h2><p>',
                "</p></section>\n",
                1_024,
            )
        )
    data = (prefix + "".join(sections) + suffix).encode("ascii")
    if len(data) != target_bytes_for("html", complexity):
        raise PersonaV2IncidentalTextRendererError("HTML formula drifted")
    return data


def _notebook_cell(ordinal, serialized_length):
    row = {
        "cell_type": "markdown",
        "id": f"cell-{ordinal:03d}",
        "metadata": {},
        "source": [""],
    }
    empty = json.dumps(row, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    padding = serialized_length - len(empty)
    if padding < len("Bounded synthetic note. "):
        raise PersonaV2IncidentalTextRendererError("notebook cell target is too small")
    prefix = "Bounded synthetic note. "
    row["source"] = [prefix + "x" * (padding - len(prefix))]
    encoded = json.dumps(
        row, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    if len(encoded) != serialized_length:
        raise PersonaV2IncidentalTextRendererError("notebook cell formula drifted")
    return encoded


def _render_ipynb(complexity):
    prefix = '{"cells":['
    suffix = '],"metadata":{},"nbformat":4,"nbformat_minor":5}\n'
    first_length = 2_048 - len(prefix) - len(suffix)
    cells = [_notebook_cell(1, first_length)]
    cells.extend(
        _notebook_cell(ordinal, 1_023)
        for ordinal in range(2, complexity + 1)
    )
    data = (prefix + ",".join(cells) + suffix).encode("ascii")
    if len(data) != target_bytes_for("ipynb", complexity):
        raise PersonaV2IncidentalTextRendererError("IPYNB formula drifted")
    return data


def _eml_attachment(ordinal):
    prefix = (
        f"--{_BOUNDARY}{_CRLF}"
        f'Content-Type: text/plain; name="note-{ordinal:02d}.txt"{_CRLF}'
        f'Content-Disposition: attachment; filename="note-{ordinal:02d}.txt"{_CRLF}'
        f"Content-Transfer-Encoding: 7bit{_CRLF}{_CRLF}"
        f"Bounded attachment {ordinal:02d}. "
    )
    return _filled_crlf_lines(prefix, _CRLF, 16_384)


def _render_eml(complexity):
    prefix = (
        f"From: synthetic-sender@example.invalid{_CRLF}"
        f"To: synthetic-recipient@example.invalid{_CRLF}"
        f"Subject: Bounded synthetic message{_CRLF}"
        f"Date: Wed, 15 Jul 2026 00:00:00 +0000{_CRLF}"
        f"Message-ID: <bounded-message@example.invalid>{_CRLF}"
        f"MIME-Version: 1.0{_CRLF}"
        f'Content-Type: multipart/mixed; boundary="{_BOUNDARY}"{_CRLF}'
        f"{_CRLF}"
        f"--{_BOUNDARY}{_CRLF}"
        f'Content-Type: text/plain; charset="us-ascii"{_CRLF}'
        f"Content-Transfer-Encoding: 7bit{_CRLF}{_CRLF}"
        f"Bounded synthetic message body. "
    )
    closing = f"{_CRLF}--{_BOUNDARY}--{_CRLF}"
    base = _filled_crlf_lines(prefix, closing, 8_192)
    insertion = "".join(_eml_attachment(ordinal) for ordinal in range(1, complexity + 1))
    if insertion:
        text = base[: -len(closing)] + _CRLF + insertion + closing[len(_CRLF) :]
    else:
        text = base
    data = text.encode("ascii")
    if len(data) != target_bytes_for("eml", complexity):
        raise PersonaV2IncidentalTextRendererError("EML formula drifted")
    return data


def _render_payload(variant, complexity):
    if variant == "log":
        return _render_log(complexity)
    if variant == "jsonl":
        return _render_jsonl(complexity)
    if variant == "json":
        return _render_json(complexity)
    if variant == "yaml":
        return _render_yaml(complexity)
    if variant == "xml":
        return _render_xml(complexity)
    if variant == "sql":
        return _render_sql(complexity)
    if variant in {"csv", "tsv"}:
        return _render_table(variant, complexity)
    if variant == "html":
        return _render_html(complexity)
    if variant == "ipynb":
        return _render_ipynb(complexity)
    if variant == "eml":
        return _render_eml(complexity)
    raise PersonaV2IncidentalTextRendererError("unknown incidental render template")


def render_incidental_text(request):
    """Render one deterministic local exemplar without source identity."""

    validate_request(request)
    profile = _profile(request.variant)
    data = _render_payload(request.variant, request.target_complexity)
    target_bytes = target_bytes_for(request.variant, request.target_complexity)
    if type(data) is not bytes or len(data) != target_bytes:
        raise PersonaV2IncidentalTextRendererError(
            "rendered payload differs from exact byte formula"
        )
    return RenderedIncidentalText(
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
        "gate_role": "incidental_searchable",
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
            "max_eml_wire_line_octets": MAX_EML_LINE_OCTETS,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "eleven-id-free-formal-ordinary-incidental-format-feasibility-variants-"
            "only-not-source-materialization-or-kcs-attestation"
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
        "variant_rows": [_contract_variant_row(variant) for variant in READY_VARIANTS],
        "vertical_slice_implementation_available": True,
    }


def build_renderer_contract():
    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free incidental text renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2IncidentalTextRendererError(str(error)) from None


def validate_renderer_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free incidental text renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2IncidentalTextRendererError(str(error)) from None


def renderer_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free incidental text renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2IncidentalTextRendererError(str(error)) from None


__all__ = [
    "IncidentalTextRenderRequest",
    "MAX_EML_LINE_OCTETS",
    "MAX_RENDERED_BYTES",
    "PersonaV2IncidentalTextRendererError",
    "READY_VARIANTS",
    "RENDERER_ID",
    "RenderedIncidentalText",
    "build_renderer_contract",
    "canonical_json_bytes",
    "render_incidental_text",
    "renderer_contract_sha256",
    "target_bytes_for",
    "validate_renderer_contract",
    "validate_request",
]
