"""Builder-independent validation for the persona-PC primary-use-case catalog.

This module intentionally does not import the catalog producer.  It carries an
independent copy of the twenty-row proposal contract, authenticates the frozen
envelope/topology inputs, recomputes every role/family/scope join, and rejects
authority or later-layer identifiers.  Caller-owned values are validated from
detached snapshots and re-authenticated on return.
"""

from __future__ import annotations

import copy
import hashlib
import re

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_topology as topology
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_topology as topology


ARTIFACT_SCHEMA = "kio.persona.pc-primary-use-case-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-primary-use-case-catalog"
MAX_CATALOG_BYTES = 256 * 1024
MAX_DEPENDENCY_BYTES = 512 * 1024

# Installed with the deterministic producer body; never embedded in that body.
EXPECTED_CATALOG_CANONICAL_BYTES = 30_008
EXPECTED_CATALOG_SHA256 = (
    "73939fc66fc234b5a8b3bfb8e6362b12807015204fd49253dde870a7f29528ed"
)

EXPECTED_PERSONA_IDS = tuple(f"p{index:02d}" for index in range(1, 21))
EXPECTED_FAMILIES = (
    "md",
    "txt_log",
    "code",
    "structured_text",
    "csv_tsv",
    "html_eml",
    "ipynb",
    "pdf_text",
    "pdf_scan",
    "docx",
    "xlsx",
    "pptx",
    "image",
    "media",
    "domain_binary",
)
EXPECTED_LIFECYCLE_ALLOWLIST = (
    "edit",
    "rename",
    "move",
    "derive",
    "duplicate",
    "archive",
    "restore",
    "purge",
)
EXPECTED_QUERY_STRATUM_ALLOWLIST = (
    "current-fact",
    "cross-format-fact",
    "old-wording",
    "rename-move",
    "deleted",
    "restored",
    "purged-negative",
)
EXPECTED_FORMAT_TERM_ROWS = (
    ("md", "md"),
    ("txt", "txt_log"),
    ("txt-log", "txt_log"),
    ("code", "code"),
    ("structured", "structured_text"),
    ("sql", "structured_text"),
    ("csv", "csv_tsv"),
    ("eml", "html_eml"),
    ("ipynb", "ipynb"),
    ("pdf", "pdf_text"),
    ("text-pdf", "pdf_text"),
    ("scan-pdf", "pdf_scan"),
    ("docx", "docx"),
    ("xlsx", "xlsx"),
    ("pptx", "pptx"),
    ("image", "image"),
    ("media", "media"),
    ("npz", "domain_binary"),
    ("domain", "domain_binary"),
)
EXPECTED_FORMAT_TERM_TO_FAMILY = dict(EXPECTED_FORMAT_TERM_ROWS)

DEPENDENCY_PINS = {
    "persona-v2-envelope": (
        "persona-pc-v2-envelope",
        "kio.persona.pc-envelope/v2",
        2,
        71_979,
        "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7",
        "persona-role-and-physical-family-marginal-owner",
    ),
    "persona-v2-topology": (
        "persona-pc-v2-topology",
        "kio.persona.pc-topology/v2",
        2,
        134_195,
        "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a",
        "exact-representative-relative-scope-owner",
    ),
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

TOP_LEVEL_KEYS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "input_binding_order",
        "input_bindings",
        "policy",
        "primary_use_cases",
        "remaining_blockers",
        "summary",
    }
)

ROW_KEYS = frozenset(
    {
        "data_classification",
        "desired_outcome",
        "persona_id",
        "persona_role",
        "primary_use_case_id",
        "proposal_evaluation_focus",
        "proposal_format_terms",
        "representative_functional_slot",
        "representative_path_interpretation",
        "representative_relative_path",
        "required_families",
        "required_family_marginal_join",
        "required_lifecycle_capabilities",
        "required_query_strata",
        "required_scope_role",
        "trigger",
    }
)

FORBIDDEN_KEYS = frozenset(
    {
        "absolute_path",
        "chunk_id",
        "final_id",
        "final_materialization_id",
        "final_source_id",
        "materialization_id",
        "query_id",
        "query_text",
        "rendered_query",
        "rendered_query_text",
        "source_id",
        "source_ids",
    }
)

