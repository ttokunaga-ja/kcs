"""Representative, non-authorizing persona-PC v2 source-intent shards.

This module implements one *pre-solve* ``pilot`` origin row for every
synthetic owner.  It is a schema and dependency-direction vertical slice, not
the 203,000-source inventory.  Every source-specific value that would make a
row exceed the JSONL record budget is normalized into a shard-local catalog
and referenced by an immutable key.

The source-intent shard is the canonical owner of its W0 ``present_fact_ids``
set.  A later fact-membership body must project that set with exact total-set
equality; it may not add, omit, or duplicate a fact.  The shard deliberately
contains no logical-document identity, history event, evaluation input,
allocation result, final source/materialization identity, or downstream
digest.

Dependency direction is one-way and corpus-only::

    topology / realism / variant / candidate source profile
                          route BODY / typed fact graph
                                      |
                                      v
                         source-intent origin shard

The route review/evidence receipt is intentionally not imported or hashed.
Future identity namespaces must use content-affecting corpus semantic inputs;
replacing non-content review evidence must not perturb intent bytes.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import re

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_realism_profile as realism
    from . import persona_v2_route_affinity as route_affinity
    from . import persona_v2_source_profile_catalog as source_profiles
    from . import persona_v2_topology as topology
    from . import persona_v2_variant_catalog as variants
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_realism_profile as realism
    import persona_v2_route_affinity as route_affinity
    import persona_v2_source_profile_catalog as source_profiles
    import persona_v2_topology as topology
    import persona_v2_variant_catalog as variants


ARTIFACT_SCHEMA = "kio.persona.pc-source-intent-origin-shard/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-source-intent-origin-shard"

MAX_SHARD_BYTES = 4 * 2**20
MAX_INTENTS_PER_SHARD = 4_096
MAX_PERSONA_PACKAGE_BYTES = 16 * 2**20
MAX_INTENT_JSONL_RECORD_BYTES = 768
JSONL_RECORD_TERMINATOR = "LF"
JSONL_RECORD_TERMINATOR_BYTES = 1
MAX_INTENT_ROW_BODY_BYTES = (
    MAX_INTENT_JSONL_RECORD_BYTES - JSONL_RECORD_TERMINATOR_BYTES
)
REPRESENTATIVE_INTENTS_PER_PERSONA = 1
MAX_CATALOG_ENTRIES_PER_SHARD = MAX_INTENTS_PER_SHARD
MAX_CATALOG_ID_BYTES = 128
MAX_ELIGIBLE_SCOPE_KEYS_PER_SET = 20
MAX_PRESENT_FACT_IDS_PER_SET = 32
MAX_SYNTHETIC_ENTITY_IDS_PER_SET = 16

INTENT_ORIGINS = ("pilot", "full-residual")
SOLVER_DELTA_ORIGIN = "full-minus-pilot"

INTENT_ROW_FIELDS = frozenset(
    {
        "content_context_id",
        "deterministic_payload_seed",
        "eligible_scope_set_id",
        "intent_key",
        "origin",
        "persona_id",
        "placement_context_id",
        "present_fact_set_key",
        "quota_context_id",
        "source_profile_id",
    }
)

# These caps make the lexical maximum record independently checkable.  Exact
# regenerated artifacts impose the stronger semantic/reference constraints.
INTENT_ROW_STRING_BYTE_LIMITS = {
    "content_context_id": 48,
    "deterministic_payload_seed": 64,
    "eligible_scope_set_id": 48,
    "intent_key": 48,
    "origin": len("full-residual"),
    "persona_id": 3,
    "placement_context_id": 48,
    "present_fact_set_key": 64,
    "quota_context_id": 48,
    "source_profile_id": 96,
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_inventory",
        "authorizes_source_plan",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "joint_allocation_proved",
        "kio_execution_available",
        "source_intent_refinement_policy_bound",
    }
)

PROHIBITED_FIELD_NAMES = frozenset(
    {
        "answer_membership",
        "chunk_id",
        "compiled_relevance",
        "fact_membership_sha256",
        "final_id",
        "final_source_id",
        "history_intent_sha256",
        "input_closure_manifest_sha256",
        "logical_document_key",
        "materialization_id",
        "query_id",
        "query_intent",
        "query_text",
        "semantic_oracle",
        "solution_sha256",
        "source_id",
        "source_plan_sha256",
    }
)
PROHIBITED_FIELD_FRAGMENTS = (
    "answer_membership",
    "compiled_relevance",
    "final_materialization",
    "final_source",
    "history_intent",
    "materialization_id",
    "oracle",
    "query",
    "solver_solution",
    "source_plan",
)
PROHIBITED_FIELD_SUFFIXES = (
    "_chunk_id",
    "_event_id",
    "_event_ids",
    "_observed_rank",
    "_observed_score",
    "_source_id",
)
PROHIBITED_FRAGMENT_EXEMPT_FIELD_NAMES = frozenset({"authorizes_source_plan"})

_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


class PersonaV2SourceIntentError(ValueError):
    """Raised when a source-intent shard or dependency violates the slice."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2SourceIntentError(f"unknown persona ID: {persona_id!r}")


