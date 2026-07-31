"""Non-authorizing conditional history semantics for persona-PC fidelity v2.

This is a pre-solve vertical slice, not a compiled event plan.  The joint
solver has not assigned a history cohort, scope, quota, source identity, or
materialization identity.  Consequently this artifact only defines
conditional cohort templates, the one W0-to-W1 typed-fact transition required
by the bound representative membership, surface-edit carry-forward rules, and
delete/restore lifecycle dependency templates.

No row in this module authorizes filesystem or KIO history mutation.  The
restore/deleted rows are schema prototypes and count as zero of the required
ten distinct anchors per persona.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_membership as fact_membership
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_membership as fact_membership


ARTIFACT_SCHEMA = "kio.persona.pc-history-intent/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-history-intent"
MAX_HISTORY_INTENT_BYTES = 256 * 1024

CHECKPOINT_ORDER = (
    "W0",
    "W1",
    "W2",
    "W3",
    "W4",
    "W5-pre-purge",
    "W5-final",
)
HISTORY_COHORT_ORDER = ("P", "X", "Y", "N", "U")

_EVENT_TEMPLATE_ROWS = (
    (
        "history-template-w1-typed-small-edit-v1",
        "W1",
        "edit",
        "typed-fact-revision",
        True,
        False,
        "typed-revision-symmetric-difference",
        "apply-bound-typed-revision",
    ),
    (
        "history-template-w3-surface-major-edit-v1",
        "W3",
        "edit",
        "surface-only",
        True,
        False,
        "exact-empty",
        "exact-carry-forward",
    ),
    (
        "history-template-w5-surface-correction-v1",
        "W5-pre-purge",
        "edit",
        "surface-only",
        True,
        False,
        "exact-empty",
        "exact-carry-forward",
    ),
    (
        "history-template-w5-replacement-create-index-v1",
        "W5-pre-purge",
        "replacement-create-index",
        "structural-copy",
        True,
        True,
        "exact-empty",
        "exact-carry-forward",
    ),
    (
        "history-template-w5-old-path-purge-v1",
        "W5-final",
        "path-purge",
        "structural-only",
        False,
        False,
        "exact-empty",
        "no-new-source-version",
    ),
    (
        "history-template-w5-replacement-current-confirmation-v1",
        "W5-pre-purge",
        "current-confirmation",
        "attestation-only",
        False,
        False,
        "exact-empty",
        "no-new-source-version",
    ),
    (
        "history-template-w4-delete-v1",
        "W4",
        "delete",
        "structural-only",
        False,
        False,
        "exact-empty",
        "no-new-source-version",
    ),
    (
        "history-template-w4-replacement-create-index-v1",
        "W4",
        "replacement-create-index",
        "structural-copy",
        True,
        True,
        "exact-empty",
        "exact-carry-forward",
    ),
    (
        "history-template-w2-same-scope-rename-v1",
        "W2",
        "rename",
        "structural-only",
        False,
        False,
        "exact-empty",
        "no-new-source-version",
    ),
    (
        "history-template-w3-exact-duplicate-v1",
        "W3",
        "exact-duplicate",
        "structural-copy",
        False,
        True,
        "exact-empty",
        "exact-carry-forward",
    ),
    (
        "history-template-w5-restore-v1",
        "W5-pre-purge",
        "restore",
        "structural-restore",
        False,
        True,
        "exact-empty",
        "exact-carry-forward",
    ),
    (
        "history-template-w5-destination-index-v1",
        "W5-pre-purge",
        "destination-index",
        "index-only",
        False,
        False,
        "exact-empty",
        "no-new-source-version",
    ),
    (
        "history-template-w5-forced-purged-commit-v1",
        "W5-final",
        "forced-purged-commit",
        "commit-only",
        False,
        False,
        "exact-empty",
        "no-new-source-version",
    ),
    (
        "history-template-w5-post-purge-noop-index-v1",
        "W5-final",
        "post-purge-noop-index",
        "index-only",
        False,
        False,
        "exact-empty",
        "no-new-source-version",
    ),
)

_COHORT_ROWS = (
    (
        "P",
        (
            "history-template-w1-typed-small-edit-v1",
            "history-template-w5-replacement-create-index-v1",
            "history-template-w5-replacement-current-confirmation-v1",
            "history-template-w5-old-path-purge-v1",
            "history-template-w5-forced-purged-commit-v1",
            "history-template-w5-post-purge-noop-index-v1",
        ),
        (),
    ),
    (
        "X",
        (
            "history-template-w1-typed-small-edit-v1",
            "history-template-w3-surface-major-edit-v1",
            "history-template-w4-delete-v1",
            "history-template-w4-replacement-create-index-v1",
        ),
        (),
    ),
    (
        "Y",
        (
            "history-template-w1-typed-small-edit-v1",
            "history-template-w3-surface-major-edit-v1",
        ),
        (),
    ),
    (
        "N",
        (
            "history-template-w3-surface-major-edit-v1",
            "history-template-w5-surface-correction-v1",
        ),
        (),
    ),
    (
        "U",
        (),
        (
            "history-template-w2-same-scope-rename-v1",
            "history-template-w3-exact-duplicate-v1",
        ),
    ),
)

_PROHIBITED_KEYS = frozenset(
    (
        "absolute_path",
        "actual_chunk_id",
        "actual_event_id",
        "actual_rank",
        "actual_source_id",
        "assigned_history_cohort_id",
        "assigned_scope_key",
        "chunk_id",
        "final_materialization_id",
        "final_source_id",
        "history_event_id",
        "materialization_id",
        "query_key",
        "raw_sha256",
        "replay_root",
        "runtime_timestamp",
        "source_id",
    )
)


class PersonaV2HistoryIntentError(ValueError):
    """Raised when conditional history semantics drift or imply execution."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2HistoryIntentError(f"unknown persona: {persona_id!r}")
    return persona_id