EXPECTED_REMAINING_BLOCKERS = (
    "source-instance-membership-not-bound",
    "lifecycle-capabilities-not-matched-to-anonymous-capability-instances",
    "query-strata-not-resolved-to-rendered-query-instances",
    "compiled-history-plan-not-bound",
    "evaluation-target-resolution-not-bound",
    "external-frame-header-schema-dispatcher-not-implemented",
    "g0-contract-not-frozen",
)


class PersonaV2PrimaryUseCaseCatalogValidationError(ValueError):
    """Raised when an independently validated use-case catalog is invalid."""


def _fail(message):
    raise PersonaV2PrimaryUseCaseCatalogValidationError(message)


# Independent transcription of proposal section 3.3.  Fields match the
# producer's authored tuple but this module never calls or imports its builder.
_EXPECTED_ROWS = (
    ("p01", "uc01-incident-design-rationale", "production defect", "修正案と設計根拠を回収", ("md", "code", "structured"), ("edit", "rename", "derive"), "M3-1 current + M3-2 rename", ("current-fact", "rename-move")),
    ("p02", "uc02-production-incident-reconstruction", "alert escalation", "logs/runbook/postmortemで原因を再構成", ("txt-log", "md", "structured", "code"), ("edit", "archive", "restore"), "M3-2 old wording + M3-3 restored", ("old-wording", "restored")),
    ("p03", "uc03-control-evidence-package", "auditor request", "controlと証跡版をpackage化", ("structured", "csv", "pdf", "docx", "eml"), ("move", "archive", "purge"), "M3-1 evidence + M3-3 deleted/purged", ("current-fact", "deleted", "purged-negative")),
    ("p04", "uc04-experiment-reproduction", "model regression", "notebook/config/resultを再現", ("code", "ipynb", "csv", "npz", "pdf"), ("edit", "derive", "duplicate"), "M3-1 cross-format + M3-2 revision", ("cross-format-fact", "old-wording")),
    ("p05", "uc05-kpi-lineage-reconciliation", "KPI discrepancy", "forecastとsource lineageを照合", ("csv", "xlsx", "structured", "sql"), ("edit", "duplicate", "archive"), "M3-1 current + M3-2 history", ("current-fact", "old-wording")),
    ("p06", "uc06-assay-result-trace", "assay outlier", "protocol/cohort/run/resultを追跡", ("csv", "pdf", "docx", "image", "domain"), ("edit", "derive", "archive"), "M3-1 evidence chain + M3-2 history", ("current-fact", "old-wording")),
    ("p07", "uc07-archive-citation-recovery", "manuscript claim", "scan/OCR/notesから引用根拠を復元", ("scan-pdf", "text-pdf", "txt", "docx"), ("edit", "move", "restore"), "M3-2 move + M3-3 restored", ("rename-move", "restored")),
    ("p08", "uc08-product-decision-reconstruction", "roadmap dispute", "PRD/deck/feedbackの決定経緯を再構成", ("md", "docx", "pptx", "pdf", "eml"), ("edit", "rename", "duplicate"), "M3-1 cross-format + M3-2 rename", ("cross-format-fact", "rename-move")),
    ("p09", "uc09-user-study-finding-trace", "design challenge", "transcript/recording/noteをfindingへ結ぶ", ("txt", "media", "image", "docx", "pdf"), ("edit", "derive", "archive"), "M3-1 cross-format + M3-2 wording", ("cross-format-fact", "old-wording")),
    ("p10", "uc10-client-recommendation-evidence", "partner review", "workbook/deck/sourceの根拠鎖を提出", ("xlsx", "pptx", "pdf", "docx", "csv"), ("edit", "duplicate", "move"), "M3-1 cross-format + M3-2 move", ("cross-format-fact", "rename-move")),
    ("p11", "uc11-account-commitment-context", "renewal negotiation", "mail/proposal/action planの約束を確認", ("eml", "pdf", "docx", "pptx"), ("edit", "rename", "archive"), "M3-1 current + M3-2 rename/history", ("current-fact", "rename-move", "old-wording")),
    ("p12", "uc12-escalation-timeline", "customer escalation", "case/log/runbookから時系列を構築", ("txt-log", "md", "structured", "csv", "eml"), ("edit", "move", "restore"), "M3-2 move + M3-3 restored", ("rename-move", "restored")),
    ("p13", "uc13-legal-hold-matter-recovery", "hold/e-discovery request", "privileged matter evidenceを保全", ("pdf", "docx", "eml", "scan-pdf"), ("edit", "archive", "purge"), "M3-2 history + M3-3 deleted/purged", ("old-wording", "deleted", "purged-negative")),
    ("p14", "uc14-close-variance-reconciliation", "month close variance", "ERP export/workbook/evidenceを照合", ("xlsx", "csv", "pdf", "docx"), ("edit", "duplicate", "archive"), "M3-1 current + M3-2 history", ("current-fact", "old-wording")),
    ("p15", "uc15-candidate-decision-audit", "complaint/re-open", "interview/mail/ATS記録を監査", ("pdf", "docx", "eml", "csv"), ("edit", "move", "purge"), "M3-2 move + M3-3 deleted/purged", ("rename-move", "deleted", "purged-negative")),
    ("p16", "uc16-protocol-deviation-evidence", "clinical review", "protocol/case/export/imageを結合", ("text-pdf", "scan-pdf", "csv", "docx", "xlsx", "domain"), ("edit", "archive", "restore"), "M3-1 cross-format + M3-3 restored", ("cross-format-fact", "restored")),
    ("p17", "uc17-drawing-revision-impact", "field change/RFI", "drawing revisionと工程影響を追跡", ("pdf", "image", "domain", "xlsx", "docx"), ("edit", "rename", "move"), "M3-1 evidence + M3-2 rename/move", ("current-fact", "rename-move")),
    ("p18", "uc18-capa-root-cause-trace", "nonconformance", "CAPA/log/inspection evidenceを追跡", ("pdf", "csv", "txt-log", "xlsx", "docx", "domain"), ("edit", "archive", "purge"), "M3-2 history + M3-3 purged", ("old-wording", "purged-negative")),
    ("p19", "uc19-course-revision-recovery", "next-term revision", "lesson/deck/LMS artifactを再利用", ("pdf", "docx", "pptx", "image", "media"), ("edit", "duplicate", "restore"), "M3-1 cross-format + M3-3 restored", ("cross-format-fact", "restored")),
    ("p20", "uc20-investigation-claim-verification", "tip/FOIA drop", "mail/document/transcriptでclaimを検証", ("txt", "pdf", "eml", "scan-pdf", "image", "media"), ("edit", "move", "purge"), "M3-1 evidence + M3-3 deleted/purged", ("current-fact", "deleted", "purged-negative")),
)


