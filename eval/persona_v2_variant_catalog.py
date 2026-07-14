"""Completion sidecar for the persona-PC v2 variant dictionary.

The envelope freezes 71 variant identities and 566 persona/family/variant
marginals, but deliberately marks renderer/validator feasibility incomplete.
This sidecar expands every identity into a single extension, content MIME,
expected KCS path MIME, gate role, search/complexity/byte contract, safety
profile, and exact tiny/pilot/full marginal row.  It is still non-authorizing:
v2 ID-free renderers and independent validators are not implemented yet.
"""

from __future__ import annotations

import copy

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_input_bindings as input_bindings
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_input_bindings as input_bindings


ARTIFACT_SCHEMA = "kcs.persona.pc-variant-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-variant-catalog"
MAX_CATALOG_BYTES = 2 * 2**20
MAX_FORMAL_ORDINARY_BYTES = 512 * 1024
MAX_FORMAL_TAIL_BYTES = 4 * 2**20
MAX_RENDERED_SOURCE_BYTES = 100 * 2**20
MAX_EXPANDED_CONTAINER_BYTES = 8 * 2**20
MAX_TAIL_FILES_PER_PERSONA = 16
PROFILE_ORDER = ("tiny-smoke", "pilot", "full")

_CONTRIBUTOR_VARIANTS = frozenset(
    ("md", "markdown", "txt", "py", "rs", "ts", "go", "js", "cpp", "pdf-text")
)
_REUSABLE_V1_PRIMITIVE_VARIANTS = frozenset(
    (
        "md", "markdown", "txt", "py", "rs", "ts", "log", "jsonl",
        "json", "yaml", "xml", "sql", "csv", "tsv", "html", "eml",
        "ipynb", "pdf-text", "pdf-scan", "docx", "xlsx", "pptx",
        "png", "wav", "pcap",
    )
)

_CONTENT_MIME_BY_VARIANT = {
    "aiff": "audio/aiff",
    "bmp": "image/bmp",
    "cpp": "text/x-c++src",
    "csv": "text/csv",
    "dicom-part10": "application/dicom",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "eml": "message/rfc822",
    "go": "text/x-go",
    "html": "text/html",
    "ifczip": "application/zip",
    "ipynb": "application/x-ipynb+json",
    "jpg": "image/jpeg",
    "js": "text/javascript",
    "json": "application/json",
    "jsonl": "application/x-ndjson",
    "log": "text/plain",
    "markdown": "text/markdown",
    "md": "text/markdown",
    "mid": "audio/midi",
    "npz": "application/zip",
    "pcap": "application/vnd.tcpdump.pcap",
    "pdf-scan": "application/pdf",
    "pdf-text": "application/pdf",
    "png": "image/png",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "py": "text/x-python",
    "rs": "text/x-rust",
    "sql": "application/sql",
    "tif": "image/tiff",
    "ts": "text/typescript",
    "tsv": "text/tab-separated-values",
    "txt": "text/plain",
    "wav": "audio/wav",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xml": "application/xml",
    "yaml": "application/yaml",
}


class PersonaV2VariantCatalogError(ValueError):
    """Raised when the completion catalog differs from the exact v2 inputs."""


def _variant_families():
    result = {}
    for persona_id in envelope.PERSONA_IDS:
        counts = envelope.variant_counts(persona_id, "full")
        for family in envelope.FORMAT_KEYS:
            for variant in counts[family]:
                variant_id = variant["variant_id"]
                previous = result.setdefault(variant_id, family)
                if previous != family:
                    raise PersonaV2VariantCatalogError(
                        f"variant belongs to multiple families: {variant_id}"
                    )
    return result


def _content_mime(variant_id):
    if variant_id in _CONTENT_MIME_BY_VARIANT:
        return _CONTENT_MIME_BY_VARIANT[variant_id]
    if variant_id.endswith("-zip"):
        return "application/zip"
    if variant_id.endswith("-ustar"):
        return "application/x-tar"
    if variant_id.endswith("-gzip"):
        return "application/gzip"
    raise PersonaV2VariantCatalogError(f"missing content MIME: {variant_id}")


