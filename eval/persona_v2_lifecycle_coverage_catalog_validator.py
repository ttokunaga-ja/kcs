"""Independent validation for the persona-v2 lifecycle coverage catalog.

This module deliberately does not import the catalog producer.  It reconstructs
the query-independent capability, rendition, witness, move-receipt, and
operation-algebra domains from fixed design constants, authenticates every
frozen input, and reauthenticates caller-owned values after validation.
"""

from __future__ import annotations

import copy
import hashlib
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


ARTIFACT_SCHEMA = "kio.persona.pc-lifecycle-coverage-catalog/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-lifecycle-coverage-catalog"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2
MAX_CATALOG_BYTES = 4 * 2**20
MAX_DEPENDENCY_BYTES = 2 * 2**20

# Installed after the independently reconstructed body is reviewed.
EXPECTED_CATALOG_CANONICAL_BYTES = 1_385_596
EXPECTED_CATALOG_SHA256 = (
    "1760eeed4bde8c7a1c2c720a437fb4c3d62971af3f2159e768696e938389b9d4"
)

PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, 21))
ALLOCATION_CLASS_ORDER = ("P", "X", "Y", "N", "U", "I")
WAVE_ORDER = ("W1", "W2", "W3", "W4", "W5-pre-purge", "W5-final")

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-envelope": (
        71_979,
        "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7",
    ),
    "persona-v2-chunk-accounting": (
        19_801,
        "66a9bd0b5ab8c5f61cd4bdc66b45532810d65b056fcaf8955fff7f366248ab52",
    ),
    "persona-v2-lifecycle-demand": (
        463_571,
        "372a466e3994c9e41662457f144fc03338d96b76f57f9306e62bbe9511422005",
    ),
    "persona-v2-overlay-contract": (
        71_179,
        "e9154297f6dd5cf30ccbcc819d725cb08c533ec84a7b2df359937ddfb6517c23",
    ),
    "persona-v2-source-semantic-membership-catalog": (
        436_495,
        "d54ad435447a6b7adf87c0190bd8ed452caa3015b82ac18da1c81825efeba63b",
    ),
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_lifecycle_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_evaluation_target_resolution",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_query_rendering",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_instance_matching",
        "authorizes_source_plan",
        "compiled_history_plan_available",
        "evaluation_target_mapping_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "source_instance_matching_complete",
    }
)

_DEPENDENCIES = (
    (
        "persona-v2-envelope",
        "persona-history-checkpoint-and-cohort-scale",
        "persona-pc-v2-envelope",
        "kio.persona.pc-envelope/v2",
    ),
    (
        "persona-v2-chunk-accounting",
        "four-ledger-identity-and-existing-operation-delta-base",
        "persona-pc-v2-chunk-accounting",
        "kio.persona.pc-chunk-accounting/v1",
    ),
    (
        "persona-v2-lifecycle-demand",
        "immutable-anonymous-historical-demand-snapshot",
        "persona-pc-v2-lifecycle-demand",
        "kio.persona.pc-lifecycle-demand/v2",
    ),
    (
        "persona-v2-overlay-contract",
        "immutable-format-rendition-and-placement-boundary-snapshot",
        "persona-pc-v2-overlay-contract",
        "kio.persona.pc-overlay-contract/v2",
    ),
    (
        "persona-v2-source-semantic-membership-catalog",
        "semantic-anchor-singleton-profile-cycle-and-transitive-fact-graph-owner",
        "persona-pc-v2-source-semantic-membership-catalog",
        "kio.persona.pc-source-semantic-membership-catalog/v2",
    ),
)

# class, count, allocation, fact, W1 edit, companion, event profiles
_CAPABILITY_CLASSES = (
    ("stable-current-default", 9, "U", "stable-current-fact", False, False, ()),
    ("stable-current-cross-format", 9, "U", "stable-current-fact", False, True, ()),
    ("stable-current-locale", 9, "U", "stable-current-fact", False, False, ()),
    ("replacement-current-default", 1, "Y", "w1-replacement-fact", True, False, ("w1-typed-edit", "w3-surface-edit")),
    ("replacement-current-cross-format", 1, "Y", "w1-replacement-fact", True, True, ("w1-typed-edit", "w3-surface-edit")),
    ("replacement-current-locale", 1, "Y", "w1-replacement-fact", True, False, ("w1-typed-edit", "w3-surface-edit")),
    ("same-scope-rename", 5, "U", "stable-current-fact", False, False, ("w2-rename",)),
    ("stable-cross-scope-move", 4, "I", "stable-current-fact", False, False, ("w2-move",)),
    ("w1-edited-cross-scope-move", 1, "I", "w1-replacement-fact", True, False, ("w1-incidental-typed-edit", "w2-move")),
    ("old-wording-history", 10, "Y", "w0-prior-fact", True, False, ("w1-typed-edit", "w3-surface-edit")),
    ("locale-history", 10, "Y", "w0-prior-fact", True, False, ("w1-typed-edit", "w3-surface-edit")),
    ("archive-history", 10, "Y", "w0-prior-fact", True, False, ("w1-typed-edit", "w3-surface-edit", "w4-archive")),
    ("final-deleted", 10, "X", "w1-visible-fact", True, False, ("w1-typed-edit", "w3-surface-edit", "w4-delete", "w4-create-x-prime")),
    ("current-restored", 10, "X", "w1-visible-fact", True, False, ("w1-typed-edit", "w3-surface-edit", "w4-delete", "w4-create-x-prime", "w5-export-x", "w5-restore-x", "w5-delete-x-prime")),
    ("purged-negative", 15, "P", "purge-only-witness-fact", True, False, ("w1-typed-edit", "w5-create-p-prime", "w5-purge-p")),
)

_PROJECTIONS = (
    ("search-semantic-endpoint-v1", "contract-current"),
    ("search-semantic-endpoint-v1", "contract-history-only"),
    ("search-semantic-endpoint-v1", "incidental-current"),
    ("search-semantic-endpoint-v1", "incidental-history-only"),
    ("persona-global-chunk-hash-v1", "distinct-chunk-hashes"),
    ("history-path-binding-v1", "reachable-path-bindings"),
    ("physical-storage-v1", "managed-source-regular-files"),
    ("physical-storage-v1", "raw-cas-regular-objects"),
    ("physical-storage-v1", "chunk-cas-regular-objects"),
    ("physical-storage-v1", "managed-source-inodes"),
    ("physical-storage-v1", "raw-cas-inodes"),
    ("physical-storage-v1", "chunk-cas-inodes"),
)


class PersonaV2LifecycleCoverageCatalogValidationError(ValueError):
    """Raised when the coverage catalog or one of its inputs is invalid."""


def _fail(message):
    raise PersonaV2LifecycleCoverageCatalogValidationError(message)


