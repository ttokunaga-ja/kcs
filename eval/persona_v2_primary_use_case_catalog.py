"""Non-authorizing primary-use-case catalog for persona-PC fidelity v2.

The proposal owns one primary use case for each of the twenty independent
persona-PCs.  This sidecar preserves the proposal wording, normalizes its
format terms to the frozen physical-family vocabulary, and joins every row to
the exact persona role and representative primary scope already owned by the
envelope/topology artifacts.

This is design input only.  It contains no rendered query text, source or
final identifiers, absolute paths, source-instance membership, solver result,
filesystem mutation, evaluation result, or G0 authority.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_primary_use_case_catalog_validator as independent
    from . import persona_v2_topology as topology
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_primary_use_case_catalog_validator as independent
    import persona_v2_topology as topology


ARTIFACT_SCHEMA = "kio.persona.pc-primary-use-case-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-primary-use-case-catalog"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2
MAX_CATALOG_BYTES = 256 * 1024

PERSONA_IDS = tuple(f"p{index:02d}" for index in range(1, 21))

LIFECYCLE_CAPABILITY_ALLOWLIST = (
    "edit",
    "rename",
    "move",
    "derive",
    "duplicate",
    "archive",
    "restore",
    "purge",
)

QUERY_STRATUM_ALLOWLIST = (
    "current-fact",
    "cross-format-fact",
    "old-wording",
    "rename-move",
    "deleted",
    "restored",
    "purged-negative",
)

FORMAT_TERM_TO_FAMILY = {
    "md": "md",
    "txt": "txt_log",
    "txt-log": "txt_log",
    "code": "code",
    "structured": "structured_text",
    "sql": "structured_text",
    "csv": "csv_tsv",
    "eml": "html_eml",
    "ipynb": "ipynb",
    "pdf": "pdf_text",
    "text-pdf": "pdf_text",
    "scan-pdf": "pdf_scan",
    "docx": "docx",
    "xlsx": "xlsx",
    "pptx": "pptx",
    "image": "image",
    "media": "media",
    "npz": "domain_binary",
    "domain": "domain_binary",
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_evaluation_results_attested",
        "actual_filesystem_scope_attested",
        "authorizes_compiled_history_plan",
        "authorizes_evaluation_target_resolution",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_query_rendering",
        "authorizes_solver_execution",
        "authorizes_source_instance_matching",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "query_instances_rendered",
        "source_instance_matching_available",
    }
)

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-envelope": (
        71_979,
        "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7",
    ),
    "persona-v2-topology": (
        134_195,
        "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a",
    ),
}


class PersonaV2PrimaryUseCaseCatalogError(ValueError):
    """Raised when the primary-use-case catalog drifts or gains authority."""


def _fail(message):
    raise PersonaV2PrimaryUseCaseCatalogError(message)


# persona, use case, trigger, desired outcome, proposal format terms,
# lifecycle capabilities, proposal evaluation focus, query strata.
_USE_CASE_ROWS = (
    (
        "p01",
        "uc01-incident-design-rationale",
        "production defect",
        "修正案と設計根拠を回収",
        ("md", "code", "structured"),
        ("edit", "rename", "derive"),
        "M3-1 current + M3-2 rename",
        ("current-fact", "rename-move"),
    ),
    (
        "p02",
        "uc02-production-incident-reconstruction",
        "alert escalation",
        "logs/runbook/postmortemで原因を再構成",
        ("txt-log", "md", "structured", "code"),
        ("edit", "archive", "restore"),
        "M3-2 old wording + M3-3 restored",
        ("old-wording", "restored"),
    ),
    (
        "p03",
        "uc03-control-evidence-package",
        "auditor request",
        "controlと証跡版をpackage化",
        ("structured", "csv", "pdf", "docx", "eml"),
        ("move", "archive", "purge"),
        "M3-1 evidence + M3-3 deleted/purged",
        ("current-fact", "deleted", "purged-negative"),
    ),
    (
        "p04",
        "uc04-experiment-reproduction",
        "model regression",
        "notebook/config/resultを再現",
        ("code", "ipynb", "csv", "npz", "pdf"),
        ("edit", "derive", "duplicate"),
        "M3-1 cross-format + M3-2 revision",
        ("cross-format-fact", "old-wording"),
    ),
    (
        "p05",
        "uc05-kpi-lineage-reconciliation",
        "KPI discrepancy",
        "forecastとsource lineageを照合",
        ("csv", "xlsx", "structured", "sql"),
        ("edit", "duplicate", "archive"),
        "M3-1 current + M3-2 history",
        ("current-fact", "old-wording"),
    ),
    (
        "p06",
        "uc06-assay-result-trace",
        "assay outlier",
        "protocol/cohort/run/resultを追跡",
        ("csv", "pdf", "docx", "image", "domain"),
        ("edit", "derive", "archive"),
        "M3-1 evidence chain + M3-2 history",
        ("current-fact", "old-wording"),
    ),
    (
        "p07",
        "uc07-archive-citation-recovery",
        "manuscript claim",
        "scan/OCR/notesから引用根拠を復元",
        ("scan-pdf", "text-pdf", "txt", "docx"),
        ("edit", "move", "restore"),
        "M3-2 move + M3-3 restored",
        ("rename-move", "restored"),
    ),
    (
        "p08",
        "uc08-product-decision-reconstruction",
        "roadmap dispute",
        "PRD/deck/feedbackの決定経緯を再構成",
        ("md", "docx", "pptx", "pdf", "eml"),
        ("edit", "rename", "duplicate"),
        "M3-1 cross-format + M3-2 rename",
        ("cross-format-fact", "rename-move"),
    ),
    (
        "p09",
        "uc09-user-study-finding-trace",
        "design challenge",
        "transcript/recording/noteをfindingへ結ぶ",
        ("txt", "media", "image", "docx", "pdf"),
        ("edit", "derive", "archive"),
        "M3-1 cross-format + M3-2 wording",
        ("cross-format-fact", "old-wording"),
    ),
    (
        "p10",
        "uc10-client-recommendation-evidence",
        "partner review",
        "workbook/deck/sourceの根拠鎖を提出",
        ("xlsx", "pptx", "pdf", "docx", "csv"),
        ("edit", "duplicate", "move"),
        "M3-1 cross-format + M3-2 move",
        ("cross-format-fact", "rename-move"),
    ),
    (
        "p11",
        "uc11-account-commitment-context",
        "renewal negotiation",
        "mail/proposal/action planの約束を確認",
        ("eml", "pdf", "docx", "pptx"),
        ("edit", "rename", "archive"),
        "M3-1 current + M3-2 rename/history",
        ("current-fact", "rename-move", "old-wording"),
    ),
    (
        "p12",
        "uc12-escalation-timeline",
        "customer escalation",
        "case/log/runbookから時系列を構築",
        ("txt-log", "md", "structured", "csv", "eml"),
        ("edit", "move", "restore"),
        "M3-2 move + M3-3 restored",
        ("rename-move", "restored"),
    ),
    (
        "p13",
        "uc13-legal-hold-matter-recovery",
        "hold/e-discovery request",
        "privileged matter evidenceを保全",
        ("pdf", "docx", "eml", "scan-pdf"),
        ("edit", "archive", "purge"),
        "M3-2 history + M3-3 deleted/purged",
        ("old-wording", "deleted", "purged-negative"),
    ),
    (
        "p14",
        "uc14-close-variance-reconciliation",
        "month close variance",
        "ERP export/workbook/evidenceを照合",
        ("xlsx", "csv", "pdf", "docx"),
        ("edit", "duplicate", "archive"),
        "M3-1 current + M3-2 history",
        ("current-fact", "old-wording"),
    ),
    (
        "p15",
        "uc15-candidate-decision-audit",
        "complaint/re-open",
        "interview/mail/ATS記録を監査",
        ("pdf", "docx", "eml", "csv"),
        ("edit", "move", "purge"),
        "M3-2 move + M3-3 deleted/purged",
        ("rename-move", "deleted", "purged-negative"),
    ),
    (
        "p16",
        "uc16-protocol-deviation-evidence",
        "clinical review",
        "protocol/case/export/imageを結合",
        ("text-pdf", "scan-pdf", "csv", "docx", "xlsx", "domain"),
        ("edit", "archive", "restore"),
        "M3-1 cross-format + M3-3 restored",
        ("cross-format-fact", "restored"),
    ),
    (
        "p17",
        "uc17-drawing-revision-impact",
        "field change/RFI",
        "drawing revisionと工程影響を追跡",
        ("pdf", "image", "domain", "xlsx", "docx"),
        ("edit", "rename", "move"),
        "M3-1 evidence + M3-2 rename/move",
        ("current-fact", "rename-move"),
    ),
    (
        "p18",
        "uc18-capa-root-cause-trace",
        "nonconformance",
        "CAPA/log/inspection evidenceを追跡",
        ("pdf", "csv", "txt-log", "xlsx", "docx", "domain"),
        ("edit", "archive", "purge"),
        "M3-2 history + M3-3 purged",
        ("old-wording", "purged-negative"),
    ),
    (
        "p19",
        "uc19-course-revision-recovery",
        "next-term revision",
        "lesson/deck/LMS artifactを再利用",
        ("pdf", "docx", "pptx", "image", "media"),
        ("edit", "duplicate", "restore"),
        "M3-1 cross-format + M3-3 restored",
        ("cross-format-fact", "restored"),
    ),
    (
        "p20",
        "uc20-investigation-claim-verification",
        "tip/FOIA drop",
        "mail/document/transcriptでclaimを検証",
        ("txt", "pdf", "eml", "scan-pdf", "image", "media"),
        ("edit", "move", "purge"),
        "M3-1 evidence + M3-3 deleted/purged",
        ("current-fact", "deleted", "purged-negative"),
    ),
)


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        _fail(f"{label} authority must be non-empty and all false")


def _dependency_binding(name, role, value, *, canonical, validate):
    validate(value)
    _require_negative_authority(value, label=name)
    raw = canonical(value)
    actual = (len(raw), hashlib.sha256(raw).hexdigest())
    if actual != EXPECTED_DEPENDENCY_PINS[name]:
        _fail(f"{name} differs from its frozen dependency pin")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": actual[0],
        "dependency_role": role,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "sha256": actual[1],
    }


def _unique_in_order(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _use_case_row(authored, *, envelope_by_persona, topology_by_persona):
    (
        persona_id,
        primary_use_case_id,
        trigger,
        desired_outcome,
        proposal_format_terms,
        lifecycle_capabilities,
        proposal_evaluation_focus,
        query_strata,
    ) = authored
    if persona_id not in envelope_by_persona or persona_id not in topology_by_persona:
        _fail("use-case persona is absent from an upstream marginal")
    envelope_row = envelope_by_persona[persona_id]
    topology_row = topology_by_persona[persona_id]
    if envelope_row["role"] != topology_row["role"]:
        _fail(f"{persona_id} role differs between envelope and topology")
    representative_path = envelope_row["representative_primary_scope"]
    matching_scopes = [
        row
        for row in topology_row["scopes"]
        if row["relative_path"] == representative_path
    ]
    if len(matching_scopes) != 1 or matching_scopes[0]["kind"] != "primary":
        _fail(f"{persona_id} representative primary scope does not exactly resolve")
    scope = matching_scopes[0]

    family_ids = _unique_in_order(
        [FORMAT_TERM_TO_FAMILY[term] for term in proposal_format_terms]
    )
    family_join = []
    for family_id in family_ids:
        ratio = envelope_row["format_percentages"][family_id]
        count = envelope.family_counts(persona_id, "full")[family_id]
        if ratio <= 0 or count <= 0:
            _fail(f"{persona_id}/{family_id} required family has no physical marginal")
        family_join.append(
            {
                "family_id": family_id,
                "full_physical_file_count": count,
                "full_physical_ratio_pct": ratio,
            }
        )

    if any(item not in LIFECYCLE_CAPABILITY_ALLOWLIST for item in lifecycle_capabilities):
        _fail(f"{persona_id} uses an unknown lifecycle capability")
    if any(item not in QUERY_STRATUM_ALLOWLIST for item in query_strata):
        _fail(f"{persona_id} uses an unknown query stratum")

    return {
        "data_classification": "synthetic-non-pii",
        "desired_outcome": desired_outcome,
        "persona_id": persona_id,
        "persona_role": envelope_row["role"],
        "primary_use_case_id": primary_use_case_id,
        "proposal_evaluation_focus": proposal_evaluation_focus,
        "proposal_format_terms": list(proposal_format_terms),
        "representative_functional_slot": scope["functional_slot"],
        "representative_path_interpretation": (
            "exact-persona-root-relative-envelope-representative-primary-scope"
        ),
        "representative_relative_path": representative_path,
        "required_families": family_ids,
        "required_family_marginal_join": family_join,
        "required_lifecycle_capabilities": list(lifecycle_capabilities),
        "required_query_strata": list(query_strata),
        "required_scope_role": "primary",
        "trigger": trigger,
    }


@functools.lru_cache(maxsize=1)
def _canonical_catalog_value():
    envelope_value = envelope.build_envelope_contract()
    topology_value = topology.build_topology_contract()
    input_bindings = [
        _dependency_binding(
            "persona-v2-envelope",
            "persona-role-and-physical-family-marginal-owner",
            envelope_value,
            canonical=envelope.canonical_json_bytes,
            validate=envelope.validate_envelope_contract,
        ),
        _dependency_binding(
            "persona-v2-topology",
            "exact-representative-relative-scope-owner",
            topology_value,
            canonical=topology.canonical_json_bytes,
            validate=topology.validate_topology_contract,
        ),
    ]
    envelope_by_persona = {
        row["persona_id"]: row for row in envelope_value["personas"]
    }
    topology_by_persona = {
        row["persona_id"]: row for row in topology_value["personas"]
    }
    rows = [
        _use_case_row(
            authored,
            envelope_by_persona=envelope_by_persona,
            topology_by_persona=topology_by_persona,
        )
        for authored in _USE_CASE_ROWS
    ]
    if [row["persona_id"] for row in rows] != list(PERSONA_IDS):
        _fail("primary use cases must follow the exact twenty-persona order")
    if len({row["primary_use_case_id"] for row in rows}) != len(PERSONA_IDS):
        _fail("primary use case IDs must be one-to-one with personas")

    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_integer_bits": artifact_common.MAX_INTEGER_BITS,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_twenty_primary_use_cases_authored": True,
            "compiled_history_plan_bound": False,
            "evaluation_target_resolution_bound": False,
            "family_marginal_positive_join_complete": True,
            "one_to_one_persona_use_case_mapping_complete": True,
            "query_instances_rendered": False,
            "representative_primary_scope_join_complete": True,
            "source_instance_membership_bound": False,
        },
        "completion_scope": (
            "primary-use-case-design-and-upstream-marginal-join-only-no-source-"
            "instance-no-rendered-query-no-evaluation-no-write-no-g0"
        ),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "policy": {
            "format_term_to_family": [
                {"family_id": family_id, "proposal_format_term": term}
                for term, family_id in FORMAT_TERM_TO_FAMILY.items()
            ],
            "lifecycle_capability_allowlist": list(
                LIFECYCLE_CAPABILITY_ALLOWLIST
            ),
            "one_primary_use_case_per_persona": True,
            "primary_use_case_reuse_across_personas_allowed": False,
            "proposal_ellipsis_resolution": (
                "proposal scope ellipses are shorthand only; each row binds the "
                "exact envelope representative_primary_scope and that path must "
                "resolve to one topology scope whose kind is primary"
            ),
            "query_stratum_allowlist": list(QUERY_STRATUM_ALLOWLIST),
            "required_family_semantics": (
                "minimum-positive-use-case-witness-families-not-a-complete-physical-mix"
            ),
            "scope_path_kind": "persona-root-relative-never-absolute",
            "synthetic_data_only": True,
            "synthetic_personal_data_present": False,
            "use_case_status": (
                "authored-benchmark-stress-design-not-observed-user-behavior"
            ),
        },
        "primary_use_cases": rows,
        "remaining_blockers": [
            "source-instance-membership-not-bound",
            "lifecycle-capabilities-not-matched-to-anonymous-capability-instances",
            "query-strata-not-resolved-to-rendered-query-instances",
            "compiled-history-plan-not-bound",
            "evaluation-target-resolution-not-bound",
            "external-frame-header-schema-dispatcher-not-implemented",
            "g0-contract-not-frozen",
        ],
        "summary": {
            "persona_count": len(rows),
            "primary_use_case_count": len(rows),
            "unique_persona_role_count": len({row["persona_role"] for row in rows}),
            "unique_primary_use_case_count": len(
                {row["primary_use_case_id"] for row in rows}
            ),
        },
    }


def build_primary_use_case_catalog():
    """Return a detached deterministic twenty-row catalog."""

    return copy.deepcopy(_canonical_catalog_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 primary use case catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2PrimaryUseCaseCatalogError(str(error)) from None


def validate_primary_use_case_catalog(value):
    """Validate through the builder-independent semantic validator."""

    try:
        return independent.validate_primary_use_case_catalog(
            value,
            envelope_value=envelope.build_envelope_contract(),
            topology_value=topology.build_topology_contract(),
        )
    except independent.PersonaV2PrimaryUseCaseCatalogValidationError as error:
        raise PersonaV2PrimaryUseCaseCatalogError(str(error)) from None


def primary_use_case_catalog_sha256(value=None):
    if value is None:
        value = build_primary_use_case_catalog()
    validate_primary_use_case_catalog(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
