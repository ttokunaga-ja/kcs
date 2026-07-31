"""Non-authorizing recursive-robustness lane catalog for persona-PC v2.

This catalog freezes the twenty-person ambient-tree plans described by the
persona-PC fidelity proposal.  It is deliberately separate from the formal
retrieval/history roots: every row is an unregistered, raw-only robustness
candidate plan with its own manifest and future observed receipt.

Nothing in this module creates a directory or file, predicts an observed
filesystem result, registers a KIO scope, or grants writer, execution, formal
gate, or G0 authority.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_realism_profile as realism
    from . import persona_v2_recursive_robustness_lane_catalog_validator as independent
    from . import persona_v2_topology as topology
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_realism_profile as realism
    import persona_v2_recursive_robustness_lane_catalog_validator as independent
    import persona_v2_topology as topology


ARTIFACT_SCHEMA = "kio.persona.pc-recursive-robustness-lane-catalog/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-recursive-robustness-lane-catalog"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2
LANE_ID = "recursive-robustness-v1"
MAX_CATALOG_BYTES = 512 * 1024

PERSONA_IDS = tuple(f"p{index:02d}" for index in range(1, 21))
DEPTH_ORDER = (6, 7, 8)

CATEGORY_ROWS = (
    ("benign-nested-document", 102),
    ("exact-near-conflict-copy", 38),
    ("cache-temp", 38),
    ("partial-download", 26),
    ("hidden-lockfile", 26),
    ("empty-file", 13),
    ("unicode-case-collision", 13),
)
CANDIDATE_FILES_PER_PERSONA = sum(count for _, count in CATEGORY_ROWS)
AUTHORED_DIRECTORIES_PER_PERSONA = 128
UNICODE_NONCOLLISION_CANDIDATES = 7
CASE_COLLISION_PAIR_COUNT = 3
CASE_COLLISION_BASE_CANDIDATES = CASE_COLLISION_PAIR_COUNT
CASE_COLLISION_MATE_CANDIDATES = CASE_COLLISION_PAIR_COUNT

AUTHORITY_FIELDS = frozenset(
    {
        "actual_filesystem_paths_attested",
        "actual_native_realization_attested",
        "authorizes_formal_gate",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "manifest_published",
        "receipt_published",
        "robustness_execution_available",
    }
)

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-topology": (
        134_195,
        "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a",
    ),
    "persona-v2-realism-profile": (
        36_811,
        "990139d3a544ad57ea77752a6a2de8d4345897e961ca85bd506bd1ee041b3fdb",
    ),
}


class PersonaV2RecursiveRobustnessLaneCatalogError(ValueError):
    """Raised when the robustness lane catalog drifts or gains authority."""


def _fail(message):
    raise PersonaV2RecursiveRobustnessLaneCatalogError(message)


# persona, representative parent below ambient-home, phenomenon id,
# planned Dmax, planned file counts at D6/D7/D8.
_AMBIENT_ROWS = (
    ("p01", "scratch/product-alpha/feature-auth/rebase-03/conflicts/files", "merge-copy-generated-case-variation", 6, (256, 0, 0)),
    ("p02", "incident-staging/inc-2026-0713/checkout/prod/pods/pod-004/logs", "log-rotation-partial-file", 7, (62, 194, 0)),
    ("p03", "evidence-staging/soc2/cc6-1/2026/request-042/raw", "evidence-duplicate-incomplete-export", 6, (256, 0, 0)),
    ("p04", "scratch/runs/model-alpha/exp-0042/seed-003/checkpoints/epoch-020", "checkpoint-cache-fanout", 7, (64, 192, 0)),
    ("p05", "staging/warehouse/20260713/sales/region-jp/part-0007", "partition-duplicate-csv", 6, (256, 0, 0)),
    ("p06", "instrument-staging/mass-spec/run-001/vendor/raw/chunks", "vendor-container-partial-transfer", 6, (256, 0, 0)),
    ("p07", "imports/archive-alpha/box-001/folder-07/item-003/derivatives/ocr", "unicode-scan-ocr-pair", 8, (47, 83, 126)),
    ("p08", "meeting-imports/teams/product-alpha/2026/q3/chat/attachments", "sync-conflict-office-lockfile", 7, (68, 188, 0)),
    ("p09", "recorder-staging/study-alpha/session-017/audio/raw/channels", "media-sidecar-partial-wave", 6, (256, 0, 0)),
    ("p10", "vdi-export/client-alpha/phase-1/workstream-finance/share/old/final", "nested-final-copy-office-lock", 7, (70, 186, 0)),
    ("p11", "outlook-cache/account-alpha/2026/07/thread-0042/attachments", "attachment-copy-unicode-space", 6, (256, 0, 0)),
    ("p12", "ticket-cache/customer-alpha/case-1042/updates/2026/07/attachments", "screenshot-copy-partial", 7, (72, 184, 0)),
    ("p13", "legal-hold/matter-alpha/collection-01/custodian-syn-01/mail/attachments", "deep-hold-unicode-filename", 6, (256, 0, 0)),
    ("p14", "onedrive-sync/finance/close/fy2026/q1/2026-03/review/final", "conflicted-workbook-final-copy", 8, (54, 82, 120)),
    ("p15", "ats-cache/req-alpha/candidate-syn-017/interviews/round-2/panel", "repeated-scorecard", 6, (256, 0, 0)),
    ("p16", "secure-smb/study-alpha/site-03/subject-syn-004/visit-02/imaging/series-01", "dicom-many-siblings", 7, (76, 180, 0)),
    ("p17", "cde-cache/project-alpha/shared/wip/architecture/models/rev-b", "ifczip-revision-offline-cache", 7, (77, 179, 0)),
    ("p18", "plm-cache/product-alpha/changes/eco-0042/attachments/supplier-alpha/certificates", "temporary-obsolete-copy", 7, (78, 178, 0)),
    ("p19", "drive-sync/course-alpha/2026/term-1/week-04/student-work-synthetic/team-07/final", "duplicate-submission-space", 8, (59, 79, 118)),
    ("p20", "source-drop/story-alpha/source-syn-017/device-export/messages/attachments/2026-07", "heic-partial-evidence-chain", 7, (80, 176, 0)),
)


def _dependency_binding(name, role, value, *, canonical, validate):
    try:
        validate(value)
        raw = canonical(value)
    except Exception as error:
        _fail(f"{name} dependency validation failed: {type(error).__name__}")
    expected_size, expected_digest = EXPECTED_DEPENDENCY_PINS[name]
    if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != expected_digest:
        _fail(f"{name} dependency pin drifted")
    authority = value.get("authority")
    if (
        type(authority) is not dict
        or not authority
        or any(type(flag) is not bool or flag is not False for flag in authority.values())
        or value.get("g0_contract_frozen") is not False
    ):
        _fail(f"{name} dependency must remain non-authorizing")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": expected_size,
        "dependency_role": role,
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "name": name,
        "sha256": expected_digest,
    }


def _relative_parts(path, *, label):
    if type(path) is not str or not path:
        _fail(f"{label} must be a non-empty relative path")
    if unicodedata.normalize("NFC", path) != path:
        _fail(f"{label} must be NFC")
    if path.startswith(("/", "\\")) or "\\" in path or ":" in path:
        _fail(f"{label} must be a portable relative POSIX path")
    parts = path.split("/")
    if any(
        not part
        or part in (".", "..")
        or part.casefold() == ".kio"
        or len(part.encode("utf-8", "strict")) > 255
        for part in parts
    ):
        _fail(f"{label} contains a prohibited path component")
    return tuple(parts)


def _paths_overlap(left, right):
    common = min(len(left), len(right))
    return left[:common] == right[:common]


def _directory_depth_histogram(ordinal, planned_dmax):
    counts = [
        5 + ((ordinal * depth + ordinal + depth) % 9)
        for depth in range(1, planned_dmax)
    ]
    counts.append(AUTHORED_DIRECTORIES_PER_PERSONA - sum(counts))
    if any(type(count) is not int or count <= 0 for count in counts):
        _fail("authored directory depth apportionment is invalid")
    return [
        {"authored_directory_count": count, "depth": depth}
        for depth, count in enumerate(counts, start=1)
    ]


def _native_realization_plan(case_mode):
    if case_mode == "case-insensitive":
        target_failure_lower = target_failure_upper = CASE_COLLISION_MATE_CANDIDATES
        target_realizable_lower = target_realizable_upper = (
            CANDIDATE_FILES_PER_PERSONA - CASE_COLLISION_MATE_CANDIDATES
        )
        target_expectation = "target-case-insensitive-conditional-expectation"
    elif case_mode == "case-sensitive":
        target_failure_lower = target_failure_upper = 0
        target_realizable_lower = target_realizable_upper = CANDIDATE_FILES_PER_PERSONA
        target_expectation = "target-case-sensitive-conditional-expectation"
    elif case_mode == "portable-snapshot-case-unspecified":
        target_failure_lower = 0
        target_failure_upper = CASE_COLLISION_MATE_CANDIDATES
        target_realizable_lower = (
            CANDIDATE_FILES_PER_PERSONA - CASE_COLLISION_MATE_CANDIDATES
        )
        target_realizable_upper = CANDIDATE_FILES_PER_PERSONA
        target_expectation = "target-case-semantics-unspecified"
    else:
        _fail("unknown persona case mode")
    return {
        "case_collision_base_candidate_count": CASE_COLLISION_BASE_CANDIDATES,
        "case_collision_mate_candidate_count": CASE_COLLISION_MATE_CANDIDATES,
        "case_collision_pair_count": CASE_COLLISION_PAIR_COUNT,
        "conditional_execution_case_outcomes": [
            {
                "execution_filesystem_case_mode": "case-insensitive",
                "expected_manifest_only_failure_count": CASE_COLLISION_MATE_CANDIDATES,
                "expected_native_realized_candidate_count": (
                    CANDIDATE_FILES_PER_PERSONA - CASE_COLLISION_MATE_CANDIDATES
                ),
            },
            {
                "execution_filesystem_case_mode": "case-sensitive",
                "expected_manifest_only_failure_count": 0,
                "expected_native_realized_candidate_count": CANDIDATE_FILES_PER_PERSONA,
            },
        ],
        "execution_filesystem_case_mode_binding_status": (
            "unbound-until-native-replay-receipt"
        ),
        "expected_manifest_only_failure_count_lower_bound": 0,
        "expected_manifest_only_failure_count_upper_bound": (
            CASE_COLLISION_MATE_CANDIDATES
        ),
        "native_realizable_candidate_count_lower_bound": (
            CANDIDATE_FILES_PER_PERSONA - CASE_COLLISION_MATE_CANDIDATES
        ),
        "native_realizable_candidate_count_upper_bound": CANDIDATE_FILES_PER_PERSONA,
        "native_realization_status": (
            "not-executed-execution-filesystem-case-mode-unbound"
        ),
        "target_semantics_conditional_expectation_kind": target_expectation,
        "target_semantics_conditional_manifest_only_failure_count_lower_bound": (
            target_failure_lower
        ),
        "target_semantics_conditional_manifest_only_failure_count_upper_bound": (
            target_failure_upper
        ),
        "target_semantics_conditional_native_realizable_count_lower_bound": (
            target_realizable_lower
        ),
        "target_semantics_conditional_native_realizable_count_upper_bound": (
            target_realizable_upper
        ),
        "unicode_noncollision_candidate_count": UNICODE_NONCOLLISION_CANDIDATES,
    }


def _persona_row(authored, *, ordinal, topology_row, realism_row):
    persona_id, representative_path, phenomenon_id, planned_dmax, file_counts = authored
    if persona_id != topology_row["persona_id"] or persona_id != realism_row["persona_id"]:
        _fail("persona order differs across robustness inputs")
    if topology_row["role"] != realism_row["role"]:
        _fail(f"{persona_id} role differs between topology and realism profile")
    representative_parts = _relative_parts(
        representative_path, label=f"{persona_id} representative parent"
    )
    representative_depth = len(representative_parts)
    if planned_dmax not in DEPTH_ORDER or not 6 <= representative_depth <= planned_dmax:
        _fail(f"{persona_id} representative depth/planned Dmax is invalid")
    if type(file_counts) is not tuple or len(file_counts) != len(DEPTH_ORDER):
        _fail(f"{persona_id} file depth vector shape drifted")
    if any(type(count) is not int or count < 0 for count in file_counts):
        _fail(f"{persona_id} file depth counts must be non-negative integers")
    if sum(file_counts) != CANDIDATE_FILES_PER_PERSONA:
        _fail(f"{persona_id} file depth counts do not sum to 256")
    if file_counts[planned_dmax - DEPTH_ORDER[0]] <= 0:
        _fail(f"{persona_id} planned Dmax lacks a file candidate")
    if any(file_counts[depth - DEPTH_ORDER[0]] for depth in DEPTH_ORDER if depth > planned_dmax):
        _fail(f"{persona_id} has file candidates below a forbidden deeper level")

    ambient_root = f"devices/{persona_id}/ambient-home"
    formal_root = f"devices/{persona_id}/home"
    ambient_root_parts = _relative_parts(ambient_root, label=f"{persona_id} ambient root")
    formal_root_parts = _relative_parts(formal_root, label=f"{persona_id} formal root")
    if _paths_overlap(ambient_root_parts, formal_root_parts):
        _fail(f"{persona_id} ambient/formal roots overlap")
    for scope in topology_row["scopes"]:
        formal_scope = formal_root_parts + _relative_parts(
            scope["relative_path"], label=f"{persona_id} formal scope reference"
        )
        ambient_parent = ambient_root_parts + representative_parts
        if _paths_overlap(formal_scope, ambient_parent):
            _fail(f"{persona_id} robustness parent overlaps a formal scope")

    manifest_path = f"lane-manifests/{LANE_ID}/{persona_id}.plan.json"
    receipt_path = f"lane-receipts/{LANE_ID}/{persona_id}.observed.json"
    _relative_parts(manifest_path, label=f"{persona_id} manifest path")
    _relative_parts(receipt_path, label=f"{persona_id} receipt path")
    if manifest_path == receipt_path:
        _fail(f"{persona_id} manifest and receipt paths must differ")

    return {
        "authored_directory_count": AUTHORED_DIRECTORIES_PER_PERSONA,
        "authored_directory_depth_histogram": _directory_depth_histogram(
            ordinal, planned_dmax
        ),
        "candidate_category_counts": [
            {"candidate_count": count, "category_id": category_id}
            for category_id, count in CATEGORY_ROWS
        ],
        "candidate_file_count": CANDIDATE_FILES_PER_PERSONA,
        "candidate_file_depth_histogram": [
            {"candidate_count": count, "depth": depth}
            for depth, count in zip(DEPTH_ORDER, file_counts)
        ],
        "data_classification": "synthetic-non-pii",
        "device_relative_ambient_root": ambient_root,
        "device_relative_formal_root": formal_root,
        "formal_gate_eligible": False,
        "formal_scope_overlap": False,
        "formal_scope_reference_count": len(topology_row["scopes"]),
        "kio_control_tree_allowed": False,
        "lane_id": LANE_ID,
        "lane_local_gate_role": "raw_only",
        "manifest_relative_path": manifest_path,
        "manifest_status": "planned-not-written",
        "native_realization_plan": _native_realization_plan(realism_row["case_mode"]),
        "os_semantics_id": realism_row["os_semantics_id"],
        "path_state": "contract-only-not-materialized",
        "persona_id": persona_id,
        "persona_role": topology_row["role"],
        "planned_dmax": planned_dmax,
        "planned_max_fan_out": 16 + ordinal,
        "receipt_relative_path": receipt_path,
        "receipt_status": "required-after-native-replay-not-present",
        "registered_scope": False,
        "representative_parent_depth": representative_depth,
        "representative_parent_is_planned_dmax": representative_depth == planned_dmax,
        "representative_parent_relative_path": representative_path,
        "representative_phenomenon_id": phenomenon_id,
        "requested_chunks": 0,
        "shape_vector_id": f"{persona_id}-recursive-ambient-shape-v1",
        "target_case_mode": realism_row["case_mode"],
        "target_os_execution_mode": realism_row["os_execution_mode"],
    }


@functools.lru_cache(maxsize=1)
def _canonical_catalog_value():
    topology_value = topology.build_topology_contract()
    realism_value = realism.build_realism_profile()
    input_bindings = [
        _dependency_binding(
            "persona-v2-topology",
            "formal-scope-non-overlap-reference-owner",
            topology_value,
            canonical=topology.canonical_json_bytes,
            validate=topology.validate_topology_contract,
        ),
        _dependency_binding(
            "persona-v2-realism-profile",
            "persona-role-and-target-case-semantics-owner",
            realism_value,
            canonical=realism.canonical_json_bytes,
            validate=realism.validate_realism_profile,
        ),
    ]
    topology_by_persona = {
        row["persona_id"]: row for row in topology_value["personas"]
    }
    realism_by_persona = {
        row["persona_id"]: row for row in realism_value["personas"]
    }
    rows = [
        _persona_row(
            authored,
            ordinal=ordinal,
            topology_row=topology_by_persona[authored[0]],
            realism_row=realism_by_persona[authored[0]],
        )
        for ordinal, authored in enumerate(_AMBIENT_ROWS, start=1)
    ]
    if [row["persona_id"] for row in rows] != list(PERSONA_IDS):
        _fail("robustness rows must follow exact persona order")

    suite_depth_counts = {
        depth: sum(
            row["candidate_file_depth_histogram"][index]["candidate_count"]
            for row in rows
        )
        for index, depth in enumerate(DEPTH_ORDER)
    }
    if set(depth for depth, count in suite_depth_counts.items() if count > 0) != set(DEPTH_ORDER):
        _fail("suite must cover D6, D7, and D8")
    planned_dmax_counts = {
        depth: sum(row["planned_dmax"] == depth for row in rows)
        for depth in DEPTH_ORDER
    }
    native_lower = sum(
        row["native_realization_plan"][
            "native_realizable_candidate_count_lower_bound"
        ]
        for row in rows
    )
    native_upper = sum(
        row["native_realization_plan"][
            "native_realizable_candidate_count_upper_bound"
        ]
        for row in rows
    )
    target_conditional_native_lower = sum(
        row["native_realization_plan"][
            "target_semantics_conditional_native_realizable_count_lower_bound"
        ]
        for row in rows
    )
    target_conditional_native_upper = sum(
        row["native_realization_plan"][
            "target_semantics_conditional_native_realizable_count_upper_bound"
        ]
        for row in rows
    )

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
        "case_collision_pair_contract": {
            "candidate_manifest_required_member_fields": [
                "candidate_id",
                "collision_pair_id",
                "collision_role",
                "parent_relative_path",
                "basename_portable_ascii",
                "collision_key",
            ],
            "basename_difference_rule": "ascii-letter-case-only",
            "basename_nfc_required": True,
            "basename_repertoire": "portable-ascii",
            "collision_key_algorithm": "portable-ascii-lower-v1",
            "collision_key_expression": "ASCII-lower(basename)",
            "collision_key_reuse_across_pairs_allowed": False,
            "collision_roles": ["base", "mate"],
            "distinct_exact_basename_required": True,
            "distinct_exact_relative_path_required": True,
            "equal_collision_key_required": True,
            "materialization_order": ["base", "mate"],
            "members_per_pair": 2,
            "one_member_per_collision_role_required": True,
            "pair_count_per_persona": CASE_COLLISION_PAIR_COUNT,
            "pair_id_unique_per_persona": True,
            "portable_ascii_basename_required": True,
            "same_parent_directory_required": True,
        },
        "completion_claims": {
            "all_twenty_persona_lane_plans_bound": True,
            "candidate_category_counts_bound": True,
            "candidate_paths_materialized": False,
            "candidate_vs_native_realization_contract_bound": True,
            "formal_scope_non_overlap_plan_bound": True,
            "native_realization_receipts_attested": False,
            "persona_planned_dmax_bound": True,
            "persona_realized_dmax_attested": False,
            "physical_writer_implemented": False,
            "separate_manifest_and_receipt_paths_bound": True,
            "suite_d6_d7_d8_coverage_planned": True,
        },
        "completion_scope": (
            "recursive-robustness-plan-only-no-files-no-directories-no-native-"
            "receipt-no-formal-scope-no-chunks-no-recall-no-writer-no-g0"
        ),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "lane_contract": {
            "candidate_count_is_not_native_realized_count": True,
            "capacity_receipt_required": True,
            "completed_root_copy_allowed": False,
            "formal_chunk_denominator_membership": "excluded",
            "formal_family_ratio_membership": "excluded",
            "formal_gate_eligible": False,
            "formal_recall_latency_membership": "excluded",
            "hardlink_clone_or_symlink_allowed": False,
            "history_mode": "representative-operations-separate-manifest-only",
            "intermediate_directory_files_required": True,
            "lane_id": LANE_ID,
            "lane_root_template": "robustness-root/devices/{persona_id}/ambient-home",
            "native_realization_receipt_must_match_planned_dmax": True,
            "registered_scope": False,
            "replay_count": 1,
            "requested_chunks": 0,
            "separate_formal_root_template": "formal-root/devices/{persona_id}/home",
            "separate_manifest_and_receipt_required": True,
        },
        "orders": {
            "candidate_category_order": [row[0] for row in CATEGORY_ROWS],
            "file_depth_order": list(DEPTH_ORDER),
            "persona_order": list(PERSONA_IDS),
        },
        "personas": rows,
        "receipt_contract": {
            "actual_native_realized_and_unrealized_counts_required": True,
            "candidate_manifest_digest_required": True,
            "case_collision_candidate_outcome_reconciliation_required": True,
            "case_collision_pair_structure_validation_required": True,
            "candidate_manifest_pair_member_fields_required": True,
            "collision_key_recomputation_required": True,
            "conditional_case_outcome_match_required": True,
            "declared_entry_reconciliation_required": True,
            "execution_filesystem_case_mode_required": True,
            "formal_leaf_nonintersection_required": True,
            "manifest_only_expected_failure_excluded_from_native_realized_count": True,
            "path_depth_histogram_required": True,
            "planned_realized_dmax_equality_required": True,
            "same_parent_pair_validation_required": True,
            "traversal_and_exclusion_reason_counts_required": True,
            "undeclared_entry_rejection_required": True,
        },
        "remaining_blockers": [
            "physical-robustness-writer-not-implemented",
            "native-filesystem-realization-not-executed",
            "observed-manifest-and-capacity-receipts-not-attested",
            "execution-filesystem-case-mode-unbound",
            "p19-target-case-semantics-unspecified",
            "formal-g0-suite-descriptor-not-bound",
            "g0-contract-not-frozen",
        ],
        "summary": {
            "authored_directory_count_per_persona": AUTHORED_DIRECTORIES_PER_PERSONA,
            "candidate_category_counts_per_persona": [
                {"candidate_count": count, "category_id": category_id}
                for category_id, count in CATEGORY_ROWS
            ],
            "candidate_file_count_per_persona": CANDIDATE_FILES_PER_PERSONA,
            "persona_count": len(rows),
            "persona_planned_dmax_counts": [
                {"depth": depth, "persona_count": planned_dmax_counts[depth]}
                for depth in DEPTH_ORDER
            ],
            "suite_authored_directory_count": (
                len(rows) * AUTHORED_DIRECTORIES_PER_PERSONA
            ),
            "suite_candidate_file_count": len(rows) * CANDIDATE_FILES_PER_PERSONA,
            "suite_candidate_file_depth_histogram": [
                {"candidate_count": suite_depth_counts[depth], "depth": depth}
                for depth in DEPTH_ORDER
            ],
            "suite_native_realizable_candidate_count_lower_bound": native_lower,
            "suite_native_realizable_candidate_count_upper_bound": native_upper,
            "suite_target_semantics_conditional_native_realizable_lower_bound": (
                target_conditional_native_lower
            ),
            "suite_target_semantics_conditional_native_realizable_upper_bound": (
                target_conditional_native_upper
            ),
        },
    }


def build_recursive_robustness_lane_catalog():
    """Return a detached deterministic twenty-person robustness plan."""

    return copy.deepcopy(_canonical_catalog_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 recursive robustness lane catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RecursiveRobustnessLaneCatalogError(str(error)) from None


def validate_recursive_robustness_lane_catalog(value):
    """Validate through the builder-independent semantic validator."""

    try:
        return independent.validate_recursive_robustness_lane_catalog(
            value,
            topology_value=topology.build_topology_contract(),
            realism_profile_value=realism.build_realism_profile(),
        )
    except independent.PersonaV2RecursiveRobustnessLaneCatalogValidationError as error:
        raise PersonaV2RecursiveRobustnessLaneCatalogError(str(error)) from None


def recursive_robustness_lane_catalog_sha256(value=None):
    if value is None:
        value = build_recursive_robustness_lane_catalog()
    validate_recursive_robustness_lane_catalog(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