def _strict_equal(value, expected):
    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        return set(value) == set(expected) and all(
            _strict_equal(value[key], expected[key]) for key in expected
        )
    if type(expected) is list:
        return len(value) == len(expected) and all(
            _strict_equal(item, wanted)
            for item, wanted in zip(value, expected)
        )
    return value == expected


def _canonical(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _snapshot(value, *, label, max_bytes):
    raw = _canonical(value, label=label, max_bytes=max_bytes)
    return json.loads(raw.decode("utf-8")), raw


def _reauth(value, opening_raw, *, label, max_bytes):
    closing_raw = _canonical(value, label=label, max_bytes=max_bytes)
    if closing_raw != opening_raw:
        _fail(f"{label} changed during validation")


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _class_contracts():
    return [
        {
            "allocation_class": allocation,
            "capability_class_key": class_key,
            "cross_format_companion_required": companion,
            "fact_requirement": fact_requirement,
            "gate_role_requirement": (
                "incidental_searchable" if allocation == "I" else "contract_contributor"
            ),
            "primary_count_per_persona": count,
            "required_event_profile_keys": list(events),
            "w1_typed_edit_required": edited,
        }
        for class_key, count, allocation, fact_requirement, edited, companion, events
        in _CAPABILITY_CLASSES
    ]


def _primary_capabilities():
    rows = []
    for persona_id in PERSONA_IDS:
        ordinal = 1
        for class_key, count, allocation, fact_requirement, edited, companion, events in _CAPABILITY_CLASSES:
            for class_ordinal in range(1, count + 1):
                rows.append(
                    {
                        "allocation_class": allocation,
                        "capability_class_key": class_key,
                        "capability_key": f"{persona_id}-lifecycle-capability-{ordinal:03d}",
                        "class_ordinal": class_ordinal,
                        "cross_format_companion_required": companion,
                        "fact_requirement": fact_requirement,
                        "gate_role_requirement": (
                            "incidental_searchable" if allocation == "I" else "contract_contributor"
                        ),
                        "history_cohort_requirement": [] if allocation == "I" else [allocation],
                        "logical_document_slot_key": f"{persona_id}-lifecycle-document-slot-{ordinal:03d}",
                        "persona_id": persona_id,
                        "required_event_profile_keys": list(events),
                        "source_matching_status": "unbound",
                        "w1_typed_edit_required": edited,
                    }
                )
                ordinal += 1
    return rows


def _companions(primary):
    rows = []
    for persona_id in PERSONA_IDS:
        selected = [
            row
            for row in primary
            if row["persona_id"] == persona_id
            and row["cross_format_companion_required"]
        ]
        if len(selected) != 10:
            _fail("independent cross-format selection drifted")
        for ordinal, row in enumerate(selected, start=1):
            rows.append(
                {
                    "allocation_class": row["allocation_class"],
                    "companion_requirement_key": f"{persona_id}-rendition-companion-{ordinal:02d}",
                    "distinct_family_required": True,
                    "distinct_raw_payload_required": True,
                    "gate_role_requirement": "contract_contributor",
                    "logical_document_relation": "same-canonical-logical-document",
                    "persona_id": persona_id,
                    "primary_capability_key": row["capability_key"],
                    "rendition_group_key": f"{persona_id}-rendition-group-{ordinal:02d}",
                    "same_fact_language_topic_and_revision_required": True,
                    "same_solved_scope_required": True,
                    "source_matching_status": "unbound",
                    "w1_typed_edit_required": row["w1_typed_edit_required"],
                }
            )
    return rows


def _witnesses(primary):
    return [
        {
            "capability_key": row["capability_key"],
            "fact_overlay_status": "unbound",
            "forbidden_consumers": [
                "P-prime-capacity-replacement",
                "any-other-source-or-rendition",
                "distractor-content",
                "padding-or-ambient-content",
            ],
            "persona_id": row["persona_id"],
            "purge_witness_key": row["capability_key"].replace(
                "lifecycle-capability", "purge-witness"
            ),
            "suite_global_uniqueness_required": True,
        }
        for row in primary
        if row["capability_class_key"] == "purged-negative"
    ]


def _delta(overrides=()):
    mapping = {
        key: ("preserve", 0, "zero") for key in _PROJECTIONS
    }
    for metric, projection, direction, coefficient, symbol in overrides:
        key = (metric, projection)
        if key not in mapping:
            _fail("independent operation references an unknown projection")
        mapping[key] = (direction, coefficient, symbol)
    return [
        {
            "coefficient": mapping[(metric, projection)][1],
            "direction": mapping[(metric, projection)][0],
            "metric_id": metric,
            "projection": projection,
            "symbol": mapping[(metric, projection)][2],
        }
        for metric, projection in _PROJECTIONS
    ]


def _operation(key, wave, scope, path, overrides=(), preconditions=()):
    return {
        "delta_terms": _delta(overrides),
        "operation_key": key,
        "path_transition_rule_key": path,
        "preconditions": list(preconditions),
        "scope_relation_rule_key": scope,
        "symbolic_only_no_event_instance": True,
        "wave": wave,
    }


def _operations():
    edit = (
        ("search-semantic-endpoint-v1", "contract-history-only", "increase", 1, "q"),
        ("persona-global-chunk-hash-v1", "distinct-chunk-hashes", "increase", 1, "q"),
        ("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "q"),
        ("physical-storage-v1", "raw-cas-regular-objects", "increase", 1, "one"),
        ("physical-storage-v1", "chunk-cas-regular-objects", "increase", 1, "q"),
        ("physical-storage-v1", "raw-cas-inodes", "increase", 1, "one"),
        ("physical-storage-v1", "chunk-cas-inodes", "increase", 1, "q"),
    )
    common_edit_storage_preconditions = (
        "before-and-after-source-endpoint-counts-equal-q",
        "before-and-after-chunk-sets-are-disjoint",
        "same-live-managed-path-is-atomically-replaced",
        "before-version-remains-history-reachable-after-edit",
        "after-raw-object-is-absent-from-scope-cas-before-edit",
        "after-chunk-hashes-are-absent-from-persona-global-ledger-and-scope-cas-before-edit",
    )
    w1_typed_edit_preconditions = common_edit_storage_preconditions + (
        "new-version-carries-authenticated-typed-replacement-revision",
        "old-and-new-fact-revision-identities-are-distinct",
    )
    surface_edit_preconditions = common_edit_storage_preconditions + (
        "changed-fact-ids-exact-empty",
        "present-facts-exact-carry-forward",
    )
    incidental_edit = tuple(
        (
            metric,
            (
                "incidental-history-only"
                if projection == "contract-history-only"
                else projection
            ),
            direction,
            coefficient,
            "qIE" if symbol == "q" else symbol,
        )
        for metric, projection, direction, coefficient, symbol in edit
    )
    rename = (
        ("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qR"),
    )
    move = (
        ("search-semantic-endpoint-v1", "incidental-history-only", "increase", 1, "qIM"),
        ("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qIM"),
        ("physical-storage-v1", "raw-cas-regular-objects", "increase", 1, "nIM"),
        ("physical-storage-v1", "chunk-cas-regular-objects", "increase", 1, "qIM"),
        ("physical-storage-v1", "raw-cas-inodes", "increase", 1, "nIM"),
        ("physical-storage-v1", "chunk-cas-inodes", "increase", 1, "qIM"),
    )
    diagnostic = (
        ("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qD"),
        ("physical-storage-v1", "managed-source-regular-files", "increase", 1, "one"),
        ("physical-storage-v1", "raw-cas-regular-objects", "increase", 1, "one"),
        ("physical-storage-v1", "chunk-cas-regular-objects", "increase", 1, "qD"),
        ("physical-storage-v1", "managed-source-inodes", "increase", 1, "one"),
        ("physical-storage-v1", "raw-cas-inodes", "increase", 1, "one"),
        ("physical-storage-v1", "chunk-cas-inodes", "increase", 1, "qD"),
    )
    duplicate = (
        ("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qD"),
        ("physical-storage-v1", "managed-source-regular-files", "increase", 1, "one"),
        ("physical-storage-v1", "managed-source-inodes", "increase", 1, "one"),
    )
    cross_scope_duplicate = (
        ("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qD"),
        ("physical-storage-v1", "managed-source-regular-files", "increase", 1, "one"),
        ("physical-storage-v1", "raw-cas-regular-objects", "increase", 1, "one"),
        ("physical-storage-v1", "chunk-cas-regular-objects", "increase", 1, "qD"),
        ("physical-storage-v1", "managed-source-inodes", "increase", 1, "one"),
        ("physical-storage-v1", "raw-cas-inodes", "increase", 1, "one"),
        ("physical-storage-v1", "chunk-cas-inodes", "increase", 1, "qD"),
    )
    delete_x = (
        ("search-semantic-endpoint-v1", "contract-current", "decrease", 1, "qX"),
        ("search-semantic-endpoint-v1", "contract-history-only", "increase", 1, "qX"),
        ("physical-storage-v1", "managed-source-regular-files", "decrease", 1, "one"),
        ("physical-storage-v1", "managed-source-inodes", "decrease", 1, "one"),
    )
    create_x = (
        ("search-semantic-endpoint-v1", "contract-current", "increase", 1, "qX"),
        ("persona-global-chunk-hash-v1", "distinct-chunk-hashes", "increase", 1, "qX"),
        ("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qX"),
        ("physical-storage-v1", "managed-source-regular-files", "increase", 1, "one"),
        ("physical-storage-v1", "raw-cas-regular-objects", "increase", 1, "one"),
        ("physical-storage-v1", "chunk-cas-regular-objects", "increase", 1, "qX"),
        ("physical-storage-v1", "managed-source-inodes", "increase", 1, "one"),
        ("physical-storage-v1", "raw-cas-inodes", "increase", 1, "one"),
        ("physical-storage-v1", "chunk-cas-inodes", "increase", 1, "qX"),
    )
    create_p = tuple(
        (
            metric,
            projection,
            direction,
            coefficient,
            "qP" if symbol == "qX" else symbol,
        )
        for metric, projection, direction, coefficient, symbol in create_x
    )
    restore_x = (
        ("search-semantic-endpoint-v1", "contract-current", "increase", 1, "qXR"),
        ("search-semantic-endpoint-v1", "contract-history-only", "decrease", 1, "qXR"),
        ("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qXR"),
        ("physical-storage-v1", "managed-source-regular-files", "increase", 1, "one"),
        ("physical-storage-v1", "managed-source-inodes", "increase", 1, "one"),
    )
    delete_x_prime = (
        ("search-semantic-endpoint-v1", "contract-current", "decrease", 1, "qXR"),
        ("search-semantic-endpoint-v1", "contract-history-only", "increase", 1, "qXR"),
        ("physical-storage-v1", "managed-source-regular-files", "decrease", 1, "one"),
        ("physical-storage-v1", "managed-source-inodes", "decrease", 1, "one"),
    )
    purge = (
        ("search-semantic-endpoint-v1", "contract-current", "decrease", 1, "qP"),
        ("search-semantic-endpoint-v1", "contract-history-only", "decrease", 1, "qP"),
        ("persona-global-chunk-hash-v1", "distinct-chunk-hashes", "decrease", 2, "qP"),
        ("history-path-binding-v1", "reachable-path-bindings", "decrease", 2, "qP"),
        ("physical-storage-v1", "managed-source-regular-files", "decrease", 1, "one"),
        ("physical-storage-v1", "raw-cas-regular-objects", "decrease", 2, "one"),
        ("physical-storage-v1", "chunk-cas-regular-objects", "decrease", 2, "qP"),
        ("physical-storage-v1", "managed-source-inodes", "decrease", 1, "one"),
        ("physical-storage-v1", "raw-cas-inodes", "decrease", 2, "one"),
        ("physical-storage-v1", "chunk-cas-inodes", "decrease", 2, "qP"),
    )
    w5_n = tuple(
        (
            metric,
            projection,
            direction,
            coefficient,
            "qN" if symbol == "q" else symbol,
        )
        for metric, projection, direction, coefficient, symbol in edit
    )
    return [
        _operation("w1-typed-edit", "W1", "same-bound-leaf-scope", "preserve-relative-path", edit, w1_typed_edit_preconditions),
        _operation("w1-incidental-typed-edit", "W1", "same-bound-leaf-scope", "preserve-relative-path", incidental_edit, w1_typed_edit_preconditions + ("edited-incidental-source-is-reindexed-before-pre-w2-receipt", "old-history-and-new-current-endpoint-counts-equal-qIE", "old-history-and-new-current-endpoint-sets-are-disjoint")),
        _operation("w2-rename", "W2", "same-bound-leaf-scope", "replace-basename-in-same-parent", rename, ("destination-path-absent", "raw-bytes-and-chunk-set-preserved")),
        _operation("w2-move", "W2", "different-leaf-scope-same-persona", "move-to-different-scope-path", move, ("pre-w2-five-source-receipt-bundle-accepted", "destination-path-endpoint-and-cas-absent-for-all-five-sources", "five-raw-identities-are-distinct-and-absent-from-destination-stores", "all-destination-endpoints-and-paths-are-pairwise-distinct", "raw-bytes-and-chunk-set-preserved")),
        _operation("w3-surface-edit", "W3", "same-bound-leaf-scope", "preserve-relative-path", edit, surface_edit_preconditions),
        _operation("w3-derive-diagnostic", "W3", "same-or-downstream-selected-leaf-scope", "create-distinct-derived-path", diagnostic, ("excluded-from-contract-current-and-history-denominators", "derived-facts-remain-distinct", "derived-raw-object-and-chunk-hashes-are-new-in-persona-and-destination-scope", "destination-path-is-absent")),
        _operation("w3-duplicate-diagnostic-same-scope", "W3", "same-bound-leaf-scope", "create-distinct-duplicate-path", duplicate, ("excluded-from-contract-current-and-history-denominators", "raw-and-chunk-identities-exactly-reused", "destination-path-and-path-bindings-are-absent")),
        _operation("w3-duplicate-diagnostic-cross-scope", "W3", "different-leaf-scope-same-persona", "create-distinct-duplicate-path", cross_scope_duplicate, ("excluded-from-contract-current-and-history-denominators", "raw-and-chunk-identities-exactly-reused", "destination-path-endpoint-and-cas-are-absent", "persona-global-chunk-hashes-already-exist")),
        _operation("w4-delete", "W4", "same-bound-leaf-scope", "remove-live-retain-deleted-binding", delete_x, ("exactly-one-live-source-path-before-delete",)),
        _operation("w4-create-x-prime", "W4", "same-capacity-scope-as-replaced-x", "create-distinct-capacity-replacement-path", create_x, ("x-prime-logical-document-raw-chunks-facts-and-path-distinct", "x-prime-raw-object-and-chunk-hashes-are-absent-from-persona-and-destination-cas", "destination-path-endpoints-and-bindings-are-absent")),
        _operation("w4-archive", "W4", "same-bound-leaf-scope", "move-under-existing-archive-container", rename, ("archive-container-is-within-the-same-indexed-scope",)),
        _operation("w5-correct-n", "W5-pre-purge", "same-bound-leaf-scope", "preserve-relative-path", w5_n, surface_edit_preconditions),
        _operation("w5-create-p-prime", "W5-pre-purge", "same-capacity-scope-as-replaced-p", "create-distinct-capacity-replacement-path", create_p, ("p-prime-does-not-inherit-purge-witness-or-original-facts", "p-prime-raw-object-and-chunk-hashes-are-absent-from-persona-and-destination-cas", "destination-path-endpoints-and-bindings-are-absent")),
        _operation("w5-export-x", "W5-pre-purge", "nonindexed-export-staging", "emit-nonindexed-byte-exact-export", (), ("export-is-outside-all-twelve-index-and-managed-storage-projections",)),
        _operation("w5-restore-x", "W5-pre-purge", "same-original-x-leaf-scope", "create-distinct-restored-live-path", restore_x, ("byte-exact-deleted-payload-and-chunk-set-reingested", "deleted-history-endpoint-count-equals-qXR-and-becomes-current", "same-original-scope-raw-and-chunk-cas-objects-exist-and-are-reused", "destination-live-path-and-binding-are-absent", "destination-index-succeeds")),
        _operation("w5-delete-x-prime", "W5-pre-purge", "same-capacity-scope-as-paired-x-prime", "remove-live-retain-deleted-binding", delete_x_prime, ("paired-one-to-one-with-restored-x", "paired-x-prime-current-endpoint-count-equals-qXR", "exactly-one-live-x-prime-source-path-before-delete")),
        _operation("w5-purge-p", "W5-final", "same-bound-leaf-scope", "remove-all-live-and-history-bindings", purge, ("original-p-has-exactly-two-disjoint-qP-chunk-versions", "raw-chunks-facts-and-purge-witness-have-no-other-reference", "p-prime-current-confirmed-before-purge")),
        _operation("w5-forced-purged-commit", "W5-final", "same-bound-leaf-scope", "commit-purged-state", (), ("corresponding-purge-completed",)),
        _operation("w5-post-purge-noop-index", "W5-final", "each-of-twenty-leaf-scopes", "scope-only-no-path-transition", (), ("all-persona-purges-and-forced-commits-completed",)),
    ]


def _scope_rules():
    return [
        {"concrete_scope_present": False, "rule_key": "same-bound-leaf-scope", "same_persona": True, "same_scope": True},
        {"concrete_scope_present": False, "different_scope": True, "rule_key": "different-leaf-scope-same-persona", "same_persona": True},
        {"concrete_scope_present": False, "rule_key": "same-or-downstream-selected-leaf-scope", "same_persona": True, "solver_choice_required": True},
        {"concrete_scope_present": False, "rule_key": "same-capacity-scope-as-replaced-x", "same_persona": True, "same_scope_as_dependency": True},
        {"concrete_scope_present": False, "rule_key": "same-capacity-scope-as-replaced-p", "same_persona": True, "same_scope_as_dependency": True},
        {"concrete_scope_present": False, "indexed_scope": False, "rule_key": "nonindexed-export-staging", "same_persona": True},
        {"concrete_scope_present": False, "rule_key": "same-original-x-leaf-scope", "same_persona": True, "same_scope_as_dependency": True},
        {"concrete_scope_present": False, "rule_key": "same-capacity-scope-as-paired-x-prime", "same_persona": True, "same_scope_as_dependency": True},
        {"all_twenty_scopes_required": True, "concrete_scope_present": False, "rule_key": "each-of-twenty-leaf-scopes", "same_persona": True},
    ]


def _path_rules():
    return [
        {"after_live": True, "before_live": True, "path_relation": "equal", "rule_key": "preserve-relative-path"},
        {"after_live": True, "before_live": True, "parent_relation": "equal", "path_relation": "distinct-basename", "rule_key": "replace-basename-in-same-parent"},
        {"after_live": True, "before_live": True, "path_relation": "different-scope-and-destination-absent", "rule_key": "move-to-different-scope-path"},
        {"after_live": True, "before_live": False, "path_relation": "new-derived-path", "rule_key": "create-distinct-derived-path"},
        {"after_live": True, "before_live": False, "path_relation": "new-duplicate-path", "rule_key": "create-distinct-duplicate-path"},
        {"after_live": False, "before_live": True, "deleted_binding_retained": True, "rule_key": "remove-live-retain-deleted-binding"},
        {"after_live": True, "before_live": False, "path_relation": "new-capacity-replacement-path", "rule_key": "create-distinct-capacity-replacement-path"},
        {"after_live": True, "archive_container_required": True, "before_live": True, "path_relation": "same-scope-archive-child", "rule_key": "move-under-existing-archive-container"},
        {"after_live": True, "before_live": False, "indexed_path": False, "rule_key": "emit-nonindexed-byte-exact-export"},
        {"after_live": True, "before_live": False, "path_relation": "same-scope-new-managed-path", "rule_key": "create-distinct-restored-live-path"},
        {"after_live": False, "before_live": True, "history_binding_retained": False, "rule_key": "remove-all-live-and-history-bindings"},
        {"after_live": False, "before_live": False, "rule_key": "commit-purged-state"},
        {"after_live": False, "before_live": False, "rule_key": "scope-only-no-path-transition", "scope_operation_only": True},
    ]


def _symbol_contracts():
    rows = (
        ("zero", 0, 0, "authored", "all-operation-instances", "exact-additive-identity"),
        ("one", 1, 1, "authored", "one-source-event-instance", "one-regular-file-raw-object-or-inode"),
        ("q", 1, 70, "compiled-source-endpoint-count", "one-source-edit-instance", "source-endpoint-chunk-count"),
        ("qIE", 1, 70, "post-W1-attestation-before-W2-event-compilation", "one-edited-move-source", "equal-edited-old-history-and-new-current-endpoint-count"),
        ("nIM", 5, 5, "authored", "five-source-move-bundle", "distinct-move-source-and-raw-identity-count"),
        ("qIM", 5, 350, "post-W1-attestation-before-W2-event-compilation", "five-source-move-bundle", "four-stable-W0-counts-plus-edited-W1-new-current-count"),
        ("qR", 1, 70, "compiled-source-endpoint-count", "one-source-rename-or-archive-instance", "renamed-source-endpoint-count"),
        ("qD", 1, 70, "compiled-derived-source-endpoint-count", "one-derived-or-duplicate-instance", "derived-or-duplicated-source-endpoint-count"),
        ("qX", 1, 70, "compiled-source-endpoint-count", "one-X-source-instance", "X-source-endpoint-count"),
        ("qP", 1, 70, "compiled-source-endpoint-count", "one-P-source-instance", "P-source-endpoint-count"),
        ("qXR", 1, 70, "compiled-paired-source-endpoint-count", "one-restored-X-and-paired-X-prime-instance", "equal-restored-X-and-paired-X-prime-endpoint-count"),
        ("qN", 1, 70, "compiled-source-endpoint-count", "one-N-source-instance", "N-source-endpoint-count"),
    )
    return [
        {
            "inclusive_maximum": maximum,
            "inclusive_minimum": minimum,
            "instantiation_granularity": granularity,
            "meaning": meaning,
            "resolution_stage": stage,
            "symbol": symbol,
        }
        for symbol, minimum, maximum, stage, granularity, meaning in rows
    ]


def _operation_instantiation_contract():
    return {
        "all_exact_deltas_require_every_operation_precondition": True,
        "collision_or_reference_failure_invalidates_exact_global_and_cas_delta": True,
        "concrete_event_instance_present": False,
        "default_granularity": "one-source-one-operation-instance",
        "duplicate_diagnostic_scope_branches_are_mutually_exclusive": True,
        "five_source_aggregate_operation_keys": ["w2-move"],
        "post_purge_scope_operation_keys": ["w5-post-purge-noop-index"],
        "restore_scope_policy": "same-original-leaf-required-for-history-minus-qXR-and-cas-reuse",
        "source_instance_repetition_owned_by_downstream_compiled-history-plan": True,
        "symbol_values_are_not_observed_or_bound_in_this_catalog": True,
    }


def _move_policies(primary):
    rows = []
    for persona_id in PERSONA_IDS:
        moves = [
            row
            for row in primary
            if row["persona_id"] == persona_id and row["allocation_class"] == "I"
        ]
        stable = [row for row in moves if not row["w1_typed_edit_required"]]
        edited = [row for row in moves if row["w1_typed_edit_required"]]
        if len(stable) != 4 or len(edited) != 1:
            _fail("independent move policy split drifted")
        rows.append(
            {
                "accepted_bundle_component_count": 5,
                "bundle_resolution_stage": "post-W1-attestation-before-W2-event-compilation",
                "edited_move_capability_key": edited[0]["capability_key"],
                "edited_move_new_current_count_inclusive_maximum": 70,
                "edited_move_new_current_count_inclusive_minimum": 1,
                "edited_move_observation_checkpoint": "W1-after-typed-edit-and-index",
                "edited_move_old_history_count_inclusive_maximum": 70,
                "edited_move_old_history_count_inclusive_minimum": 1,
                "edited_move_old_history_endpoint_set_disjoint_from_new_current": True,
                "edited_move_old_history_equals_new_current_count": True,
                "edited_move_receipt_identity_dimensions": [
                    "typed-revision-identity",
                    "source-plan-identity",
                    "source-scope-identity",
                    "chunk-configuration-identity",
                ],
                "edited_w1_current_count_must_equal_move_count": True,
                "failure_modes_block_w2": [
                    "missing-observation",
                    "zero-observation",
                    "per-source-outside-1-through-70",
                    "bundle-total-outside-5-through-350",
                    "source-or-plan-identity-mismatch",
                    "typed-revision-or-scope-identity-mismatch",
                    "chunk-configuration-mismatch",
                    "old-history-and-new-current-endpoint-overlap",
                    "old-history-and-new-current-count-mismatch",
                    "duplicate-source-or-observation",
                    "edited-w1-count-differs-from-pre-move-count",
                ],
                "nIM_exact": 5,
                "persona_id": persona_id,
                "qIE_definition": "edited-source-W1-old-history-endpoint-count-equal-to-new-current-count",
                "qIE_inclusive_maximum": 70,
                "qIE_inclusive_minimum": 1,
                "qIM_definition": "sum-of-four-W0-stable-current-counts-plus-edited-W1-new-current-count",
                "qIM_inclusive_maximum": 350,
                "qIM_inclusive_minimum": 5,
                "receipt_attested": False,
                "source_observation_inclusive_maximum": 70,
                "source_observation_inclusive_minimum": 1,
                "stable_move_capability_keys": [
                    row["capability_key"] for row in stable
                ],
                "stable_move_observation_count": 4,
                "stable_move_observation_checkpoint": "W0-after-offline-index",
                "stable_move_receipt_identity_dimensions": [
                    "source-plan-identity",
                    "source-scope-identity",
                    "chunk-configuration-identity",
                ],
                "symbolic_delta_contract": {
                    "W1-incidental-history-only": "+qIE",
                    "W2-chunk-cas-and-history-bindings": "+qIM",
                    "W2-incidental-history-only": "+qIM",
                    "W2-raw-cas-objects-and-inodes": "+nIM",
                },
                "w5_pre_incidental_cap_proof": {
                    "full_cap": 20_400,
                    "full_headroom": 9_780,
                    "full_upper": 10_620,
                    "pilot_cap": 2_040,
                    "pilot_headroom": 600,
                    "pilot_upper": 1_440,
                    "upper_formula": "incidental-current-upper-plus-qIE-upper-plus-qIM-upper",
                },
            }
        )
    return rows


def _dependency_bindings(dependency_values):
    values = (
        dependency_values["envelope"],
        dependency_values["accounting"],
        dependency_values["lifecycle"],
        dependency_values["overlay"],
        dependency_values["semantic_catalog"],
    )
    rows = []
    for (name, role, kind, schema), value in zip(_DEPENDENCIES, values):
        if type(value) is not dict:
            _fail(f"{name} must be an object")
        expected_identity = {
            "artifact_kind": kind,
            "artifact_schema": schema,
            "fixture_id": FIXTURE_ID,
            "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
            "g0_contract_frozen": False,
        }
        for field, expected in expected_identity.items():
            if type(value.get(field)) is not type(expected) or value.get(field) != expected:
                _fail(f"{name} identity or authority drifted")
        authority = value.get("authority")
        if type(authority) is not dict or not authority or any(
            type(flag) is not bool or flag is not False
            for flag in authority.values()
        ):
            _fail(f"{name} unexpectedly authorizes downstream work")
        raw = _canonical(
            value,
            label=f"{name} dependency",
            max_bytes=MAX_DEPENDENCY_BYTES,
        )
        pin = (len(raw), hashlib.sha256(raw).hexdigest())
        if pin != EXPECTED_DEPENDENCY_PINS[name]:
            _fail(f"{name} differs from its frozen dependency pin")
        rows.append(
            {
                "artifact_kind": value["artifact_kind"],
                "artifact_schema": value["artifact_schema"],
                "artifact_schema_version": value["artifact_schema_version"],
                "canonical_bytes": pin[0],
                "dependency_role": role,
                "fixture_id": value["fixture_id"],
                "fixture_schema_version": value["fixture_schema_version"],
                "name": name,
                "sha256": pin[1],
            }
        )
    return rows


def _historical_receipt(dependency_values):
    lifecycle = dependency_values["lifecycle"]
    semantic_catalog = dependency_values["semantic_catalog"]
    try:
        suite_counts = lifecycle["suite_summary"][
            "allocation_class_capability_counts"
        ]
        old_counts = {
            key: value // len(PERSONA_IDS)
            for key, value in suite_counts.items()
        }
        lifecycle_match = lifecycle["completion_claims"][
            "source_instance_matching_complete"
        ]
        boundary_match = lifecycle["boundary_assertions"][
            "source_instance_matching_complete"
        ]
        rendition_complete = dependency_values["overlay"]["completion_claims"][
            "format_rendition_semantics_complete"
        ]
    except (KeyError, TypeError, ZeroDivisionError) as error:
        raise PersonaV2LifecycleCoverageCatalogValidationError(
            "historical dependency evidence is malformed"
        ) from error
    if not _strict_equal(
        old_counts, {"P": 15, "X": 20, "Y": 30, "N": 0, "U": 35, "I": 5}
    ):
        _fail("historical lifecycle allocation no longer matches its frozen receipt")
    if lifecycle_match is not False or boundary_match is not False or rendition_complete is not False:
        _fail("historical inputs unexpectedly claim source or rendition completion")
    expected_cycle = (
        "singleton-index-equals-semantic-anchor-slot-ordinal-minus-one-"
        "modulo-32-in-fact-slot-then-graph-slot-order"
    )
    try:
        cycle = semantic_catalog["assignment_contract"][
            "singleton_anchor_profile_cycle"
        ]
        source_bound = semantic_catalog["completion_claims"][
            "concrete_source_membership_bound"
        ]
        history_bound = semantic_catalog["completion_claims"][
            "history_membership_bound"
        ]
        fact_profiles = semantic_catalog["fact_profiles"]
        semantic_bindings = semantic_catalog["input_bindings"]
    except (KeyError, TypeError) as error:
        raise PersonaV2LifecycleCoverageCatalogValidationError(
            "semantic catalog evidence is malformed"
        ) from error
    if cycle != expected_cycle or source_bound is not False or history_bound is not False:
        _fail("semantic catalog cycle or negative boundary drifted")
    positions_by_persona = []
    for persona_id in PERSONA_IDS:
        singleton_profiles = [
            row
            for row in fact_profiles
            if row.get("persona_id") == persona_id
            and row.get("profile_kind") == "w0-singleton"
        ]
        if len(singleton_profiles) != 32:
            _fail("semantic catalog singleton profile count drifted")
        positions_by_persona.append(
            [
                ordinal
                for ordinal, row in enumerate(singleton_profiles, start=1)
                if row.get("fact_profile_id", "").endswith("-singleton-s05-v2")
            ]
        )
    if any(positions != [17, 18, 19, 20] for positions in positions_by_persona):
        _fail("semantic catalog W1-prior singleton positions drifted")
    if sum(
        type(row) is dict and row.get("name") == "persona-v2-fact-graph"
        for row in semantic_bindings
    ) != 20:
        _fail("semantic catalog fact-graph binding count drifted")
    prior_positions = positions_by_persona[0]
    available_prior = sum(
        ((ordinal - 1) % 32) + 1 in prior_positions
        for ordinal in range(1, 106)
    )
    return {
        "available_w1_prior_semantic_anchor_count_per_persona": available_prior,
        "corrected_allocation_class_counts_per_persona": {"P": 15, "X": 20, "Y": 33, "N": 0, "U": 32, "I": 5},
        "corrected_cross_format_rendition_companion_count_per_persona": 10,
        "corrected_purge_only_witness_count_per_persona": 15,
        "corrected_w1_edited_source_ref_count_per_persona": 70,
        "historical_allocation_class_counts_per_persona": old_counts,
        "historical_format_rendition_group_count_per_persona": 0,
        "historical_purge_only_witness_count_per_persona": 0,
        "historical_required_w1_revision_capability_count_per_persona": (
            old_counts["P"] + old_counts["X"] + old_counts["Y"]
        ),
        "historical_w1_revision_anchor_deficit_per_persona": (
            old_counts["P"] + old_counts["X"] + old_counts["Y"] - available_prior
        ),
        "immutable_lifecycle_body_mutated": False,
        "mismatched_unedited_replacement_fact_capability_count_per_persona": 4,
        "receipt_scope": "deterministic-design-reconciliation-not-source-instance-attestation",
        "semantic_anchor_assignment_root_bound": False,
        "semantic_anchor_source_instance_assignment_attested": False,
        "semantic_anchor_profile_cycle_length": 32,
        "semantic_anchor_slot_count_per_persona": 105,
        "semantic_catalog_singleton_cycle_authenticated": True,
        "semantic_catalog_transitively_bound_fact_graph_count": 20,
        "singleton_prior_profile_positions_one_based": prior_positions,
        "singleton_prior_state_rule": "transitively-bound-fact-graph-s05-W0-current-becomes-W1-history-only",
        "source_instance_evidence_bound": False,
        "source_matchable_authority": False,
        "supersession_reason_count": 4,
        "supersession_reasons": [
            "w1-prior-anchor-capacity-is-insufficient",
            "four-replacement-fact-capabilities-are-in-unedited-u-or-i-classes",
            "two-family-rendition-relation-is-absent",
            "purge-only-unique-witness-facts-are-absent",
        ],
    }


def _suite_summary(primary, companions, witnesses):
    allocation = {key: 0 for key in ALLOCATION_CLASS_ORDER}
    for row in primary:
        allocation[row["allocation_class"]] += 1
    return {
        "allocation_class_primary_counts": allocation,
        "cross_format_companion_requirement_count": len(companions),
        "matched_w0_source_ref_requirement_count": len(primary) + len(companions),
        "persona_count": len(PERSONA_IDS),
        "primary_capability_count": len(primary),
        "primary_capability_count_per_persona": 105,
        "purge_witness_requirement_count": len(witnesses),
        "reserved_unused_semantic_anchor_slot_count": 100,
        "w1_edited_source_ref_requirement_count": 1_400,
    }


def _expected_body(dependency_values):
    bindings = _dependency_bindings(dependency_values)
    primary = _primary_capabilities()
    companions = _companions(primary)
    witnesses = _witnesses(primary)
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "capability_class_contracts": _class_contracts(),
        "completion_claims": {
            "all_2100_primary_capabilities_authored": True,
            "all_200_rendition_companion_requirements_authored": True,
            "all_300_purge_witness_requirements_authored": True,
            "compiled_history_plan_available": False,
            "concrete_source_instance_matching_complete": False,
            "evaluation_target_mapping_complete": False,
            "full_symbolic_operation_path_scope_algebra_authored": True,
            "historical_lifecycle_source_matchability_reconciled": True,
            "observed_move_receipts_attested": False,
            "query_or_oracle_dependency_present": False,
            "solved_scope_path_quota_or_final_ids_present": False,
        },
        "completion_scope": (
            "query-independent-lifecycle-coverage-and-symbolic-algebra-only-"
            "no-source-matching-no-query-oracle-no-solution-no-execution-no-g0"
        ),
        "cross_format_companion_requirements": companions,
        "dependency_direction_contract": {
            "allowed_downstream_consumers": [
                "corpus-semantic-namespace-builder",
                "evaluation-target-resolution-builder",
                "source-matched-lifecycle-intent-builder",
            ],
            "catalog_is_common_upstream_of_corpus_and_evaluation_resolution": True,
            "corpus_source_matching_may_import_query_or_oracle": False,
            "evaluation_target_resolution_may_back_bind_source_matching": False,
            "query_or_oracle_body_or_hash_present": False,
        },
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "historical_lifecycle_source_matchability_receipt": _historical_receipt(dependency_values),
        "historical_symbolic_algebra_reconciliation": {
            "duplicate_diagnostic_preserves_downstream_scope_choice_via_same_and-cross-scope-branches": True,
            "edited_move_receipt_timing_supersedes_historical-W0-only-qIM-timing": True,
            "historical_lifecycle_demand_is_execution_authority": False,
            "nonindexed_export_is_outside_all_twelve-authenticated-projections": True,
            "restore_is_narrowed_to-original-scope-for-exact-history-transition-and-cas-reuse": True,
        },
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
        "move_receipt_policies": _move_policies(primary),
        "operation_algebra": _operations(),
        "operation_instantiation_contract": _operation_instantiation_contract(),
        "orders": {
            "allocation_class_order": list(ALLOCATION_CLASS_ORDER),
            "persona_order": list(PERSONA_IDS),
            "wave_order": list(WAVE_ORDER),
        },
        "path_transition_rules": _path_rules(),
        "primary_capabilities": primary,
        "purge_witness_requirements": witnesses,
        "remaining_blockers": [
            "203000-source-instance-parameter-assignment-not-bound",
            "source-matched-lifecycle-intent-not-built",
            "lifecycle-fact-and-rendition-overlay-not-built",
            "scope-bucket-cohort-quota-solution-and-proof-not-built",
            "solution-compiled-history-plan-and-pre-w2-patch-not-built",
            "evaluation-target-resolution-query-render-and-compiled-relevance-not-built",
            "filesystem-render-index-history-kio-receipts-and-g0-not-built",
        ],
        "scope_relation_rules": _scope_rules(),
        "source_matching_domain": {
            "concrete_intent_key_present": False,
            "full_must_reuse_pilot_primary_and_companion_selection": True,
            "incidental_primary_source_count_per_persona": 5,
            "w0_source_ref_requirement_count_per_persona": 115,
            "pilot_contributor_primary_count_per_persona": 100,
            "pilot_cross_format_companion_count_per_persona": 10,
            "semantic_anchor_slots_consumed_per_persona": 100,
            "semantic_anchor_slots_reserved_unused_per_persona": 5,
            "solved_scope_path_quota_and_final_identity_present": False,
        },
        "suite_summary": _suite_summary(primary, companions, witnesses),
        "symbol_contracts": _symbol_contracts(),
    }


def _assert_forbidden_later_layer_fields_absent(value):
    forbidden = {
        "absolute_path",
        "assigned_scope_key",
        "chunk_id",
        "final_materialization_id",
        "final_source_id",
        "materialization_id",
        "oracle_key",
        "oracle_sha256",
        "planned_materialization_id",
        "planned_source_id",
        "query_body_sha256",
        "query_id",
        "query_intent_key",
        "query_key",
        "query_text",
        "raw_id",
        "relative_path",
        "semantic_oracle",
        "solved_scope_key",
        "source_id",
        "source_instance_key",
    }
    forbidden_artifact_fragments = (
        "query-intent",
        "semantic-oracle",
        "evaluation-oracle",
    )
    if type(value) is list:
        for item in value:
            _assert_forbidden_later_layer_fields_absent(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in forbidden:
            _fail("concrete source, evaluation, scope, path, or identity field is present")
        if key in {"artifact_kind", "artifact_schema", "name"} and type(item) is str:
            if any(fragment in item for fragment in forbidden_artifact_fragments):
                _fail("catalog contains a forbidden evaluation dependency")
        _assert_forbidden_later_layer_fields_absent(item)


def _validate_reconstructed_invariants(value):
    primary = value["primary_capabilities"]
    companions = value["cross_format_companion_requirements"]
    witnesses = value["purge_witness_requirements"]

    if len(primary) != 2_100 or len(companions) != 200 or len(witnesses) != 300:
        _fail("coverage catalog suite cardinality drifted")
    seen_capability = {row["capability_key"] for row in primary}
    seen_slot = {row["logical_document_slot_key"] for row in primary}
    seen_witness = {row["purge_witness_key"] for row in witnesses}
    if len(seen_capability) != 2_100 or len(seen_slot) != 2_100 or len(seen_witness) != 300:
        _fail("capability, logical-document, or purge-witness identity is not unique")

    for persona_id in PERSONA_IDS:
        persona_primary = [row for row in primary if row["persona_id"] == persona_id]
        persona_companions = [row for row in companions if row["persona_id"] == persona_id]
        persona_witnesses = [row for row in witnesses if row["persona_id"] == persona_id]
        allocation = {key: 0 for key in ALLOCATION_CLASS_ORDER}
        for row in persona_primary:
            allocation[row["allocation_class"]] += 1
            if row["source_matching_status"] != "unbound":
                _fail("a primary capability was source matched")
        if not _strict_equal(
            allocation,
            {"P": 15, "X": 20, "Y": 33, "N": 0, "U": 32, "I": 5},
        ):
            _fail("corrected per-persona allocation split drifted")
        if len(persona_primary) != 105 or len(persona_companions) != 10 or len(persona_witnesses) != 15:
            _fail("per-persona primary, companion, or witness count drifted")
        if any(row["source_matching_status"] != "unbound" for row in persona_companions):
            _fail("a rendition companion was source matched")
        edited_primary = sum(
            row["w1_typed_edit_required"] is True for row in persona_primary
        )
        edited_companions = sum(
            row["w1_typed_edit_required"] is True for row in persona_companions
        )
        if edited_primary != 69 or edited_companions != 1:
            _fail("the exact 70 W1-edited source-ref requirement drifted")
        incidental = [row for row in persona_primary if row["allocation_class"] == "I"]
        if (
            sum(row["w1_typed_edit_required"] is False for row in incidental) != 4
            or sum(row["w1_typed_edit_required"] is True for row in incidental) != 1
        ):
            _fail("the four-stable plus one-edited move split drifted")

    primary_keys = {row["capability_key"] for row in primary}
    if any(row["primary_capability_key"] not in primary_keys for row in companions):
        _fail("a rendition companion lacks its primary capability")
    if any(row["capability_key"] not in primary_keys for row in witnesses):
        _fail("a purge witness lacks its primary capability")

    operation_keys = {row["operation_key"] for row in value["operation_algebra"]}
    scope_keys = {row["rule_key"] for row in value["scope_relation_rules"]}
    path_keys = {row["rule_key"] for row in value["path_transition_rules"]}
    if len(operation_keys) != 19 or len(scope_keys) != 9 or len(path_keys) != 13:
        _fail("operation, scope, or path symbolic algebra cardinality drifted")
    symbol_rows = value["symbol_contracts"]
    symbol_keys = {row["symbol"] for row in symbol_rows}
    if len(symbol_keys) != 12:
        _fail("symbol contract is missing or duplicated")
    for operation in value["operation_algebra"]:
        if operation["scope_relation_rule_key"] not in scope_keys:
            _fail("operation references an unknown scope rule")
        if operation["path_transition_rule_key"] not in path_keys:
            _fail("operation references an unknown path rule")
        if len(operation["delta_terms"]) != len(_PROJECTIONS):
            _fail("operation does not close over the full projection algebra")
        terms = [
            (term["metric_id"], term["projection"])
            for term in operation["delta_terms"]
        ]
        if terms != list(_PROJECTIONS):
            _fail("operation projection order or coverage drifted")
        for term in operation["delta_terms"]:
            if type(term["coefficient"]) is not int or term["coefficient"] < 0:
                _fail("operation coefficient is not an exact nonnegative integer")
            if term["direction"] not in {"preserve", "increase", "decrease"}:
                _fail("operation direction is outside the closed algebra")
            if (term["direction"] == "preserve") != (
                term["coefficient"] == 0 and term["symbol"] == "zero"
            ):
                _fail("preserve terms must be exact symbolic zero and vice versa")
            if term["symbol"] not in symbol_keys:
                _fail("operation references an undefined symbol")

    authority = value["authority"]
    if set(authority) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        _fail("coverage catalog authority must be exact and all false")
    if value["g0_contract_frozen"] is not False:
        _fail("coverage catalog cannot freeze G0")
    if value["completion_claims"]["concrete_source_instance_matching_complete"] is not False:
        _fail("source matching must remain incomplete")
    if value["source_matching_domain"]["concrete_intent_key_present"] is not False:
        _fail("a concrete lifecycle intent was bound")
    if value["historical_lifecycle_source_matchability_receipt"]["source_matchable_authority"] is not False:
        _fail("historical lifecycle demand was treated as source-matchable authority")


def _validate_snapshot(value, dependency_values):
    _assert_forbidden_later_layer_fields_absent(value)
    expected = _expected_body(dependency_values)
    if not _strict_equal(value, expected):
        _fail("lifecycle coverage catalog differs from independent reconstruction")
    _validate_reconstructed_invariants(value)
    return True


def validate_lifecycle_coverage_catalog(
    value,
    *,
    envelope_value,
    chunk_accounting_value,
    lifecycle_demand_value,
    overlay_contract_value,
    source_semantic_catalog_value,
    validation_observer=None,
):
    """Validate detached catalog and dependency snapshots independently."""

    value_snapshot, value_raw = _snapshot(
        value,
        label="persona v2 lifecycle coverage catalog",
        max_bytes=MAX_CATALOG_BYTES,
    )
    originals = {
        "envelope": envelope_value,
        "accounting": chunk_accounting_value,
        "lifecycle": lifecycle_demand_value,
        "overlay": overlay_contract_value,
        "semantic_catalog": source_semantic_catalog_value,
    }
    snapshots = {}
    opening_raw = {}
    for key, dependency in originals.items():
        snapshots[key], opening_raw[key] = _snapshot(
            dependency,
            label=f"persona v2 lifecycle coverage {key} input",
            max_bytes=MAX_DEPENDENCY_BYTES,
        )
    try:
        pin = (len(value_raw), hashlib.sha256(value_raw).hexdigest())
        if pin != (EXPECTED_CATALOG_CANONICAL_BYTES, EXPECTED_CATALOG_SHA256):
            _fail("lifecycle coverage catalog differs from its installed canonical body pin")
        if validation_observer is not None:
            validation_observer(value, originals)
        return _validate_snapshot(value_snapshot, snapshots)
    finally:
        _reauth(
            value,
            value_raw,
            label="lifecycle coverage catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
        for key, dependency in originals.items():
            _reauth(
                dependency,
                opening_raw[key],
                label=f"lifecycle coverage {key} input",
                max_bytes=MAX_DEPENDENCY_BYTES,
            )