def _complexity_contract(family, variant_id, gate_role):
    if variant_id in {"md", "markdown", "txt"}:
        profile, unit, minimum, maximum = "heading-quota-v2", "sections", 1, 70
    elif family == "code":
        profile, unit, minimum, maximum = "code-hard-split-v2", "normalized-spans", 1, 70
    elif variant_id == "pdf-text":
        profile, unit, minimum, maximum = "pdf-page-complexity-v2", "text-pages", 1, 72
    elif variant_id == "log":
        profile, unit, minimum, maximum = "log-records-v2", "log-records", 1, 4_096
    elif variant_id == "jsonl":
        profile, unit, minimum, maximum = "jsonl-records-v2", "jsonl-records", 1, 4_096
    elif variant_id == "json":
        profile, unit, minimum, maximum = "json-nodes-v2", "json-nodes", 1, 1_024
    elif variant_id == "yaml":
        profile, unit, minimum, maximum = "yaml-nodes-v2", "yaml-nodes", 1, 1_024
    elif variant_id == "xml":
        profile, unit, minimum, maximum = "xml-elements-v2", "xml-elements", 1, 1_024
    elif variant_id == "sql":
        profile, unit, minimum, maximum = "sql-statements-v2", "sql-statements", 1, 256
    elif variant_id in {"csv", "tsv"}:
        profile, unit, minimum, maximum = "tabular-rows-v2", "tabular-rows", 1, 10_000
    elif variant_id == "html":
        profile, unit, minimum, maximum = "html-sections-v2", "html-sections", 1, 256
    elif variant_id == "eml":
        profile, unit, minimum, maximum = "eml-attachments-v2", "attachments", 0, 5
    elif variant_id == "ipynb":
        profile, unit, minimum, maximum = "notebook-cells-v2", "notebook-cells", 1, 256
    elif variant_id == "pdf-scan":
        profile, unit, minimum, maximum = "scan-pdf-v2", "scan-pages", 1, 50
    elif variant_id == "docx":
        profile, unit, minimum, maximum = "docx-v2", "document-sections", 1, 64
    elif variant_id == "xlsx":
        profile, unit, minimum, maximum = "xlsx-v2", "worksheets", 1, 20
    elif variant_id == "pptx":
        profile, unit, minimum, maximum = "pptx-v2", "slides", 1, 40
    elif family == "image":
        profile, unit, minimum, maximum = "raster-v2", "pixels", 4_096, 16_777_216
    elif family == "media":
        profile, unit, minimum, maximum = "audio-midi-v2", "frames-or-events", 1, 4_800_000
    elif variant_id == "npz":
        profile, unit, minimum, maximum = "npz-v2", "array-elements", 1, 1_000_000
    elif variant_id == "pcap":
        profile, unit, minimum, maximum = "pcap-v2", "packets", 1, 4_096
    elif variant_id == "dicom-part10":
        profile, unit, minimum, maximum = "dicom-v2", "frames", 1, 64
    elif variant_id == "ifczip":
        profile, unit, minimum, maximum = "ifczip-v2", "spf-members", 1, 1
    elif variant_id.endswith("-gzip"):
        profile, unit, minimum, maximum = "archive-v2", "records", 1, 4_096
    elif variant_id.endswith("-zip") or variant_id.endswith("-ustar"):
        profile, unit, minimum, maximum = "archive-v2", "members", 1, 64
    else:
        raise PersonaV2VariantCatalogError(
            f"missing complexity contract: {family}/{variant_id}"
        )
    return {
        "complexity_profile_id": profile,
        "complexity_unit": unit,
        "maximum": maximum,
        "minimum": minimum,
        "quota_relation": (
            "requested-chunk-quota-separate-from-format-complexity-formula-not-bound"
            if variant_id in _CONTRIBUTOR_VARIANTS
            else "requested-contract-quota-must-be-zero"
        ),
    }