def _canonical_fact_ids(fact_ids, *, label):
    if (
        type(fact_ids) is not list
        or not fact_ids
        or any(type(fact_id) is not str or not fact_id for fact_id in fact_ids)
        or fact_ids != sorted(fact_ids)
        or len(fact_ids) != len(set(fact_ids))
    ):
        raise PersonaV2HistoryIntentError(
            f"{label} must be a non-empty sorted unique fact-ID list"
        )
    return list(fact_ids)


def apply_typed_revision(present_fact_ids, revision_membership):
    """Apply one bound typed revision and return exact W1 memberships.

    ``changed_fact_ids`` is the symmetric difference between complete before
    and after memberships.  The function rejects an already-applied or partial
    revision so a compiled plan cannot silently double-apply it.
    """

    before = _canonical_fact_ids(present_fact_ids, label="pre-revision membership")
    if type(revision_membership) is not dict or set(revision_membership) != {
        "current_fact_id",
        "prior_fact_ids",
        "revision_chain_id",
    }:
        raise PersonaV2HistoryIntentError("typed revision membership shape drifted")
    prior = _canonical_fact_ids(
        revision_membership["prior_fact_ids"], label="prior revision facts"
    )
    current = revision_membership["current_fact_id"]
    revision_chain_id = revision_membership["revision_chain_id"]
    if type(current) is not str or not current:
        raise PersonaV2HistoryIntentError("current revision fact must be a string")
    if type(revision_chain_id) is not str or not revision_chain_id:
        raise PersonaV2HistoryIntentError("revision chain ID must be a string")
    before_set = set(before)
    prior_set = set(prior)
    if not prior_set <= before_set or current in before_set:
        raise PersonaV2HistoryIntentError(
            "typed revision requires every prior fact present and current fact absent"
        )
    after = sorted((before_set - prior_set) | {current})
    changed = sorted(before_set ^ set(after))
    if changed != sorted(prior + [current]):
        raise PersonaV2HistoryIntentError(
            "typed revision changed membership is not the exact symmetric difference"
        )
    return {"changed_fact_ids": changed, "present_fact_ids": after}


def require_surface_carry_forward(before_fact_ids, after_fact_ids, changed_fact_ids):
    """Fail closed unless a surface edit preserves the exact full membership."""

    before = _canonical_fact_ids(before_fact_ids, label="surface before membership")
    after = _canonical_fact_ids(after_fact_ids, label="surface after membership")
    if type(changed_fact_ids) is not list or changed_fact_ids != []:
        raise PersonaV2HistoryIntentError(
            "surface edit changed_fact_ids must be the exact empty list"
        )
    if after != before:
        raise PersonaV2HistoryIntentError(
            "surface edit must carry the exact prior present_fact_ids list"
        )
    return True


