"""Exact, non-authorizing formal source-recipe *profile* catalog.

This artifact resolves the seventy-one recipe-profile reservation slots.  It
does not resolve any of the 203,000 physical source instances.  In particular,
there are no selected filenames, renderer parameters, target byte counts,
chunk quotas, scopes, solver coordinates, source/materialization identifiers,
payloads, filesystem paths, or execution receipts in this catalog.

The catalog is strictly downstream of the frozen variant catalog, inventory
profile catalog, all-format implementation registry, and source-semantic
profile catalog.  Those upstream artifacts remain byte-identical; their
``reserved-unbound`` fields describe their own historical boundary and are not
rewritten by this sidecar.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_formal_source_recipe_catalog_validator as independent
    from . import persona_v2_format_implementation_registry as implementation_registry
    from . import persona_v2_realism_profile as realism_profile
    from . import persona_v2_source_inventory_profile as inventory_catalog
    from . import persona_v2_source_profile_catalog as historical_catalog
    from . import persona_v2_source_semantic_membership_package as semantic_catalog
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_fact_graph as fact_graph
    import persona_v2_formal_source_recipe_catalog_validator as independent
    import persona_v2_format_implementation_registry as implementation_registry
    import persona_v2_realism_profile as realism_profile
    import persona_v2_source_inventory_profile as inventory_catalog
    import persona_v2_source_profile_catalog as historical_catalog
    import persona_v2_source_semantic_membership_package as semantic_catalog
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA = "kio.persona.pc-formal-source-recipe-profile-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-formal-source-recipe-profile-catalog"
MAX_CATALOG_BYTES = 1024 * 1024
EXPECTED_PROFILE_COUNT = 71

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-variant-catalog": (
        211_733,
        "807dd3cdd8df613ac21e6ba64877fb5abb40c72ed4949abaa0d440a449e7f9e9",
    ),
    "persona-v2-source-inventory-profile-catalog": (
        87_391,
        "9b0de3defbc106f0bfa8b96ca2134886acd6766ac69196e3498b6b6f7edf43c0",
    ),
    "persona-v2-format-implementation-registry": (
        333_881,
        "59ae0b2e5c755732e6937e70ada4b243ea2c7432a9ce654c7e9c219b4a13bc5d",
    ),
    "persona-v2-source-semantic-membership-catalog": (
        436_495,
        "d54ad435447a6b7adf87c0190bd8ed452caa3015b82ac18da1c81825efeba63b",
    ),
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_payload_bytes_attested",
        "authorizes_final_source_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_query_plan",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_instances",
        "authorizes_source_inventory",
        "authorizes_source_plan",
        "authorizes_source_recipe_instances",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "renderer_execution_environment_available",
        "semantic_payload_adapter_available",
    }
)

EXPECTED_COVERAGE = {
    "contract_contributor": {
        "full": 69_236,
        "full-residual": 62_311,
        "pilot": 6_925,
        "variant_count": 10,
    },
    "incidental_searchable": {
        "full": 60_414,
        "full-residual": 54_374,
        "pilot": 6_040,
        "variant_count": 11,
    },
    "raw_only": {
        "full": 73_350,
        "full-residual": 66_015,
        "pilot": 7_335,
        "variant_count": 50,
    },
    "total": {
        "active_persona_variant_rows": 541,
        "full": 203_000,
        "full-residual": 182_700,
        "pilot": 20_300,
        "profile_count": 71,
    },
}


class PersonaV2FormalSourceRecipeCatalogError(ValueError):
    """Raised when the profile-only formal recipe contract is violated."""


def recipe_profile_id(variant_id):
    if type(variant_id) is not str or not variant_id:
        raise PersonaV2FormalSourceRecipeCatalogError(
            "variant ID must be a non-empty string"
        )
    return f"persona-v2-formal-source-recipe-profile-{variant_id}-v2"


def content_template_profile_id(variant_id):
    if type(variant_id) is not str or not variant_id:
        raise PersonaV2FormalSourceRecipeCatalogError(
            "variant ID must be a non-empty string"
        )
    return f"persona-v2-content-template-profile-{variant_id}-v2"


def filename_template_profile_id(variant_id):
    if type(variant_id) is not str or not variant_id:
        raise PersonaV2FormalSourceRecipeCatalogError(
            "variant ID must be a non-empty string"
        )
    return f"persona-v2-filename-template-profile-{variant_id}-v2"


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        raise PersonaV2FormalSourceRecipeCatalogError(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        raise PersonaV2FormalSourceRecipeCatalogError(
            f"{label} authority must be non-empty and all false"
        )


def _artifact_binding(name, dependency_role, value, *, validate, canonical):
    validate(value)
    _require_negative_authority(value, label=name)
    raw = canonical(value)
    sha256 = hashlib.sha256(raw).hexdigest()
    expected = EXPECTED_DEPENDENCY_PINS[name]
    if (len(raw), sha256) != expected:
        raise PersonaV2FormalSourceRecipeCatalogError(
            f"{name} differs from its frozen dependency pin"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": dependency_role,
        "name": name,
        "sha256": sha256,
    }


def _dependency_binding_without_revalidation(name, dependency_role, value, canonical):
    """Bind an exact already-frozen body without invoking an O(n²) validator.

    The semantic catalog's historical public validator repeatedly rebuilds the
    complete fact-graph suite for each of twenty graph digests.  This local
    reconstruction produces the exact pinned body once, then authenticates its
    canonical bytes here and again in the independent downstream validator.
    """

    _require_negative_authority(value, label=name)
    raw = canonical(value)
    sha256 = hashlib.sha256(raw).hexdigest()
    if (len(raw), sha256) != EXPECTED_DEPENDENCY_PINS[name]:
        raise PersonaV2FormalSourceRecipeCatalogError(
            f"{name} differs from its frozen dependency pin"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": dependency_role,
        "name": name,
        "sha256": sha256,
    }


@functools.lru_cache(maxsize=1)
def _source_semantic_catalog_dependency():
    """Build the exact frozen semantic catalog without repeated suite rebuilds."""

    inputs = semantic_catalog._catalog_inputs()
    inventory_value = inputs["inventory"]
    realism_value = inputs["realism"]

    def binding(name, role, value, canonical, *, persona_id=None):
        raw = canonical(value)
        result = {
            "artifact_kind": value["artifact_kind"],
            "artifact_schema": value["artifact_schema"],
            "artifact_schema_version": value["artifact_schema_version"],
            "canonical_bytes": len(raw),
            "dependency_role": role,
            "name": name,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        if persona_id is not None:
            result["persona_id"] = persona_id
        return result

    graph_bindings = [
        binding(
            "persona-v2-fact-graph",
            "typed-fact-profile-source",
            graph_value,
            fact_graph.canonical_json_bytes,
            persona_id=graph_value["persona_id"],
        )
        for graph_value in inputs["graph_values"]
    ]
    input_bindings = [
        binding(
            "persona-v2-source-inventory-profile-catalog",
            "source-semantic-profile-foreign-keys",
            inventory_value,
            inventory_catalog.canonical_json_bytes,
        ),
        binding(
            "persona-v2-realism-profile",
            "persona-language-weight-owner",
            realism_value,
            realism_profile.canonical_json_bytes,
        ),
        *graph_bindings,
    ]
    value = {
        "artifact_kind": semantic_catalog.CATALOG_ARTIFACT_KIND,
        "artifact_schema": semantic_catalog.CATALOG_ARTIFACT_SCHEMA,
        "artifact_schema_version": semantic_catalog.ARTIFACT_SCHEMA_VERSION,
        "assignment_contract": {
            "component_edges": [
                "content-relation-anchor-to-derivative",
                "attachment-host-to-standalone-member",
            ],
            "conflict_anchor_maps_branch_a": True,
            "conflict_derivative_maps_branch_b": True,
            "empty_profile_allowed_gate_role": "raw_only",
            "fixed_topic_components": ["semantic-anchor", "conflict-copy"],
            "free_component_order": (
                "source-count-descending-then-minimum-intent-key-ascii"
            ),
            "label_choice_score": (
                "target-count-times-assigned-total-plus-component-size-minus-"
                "assigned-label-count-times-origin-source-count"
            ),
            "label_tie_break": "ascii-label",
            "language_fixed_components_present": False,
            "normal_conflict_presentation_mode": (
                "explicit-unordered-current-alternatives"
            ),
            "normal_profile_present_fact_count": 8,
            "quota_algorithm_id": semantic_catalog.envelope.APPORTIONMENT_ALGORITHM_ID,
            "quota_profiles": (
                "pilot-Hamilton-full-Hamilton-residual-equals-full-minus-pilot"
            ),
            "raw_only_present_fact_count": 0,
            "searchable_default_profile_kind": "graph-normal-w0",
            "singleton_anchor_profile_cycle": (
                "singleton-index-equals-semantic-anchor-slot-ordinal-minus-one-"
                "modulo-32-in-fact-slot-then-graph-slot-order"
            ),
        },
        "authority": semantic_catalog._negative_authority(),
        "canonical_limits": {
            "max_body_bytes": semantic_catalog.MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_900_fact_profiles_bound": True,
            "all_71_semantic_profiles_bound": True,
            "all_80_semantic_topics_bound": True,
            "all_w0_profile_fact_ids_typed_graph_owned": True,
            "concrete_source_membership_bound": False,
            "formal_complete_persona_package_cap_proved": False,
            "history_membership_bound": False,
        },
        "completion_scope": (
            "exact-w0-source-semantic-profile-and-topic-catalog-only-no-render-"
            "no-solver-no-history-no-execution-no-g0"
        ),
        "dependency_direction_contract": {
            "catalog_may_bind_origin_profile_or_suite_manifest": False,
            "fact_graphs_inventory_profiles_and_realism_are_strictly_upstream": True,
            "source_membership_manifests_must_bind_catalog": True,
        },
        "fact_profiles": copy.deepcopy(inputs["fact_profiles"]),
        "fixture_id": semantic_catalog.envelope.FIXTURE_ID,
        "fixture_schema_version": semantic_catalog.envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-stress-design-not-observed-user-statistics"
        ),
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "fact_profiles": (
                "persona-then-empty-then-singleton-fact-then-graph-then-normal-"
                "then-conflict-graph-then-branch"
            ),
            "persona": list(semantic_catalog.envelope.PERSONA_IDS),
            "semantic_topics": "persona-then-graph-id-ascii",
            "topic_slot": list(semantic_catalog.TOPIC_SLOT_ORDER),
        },
        "remaining_blockers": [
            "formal-source-recipes-and-missing-renderer-validator-implementations",
            "concrete-logical-overlay-materialization",
            "history-and-checkpoint-transition-membership",
            "scope-placement-allocation-and-proof",
            "render-write-chunk-observation-and-kio-execution",
            "future-complete-persona-package-cap-proof",
        ],
        "semantic_profiles": [],
        "semantic_topics": copy.deepcopy(inputs["topics"]),
        "summary": {
            "conflict_branch_profile_count": 160,
            "empty_profile_count": 20,
            "fact_profile_count": len(inputs["fact_profiles"]),
            "normal_profile_count": 80,
            "persona_count": len(semantic_catalog.envelope.PERSONA_IDS),
            "semantic_profile_count": inventory_catalog.EXPECTED_PROFILE_COUNT,
            "semantic_topic_count": len(inputs["topics"]),
            "singleton_profile_count": 640,
        },
    }
    document_roles = {
        "code": "source-code",
        "csv_tsv": "tabular-record",
        "docx": "word-processing-document",
        "domain_binary": "domain-binary-record",
        "html_eml": "web-or-message",
        "image": "image-asset",
        "ipynb": "notebook",
        "md": "narrative-document",
        "media": "media-asset",
        "pdf_scan": "scanned-document",
        "pdf_text": "text-pdf-document",
        "pptx": "presentation",
        "structured_text": "structured-record",
        "txt_log": "plain-text-record",
        "xlsx": "spreadsheet",
    }
    for source_profile in inventory_value["source_profile_rows"]:
        variant_id = source_profile["variant_id"]
        value["semantic_profiles"].append(
            {
                "content_template_slot_id": (
                    f"persona-v2-content-template-slot-{variant_id}-v2"
                ),
                "document_role": document_roles[source_profile["family"]],
                "family": source_profile["family"],
                "filename_template_slot_id": (
                    f"persona-v2-filename-template-slot-{variant_id}-v2"
                ),
                "formal_recipe_binding_status": source_profile["source_recipe"][
                    "binding_status"
                ],
                "gate_role": source_profile["gate_role"],
                "language_binding_mode": "origin-component-language",
                "semantic_profile_id": (
                    f"persona-v2-source-semantic-profile-{variant_id}-v2"
                ),
                "source_profile_id": source_profile["source_profile_id"],
                "variant_id": variant_id,
            }
        )
    raw = semantic_catalog.canonical_json_bytes(value)
    if (len(raw), hashlib.sha256(raw).hexdigest()) != EXPECTED_DEPENDENCY_PINS[
        "persona-v2-source-semantic-membership-catalog"
    ]:
        raise PersonaV2FormalSourceRecipeCatalogError(
            "optimized semantic catalog reconstruction drifted"
        )
    return value


def _canonical_fragment(value, *, label):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=128 * 1024,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormalSourceRecipeCatalogError(str(error)) from None


def _chunk_policy_rows():
    return [
        {
            "contract_chunk_denominator_eligible": True,
            "expected_incidental_chunks_upper": {
                "assignment_required_at_source_instance": False,
                "exact_value": 0,
                "selected_value_present": False,
            },
            "gate_role": "contract_contributor",
            "incidental_cap_eligible": False,
            "observed_chunk_gate": "actual-equals-assigned-quota",
            "policy_id": "persona-v2-contract-contributor-chunk-policy-v2",
            "requested_chunks": {
                "inclusive_maximum": 70,
                "inclusive_minimum": 1,
                "mode": "source-instance-integer-range",
                "selected_value_present": False,
            },
            "requested_chunks_equal_format_complexity": False,
            "wave_cap_policy_id": "not-applicable",
        },
        {
            "contract_chunk_denominator_eligible": False,
            "expected_incidental_chunks_upper": {
                "assignment_required_at_source_instance": True,
                "inclusive_maximum": 15_000,
                "inclusive_minimum": 0,
                "selected_value_present": False,
            },
            "gate_role": "incidental_searchable",
            "incidental_cap_eligible": True,
            "observed_chunk_gate": "actual-within-source-and-wave-cap",
            "policy_id": "persona-v2-incidental-searchable-chunk-policy-v2",
            "requested_chunks": {
                "exact_value": 0,
                "mode": "exact-zero",
                "selected_value_present": False,
            },
            "requested_chunks_equal_format_complexity": False,
            "wave_cap_policy_id": "persona-v2-dynamic-incidental-wave-caps-v2",
        },
        {
            "contract_chunk_denominator_eligible": False,
            "expected_incidental_chunks_upper": {
                "assignment_required_at_source_instance": False,
                "exact_value": 0,
                "selected_value_present": False,
            },
            "gate_role": "raw_only",
            "incidental_cap_eligible": False,
            "observed_chunk_gate": "actual-equals-zero",
            "policy_id": "persona-v2-raw-only-chunk-policy-v2",
            "requested_chunks": {
                "exact_value": 0,
                "mode": "exact-zero",
                "selected_value_present": False,
            },
            "requested_chunks_equal_format_complexity": False,
            "wave_cap_policy_id": "not-applicable",
        },
    ]


def _dynamic_incidental_wave_cap_policy():
    profile_inputs = (
        ("full", 135_000, 210_000, 15_000, 30_000),
        ("pilot", 13_500, 21_000, 1_500, 3_000),
    )
    checkpoints = {
        "full": (
            ("W0", 120_000, 0),
            ("W1", 120_000, 24_000),
            ("W2", 120_000, 24_000),
            ("W3", 120_000, 48_000),
            ("W4", 120_000, 60_000),
            ("W5-pre-purge", 124_800, 64_800),
            ("W5-final", 120_000, 60_000),
        ),
        "pilot": (
            ("W0", 12_000, 0),
            ("W1", 12_000, 2_400),
            ("W2", 12_000, 2_400),
            ("W3", 12_000, 4_800),
            ("W4", 12_000, 6_000),
            ("W5-pre-purge", 12_480, 6_480),
            ("W5-final", 12_000, 6_000),
        ),
    }
    rows = []
    for (
        profile,
        current_eligible,
        total_eligible,
        base_current,
        base_total,
    ) in profile_inputs:
        checkpoint_rows = []
        for checkpoint, current_chunks, history_chunks in checkpoints[profile]:
            checkpoint_rows.append(
                {
                    "checkpoint": checkpoint,
                    "contributor_current_chunks": current_chunks,
                    "contributor_history_only_chunks": history_chunks,
                    "incidental_current_cap": min(
                        base_current, current_eligible - current_chunks
                    ),
                    "incidental_current_plus_history_cap": min(
                        base_total,
                        total_eligible - current_chunks - history_chunks,
                    ),
                }
            )
        rows.append(
            {
                "base_incidental_current": base_current,
                "base_incidental_current_plus_history": base_total,
                "checkpoint_rows": checkpoint_rows,
                "current_eligible_ceiling": current_eligible,
                "current_plus_history_eligible_ceiling": total_eligible,
                "profile": profile,
            }
        )
    return {
        "cap_formulas": {
            "current": (
                "min(base-incidental-current,current-eligible-ceiling-minus-C(w))"
            ),
            "current_plus_history": (
                "min(base-incidental-current-plus-history,current-plus-history-"
                "eligible-ceiling-minus-C(w)-minus-H(w))"
            ),
        },
        "exact_integer_profile_and_checkpoint_table": True,
        "observed_values_present": False,
        "policy_id": "persona-v2-dynamic-incidental-wave-caps-v2",
        "profile_rows": rows,
        "source_instance_assignments_present": False,
    }


def _policy_catalogs(variant_value):
    return {
        "dynamic_incidental_wave_cap_policy": (
            _dynamic_incidental_wave_cap_policy()
        ),
        "filename_core_policy": {
            "basename_case": "lowercase-ascii",
            "casefold_uniqueness_check_phase": "downstream-final-source-plan",
            "collision_suffix_from_internal_identity_forbidden": True,
            "empty_optional_component_rule": "omit-before-hyphen-join",
            "extension_appended_exactly_once": True,
            "identity_tokens_forbidden": [
                "digest",
                "fixture-nonce",
                "intent-key",
                "materialization-id",
                "persona-id",
                "source-id",
            ],
            "lowercase_ascii_required": True,
            "max_basename_bytes": 120,
            "overlength_rule": "reject-source-instance-no-truncation",
            "path_separator_forbidden": True,
            "policy_id": "persona-v2-lowercase-ascii-semantic-basename-v2",
            "primary_entity_selection": "minimum-synthetic-entity-id-ascii",
            "stem_component_order": [
                "document-role",
                "project-or-case-slug",
                "primary-synthetic-entity-slug",
                "period",
                "status",
                "version",
            ],
            "stem_separator": "hyphen",
            "token_grammar": "lowercase-ascii-alnum-with-internal-hyphens",
            "version_grammar": "literal-v-plus-zero-padded-two-digit-positive-integer",
        },
        "gate_role_chunk_policies": _chunk_policy_rows(),
        "lane_contracts": copy.deepcopy(variant_value["lane_contracts"]),
    }


def _fact_profile_rule(gate_role):
    if gate_role == "raw_only":
        return "empty-present-fact-profile-only-no-search-participation"
    if gate_role in {"contract_contributor", "incidental_searchable"}:
        return "source-owned-nonempty-present-fact-profile-required"
    raise PersonaV2FormalSourceRecipeCatalogError(
        f"unknown recipe gate role: {gate_role}"
    )


def _content_policy(semantic_row, variant_id):
    return {
        "content_instance_values_bound": False,
        "content_template_profile_id": content_template_profile_id(variant_id),
        "content_template_slot_id": semantic_row["content_template_slot_id"],
        "control_input_fields": [
            "document-role",
            "fact-graph-projection",
            "language",
            "period",
            "project-or-case",
            "semantic-version",
            "status",
            "synthetic-entities",
            "topic",
        ],
        "document_role": semantic_row["document_role"],
        "fact_profile_rule": _fact_profile_rule(semantic_row["gate_role"]),
        "language_binding_mode": semantic_row["language_binding_mode"],
        "literal_exposure_forbidden_fields": [
            "digest-or-hash",
            "fixture-nonce",
            "intent-key",
            "materialization-id",
            "persona-id",
            "query-oracle-review-identifiers",
            "scope-key-or-path",
            "source-id",
        ],
        "query_oracle_inputs_allowed": False,
        "semantic_content_adapter_conformance_attested": False,
        "semantic_membership_mode": (
            "source-owned-content-context-and-present-fact-set-by-intent-key"
        ),
    }


def _filename_policy(semantic_row, implementation_row):
    variant_id = implementation_row["variant_id"]
    return {
        "basename_instance_bound": False,
        "basename_policy_id": "persona-v2-lowercase-ascii-semantic-basename-v2",
        "compound_suffix_parts": copy.deepcopy(
            implementation_row["compound_suffix_parts"]
        ),
        "filename_extension": implementation_row["filename_extension"],
        "filename_template_profile_id": filename_template_profile_id(variant_id),
        "filename_template_slot_id": semantic_row["filename_template_slot_id"],
        "scope_casefold_uniqueness_attested": False,
    }


def _implementation_binding(implementation_row, contract_by_id):
    implementation = implementation_row["implementation"]
    renderer = contract_by_id[implementation["renderer_binding_id"]]
    validator = contract_by_id[implementation["validator_binding_id"]]
    return {
        "implementation_pair_id": implementation["pair_id"],
        "implementation_profile_id": implementation["implementation_profile_id"],
        "renderer": {
            "binding_id": renderer["binding_id"],
            "contract_sha256": renderer["sha256"],
            "renderer_id": implementation["renderer_id"],
            "renderer_schema_version": implementation["renderer_schema_version"],
        },
        "validator": {
            "binding_id": validator["binding_id"],
            "contract_sha256": validator["sha256"],
            "validator_id": implementation["validator_id"],
            "validator_profile_id": implementation["validator_profile_id"],
            "validator_schema_version": implementation["validator_schema_version"],
        },
    }


def _runtime_binding(implementation_row, pair_receipt):
    receipt = implementation_row["conformance_receipt"]
    receipt_raw = _canonical_fragment(
        receipt, label="variant runtime conformance receipt"
    )
    pair_raw = _canonical_fragment(
        pair_receipt, label="implementation-pair conformance receipt"
    )
    return {
        "conformance_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "conformance_scope": (
            "identity-free-minimum-midpoint-maximum-format-feasibility-only"
        ),
        "implementation_pair_id": implementation_row["implementation"]["pair_id"],
        "pair_payload_aggregate_sha256": pair_receipt[
            "payload_aggregate_sha256"
        ],
        "pair_receipt_sha256": hashlib.sha256(pair_raw).hexdigest(),
        "payload_aggregate_sha256": receipt["aggregate_sha256"],
        "probe_count": receipt["probe_count"],
        "probe_profile": receipt["probe_profile"],
        "runtime_validator_accepted_all": receipt["validator_accepted_all"],
        "variant_id": implementation_row["variant_id"],
    }


def _complexity_byte_policy(implementation_row):
    normalized = implementation_row["normalized_contract"]
    return {
        "complexity": copy.deepcopy(normalized["complexity"]),
        "formal_lane_policy_id": "formal-retrieval-history-v2",
        "formula": copy.deepcopy(normalized["formula"]),
        "lane": copy.deepcopy(normalized["lane"]),
        "parameter_shape": copy.deepcopy(normalized["parameter_shape"]),
        "quantization": copy.deepcopy(normalized["quantization"]),
        "selected_parameter_values_present": False,
        "selected_target_bytes_present": False,
        "selected_target_complexity_present": False,
        "target_bytes_binding_mode": "derived-exactly-by-renderer-formula",
    }


def _source_count_projection(variant_id, marginals):
    rows = marginals[variant_id]
    pilot = sum(row["pilot_count"] for row in rows)
    residual = sum(row["full_minus_pilot_count"] for row in rows)
    full = sum(row["full_count"] for row in rows)
    if full != pilot + residual:
        raise PersonaV2FormalSourceRecipeCatalogError(
            f"pilot/residual count arithmetic drifted: {variant_id}"
        )
    return {
        "active_persona_count": sum(row["full_count"] > 0 for row in rows),
        "full": full,
        "full-residual": residual,
        "pilot": pilot,
        "projection_only_no_source_instances": True,
    }


def _profile_row(
    variant_row,
    inventory_row,
    implementation_row,
    semantic_row,
    contract_by_id,
    pair_receipts,
    marginals,
):
    variant_id = variant_row["variant_id"]
    if not all(
        row["variant_id"] == variant_id
        for row in (inventory_row, implementation_row, semantic_row)
    ):
        raise PersonaV2FormalSourceRecipeCatalogError(
            f"upstream recipe-profile order drifted: {variant_id}"
        )
    recipe = inventory_row["source_recipe"]
    if recipe != {
        "binding_status": "reserved-unbound",
        "parameters_complete": False,
        "profile_id": "not-bound",
        "slot_id": inventory_catalog.source_recipe_slot_id(variant_id),
    }:
        raise PersonaV2FormalSourceRecipeCatalogError(
            f"upstream formal recipe reservation drifted: {variant_id}"
        )
    expected_semantic_binding = {
        "content_template_slot_id": (
            f"persona-v2-content-template-slot-{variant_id}-v2"
        ),
        "filename_template_slot_id": (
            f"persona-v2-filename-template-slot-{variant_id}-v2"
        ),
        "formal_recipe_binding_status": "reserved-unbound",
        "semantic_profile_id": (
            f"persona-v2-source-semantic-profile-{variant_id}-v2"
        ),
        "source_profile_id": inventory_row["source_profile_id"],
    }
    if any(
        semantic_row.get(field) != expected
        for field, expected in expected_semantic_binding.items()
    ):
        raise PersonaV2FormalSourceRecipeCatalogError(
            f"upstream semantic recipe-slot binding drifted: {variant_id}"
        )
    implementation = implementation_row["implementation"]
    pair_receipt = pair_receipts[implementation["pair_id"]]
    chunk_policy_id = {
        "contract_contributor": "persona-v2-contract-contributor-chunk-policy-v2",
        "incidental_searchable": "persona-v2-incidental-searchable-chunk-policy-v2",
        "raw_only": "persona-v2-raw-only-chunk-policy-v2",
    }[variant_row["gate_role"]]
    exact_metadata = (
        "content_media_type",
        "expected_kio_path_media_type",
        "expected_offline_disposition",
        "family",
        "filename_extension",
        "gate_role",
        "safety_profile_id",
    )
    for field in exact_metadata:
        expected = variant_row[field]
        if (
            inventory_row[field] != expected
            or implementation_row[field] != expected
            or semantic_row.get(field, expected) != expected
        ):
            raise PersonaV2FormalSourceRecipeCatalogError(
                f"recipe upstream metadata drifted: {variant_id}/{field}"
            )
    if implementation_row["search_contract"] != variant_row["search_contract"]:
        raise PersonaV2FormalSourceRecipeCatalogError(
            f"recipe search/chunk contract drifted: {variant_id}"
        )
    source_counts = _source_count_projection(variant_id, marginals)
    registry_counts = implementation_row["normalized_contract"]["lane"][
        "source_counts"
    ]
    if any(
        registry_counts[profile] != source_counts[profile]
        for profile in ("pilot", "full-residual", "full")
    ):
        raise PersonaV2FormalSourceRecipeCatalogError(
            f"recipe registry/count projection drifted: {variant_id}"
        )
    return {
        "binding_status": "profile-bound-instance-unbound",
        "chunk_policy": {
            "policy_id": chunk_policy_id,
            "selected_requested_chunks_present": False,
            "source_instance_incidental_upper_present": False,
        },
        "complexity_byte_policy": _complexity_byte_policy(implementation_row),
        "content_media_type": variant_row["content_media_type"],
        "content_policy": _content_policy(semantic_row, variant_id),
        "expected_kio_path_media_type": variant_row[
            "expected_kio_path_media_type"
        ],
        "expected_offline_disposition": variant_row[
            "expected_offline_disposition"
        ],
        "family": variant_row["family"],
        "filename_policy": _filename_policy(semantic_row, implementation_row),
        "format_feasibility_render_template_id": implementation_row[
            "render_template"
        ],
        "gate_role": variant_row["gate_role"],
        "implementation_binding": _implementation_binding(
            implementation_row, contract_by_id
        ),
        "recipe_profile_id": recipe_profile_id(variant_id),
        "runtime_conformance_binding": _runtime_binding(
            implementation_row, pair_receipt
        ),
        "safety_profile_id": variant_row["safety_profile_id"],
        "semantic_profile_id": semantic_row["semantic_profile_id"],
        "source_count_projection": source_counts,
        "source_inventory_profile_id": inventory_row["source_profile_id"],
        "source_recipe_slot_id": recipe["slot_id"],
        "variant_id": variant_id,
    }


def _coverage(rows):
    result = {}
    for role in ("contract_contributor", "incidental_searchable", "raw_only"):
        selected = [row for row in rows if row["gate_role"] == role]
        result[role] = {
            "full": sum(row["source_count_projection"]["full"] for row in selected),
            "full-residual": sum(
                row["source_count_projection"]["full-residual"] for row in selected
            ),
            "pilot": sum(row["source_count_projection"]["pilot"] for row in selected),
            "variant_count": len(selected),
        }
    result["total"] = {
        "active_persona_variant_rows": sum(
            row["source_count_projection"]["active_persona_count"] for row in rows
        ),
        "full": sum(row["source_count_projection"]["full"] for row in rows),
        "full-residual": sum(
            row["source_count_projection"]["full-residual"] for row in rows
        ),
        "pilot": sum(row["source_count_projection"]["pilot"] for row in rows),
        "profile_count": len(rows),
    }
    return result


@functools.lru_cache(maxsize=1)
def _canonical_catalog():
    variant_value = variant_catalog.build_variant_catalog()
    inventory_value = inventory_catalog.build_source_inventory_profile_catalog()
    registry_value = implementation_registry.build_format_implementation_registry()
    semantic_value = _source_semantic_catalog_dependency()

    input_bindings = [
        _artifact_binding(
            "persona-v2-variant-catalog",
            "variant-identity-marginals-search-and-lane-policy",
            variant_value,
            validate=variant_catalog.validate_variant_catalog,
            canonical=variant_catalog.canonical_json_bytes,
        ),
        _artifact_binding(
            "persona-v2-source-inventory-profile-catalog",
            "inventory-profile-and-reserved-recipe-slot-identity",
            inventory_value,
            validate=inventory_catalog.validate_source_inventory_profile_catalog,
            canonical=inventory_catalog.canonical_json_bytes,
        ),
        _artifact_binding(
            "persona-v2-format-implementation-registry",
            "all-71-format-contracts-and-runtime-conformance-receipts",
            registry_value,
            validate=implementation_registry.validate_format_implementation_registry,
            canonical=implementation_registry.canonical_json_bytes,
        ),
        _dependency_binding_without_revalidation(
            "persona-v2-source-semantic-membership-catalog",
            "semantic-content-and-filename-template-slot-identity",
            semantic_value,
            semantic_catalog.canonical_json_bytes,
        ),
    ]

    variant_rows = variant_value["variant_rows"]
    inventory_by_variant = {
        row["variant_id"]: row for row in inventory_value["source_profile_rows"]
    }
    implementation_by_variant = {
        row["variant_id"]: row for row in registry_value["implementation_rows"]
    }
    semantic_by_variant = {
        row["variant_id"]: row for row in semantic_value["semantic_profiles"]
    }
    contract_by_id = {
        row["binding_id"]: row for row in registry_value["contract_bindings"]
    }
    pair_receipts = {
        row["implementation_pair_id"]: row
        for row in registry_value["implementation_pair_conformance_receipts"]
    }
    marginals = {row["variant_id"]: [] for row in variant_rows}
    for row in variant_value["persona_variant_marginals"]:
        marginals[row["variant_id"]].append(row)

    rows = [
        _profile_row(
            variant_row,
            inventory_by_variant[variant_row["variant_id"]],
            implementation_by_variant[variant_row["variant_id"]],
            semantic_by_variant[variant_row["variant_id"]],
            contract_by_id,
            pair_receipts,
            marginals,
        )
        for variant_row in variant_rows
    ]
    coverage = _coverage(rows)
    if coverage != EXPECTED_COVERAGE:
        raise PersonaV2FormalSourceRecipeCatalogError(
            "formal recipe profile coverage drifted"
        )
    if (
        len(rows) != EXPECTED_PROFILE_COUNT
        or len({row["variant_id"] for row in rows}) != EXPECTED_PROFILE_COUNT
        or len({row["source_recipe_slot_id"] for row in rows})
        != EXPECTED_PROFILE_COUNT
        or len({row["recipe_profile_id"] for row in rows})
        != EXPECTED_PROFILE_COUNT
        or len({row["source_inventory_profile_id"] for row in rows})
        != EXPECTED_PROFILE_COUNT
        or len({row["semantic_profile_id"] for row in rows})
        != EXPECTED_PROFILE_COUNT
        or len(
            {row["content_policy"]["content_template_profile_id"] for row in rows}
        )
        != EXPECTED_PROFILE_COUNT
        or len(
            {row["content_policy"]["content_template_slot_id"] for row in rows}
        )
        != EXPECTED_PROFILE_COUNT
        or len(
            {
                row["filename_policy"]["filename_template_profile_id"]
                for row in rows
            }
        )
        != EXPECTED_PROFILE_COUNT
        or len(
            {row["filename_policy"]["filename_template_slot_id"] for row in rows}
        )
        != EXPECTED_PROFILE_COUNT
    ):
        raise PersonaV2FormalSourceRecipeCatalogError(
            "formal recipe profile slot/identity bijection drifted"
        )

    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "exact_recipe_profile_rows": EXPECTED_PROFILE_COUNT,
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_71_formal_recipe_profile_policies_bound": True,
            "content_and_filename_policy_profiles_bound": True,
            "exact_recipe_slot_profile_bijection": True,
            "format_contracts_and_runtime_receipts_bound": True,
            "physical_source_materialization_complete": False,
            "selected_complexity_and_bytes_present": False,
            "semantic_payload_materialization_complete": False,
            "source_instance_parameter_values_bound": False,
            "source_instances_bound": False,
            "source_level_allocation_solution_present": False,
        },
        "completion_scope": (
            "exact-71-formal-source-recipe-profile-policies-only-no-source-"
            "instances-no-selected-parameters-no-solver-no-render-no-write-no-g0"
        ),
        "coverage": coverage,
        "fixture_id": variant_value["fixture_id"],
        "fixture_schema_version": variant_value["fixture_schema_version"],
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "dependency_bindings": "variant-inventory-implementation-semantic",
            "recipe_profile_rows": "exact-upstream-variant-catalog-order",
        },
        "policy_catalogs": _policy_catalogs(variant_value),
        "recipe_profile_rows": rows,
        "remaining_blockers": [
            "all-source-instance-values-and-source-intent-bodies-unbound",
            "semantic-content-adapter-conformance-and-payload-materialization-unbound",
            "scope-bucket-cohort-quota-solver-solution-and-proof-unbound",
            "ordinary-tail-counts-byte-histograms-and-capacity-receipts-unbound",
            "production-mime-and-actual-chunk-observation-unbound",
            "physical-render-write-history-kio-and-g0-authority-absent",
        ],
    }
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 formal source recipe profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormalSourceRecipeCatalogError(str(error)) from None
    return value


def build_formal_source_recipe_catalog():
    """Return a detached immutable 71-row profile-policy catalog."""

    return copy.deepcopy(_canonical_catalog())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 formal source recipe profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormalSourceRecipeCatalogError(str(error)) from None


def validate_formal_source_recipe_catalog(value):
    try:
        artifact_common.validate_exact_regeneration(
            value,
            builder=build_formal_source_recipe_catalog,
            label="persona v2 formal source recipe profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormalSourceRecipeCatalogError(str(error)) from None
    renderer_contract_provider, validator_contract_provider = (
        implementation_registry._contract_providers()
    )
    renderer_probe_provider, _ = implementation_registry._probe_providers()
    try:
        independent.validate_formal_source_recipe_catalog(
            value,
            variant_catalog_value=variant_catalog.build_variant_catalog(),
            source_inventory_profile_value=(
                inventory_catalog.build_source_inventory_profile_catalog()
            ),
            format_implementation_registry_value=(
                implementation_registry.build_format_implementation_registry()
            ),
            source_semantic_membership_catalog_value=(
                _source_semantic_catalog_dependency()
            ),
            historical_source_profile_value=(
                historical_catalog.build_source_profile_catalog()
            ),
            renderer_contract_provider=renderer_contract_provider,
            validator_contract_provider=validator_contract_provider,
            renderer_probe_provider=renderer_probe_provider,
        )
    except independent.PersonaV2FormalSourceRecipeCatalogValidationError as error:
        raise PersonaV2FormalSourceRecipeCatalogError(str(error)) from None
    return True


def formal_source_recipe_catalog_sha256(value=None):
    if value is None:
        value = build_formal_source_recipe_catalog()
    validate_formal_source_recipe_catalog(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "EXPECTED_PROFILE_COUNT",
    "MAX_CATALOG_BYTES",
    "PersonaV2FormalSourceRecipeCatalogError",
    "build_formal_source_recipe_catalog",
    "canonical_json_bytes",
    "content_template_profile_id",
    "filename_template_profile_id",
    "formal_source_recipe_catalog_sha256",
    "recipe_profile_id",
    "validate_formal_source_recipe_catalog",
]