def _lane_contracts():
    return {
        "byte_stress": {
            "cardinality_per_persona": 64,
            "container_encodings_allowed_size_classes": ["small", "medium"],
            "container_expanded_bytes_cap": MAX_EXPANDED_CONTAINER_BYTES,
            "eml_attachments": {"inclusive_maximum": 50, "inclusive_minimum": 6},
            "image_media_domain_bytes": {
                "inclusive_maximum": MAX_RENDERED_SOURCE_BYTES,
                "inclusive_minimum": 128 * 1024,
            },
            "lane_local_gate_role": "raw_only",
            "lane_local_observed_chunk_gate": "actual-equals-zero",
            "lane_local_requested_chunks": 0,
            "large_and_tail_require_non_container_encoding": True,
            "per_persona_allocated_bytes_cap": 768 * 2**20,
            "per_persona_payload_bytes": 740 * 2**20,
            "pptx_slides": {"inclusive_maximum": 200, "inclusive_minimum": 41},
            "profile_distribution": [
                {"bytes_each": 128 * 1024, "file_count": 32, "size_class": "small"},
                {"bytes_each": 2 * 2**20, "file_count": 16, "size_class": "medium"},
                {"bytes_each": 32 * 2**20, "file_count": 12, "size_class": "large"},
                {"bytes_each": 80 * 2**20, "file_count": 4, "size_class": "tail"},
            ],
            "projection_is_not_a_formal_variant_source_row": True,
            "scan_pdf_pages": {"inclusive_maximum": 500, "inclusive_minimum": 51},
            "suite_allocated_bytes_cap": 15 * 2**30,
            "text_pdf_pages": {"inclusive_minimum": 201, "maximum_status": "not-bound"},
            "w0_only": True,
            "xlsx_sheets": {"inclusive_maximum": 100, "inclusive_minimum": 21},
        },
        "formal_retrieval_history": {
            "eml_attachments": {"inclusive_maximum": 5, "inclusive_minimum": 0},
            "image_media_domain_ordinary_bytes": {
                "inclusive_maximum": MAX_FORMAL_ORDINARY_BYTES,
                "inclusive_minimum": 4 * 1024,
            },
            "image_media_domain_tail_bytes": {
                "inclusive_maximum": MAX_FORMAL_TAIL_BYTES,
                "inclusive_minimum": 1 * 2**20,
                "max_files_per_persona": MAX_TAIL_FILES_PER_PERSONA,
            },
            "pptx_slides": {"inclusive_maximum": 40, "inclusive_minimum": 1},
            "scan_pdf_pages": {"inclusive_maximum": 50, "inclusive_minimum": 1},
            "text_pdf_pages": {"inclusive_maximum": 72, "inclusive_minimum": 1},
            "xlsx_sheets": {"inclusive_maximum": 20, "inclusive_minimum": 1},
        },
        "lane_separation": {
            "byte_stress_reuses_only_format_encoding_and_validator_identity": True,
            "byte_stress_changes_formal_marginals": False,
            "byte_stress_counts_toward_formal_chunks": False,
            "byte_stress_counts_toward_recall": False,
        },
    }


def _safety_profile(family, variant_id):
    if family in {"md", "txt_log", "code", "structured_text", "csv_tsv", "html_eml", "ipynb"}:
        return "bounded-text-structure-v2"
    if family in {"pdf_text", "pdf_scan"}:
        return "bounded-pdf-v2"
    if family in {"docx", "xlsx", "pptx"}:
        return "bounded-ooxml-zip-v2"
    if family == "image":
        return "bounded-raster-v2"
    if family == "media":
        return "bounded-audio-midi-v2"
    if variant_id == "pcap":
        return "bounded-pcap-v2"
    if variant_id == "npz":
        return "bounded-npz-v2"
    if variant_id == "dicom-part10":
        return "bounded-dicom-v2"
    if variant_id == "ifczip":
        return "bounded-ifczip-v2"
    return "bounded-archive-v2"


def _reusable_primitive(variant_id):
    if variant_id not in _REUSABLE_V1_PRIMITIVE_VARIANTS:
        return "none"
    if variant_id in {"md", "markdown", "txt"}:
        return "v1-heading-text-encoding-primitive"
    if variant_id in {"py", "rs", "ts"}:
        return "v1-code-padding-encoding-primitive"
    if variant_id in {"pdf-text", "pdf-scan"}:
        return "v1-pdf-encoding-primitive"
    if variant_id in {"docx", "xlsx", "pptx"}:
        return "v1-deterministic-ooxml-zip-primitive"
    if variant_id == "png":
        return "v1-png-encoding-primitive"
    if variant_id == "wav":
        return "v1-wave-encoding-primitive"
    if variant_id == "pcap":
        return "v1-pcap-encoding-primitive"
    return "v1-incidental-structured-text-encoding-primitive"