def _assert_no_prohibited_keys(value):
    if type(value) is list:
        for item in value:
            _assert_no_prohibited_keys(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in _PROHIBITED_KEYS:
            raise PersonaV2HistoryIntentError(f"prohibited history field: {key}")
        _assert_no_prohibited_keys(item)


def _sha256_paths(value, path=()):
    result = set()
    if type(value) is dict:
        for key, item in value.items():
            child = path + (key,)
            if key == "sha256" or key.endswith("_sha256"):
                result.add(child)
            result.update(_sha256_paths(item, child))
    elif type(value) is list:
        for item in value:
            result.update(_sha256_paths(item, path + ("[]",)))
    return frozenset(result)


def _envelope_binding():
    value = envelope.build_envelope_contract()
    envelope.validate_envelope_contract(value)
    raw = envelope.canonical_json_bytes(value)
    digest = envelope.envelope_contract_sha256(value)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise PersonaV2HistoryIntentError("envelope binding digest drifted")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": "history-scale",
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": "envelope",
        "sha256": digest,
    }


def _membership_binding(persona_id, value):
    fact_membership.validate_fact_membership(persona_id, value)
    raw = fact_membership.canonical_json_bytes(value)
    digest = fact_membership.fact_membership_sha256(persona_id, value)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise PersonaV2HistoryIntentError("fact membership binding digest drifted")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": "semantic-membership",
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": "fact-membership",
        "persona_id": persona_id,
        "sha256": digest,
    }


def _event_templates():
    rows = []
    for (
        template_key,
        wave,
        operation_kind,
        semantic_change_mode,
        creates_source_version,
        creates_materialization,
        changed_rule,
        present_rule,
    ) in _EVENT_TEMPLATE_ROWS:
        creates_source = operation_kind == "replacement-create-index"
        rows.append(
            {
                "changed_fact_ids_rule": changed_rule,
                "creates_materialization": creates_materialization,
                "creates_source": creates_source,
                "creates_source_version": creates_source_version,
                "event_template_key": template_key,
                "operation_kind": operation_kind,
                "present_fact_ids_rule": present_rule,
                "semantic_change_mode": semantic_change_mode,
                "wave": wave,
            }
        )
    keys = [row["event_template_key"] for row in rows]
    if len(keys) != len(set(keys)):
        raise PersonaV2HistoryIntentError("history event template keys must be unique")
    for row in rows:
        if row["semantic_change_mode"] == "surface-only":
            if (
                row["changed_fact_ids_rule"] != "exact-empty"
                or row["present_fact_ids_rule"] != "exact-carry-forward"
                or row["wave"] not in {"W3", "W5-pre-purge"}
            ):
                raise PersonaV2HistoryIntentError("surface event semantics drifted")
    return rows


def _cohort_templates(event_templates):
    known = {row["event_template_key"] for row in event_templates}
    dependency_pairs = {
        "P": (
            (
                "history-template-w5-replacement-create-index-v1",
                "history-template-w5-replacement-current-confirmation-v1",
            ),
            (
                "history-template-w5-replacement-current-confirmation-v1",
                "history-template-w5-old-path-purge-v1",
            ),
            (
                "history-template-w5-old-path-purge-v1",
                "history-template-w5-forced-purged-commit-v1",
            ),
            (
                "history-template-w5-forced-purged-commit-v1",
                "history-template-w5-post-purge-noop-index-v1",
            ),
        ),
        "X": (
            (
                "history-template-w4-delete-v1",
                "history-template-w4-replacement-create-index-v1",
            ),
        ),
        "Y": (),
        "N": (),
        "U": (),
    }
    rows = []
    for cohort_id, required, optional in _COHORT_ROWS:
        if not set(required + optional) <= known:
            raise PersonaV2HistoryIntentError("cohort references an unknown template")
        rows.append(
            {
                "allowed_optional_event_template_keys": list(optional),
                "dependency_edges": [
                    {
                        "from_event_template_key": source,
                        "relation_kind": "must-complete-before",
                        "to_event_template_key": target,
                    }
                    for source, target in dependency_pairs[cohort_id]
                ],
                "history_cohort_id": cohort_id,
                "required_event_template_keys": list(required),
            }
        )
    if [row["history_cohort_id"] for row in rows] != list(HISTORY_COHORT_ORDER):
        raise PersonaV2HistoryIntentError("history cohort order drifted")
    return rows