def _canonical(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _exact_keys(value, expected, *, label):
    if type(value) is not dict or set(value) != set(expected):
        _fail(f"{label} keys drifted")


def _require_negative_authority(value, *, label, exact_fields=None):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority:
        _fail(f"{label} authority must be a non-empty object")
    if exact_fields is not None and set(authority) != set(exact_fields):
        _fail(f"{label} authority fields drifted")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail(f"{label} authority must be all false")


def _dependency_binding(name, role, value, *, canonical, validate):
    try:
        validate(value)
    except Exception as error:
        _fail(f"{name} dependency validation failed: {type(error).__name__}")
    _require_negative_authority(value, label=name)
    raw = canonical(value)
    expected_kind, expected_schema, expected_version, size, digest, expected_role = (
        DEPENDENCY_PINS[name]
    )
    if role != expected_role or len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        _fail(f"{name} dependency pin or role drifted")
    if (
        value.get("artifact_kind") != expected_kind
        or value.get("artifact_schema") != expected_schema
        or value.get("artifact_schema_version") != expected_version
        or value.get("fixture_id") != "kio-persona-pc-v2"
        or value.get("fixture_schema_version") != 2
    ):
        _fail(f"{name} dependency identity drifted")
    return {
        "artifact_kind": expected_kind,
        "artifact_schema": expected_schema,
        "artifact_schema_version": expected_version,
        "canonical_bytes": size,
        "dependency_role": role,
        "fixture_id": "kio-persona-pc-v2",
        "fixture_schema_version": 2,
        "name": name,
        "sha256": digest,
    }


def _unique_in_order(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _expected_use_case_rows(envelope_value, topology_value):
    envelope_by_persona = {
        row["persona_id"]: row for row in envelope_value["personas"]
    }
    topology_by_persona = {
        row["persona_id"]: row for row in topology_value["personas"]
    }
    rows = []
    for authored in _EXPECTED_ROWS:
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
        envelope_row = envelope_by_persona.get(persona_id)
        topology_row = topology_by_persona.get(persona_id)
        if type(envelope_row) is not dict or type(topology_row) is not dict:
            _fail("expected persona missing from dependency")
        if envelope_row["role"] != topology_row["role"]:
            _fail(f"{persona_id} dependency role join failed")
        representative_path = envelope_row["representative_primary_scope"]
        matching = [
            scope
            for scope in topology_row["scopes"]
            if scope["relative_path"] == representative_path
        ]
        if len(matching) != 1 or matching[0]["kind"] != "primary":
            _fail(f"{persona_id} dependency topology join failed")
        scope = matching[0]
        family_ids = _unique_in_order(
            [EXPECTED_FORMAT_TERM_TO_FAMILY[term] for term in proposal_format_terms]
        )
        family_join = []
        for family_id in family_ids:
            ratio = envelope_row["format_percentages"][family_id]
            numerator = envelope_row["full_raw_files"] * ratio
            if ratio <= 0 or numerator <= 0 or numerator % 100:
                _fail(f"{persona_id}/{family_id} physical marginal is not positive exact")
            family_join.append(
                {
                    "family_id": family_id,
                    "full_physical_file_count": numerator // 100,
                    "full_physical_ratio_pct": ratio,
                }
            )
        rows.append(
            {
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
        )
    return rows


def _assert_no_forbidden_keys(value):
    if type(value) is list:
        for item in value:
            _assert_no_forbidden_keys(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in FORBIDDEN_KEYS or key.startswith("final_"):
            _fail(f"later-layer identifier field is forbidden: {key}")
        _assert_no_forbidden_keys(item)


def _validate_rows(value, expected_rows, envelope_value, topology_value):
    rows = value["primary_use_cases"]
    if type(rows) is not list or rows != expected_rows:
        _fail("twenty-row proposal transcription or upstream join drifted")
    if [row["persona_id"] for row in rows] != list(EXPECTED_PERSONA_IDS):
        _fail("persona order or one-to-one coverage drifted")
    use_case_ids = [row["primary_use_case_id"] for row in rows]
    roles = [row["persona_role"] for row in rows]
    if len(set(use_case_ids)) != 20 or len(set(roles)) != 20:
        _fail("persona/use-case/role cardinality is not exact one-to-one")

    topology_by_persona = {
        row["persona_id"]: row for row in topology_value["personas"]
    }
    envelope_by_persona = {
        row["persona_id"]: row for row in envelope_value["personas"]
    }
    for row in rows:
        _exact_keys(row, ROW_KEYS, label="primary use case row")
        persona_id = row["persona_id"]
        if row["data_classification"] != "synthetic-non-pii":
            _fail(f"{persona_id} is not classified synthetic non-PII")
        if row["persona_role"] != envelope_by_persona[persona_id]["role"]:
            _fail(f"{persona_id} role marginal join drifted")
        if row["required_scope_role"] != "primary":
            _fail(f"{persona_id} required scope role must be primary")
        relative_path = row["representative_relative_path"]
        if (
            type(relative_path) is not str
            or not relative_path
            or relative_path.startswith(("/", "\\"))
            or re.match(r"^[A-Za-z]:[\\/]", relative_path)
            or ".." in relative_path.split("/")
            or "..." in relative_path
        ):
            _fail(f"{persona_id} representative path is not safe and relative")
        scopes = topology_by_persona[persona_id]["scopes"]
        matching = [scope for scope in scopes if scope["relative_path"] == relative_path]
        if (
            len(matching) != 1
            or matching[0]["kind"] != "primary"
            or matching[0]["functional_slot"]
            != row["representative_functional_slot"]
        ):
            _fail(f"{persona_id} representative topology join drifted")
        if relative_path != envelope_by_persona[persona_id]["representative_primary_scope"]:
            _fail(f"{persona_id} representative envelope join drifted")

        families = row["required_families"]
        if (
            type(families) is not list
            or not families
            or len(families) != len(set(families))
            or any(family not in EXPECTED_FAMILIES for family in families)
        ):
            _fail(f"{persona_id} required family set is invalid")
        join = row["required_family_marginal_join"]
        if [item["family_id"] for item in join] != families:
            _fail(f"{persona_id} family marginal join order drifted")
        for item in join:
            if set(item) != {
                "family_id",
                "full_physical_file_count",
                "full_physical_ratio_pct",
            }:
                _fail(f"{persona_id} family marginal join keys drifted")
            if (
                type(item["full_physical_file_count"]) is not int
                or item["full_physical_file_count"] <= 0
                or type(item["full_physical_ratio_pct"]) is not int
                or item["full_physical_ratio_pct"] <= 0
            ):
                _fail(f"{persona_id} required family must have positive physical ratio")

        lifecycle = row["required_lifecycle_capabilities"]
        query = row["required_query_strata"]
        if (
            type(lifecycle) is not list
            or not lifecycle
            or len(lifecycle) != len(set(lifecycle))
            or any(item not in EXPECTED_LIFECYCLE_ALLOWLIST for item in lifecycle)
        ):
            _fail(f"{persona_id} lifecycle capability is outside the allowlist")
        if (
            type(query) is not list
            or not query
            or len(query) != len(set(query))
            or any(item not in EXPECTED_QUERY_STRATUM_ALLOWLIST for item in query)
        ):
            _fail(f"{persona_id} query stratum is outside the allowlist")

        text_fields = (
            row["trigger"],
            row["desired_outcome"],
            row["proposal_evaluation_focus"],
        )
        if any(type(item) is not str or not item for item in text_fields):
            _fail(f"{persona_id} authored text fields must be non-empty strings")
        if any(re.search(r"[^\s@]+@[^\s@]+", item) for item in text_fields):
            _fail(f"{persona_id} contains an email-like personal identifier")


def _validate_static(value, expected_bindings):
    _exact_keys(value, TOP_LEVEL_KEYS, label="primary use case catalog")
    if (
        value["artifact_kind"] != ARTIFACT_KIND
        or value["artifact_schema"] != ARTIFACT_SCHEMA
        or value["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or value["fixture_id"] != "kio-persona-pc-v2"
        or value["fixture_schema_version"] != 2
        or value["g0_contract_frozen"] is not False
    ):
        _fail("primary use case artifact identity drifted")
    _require_negative_authority(
        value, label="primary use case catalog", exact_fields=AUTHORITY_FIELDS
    )
    if value["input_binding_order"] != [row["name"] for row in expected_bindings]:
        _fail("dependency binding order drifted")
    if value["input_bindings"] != expected_bindings:
        _fail("dependency binding pins or roles drifted")
    if value["canonical_limits"] != {
        "max_body_bytes": MAX_CATALOG_BYTES,
        "max_integer_bits": artifact_common.MAX_INTEGER_BITS,
        "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
        "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
        "null_float_or_negative_integer_allowed": False,
        "self_hash_embedded": False,
        "unicode_normalization": "NFC",
    }:
        _fail("canonical limits drifted")
    if value["completion_claims"] != {
        "all_twenty_primary_use_cases_authored": True,
        "compiled_history_plan_bound": False,
        "evaluation_target_resolution_bound": False,
        "family_marginal_positive_join_complete": True,
        "one_to_one_persona_use_case_mapping_complete": True,
        "query_instances_rendered": False,
        "representative_primary_scope_join_complete": True,
        "source_instance_membership_bound": False,
    }:
        _fail("completion claims drifted or overclaim authority")
    if value["completion_scope"] != (
        "primary-use-case-design-and-upstream-marginal-join-only-no-source-"
        "instance-no-rendered-query-no-evaluation-no-write-no-g0"
    ):
        _fail("completion scope drifted")
    if value["policy"] != {
        "format_term_to_family": [
            {"family_id": family, "proposal_format_term": term}
            for term, family in EXPECTED_FORMAT_TERM_ROWS
        ],
        "lifecycle_capability_allowlist": list(EXPECTED_LIFECYCLE_ALLOWLIST),
        "one_primary_use_case_per_persona": True,
        "primary_use_case_reuse_across_personas_allowed": False,
        "proposal_ellipsis_resolution": (
            "proposal scope ellipses are shorthand only; each row binds the "
            "exact envelope representative_primary_scope and that path must "
            "resolve to one topology scope whose kind is primary"
        ),
        "query_stratum_allowlist": list(EXPECTED_QUERY_STRATUM_ALLOWLIST),
        "required_family_semantics": (
            "minimum-positive-use-case-witness-families-not-a-complete-physical-mix"
        ),
        "scope_path_kind": "persona-root-relative-never-absolute",
        "synthetic_data_only": True,
        "synthetic_personal_data_present": False,
        "use_case_status": "authored-benchmark-stress-design-not-observed-user-behavior",
    }:
        _fail("use-case normalization policy drifted")
    if value["summary"] != {
        "persona_count": 20,
        "primary_use_case_count": 20,
        "unique_persona_role_count": 20,
        "unique_primary_use_case_count": 20,
    }:
        _fail("primary use case summary drifted")
    if value["remaining_blockers"] != list(EXPECTED_REMAINING_BLOCKERS):
        _fail("remaining blockers drifted or were prematurely cleared")


def _validate_primary_use_case_catalog_snapshot(
    value, *, envelope_value, topology_value
):
    raw = _canonical(
        value, label="persona v2 primary use case catalog", max_bytes=MAX_CATALOG_BYTES
    )
    if (
        len(raw) != EXPECTED_CATALOG_CANONICAL_BYTES
        or hashlib.sha256(raw).hexdigest() != EXPECTED_CATALOG_SHA256
    ):
        _fail("primary use case catalog canonical body pin drifted")

    expected_bindings = [
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
    _validate_static(value, expected_bindings)
    expected_rows = _expected_use_case_rows(envelope_value, topology_value)
    _validate_rows(value, expected_rows, envelope_value, topology_value)
    _assert_no_forbidden_keys(value)
    return True


def validate_primary_use_case_catalog(
    value, *, envelope_value=None, topology_value=None
):
    """Validate detached snapshots and then re-authenticate caller-owned values."""

    if type(value) is not dict:
        _fail("primary use case catalog must be an object")
    if envelope_value is None:
        envelope_value = envelope.build_envelope_contract()
    if topology_value is None:
        topology_value = topology.build_topology_contract()
    if type(envelope_value) is not dict or type(topology_value) is not dict:
        _fail("dependency values must be objects")

    catalog_before = _canonical(
        value, label="caller primary use case catalog", max_bytes=MAX_CATALOG_BYTES
    )
    envelope_before = _canonical(
        envelope_value,
        label="caller envelope dependency",
        max_bytes=MAX_DEPENDENCY_BYTES,
    )
    topology_before = _canonical(
        topology_value,
        label="caller topology dependency",
        max_bytes=MAX_DEPENDENCY_BYTES,
    )
    result = _validate_primary_use_case_catalog_snapshot(
        copy.deepcopy(value),
        envelope_value=copy.deepcopy(envelope_value),
        topology_value=copy.deepcopy(topology_value),
    )
    if _canonical(
        value, label="closing primary use case catalog", max_bytes=MAX_CATALOG_BYTES
    ) != catalog_before:
        _fail("caller primary use case catalog mutated during validation")
    if _canonical(
        envelope_value,
        label="closing envelope dependency",
        max_bytes=MAX_DEPENDENCY_BYTES,
    ) != envelope_before:
        _fail("caller envelope dependency mutated during validation")
    if _canonical(
        topology_value,
        label="closing topology dependency",
        max_bytes=MAX_DEPENDENCY_BYTES,
    ) != topology_before:
        _fail("caller topology dependency mutated during validation")
    return result