def _variant_row(family, variant_id):
    metadata = dict(envelope.VARIANT_CATALOG[variant_id])
    extension = metadata["extension"]
    gate_role = metadata["gate_role"]
    is_container = (
        variant_id in {"docx", "xlsx", "pptx", "npz", "ifczip"}
        or variant_id.endswith("-zip")
        or variant_id.endswith("-ustar")
        or variant_id.endswith("-gzip")
    )
    byte_stress_encoding_eligible = (
        variant_id in {"pdf-text", "pdf-scan", "eml", "xlsx", "pptx"}
        or family in {"image", "media", "domain_binary"}
    )
    byte_stress_size_classes = []
    if byte_stress_encoding_eligible:
        byte_stress_size_classes = ["small", "medium"]
        if not is_container:
            byte_stress_size_classes.extend(("large", "tail"))
    complexity = _complexity_contract(family, variant_id, gate_role)
    return {
        "byte_contract": {
            "absolute_renderer_adapter_max_bytes": MAX_RENDERED_SOURCE_BYTES,
            "byte_distribution_profile_id": (
                "contributor-target-bytes-formula-not-bound-v2"
                if gate_role == "contract_contributor"
                else "bounded-container-bytes-v2"
                if is_container
                else "ordinary-bounded-source-bytes-v2"
            ),
            "byte_stress_encoding_eligible": byte_stress_encoding_eligible,
            "byte_stress_size_classes": byte_stress_size_classes,
            "exact_target_padding_method": "not-bound",
            "expanded_bytes_limit": (
                MAX_EXPANDED_CONTAINER_BYTES if is_container else MAX_RENDERED_SOURCE_BYTES
            ),
            "parameters_complete": False,
        },
        "complexity_contract": {
            **complexity,
            "feasibility_parameters_complete": False,
            "feasibility_rule_id": metadata["feasibility_rule_id"],
        },
        "compound_suffix_parts": extension.split("."),
        "content_media_type": _content_mime(variant_id),
        "expected_kcs_path_media_type": metadata["media_type"],
        "expected_offline_disposition": metadata["expected_offline_disposition"],
        "family": family,
        "filename_extension": extension,
        "gate_role": gate_role,
        "renderer": {
            "implementation_status": "not-implemented-for-v2",
            "implemented": False,
            "renderer_id": metadata["renderer_id"],
            "renderer_profile_id": complexity["complexity_profile_id"],
            "renderer_schema_version": metadata["renderer_schema_version"],
            "reusable_encoding_primitive_id": _reusable_primitive(variant_id),
        },
        "safety_profile_id": _safety_profile(family, variant_id),
        "search_contract": {
            "contract_chunk_denominator_eligible": gate_role == "contract_contributor",
            "incidental_cap_eligible": gate_role == "incidental_searchable",
            "local_prepare_route": metadata["expected_offline_disposition"],
            "observed_chunk_gate": (
                "actual-equals-assigned-quota"
                if gate_role == "contract_contributor"
                else "actual-within-source-and-wave-cap"
                if gate_role == "incidental_searchable"
                else "actual-equals-zero"
            ),
            "requested_chunk_rule": (
                "integer-1-through-70"
                if gate_role == "contract_contributor"
                else "exact-zero"
            ),
        },
        "validator": {
            "implementation_status": "not-implemented-for-v2",
            "implemented": False,
            "magic_and_structure_policy_id": _safety_profile(family, variant_id),
            "validator_id": metadata["validator_id"],
            "validator_profile_id": f"{variant_id}-standalone-validation-v2",
            "validator_schema_version": metadata["validator_schema_version"],
        },
        "variant_id": variant_id,
    }


def _marginal_rows():
    rows = []
    for persona_id in envelope.PERSONA_IDS:
        profile_counts = {
            profile: envelope.variant_counts(persona_id, profile)
            for profile in PROFILE_ORDER
        }
        for family in envelope.FORMAT_KEYS:
            full_by_id = {
                row["variant_id"]: row for row in profile_counts["full"][family]
            }
            pilot_by_id = {
                row["variant_id"]: row for row in profile_counts["pilot"][family]
            }
            tiny_by_id = {
                row["variant_id"]: row
                for row in profile_counts["tiny-smoke"][family]
            }
            for variant_id in sorted(full_by_id, key=lambda value: value.encode("ascii")):
                full_row = full_by_id[variant_id]
                pilot_count = pilot_by_id[variant_id]["count"]
                full_count = full_row["count"]
                rows.append({
                    "family": family,
                    "full_count": full_count,
                    "full_minus_pilot_count": full_count - pilot_count,
                    "persona_id": persona_id,
                    "pilot_count": pilot_count,
                    "ratio_pct": full_row["ratio_pct"],
                    "tiny_smoke_count": tiny_by_id[variant_id]["count"],
                    "variant_id": variant_id,
                })
    return rows


def _gate_role_totals(marginal_rows, count_field):
    family_by_variant = _variant_families()
    totals = {
        "contract_contributor": 0,
        "incidental_searchable": 0,
        "raw_only": 0,
    }
    for row in marginal_rows:
        metadata = envelope.VARIANT_CATALOG[row["variant_id"]]
        if family_by_variant[row["variant_id"]] != row["family"]:
            raise PersonaV2VariantCatalogError("marginal family join drifted")
        totals[metadata["gate_role"]] += row[count_field]
    return totals