def _lifecycle_templates():
    restored_states = (
        "current",
        "current",
        "current",
        "current",
        "deleted",
        "current-restored",
        "current-restored",
    )
    deleted_states = (
        "current",
        "current",
        "current",
        "current",
        "deleted",
        "deleted",
        "final-deleted",
    )
    return [
        {
            "checkpoint_states": [
                {"checkpoint": checkpoint, "state": state}
                for checkpoint, state in zip(CHECKPOINT_ORDER, restored_states)
            ],
            "counts_toward_required_anchor_inventory": False,
            "dependency_edges": [
                {
                    "from_event_template_key": "history-template-w4-delete-v1",
                    "relation_kind": "must-complete-before",
                    "to_event_template_key": "history-template-w5-restore-v1",
                },
                {
                    "from_event_template_key": "history-template-w5-restore-v1",
                    "relation_kind": "must-complete-before",
                    "to_event_template_key": "history-template-w5-destination-index-v1",
                },
            ],
            "distinct_logical_documents_required_per_persona": 10,
            "destination_index_receipt_required": True,
            "event_template_keys": [
                "history-template-w4-delete-v1",
                "history-template-w5-restore-v1",
                "history-template-w5-destination-index-v1",
            ],
            "include_deleted_required": False,
            "lifecycle_template_key": "lifecycle-template-current-restored-v1",
            "lifecycle_receipt_required": True,
            "new_materialization_required": True,
            "prototype_instance_count": 0,
            "required_evidence_state": "current-restored",
            "restored_but_unindexed_satisfies": False,
            "same_content_other_current_copy_satisfies": False,
            "searchable_contract_contributor_required": True,
            "suite_distinct_logical_document_minimum": 200,
        },
        {
            "checkpoint_states": [
                {"checkpoint": checkpoint, "state": state}
                for checkpoint, state in zip(CHECKPOINT_ORDER, deleted_states)
            ],
            "counts_toward_required_anchor_inventory": False,
            "dependency_edges": [],
            "distinct_logical_documents_required_per_persona": 10,
            "destination_index_receipt_required": False,
            "event_template_keys": ["history-template-w4-delete-v1"],
            "include_deleted_required": True,
            "lifecycle_template_key": "lifecycle-template-final-deleted-v1",
            "lifecycle_receipt_required": True,
            "new_materialization_required": False,
            "prototype_instance_count": 0,
            "required_evidence_state": "final-deleted",
            "restored_but_unindexed_satisfies": False,
            "same_content_other_current_copy_satisfies": False,
            "searchable_contract_contributor_required": True,
            "suite_distinct_logical_document_minimum": 200,
        },
    ]


def _checkpoint_contract():
    rows = {}
    for profile in ("pilot", "full"):
        rows[profile] = [
            {
                "checkpoint": checkpoint,
                "current_contract_chunks": envelope.HISTORY_CHECKPOINTS[profile][
                    checkpoint
                ][0],
                "history_only_contract_chunks": envelope.HISTORY_CHECKPOINTS[profile][
                    checkpoint
                ][1],
            }
            for checkpoint in CHECKPOINT_ORDER
        ]
    return rows