def _require_negative_authority(value, *, label):
    if type(value) is not dict:
        raise PersonaV2SourceIntentError(f"{label} must be an object")
    if value.get("g0_contract_frozen") is not False:
        raise PersonaV2SourceIntentError(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority:
        raise PersonaV2SourceIntentError(
            f"{label} must expose non-empty negative authority"
        )
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        raise PersonaV2SourceIntentError(f"{label} must remain non-authorizing")


def _artifact_binding(
    name,
    dependency_role,
    value,
    *,
    validate,
    canonical,
    persona_id=None,
):
    validate(value)
    _require_negative_authority(value, label=name)
    if (
        value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
    ):
        raise PersonaV2SourceIntentError(f"{name} fixture identity drifted")
    raw = canonical(value)
    result = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": dependency_role,
        "name": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if persona_id is not None:
        result["persona_id"] = persona_id
    return result


def _sha256_paths(value, path=()):
    paths = set()
    if type(value) is dict:
        for key, item in value.items():
            child_path = path + (key,)
            if key.endswith("sha256"):
                paths.add(child_path)
            paths.update(_sha256_paths(item, child_path))
    elif type(value) is list:
        for item in value:
            paths.update(_sha256_paths(item, path + ("[]",)))
    return frozenset(paths)


def _assert_no_prohibited_fields(value, path=()):
    if type(value) is dict:
        for key, item in value.items():
            fragment_exempt = (
                path == ("authority",)
                and key in PROHIBITED_FRAGMENT_EXEMPT_FIELD_NAMES
            )
            prohibited_fragment = (
                not fragment_exempt
                and any(fragment in key for fragment in PROHIBITED_FIELD_FRAGMENTS)
            )
            if (
                key in PROHIBITED_FIELD_NAMES
                or prohibited_fragment
                or key.endswith(PROHIBITED_FIELD_SUFFIXES)
            ):
                location = ".".join(path + (key,))
                raise PersonaV2SourceIntentError(
                    f"source-intent contains prohibited downstream field: {location}"
                )
            _assert_no_prohibited_fields(item, path + (key,))
    elif type(value) is list:
        for item in value:
            _assert_no_prohibited_fields(item, path + ("[]",))


def _validate_intent_row_bounds(row):
    if type(row) is not dict or set(row) != INTENT_ROW_FIELDS:
        raise PersonaV2SourceIntentError("intent row fields differ from the exact schema")
    for field, maximum in INTENT_ROW_STRING_BYTE_LIMITS.items():
        value = row[field]
        if (
            type(value) is not str
            or not value
            or _ID_RE.fullmatch(value) is None
            or len(value.encode("utf-8", "strict")) > maximum
        ):
            raise PersonaV2SourceIntentError(
                f"intent row {field} violates lexical or byte bounds"
            )
    if row["origin"] not in INTENT_ORIGINS or row["origin"] == SOLVER_DELTA_ORIGIN:
        raise PersonaV2SourceIntentError("intent row origin is invalid")
    try:
        raw = artifact_common.canonical_json_bytes(
            row,
            label="persona v2 source-intent row",
            max_bytes=MAX_INTENT_ROW_BODY_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceIntentError(str(error)) from None
    if len(raw) + JSONL_RECORD_TERMINATOR_BYTES > MAX_INTENT_JSONL_RECORD_BYTES:
        raise PersonaV2SourceIntentError("intent JSONL record exceeds 768 bytes")
    return len(raw) + JSONL_RECORD_TERMINATOR_BYTES


def build_lexically_maximum_intent_row_probe():
    """Return a lexical maximum row for the LF-inclusive byte-bound check.

    The probe satisfies the row's exact field and lexical schemas.  It is not
    a referential artifact row; exact regenerated shards are the semantically
    legal rows and are checked separately.
    """

    row = {
        field: "a" * maximum
        for field, maximum in INTENT_ROW_STRING_BYTE_LIMITS.items()
    }
    row["origin"] = "full-residual"
    row["persona_id"] = "p20"
    _validate_intent_row_bounds(row)
    return copy.deepcopy(row)


def _w0_present_fact_set(graph):
    present = []
    referenced_entity_ids = set()
    for fact in graph["facts"]:
        states = {
            row["checkpoint"]: row["state"]
            for row in fact["visibility_by_checkpoint"]
        }
        if states.get("W0") == "current":
            present.append(fact["fact_id"])
            referenced_entity_ids.add(fact["subject_entity_id"])
            typed_value = fact["typed_value"]
            if typed_value.get("kind") == "entity-reference":
                referenced_entity_ids.add(typed_value["entity_id"])
    if not present or len(present) != len(set(present)):
        raise PersonaV2SourceIntentError("W0 present fact set must be non-empty and unique")
    present = sorted(present)
    entity_ids = sorted(
        row["entity_id"]
        for row in graph["entities"]
        if row["entity_id"] in referenced_entity_ids
    )
    if set(entity_ids) != referenced_entity_ids:
        raise PersonaV2SourceIntentError("present facts reference an unknown entity")
    return present, entity_ids


def _primary_language(profile):
    rows = profile["language_weights_bp"]
    return min(
        rows,
        key=lambda row: (-row["weight_bp"], row["language"].encode("utf-8")),
    )["language"]


def _maximum_weight_bucket(weights, order):
    if len(weights) != len(order):
        raise PersonaV2SourceIntentError("realism bucket vector length drifted")
    return min(
        zip(order, weights),
        key=lambda row: (-row[1], row[0].encode("ascii")),
    )[0]


def _selected_candidate_profile(persona_id, variant_value, source_profile_value):
    ready_rows = {
        row["variant_id"]: row
        for row in source_profile_value["source_profile_rows"]
        if row["bounded_feasibility"]["vertical_slice_ready"]
    }
    marginals = [
        row
        for row in variant_value["persona_variant_marginals"]
        if row["persona_id"] == persona_id
        and row["variant_id"] in ready_rows
        and row["pilot_count"] > 0
    ]
    if not marginals:
        raise PersonaV2SourceIntentError(
            f"{persona_id} has no pilot-positive ready source profile"
        )
    marginal = min(
        marginals,
        key=lambda row: (-row["pilot_count"], row["variant_id"].encode("ascii")),
    )
    profile = ready_rows[marginal["variant_id"]]
    if (
        profile["gate_role"] != "contract_contributor"
        or profile["source_recipe_profile_id"] != "not-bound"
    ):
        raise PersonaV2SourceIntentError(
            "representative candidate must be a non-formal contributor profile"
        )
    return profile, marginal


def _source_profile_projection(profile):
    return {
        "binding_status": "candidate-bounded-feasibility-only-not-formal-recipe",
        "byte_formula": copy.deepcopy(profile["byte_formula"]),
        "complexity_contract": copy.deepcopy(profile["complexity_contract"]),
        "content_media_type": profile["content_media_type"],
        "expected_disposition": profile["expected_offline_disposition"],
        "expected_kio_path_media_type": profile["expected_kio_path_media_type"],
        "family": profile["family"],
        "filename_extension": profile["filename_extension"],
        "formal_source_recipe_profile_id": profile["source_recipe_profile_id"],
        "gate_role": profile["gate_role"],
        "renderer_id": profile["implementation_bindings"]["renderer_id"],
        "source_profile_id": profile["bounded_feasibility_profile_id"],
        "validator_id": profile["implementation_bindings"]["validator_id"],
        "validator_profile_id": profile["implementation_bindings"][
            "validator_profile_id"
        ],
        "variant_id": profile["variant_id"],
    }


def _shared_inputs():
    topology_value = topology.build_topology_contract()
    realism_value = realism.build_realism_profile()
    variant_value = variants.build_variant_catalog()
    source_profile_value = source_profiles.build_source_profile_catalog()
    route_value = route_affinity.build_route_affinity()
    fact_values = fact_graph.build_fact_graph_suite()

    bindings = [
        _artifact_binding(
            "topology",
            "scope-catalog",
            topology_value,
            validate=topology.validate_topology_contract,
            canonical=topology.canonical_json_bytes,
        ),
        _artifact_binding(
            "realism-profile",
            "fidelity-metadata",
            realism_value,
            validate=realism.validate_realism_profile,
            canonical=realism.canonical_json_bytes,
        ),
        _artifact_binding(
            "variant-catalog",
            "persona-variant-marginals",
            variant_value,
            validate=variants.validate_variant_catalog,
            canonical=variants.canonical_json_bytes,
        ),
        _artifact_binding(
            "source-profile-catalog",
            "candidate-source-profile",
            source_profile_value,
            validate=source_profiles.validate_source_profile_catalog,
            canonical=source_profiles.canonical_json_bytes,
        ),
        _artifact_binding(
            "route-affinity-body",
            "content-affecting-route-body",
            route_value,
            validate=route_affinity.validate_route_affinity,
            canonical=route_affinity.canonical_json_bytes,
        ),
    ]
    topology_by_persona = {
        row["persona_id"]: row for row in topology_value["personas"]
    }
    realism_by_persona = {
        row["persona_id"]: row for row in realism_value["personas"]
    }
    fact_by_persona = {row["persona_id"]: row for row in fact_values}
    if (
        tuple(topology_by_persona) != envelope.PERSONA_IDS
        or tuple(realism_by_persona) != envelope.PERSONA_IDS
        or tuple(fact_by_persona) != envelope.PERSONA_IDS
    ):
        raise PersonaV2SourceIntentError("all-persona dependency coverage drifted")
    return {
        "bindings": bindings,
        "fact_by_persona": fact_by_persona,
        "realism_by_persona": realism_by_persona,
        "realism_catalogs": realism_value["catalogs"],
        "source_profile_value": source_profile_value,
        "topology_by_persona": topology_by_persona,
        "variant_value": variant_value,
    }


def _require_exact_references(value):
    rows = value["intent_rows"]
    if len(rows) != REPRESENTATIVE_INTENTS_PER_PERSONA:
        raise PersonaV2SourceIntentError("vertical slice must have exactly one intent")
    row = rows[0]
    catalogs = value["catalogs"]
    reference_fields = {
        "content_context_id": "content_contexts",
        "eligible_scope_set_id": "eligible_scope_sets",
        "placement_context_id": "placement_contexts",
        "present_fact_set_key": "present_fact_sets",
        "quota_context_id": "quota_contexts",
        "source_profile_id": "source_profiles",
    }
    catalog_key_fields = {
        "content_contexts": "content_context_id",
        "eligible_scope_sets": "eligible_scope_set_id",
        "placement_contexts": "placement_context_id",
        "present_fact_sets": "present_fact_set_key",
        "quota_contexts": "quota_context_id",
        "source_profiles": "source_profile_id",
    }
    if set(catalogs) != set(catalog_key_fields):
        raise PersonaV2SourceIntentError("source-intent catalog schema drifted")
    for reference_field, catalog_name in reference_fields.items():
        catalog_rows = catalogs[catalog_name]
        key_field = catalog_key_fields[catalog_name]
        if (
            type(catalog_rows) is not list
            or not catalog_rows
            or len(catalog_rows) > MAX_CATALOG_ENTRIES_PER_SHARD
        ):
            raise PersonaV2SourceIntentError(
                f"{catalog_name} violates its entry-count bound"
            )
        keys = [candidate[key_field] for candidate in catalog_rows]
        if any(
            type(key) is not str
            or not key
            or len(key.encode("utf-8", "strict")) > MAX_CATALOG_ID_BYTES
            for key in keys
        ):
            raise PersonaV2SourceIntentError(
                f"{catalog_name} contains an overlong or invalid key"
            )
        if len(keys) != len(set(keys)) or keys != [row[reference_field]]:
            raise PersonaV2SourceIntentError(
                f"{catalog_name} must contain exactly the referenced entry"
            )
    fact_set = catalogs["present_fact_sets"][0]
    if (
        not fact_set["present_fact_ids"]
        or len(fact_set["present_fact_ids"]) > MAX_PRESENT_FACT_IDS_PER_SET
        or len(fact_set["present_fact_ids"])
        != len(set(fact_set["present_fact_ids"]))
    ):
        raise PersonaV2SourceIntentError("present fact set violates its unique/count bound")
    if (
        not fact_set["synthetic_entity_ids"]
        or len(fact_set["synthetic_entity_ids"])
        > MAX_SYNTHETIC_ENTITY_IDS_PER_SET
        or len(fact_set["synthetic_entity_ids"])
        != len(set(fact_set["synthetic_entity_ids"]))
    ):
        raise PersonaV2SourceIntentError("synthetic entity set violates its bound")
    scope_keys = catalogs["eligible_scope_sets"][0]["scope_keys"]
    if (
        len(scope_keys) != MAX_ELIGIBLE_SCOPE_KEYS_PER_SET
        or len(scope_keys) != len(set(scope_keys))
    ):
        raise PersonaV2SourceIntentError("eligible scope set must contain exact 20 keys")


def _canonical_shard(persona_id, shared):
    _require_persona_id(persona_id)
    topology_row = shared["topology_by_persona"][persona_id]
    fidelity = shared["realism_by_persona"][persona_id]
    fact_value = shared["fact_by_persona"][persona_id]
    fact_binding = _artifact_binding(
        "typed-fact-graph",
        "typed-fact-origin",
        fact_value,
        validate=lambda value: fact_graph.validate_fact_graph(persona_id, value),
        canonical=fact_graph.canonical_json_bytes,
        persona_id=persona_id,
    )
    profile, marginal = _selected_candidate_profile(
        persona_id,
        shared["variant_value"],
        shared["source_profile_value"],
    )
    source_profile = _source_profile_projection(profile)

    persona_ordinal = envelope.PERSONA_IDS.index(persona_id) + 1
    target_complexity = persona_ordinal * 3
    complexity = source_profile["complexity_contract"]
    if not (
        complexity["inclusive_minimum"]
        <= target_complexity
        <= complexity["inclusive_maximum"]
    ):
        raise PersonaV2SourceIntentError("target complexity exceeds candidate profile")
    formula = source_profile["byte_formula"]
    target_bytes = formula["base_bytes_at_complexity_one"] + (
        target_complexity - 1
    ) * formula["increment_bytes_per_additional_complexity"]
    if not formula["minimum_rendered_bytes"] <= target_bytes <= formula[
        "maximum_rendered_bytes"
    ]:
        raise PersonaV2SourceIntentError("target bytes exceed candidate profile")

    graph = fact_value["graphs"][0]
    present_fact_ids, synthetic_entity_ids = _w0_present_fact_set(graph)
    present_fact_set_key = f"{persona_id}-present-facts-w0-syn-0001"
    scope_set_id = f"{persona_id}-scope-set-syn-0001"
    content_context_id = f"{persona_id}-content-syn-0001"
    placement_context_id = f"{persona_id}-placement-syn-0001"
    quota_context_id = f"{persona_id}-quota-syn-0001"
    intent_key = f"{persona_id}-intent-pilot-syn-0001"
    source_profile_id = source_profile["source_profile_id"]

    mtime_bucket_id = _maximum_weight_bucket(
        fidelity["mtime_weights_bp"],
        shared["realism_catalogs"]["mtime_bucket_order"],
    )
    retention_bucket_id = _maximum_weight_bucket(
        fidelity["retention_weights_bp"],
        shared["realism_catalogs"]["retention_bucket_order"],
    )
    project_slug = graph["project_or_case_id"].rsplit("-syn-", 1)[0]
    intent_row = {
        "content_context_id": content_context_id,
        "deterministic_payload_seed": f"{persona_id}-payload-seed-syn-0001",
        "eligible_scope_set_id": scope_set_id,
        "intent_key": intent_key,
        "origin": "pilot",
        "persona_id": persona_id,
        "placement_context_id": placement_context_id,
        "present_fact_set_key": present_fact_set_key,
        "quota_context_id": quota_context_id,
        "source_profile_id": source_profile_id,
    }
    intent_record_bytes = _validate_intent_row_bounds(intent_row)
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "catalog_entry_limits": {
                "content_contexts": MAX_CATALOG_ENTRIES_PER_SHARD,
                "eligible_scope_sets": MAX_CATALOG_ENTRIES_PER_SHARD,
                "placement_contexts": MAX_CATALOG_ENTRIES_PER_SHARD,
                "present_fact_sets": MAX_CATALOG_ENTRIES_PER_SHARD,
                "quota_contexts": MAX_CATALOG_ENTRIES_PER_SHARD,
                "source_profiles": MAX_CATALOG_ENTRIES_PER_SHARD,
            },
            "framed_byte_cap_before_body_required": True,
            "intent_jsonl_record_terminator": JSONL_RECORD_TERMINATOR,
            "max_intent_jsonl_record_bytes_including_terminator": (
                MAX_INTENT_JSONL_RECORD_BYTES
            ),
            "max_intent_row_body_bytes": MAX_INTENT_ROW_BODY_BYTES,
            "max_intents_per_shard": MAX_INTENTS_PER_SHARD,
            "max_catalog_id_bytes": MAX_CATALOG_ID_BYTES,
            "max_eligible_scope_keys_per_set": MAX_ELIGIBLE_SCOPE_KEYS_PER_SET,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_persona_package_bytes": MAX_PERSONA_PACKAGE_BYTES,
            "max_present_fact_ids_per_set": MAX_PRESENT_FACT_IDS_PER_SET,
            "max_shard_body_bytes": MAX_SHARD_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "max_synthetic_entity_ids_per_set": MAX_SYNTHETIC_ENTITY_IDS_PER_SET,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "catalogs": {
            "content_contexts": [
                {
                    "content_context_id": content_context_id,
                    "content_template_id": "typed-fact-summary-candidate-v2",
                    "document_role": "typed-fact-status-note",
                    "filename_template_id": "semantic-fact-note-candidate-v2",
                    "language": _primary_language(fidelity),
                    "period": "W0",
                    "status": "current",
                    "topic_id": project_slug,
                    "version": 1,
                }
            ],
            "eligible_scope_sets": [
                {
                    "eligibility_status": (
                        "all-topology-scopes-candidate-no-reviewed-hard-eligibility"
                    ),
                    "eligible_scope_set_id": scope_set_id,
                    "scope_keys": [row["scope_key"] for row in topology_row["scopes"]],
                }
            ],
            "placement_contexts": [
                {
                    "assignment_status": "candidate-only-no-integer-placement",
                    "duplicate_or_conflict_group": "none",
                    "mtime_age_bucket_id": mtime_bucket_id,
                    "permission_profile_id": fidelity["permission_profile_id"],
                    "placement_context_id": placement_context_id,
                    "placement_profile_id": fidelity["placement_profile_id"],
                    "retention_bucket_id": retention_bucket_id,
                    "sensitivity_tier": fidelity["sensitivity_tiers"][0],
                }
            ],
            "present_fact_sets": [
                {
                    "checkpoint": "W0",
                    "graph_id": graph["graph_id"],
                    "present_fact_ids": present_fact_ids,
                    "present_fact_set_key": present_fact_set_key,
                    "project_or_case_id": graph["project_or_case_id"],
                    "synthetic_entity_ids": synthetic_entity_ids,
                }
            ],
            "quota_contexts": [
                {
                    "allowed_history_cohort_ids": ["P", "X", "Y"],
                    "allowed_quota_bucket_ids": list(envelope.DENSITY_BUCKET_ORDER),
                    "complexity_unit": complexity["measure"],
                    "contributor_eligibility": True,
                    "expected_incidental_chunks_upper": 0,
                    "history_cohort_assignment_status": "solver-unassigned",
                    "quota_bucket_assignment_status": "solver-unassigned",
                    "quota_context_id": quota_context_id,
                    "target_bytes": target_bytes,
                    "target_complexity": target_complexity,
                }
            ],
            "source_profiles": [source_profile],
        },
        "completion_claims": {
            "bounded_jsonl_loader_bound_to_source_shard_frame": False,
            "candidate_source_profile_projection_bound": True,
            "external_frame_header_schema_dispatcher_available": False,
            "fact_membership_exact_projection_bound": False,
            "formal_source_recipe_profile_bound": False,
            "full_persona_package_bound_proved": False,
            "history_event_recipe_bound": False,
            "overlay_instances_bound": False,
            "representative_origin_row_complete": True,
            "source_intent_inventory_complete": False,
            "source_intent_manifest_complete": False,
            "source_intent_origin_shard_vertical_slice_complete": True,
            "source_level_exact_allocation_complete": False,
        },
        "completion_scope": (
            "one-representative-pilot-origin-intent-per-persona-schema-slice-"
            "not-full-source-inventory-not-allocation-not-g0"
        ),
        "coverage": {
            "declared_persona_full_w0_physical_sources": fidelity[
                "w0_physical_denominators"
            ]["full"],
            "declared_persona_pilot_w0_physical_sources": fidelity[
                "w0_physical_denominators"
            ]["pilot"],
            "declared_suite_full_w0_physical_sources": sum(
                row["w0_physical_denominators"]["full"]
                for row in shared["realism_by_persona"].values()
            ),
            "represented_intent_count": REPRESENTATIVE_INTENTS_PER_PERSONA,
            "represented_origin_counts": {"full-residual": 0, "pilot": 1},
            "selected_variant_full_count": marginal["full_count"],
            "selected_variant_pilot_count": marginal["pilot_count"],
            "source_inventory_basis": "representative-schema-row-only",
            "unrepresented_persona_full_w0_physical_sources": fidelity[
                "w0_physical_denominators"
            ]["full"]
            - REPRESENTATIVE_INTENTS_PER_PERSONA,
        },
        "fact_set_projection_contract": {
            "canonical_owner": "source-intent-origin-shard-present-fact-set",
            "downstream_projection_rule": "exact-total-set-equality",
            "duplicate_fact_references_allowed": False,
            "extra_fact_references_allowed": False,
            "missing_fact_references_allowed": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "identity_namespace_policy": {
            "enclosing_payload_or_self_digest_back_reference_allowed": False,
            "future_identity_namespace_basis": (
                "content-affecting-corpus-semantic-inputs-only"
            ),
            "non_content_review_or_evidence_receipt_bytes_included": False,
            "receipt_replacement_may_change_intent_bytes": False,
            "route_body_binding_required": True,
            "runtime_root_replay_clock_or_host_inputs_included": False,
        },
        "input_binding_order": [
            "topology",
            "realism-profile",
            "variant-catalog",
            "source-profile-catalog",
            "route-affinity-body",
            "typed-fact-graph",
        ],
        "input_bindings": copy.deepcopy(shared["bindings"]) + [fact_binding],
        "intent_row_byte_counts_including_lf": [intent_record_bytes],
        "intent_rows": [intent_row],
        "isolation_policy": {
            "environment_reads_allowed": False,
            "host_identity_reads_allowed": False,
            "live_sync_allowed": False,
            "network_access_allowed": False,
            "runtime_randomness_allowed": False,
        },
        "origin_contract": {
            "aggregate_profile_to_intent_origins": {
                "full": ["pilot", "full-residual"],
                "pilot": ["pilot"],
            },
            "allowed_intent_origins": list(INTENT_ORIGINS),
            "current_shard_origin": "pilot",
            "full_manifest_reuses_pilot_shard_bytes": True,
            "full_residual_uses_separate_shards": True,
            "intent_origin_is_immutable": True,
            "solver_delta_to_intent_origin": {
                "full-minus-pilot": "full-residual"
            },
            "solver_delta_value_allowed_as_intent_origin": False,
        },
        "persona_id": persona_id,
        "remaining_blockers": [
            "formal-source-recipe-profiles-not-bound-for-all-variants",
            "all-persona-full-source-inventories-not-materialized",
            "full-residual-shards-not-materialized",
            "source-level-exact-allocation-not-proved",
            "overlay-instance-membership-not-bound",
            "fact-membership-exact-projection-not-bound",
            "review-evidence-not-bound-outside-corpus-identity-namespace",
            "external-frame-header-schema-dispatcher-not-implemented",
            "bounded-jsonl-loader-not-bound-to-source-shard-frame",
            "p12-16000-intent-overlay-manifest-package-cap-not-proved",
            "compiled-history-events-not-present",
        ],
    }
    if set(value["authority"]) != AUTHORITY_FIELDS:
        raise PersonaV2SourceIntentError("source-intent authority schema drifted")
    _require_negative_authority(value, label="source-intent origin shard")
    _require_exact_references(value)
    _assert_no_prohibited_fields(value)
    expected_sha_paths = frozenset({("input_bindings", "[]", "sha256")})
    if _sha256_paths(value) != expected_sha_paths:
        raise PersonaV2SourceIntentError(
            "source-intent has missing, unexpected, downstream, or cyclic SHA paths"
        )
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source-intent origin shard",
            max_bytes=MAX_SHARD_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceIntentError(str(error)) from None
    return value


@functools.lru_cache(maxsize=1)
def _canonical_suite_values():
    shared = _shared_inputs()
    values = tuple(
        _canonical_shard(persona_id, shared) for persona_id in envelope.PERSONA_IDS
    )
    if tuple(value["persona_id"] for value in values) != envelope.PERSONA_IDS:
        raise PersonaV2SourceIntentError("source-intent suite order drifted")
    if sum(len(value["intent_rows"]) for value in values) != len(
        envelope.PERSONA_IDS
    ):
        raise PersonaV2SourceIntentError("representative suite cardinality drifted")
    return values


def build_source_intent_origin_shard(persona_id):
    """Return one detached representative shard for ``persona_id``."""

    _require_persona_id(persona_id)
    index = envelope.PERSONA_IDS.index(persona_id)
    return copy.deepcopy(_canonical_suite_values()[index])


def build_source_intent_origin_shard_suite():
    """Return all twenty detached representative shards in persona order."""

    return copy.deepcopy(list(_canonical_suite_values()))


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source-intent origin shard",
            max_bytes=MAX_SHARD_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceIntentError(str(error)) from None


def validate_source_intent_origin_shard(persona_id, value):
    _require_persona_id(persona_id)
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=lambda: build_source_intent_origin_shard(persona_id),
            label="persona v2 source-intent origin shard",
            max_bytes=MAX_SHARD_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceIntentError(str(error)) from None


def source_intent_origin_shard_sha256(persona_id, value=None):
    _require_persona_id(persona_id)
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=lambda: build_source_intent_origin_shard(persona_id),
            label="persona v2 source-intent origin shard",
            max_bytes=MAX_SHARD_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceIntentError(str(error)) from None


def require_complete_source_intent_inventory():
    raise PersonaV2SourceIntentError(
        "the representative origin-shard schema is implemented, but 203,000 source "
        "intents, full-residual shards, exact refinement, package-cap proof, and "
        "execution authority remain absent"
    )