def _canonical_catalog_value():
    family_by_variant = _variant_families()
    variant_rows = [
        _variant_row(family, variant_id)
        for family in envelope.FORMAT_KEYS
        for variant_id in sorted(
            (
                candidate
                for candidate, candidate_family in family_by_variant.items()
                if candidate_family == family
            ),
            key=lambda value: value.encode("ascii"),
        )
    ]
    marginal_rows = _marginal_rows()
    full_active = sum(1 for row in marginal_rows if row["full_count"] > 0)
    if len(variant_rows) != 71 or len(marginal_rows) != 566 or full_active != 541:
        raise PersonaV2VariantCatalogError("variant catalog shape drifted")
    suite_counts = {
        "full": _gate_role_totals(marginal_rows, "full_count"),
        "pilot": _gate_role_totals(marginal_rows, "pilot_count"),
        "tiny-smoke": _gate_role_totals(marginal_rows, "tiny_smoke_count"),
    }
    expected_counts = {
        "full": {
            "contract_contributor": 67_296,
            "incidental_searchable": 60_414,
            "raw_only": 75_290,
        },
        "pilot": {
            "contract_contributor": 6_731,
            "incidental_searchable": 6_040,
            "raw_only": 7_529,
        },
        "tiny-smoke": {
            "contract_contributor": 1_324,
            "incidental_searchable": 1_108,
            "raw_only": 1_568,
        },
    }
    if suite_counts != expected_counts:
        raise PersonaV2VariantCatalogError("variant gate-role totals drifted")
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "filesystem_writer_available": False,
            "formal_capacity_gate_satisfied": False,
            "history_executor_available": False,
            "kcs_execution_available": False,
            "query_instances_rendered": False,
            "query_spec_hashed": False,
            "renderer_available": False,
            "validator_available": False,
        },
        "canonical_limits": {
            "exact_marginal_rows": 566,
            "exact_variant_rows": 71,
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_scope": (
            "complete-identity-and-marginal-catalog-with-initial-feasibility-design-only-"
            "renderers-and-validators-not-implemented-not-g0"
        ),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_bindings": input_bindings.build_upstream_bindings(),
        "kcs_media_policy": {
            "cross_language_production_tables_verified": False,
            "policy_id": "current-offline-path-media-type-expectation-v2",
            "policy_schema_version": 2,
        },
        "lane_contracts": _lane_contracts(),
        "orders": {
            "family": list(envelope.FORMAT_KEYS),
            "persona": list(envelope.PERSONA_IDS),
            "profile": list(PROFILE_ORDER),
            "variant_within_family": "ascending-ASCII-bytes",
        },
        "persona_variant_marginals": marginal_rows,
        "remaining_blockers": [
            "v2-id-free-content-template-contract-not-bound",
            "quota-dependent-target-complexity-and-bytes-formula-not-bound",
            "renderer-dispatch-not-implemented-for-all-71-variants",
            "standalone-validator-not-implemented-for-all-71-variants",
            "content-mime-versus-production-path-mime-cross-language-golden-missing",
            "incidental-source-and-wave-upper-policy-not-bound",
            "archive-image-media-dicom-safety-parameters-not-runtime-validated",
            "bounded-framed-loader-not-implemented",
            "intent-refinement-solver-and-resource-caps-not-calibrated",
        ],
        "renderer_validator_implementation_complete": False,
        "source_level_feasibility_complete": False,
        "suite_gate_role_counts": suite_counts,
        "variant_catalog_complete": False,
        "variant_marginals_complete": True,
        "variant_rows": variant_rows,
        "variant_rows_complete": True,
    }


def build_variant_catalog():
    """Return a detached catalog completion sidecar with no execution authority."""

    return copy.deepcopy(_canonical_catalog_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 variant catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2VariantCatalogError(str(error)) from None


def validate_variant_catalog(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_variant_catalog,
            label="persona v2 variant catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2VariantCatalogError(str(error)) from None


def variant_catalog_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_variant_catalog,
            label="persona v2 variant catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2VariantCatalogError(str(error)) from None


def require_complete_variant_catalog():
    raise PersonaV2VariantCatalogError(
        "variant identities and marginals are exact, but source-level feasibility, "
        "v2 renderers, standalone validators, and production media-policy golden "
        "remain absent"
    )