def _canonical_history_intent(persona_id, *, membership_value=None):
    _require_persona_id(persona_id)
    membership = (
        fact_membership.build_fact_membership(persona_id)
        if membership_value is None
        else membership_value
    )
    fact_membership.validate_fact_membership(persona_id, membership)
    member = membership["memberships"][0]
    if member["allowed_history_cohort_ids"] != ["P", "X", "Y"]:
        raise PersonaV2HistoryIntentError(
            "bound W0 revision membership must remain solver-eligible only for P/X/Y"
        )
    if len(member["revision_memberships"]) != 1:
        raise PersonaV2HistoryIntentError(
            "representative history transition requires exactly one revision chain"
        )
    transition = apply_typed_revision(
        member["present_fact_ids"], member["revision_memberships"][0]
    )
    require_surface_carry_forward(
        transition["present_fact_ids"], transition["present_fact_ids"], []
    )
    event_templates = _event_templates()
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_solver_execution": False,
            "compiled_history_plan_available": False,
            "filesystem_writer_available": False,
            "formal_capacity_gate_satisfied": False,
            "history_executor_available": False,
            "kio_execution_available": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_HISTORY_INTENT_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "checkpoint_chunk_contract": _checkpoint_contract(),
        "compiled_event_inventory_complete": False,
        "compiled_history_plan": False,
        "completion_scope": (
            "pre-solve-conditional-history-semantics-only-no-cohort-assignment-"
            "no-event-instance-no-path-no-final-identity-no-execution"
        ),
        "conditional_template_catalog_complete": False,
        "event_templates": event_templates,
        "fact_membership_input_complete_for_representative": True,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "history_cohort_templates": _cohort_templates(event_templates),
        "history_executor_available": False,
        "history_intent_inventory_complete": False,
        "history_operation_template_inventory_complete": False,
        "hypothesis_status": "candidate-benchmark-contract-not-executed-history",
        "input_bindings": [
            _envelope_binding(),
            _membership_binding(persona_id, membership),
        ],
        "isolation_policy": {
            "environment_reads_allowed": False,
            "host_identity_reads_allowed": False,
            "network_access_allowed": False,
            "runtime_clock_reads_allowed": False,
            "runtime_randomness_allowed": False,
        },
        "lifecycle_anchor_inventory_complete": False,
        "lifecycle_templates": _lifecycle_templates(),
        "persona_id": persona_id,
        "pilot_event_template_and_compiled_plan_byte_subset_proved": False,
        "remaining_blockers": [
            "solver-history-cohort-assignment-not-available",
            "exact-source-event-inventory-not-available",
            "move-derive-archive-and-create-operation-templates-not-complete",
            "event-flow-chunk-delta-checkpoint-reconciliation-not-implemented",
            "pilot-event-template-and-compiled-plan-byte-subset-not-proved",
            "restore-and-final-deleted-distinct-anchor-instances-not-bound",
            "ten-restored-and-ten-deleted-documents-per-persona-not-bound",
            "event-materialization-index-lifecycle-receipts-not-compiled",
            "scope-path-quota-and-final-identities-not-available",
            "history-executor-and-actual-attestation-not-available",
            "external-frame-header-schema-dispatcher-not-implemented",
            "bounded-loader-not-bound-to-artifact-frame",
        ],
        "representative_transition_constraint": {
            "allowed_history_cohort_ids": copy.deepcopy(
                member["allowed_history_cohort_ids"]
            ),
            "changed_fact_ids_at_w1": transition["changed_fact_ids"],
            "intent_key": member["intent_key"],
            "logical_document_key": member["logical_document_key"],
            "present_fact_set_key_at_w0": member["present_fact_set_key"],
            "present_fact_ids_at_w1": transition["present_fact_ids"],
            "revision_membership": copy.deepcopy(member["revision_memberships"][0]),
            "semantic_revision_boundary": "W0-to-W1-only",
            "solver_assigned_history_cohort_id_present": False,
            "w3_changed_fact_ids": [],
            "w3_present_fact_ids_rule": "exact-carry-forward-from-prior-version",
            "w5_changed_fact_ids": [],
            "w5_present_fact_ids_rule": "exact-carry-forward-from-prior-version",
        },
        "representative_transition_and_lifecycle_template_slice_complete": True,
        "representative_vertical_slice_complete": True,
    }
    _assert_no_prohibited_keys(value)
    if (
        [row.get("name") for row in value["input_bindings"]]
        != ["envelope", "fact-membership"]
        or any(
            type(row.get("sha256")) is not str or len(row["sha256"]) != 64
            for row in value["input_bindings"]
        )
    ):
        raise PersonaV2HistoryIntentError(
            "history dependency binding cardinality or digest drifted"
        )
    if _sha256_paths(value) != frozenset({("input_bindings", "[]", "sha256")}):
        raise PersonaV2HistoryIntentError(
            "history intent has a missing, downstream, or cyclic SHA binding"
        )
    return value


@functools.lru_cache(maxsize=1)
def _canonical_suite_values():
    memberships = fact_membership.build_fact_membership_suite()
    values = tuple(
        _canonical_history_intent(
            persona_id,
            membership_value=membership,
        )
        for persona_id, membership in zip(envelope.PERSONA_IDS, memberships)
    )
    if tuple(value["persona_id"] for value in values) != envelope.PERSONA_IDS:
        raise PersonaV2HistoryIntentError("history suite persona order drifted")
    return values


def build_history_intent(persona_id):
    """Return one detached pre-solve history-intent candidate."""

    _require_persona_id(persona_id)
    index = envelope.PERSONA_IDS.index(persona_id)
    return copy.deepcopy(_canonical_suite_values()[index])


def build_history_intent_suite():
    """Return all twenty detached candidates in canonical persona order."""

    return copy.deepcopy(list(_canonical_suite_values()))


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 history intent",
            max_bytes=MAX_HISTORY_INTENT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2HistoryIntentError(str(error)) from None


def validate_history_intent(persona_id, value):
    _require_persona_id(persona_id)
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=lambda: build_history_intent(persona_id),
            label="persona v2 history intent",
            max_bytes=MAX_HISTORY_INTENT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2HistoryIntentError(str(error)) from None


def history_intent_sha256(persona_id, value=None):
    _require_persona_id(persona_id)
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=lambda: build_history_intent(persona_id),
            label="persona v2 history intent",
            max_bytes=MAX_HISTORY_INTENT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2HistoryIntentError(str(error)) from None


def require_compiled_history_plan():
    raise PersonaV2HistoryIntentError(
        "conditional history templates are not a compiled event plan; solver cohort, "
        "scope/quota, final identity, receipt, executor, and actual attestation remain absent"
    )
