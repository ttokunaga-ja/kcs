"""Builder-independent validation for overlay-compatible EML histograms.

This module intentionally does not import the matching producer.  It rebuilds
the EML fanout histograms from the authenticated overlay origins, derives all
six affine renderer anchors from the implementation registry, and recomputes
the effective family, persona, suite, capacity, and infeasibility projections.
"""

from __future__ import annotations

import copy
import hashlib
import hmac

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_aggregate_byte_distribution_catalog as aggregate
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_format_implementation_registry as registry
    from . import persona_v2_format_implementation_registry_validator as registry_validator
    from . import persona_v2_overlay_reservation_layout as reservation
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_aggregate_byte_distribution_catalog as aggregate
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_format_implementation_registry as registry
    import persona_v2_format_implementation_registry_validator as registry_validator
    import persona_v2_overlay_reservation_layout as reservation


ARTIFACT_SCHEMA = "kcs.persona.pc-overlay-compatible-byte-distribution/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-overlay-compatible-byte-distribution"
MAX_CATALOG_BYTES = 2 * 2**20
EXPECTED_CATALOG_CANONICAL_BYTES = 91_039
EXPECTED_CATALOG_SHA256 = (
    "e4acd26dd7b268d86e21320a4a893416e7de169501b479a0bd8a215927265a89"
)
ORIGIN_ORDER = ("pilot", "full-residual")
PROFILE_ORDER = ("pilot", "full-residual", "full")
COMPLEXITIES = tuple(range(6))
QUANTUM = 4_096

EXPECTED_PINS = {
    "persona-v2-aggregate-byte-distribution-catalog": (
        1_576_125,
        "7f2fdcc823885401cb7ed1b8fc42c9010b38af63d2c58879babb28aadeb6b343",
    ),
    "persona-v2-format-implementation-registry": (
        333_881,
        "f585ae477daa01db4dc11bbc1edd9824696bd91eddce5870d618caaffd90c683",
    ),
    "persona-v2-overlay-reservation-suite": (
        21_680,
        "11d042775faebf353a284aad18d137d2735bfd0e29b528666a19d14a008f2c3d",
    ),
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_allocated_bytes_attested",
        "actual_chunks_attested",
        "authorizes_final_source_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kcs_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_instance_assignment",
        "authorizes_source_plan",
        "decoded_attachment_payloads_bound",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kcs_execution_available",
        "source_instance_parameters_bound",
    }
)

TOP_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "base_infeasibility_receipt",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "effective_html_eml_family_projection_rows",
        "effective_persona_summaries",
        "effective_suite_summary",
        "eml_override_rows",
        "eml_runtime_probe_receipts",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "input_binding_order",
        "input_bindings",
        "orders",
        "remaining_blockers",
        "supersession_contract",
        "supersession_summary",
    }
)


class PersonaV2OverlayCompatibleByteDistributionValidationError(ValueError):
    """Raised when an injected body fails independent reconstruction."""


def _fail(message):
    raise PersonaV2OverlayCompatibleByteDistributionValidationError(message)


def _canonical(value, *, label="overlay-compatible byte distribution"):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=MAX_CATALOG_BYTES
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _strict_equal(value, expected):
    """Compare JSON values without Python's ``True == 1`` coercion."""

    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        return set(value) == set(expected) and all(
            _strict_equal(value[key], expected[key]) for key in expected
        )
    if type(expected) is list:
        return len(value) == len(expected) and all(
            _strict_equal(item, expected_item)
            for item, expected_item in zip(value, expected)
        )
    return value == expected


def _exact(value, expected, label):
    if not _strict_equal(value, expected):
        _fail(f"{label} differs from independent reconstruction")


def _negative(value, label):
    if value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        _fail(f"{label} authority must be non-empty and all false")


def _static_fields():
    return {
        "canonical_limits": {
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_40_persona_origin_eml_host_histograms_feasible": True,
            "all_203000_source_instance_parameters_bound": False,
            "all_eml_complexities_runtime_validated": True,
            "decoded_attachment_payload_equivalence_bound": False,
            "effective_203000_source_aggregate_summary_complete": True,
            "eml_nonhost_complexity_zero_histogram_reserved": True,
            "eml_overlay_host_member_count_histogram_reserved": True,
            "filesystem_allocation_attested": False,
            "frozen_base_aggregate_mutated": False,
            "host_to_source_parameter_assignment_complete": False,
            "source_instance_assignment_complete": False,
        },
        "completion_scope": (
            "aggregate-eml-overlay-compatible-parameter-histogram-supersession-"
            "only-no-source-assignment-no-content-no-render-write-history-kcs-or-g0"
        ),
        "orders": {
            "effective_html_eml_family_projection_rows": "persona-id",
            "effective_persona_summaries": "persona-id",
            "eml_override_rows": "persona-id",
            "eml_parameter_bins": "attachment-complexity-0-through-5",
            "eml_runtime_probe_receipts": "attachment-complexity-0-through-5",
        },
        "remaining_blockers": [
            "203000-source-instance-parameter-bin-assignment-unbound",
            "exact-duplicate-pair-bin-coassignment-unbound",
            "decoded-attachment-payload-and-semantic-content-adapter-unbound",
            "scope-bucket-cohort-quota-solution-and-proof-unbound",
            "actual-filesystem-allocation-cas-index-root-capacity-and-g0-absent",
        ],
        "supersession_contract": {
            "base_artifact_remains_immutable": True,
            "base_variant_overrides": ["eml"],
            "decoded_payload_policy": "not-bound-by-this-aggregate-sidecar",
            "effective_row_rule": (
                "use-eml-override-row-for-eml-otherwise-use-exact-base-persona-variant-row"
            ),
            "full_composition_rule": "full-equals-pilot-plus-full-residual",
            "host_rule": (
                "target-complexity-equals-exact-host-member-count-1-through-5"
            ),
            "nonhost_rule": "target-complexity-equals-zero-no-untracked-attachments",
        },
    }


def _summary(entries):
    count = sum(count for _, count, _ in entries)
    raw_sum = sum(raw * count for raw, count, _ in entries)
    block_sum = sum(
        ((raw + QUANTUM - 1) // QUANTUM) * QUANTUM * count
        for raw, count, _ in entries
    )
    tail_count = sum(count for _, count, lane in entries if lane == "formal-tail")
    if count == 0:
        return {
            "block_rounded_payload_bytes": 0,
            "formal_tail_count": 0,
            "maximum_bytes": 0,
            "nearest_rank_p50_bytes": 0,
            "nearest_rank_p95_bytes": 0,
            "raw_byte_sum": 0,
            "source_count": 0,
            "statistics_defined": False,
        }
    ordered = sorted(entries, key=lambda item: item[0])

    def nearest(percent):
        rank = (count * percent + 99) // 100
        cumulative = 0
        for raw, cell_count, _ in ordered:
            cumulative += cell_count
            if cumulative >= rank:
                return raw
        _fail("nearest-rank reconstruction failed")

    return {
        "block_rounded_payload_bytes": block_sum,
        "formal_tail_count": tail_count,
        "maximum_bytes": max(raw for raw, cell_count, _ in entries if cell_count),
        "nearest_rank_p50_bytes": nearest(50),
        "nearest_rank_p95_bytes": nearest(95),
        "raw_byte_sum": raw_sum,
        "source_count": count,
        "statistics_defined": True,
    }


def _entries(row, profile):
    return [
        (
            item["exact_raw_bytes"],
            item["counts"][profile],
            item["size_lane"],
        )
        for item in row["parameter_bins"]
        if item["counts"][profile]
    ]


def _binding(name, role, value, raw):
    pin = (len(raw), hashlib.sha256(raw).hexdigest())
    if pin != EXPECTED_PINS[name]:
        _fail(f"{name} differs from frozen pin")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": pin[0],
        "dependency_role": role,
        "name": name,
        "sha256": pin[1],
    }


def _formula(registry_value):
    rows = [
        row for row in registry_value["implementation_rows"] if row["variant_id"] == "eml"
    ]
    if len(rows) != 1:
        _fail("registry must contain exactly one EML implementation")
    normalized = rows[0]["normalized_contract"]
    _exact(
        normalized["complexity"],
        {
            "counting_rule": "attachment-parts-excluding-primary-body",
            "inclusive_maximum": 5,
            "inclusive_minimum": 0,
            "measure": "attachments",
        },
        "EML complexity contract",
    )
    if normalized["formula"]["formula_kind"] != "affine":
        _fail("EML byte formula must remain affine")
    formula = normalized["formula"]["parameters"]
    _exact(
        formula,
        {
            "base_bytes_at_minimum_complexity": 8_192,
            "increment_bytes_per_additional_complexity": 16_384,
            "maximum_rendered_bytes": 90_112,
            "minimum_complexity": 0,
            "minimum_rendered_bytes": 8_192,
            "selection_phase": "solved-source-recipe-instance-not-this-contract",
        },
        "EML affine formula",
    )
    return formula, rows[0]


def _raw(formula, complexity):
    return formula["base_bytes_at_minimum_complexity"] + complexity * formula[
        "increment_bytes_per_additional_complexity"
    ]


def _origin_binding_map(reservation_value):
    rows = reservation_value.get("origin_bindings")
    if type(rows) is not list or len(rows) != 40:
        _fail("overlay reservation suite must bind forty origins")
    result = {}
    for row in rows:
        key = (row.get("persona_id"), row.get("origin"))
        if key in result:
            _fail("overlay reservation suite repeats an origin binding")
        result[key] = row
    return result


def _fanout(persona_id, origin, provider, origin_bindings):
    try:
        manifest = copy.deepcopy(provider(persona_id, origin))
    except Exception as error:
        raise PersonaV2OverlayCompatibleByteDistributionValidationError(
            "overlay reservation origin provider failed"
        ) from error
    if type(manifest) is not dict:
        _fail("overlay reservation origin provider must return an object")
    try:
        raw = reservation.canonical_json_bytes(manifest)
    except Exception as error:
        raise PersonaV2OverlayCompatibleByteDistributionValidationError(
            "overlay reservation origin provider returned an invalid body"
        ) from error
    binding = origin_bindings.get((persona_id, origin))
    if (
        type(binding) is not dict
        or binding.get("canonical_bytes") != len(raw)
        or binding.get("sha256") != hashlib.sha256(raw).hexdigest()
    ):
        _fail("overlay reservation origin differs from suite binding")
    hosts = {}
    ordinals = {}
    for row in manifest["reservation_rows"]:
        if row["row_kind"] != "attachment-membership-reservation":
            continue
        if row["host_variant_id"] != "eml":
            _fail("attachment host must be EML")
        key = row["host_intent_key"]
        count = row["host_member_count"]
        if key in hosts and hosts[key] != count:
            _fail("EML host member count is inconsistent")
        hosts[key] = count
        ordinals.setdefault(key, set()).add(row["member_ordinal"])
    fanout = {complexity: 0 for complexity in COMPLEXITIES}
    for key, count in hosts.items():
        if type(count) is not int or not 1 <= count <= 5:
            _fail("EML host member count leaves 1..5")
        if ordinals[key] != set(range(1, count + 1)):
            _fail("EML member ordinals do not close")
        fanout[count] += 1
    return fanout, len(hosts), sum(key * value for key, value in fanout.items())


def _expected_override(persona_id, base, formula, provider, origin_bindings):
    origin_fanouts = {}
    hosts = {}
    attachments = {}
    for origin in ORIGIN_ORDER:
        fanout, host_count, attachment_count = _fanout(
            persona_id, origin, provider, origin_bindings
        )
        total = base["source_counts"][origin]
        if host_count > total:
            _fail("EML hosts exceed EML sources")
        fanout[0] = total - host_count
        origin_fanouts[origin] = fanout
        hosts[origin] = host_count
        attachments[origin] = attachment_count
    hosts["full"] = hosts["pilot"] + hosts["full-residual"]
    attachments["full"] = attachments["pilot"] + attachments["full-residual"]
    bins = []
    for complexity in COMPLEXITIES:
        counts = {
            "pilot": origin_fanouts["pilot"][complexity],
            "full-residual": origin_fanouts["full-residual"][complexity],
        }
        counts["full"] = counts["pilot"] + counts["full-residual"]
        bins.append(
            {
                "bin_id": f"attachment-{complexity}",
                "counts": counts,
                "exact_raw_bytes": _raw(formula, complexity),
                "renderer_parameters": {"target_complexity": complexity},
                "size_lane": "formal-ordinary",
                "target_complexity": complexity,
            }
        )
    source_counts = {profile: base["source_counts"][profile] for profile in PROFILE_ORDER}
    return {
        "attachment_membership_counts": attachments,
        "base_implementation_profile_id": base["implementation_profile_id"],
        "base_recipe_profile_id": base["recipe_profile_id"],
        "family": base["family"],
        "gate_role": base["gate_role"],
        "host_source_counts": hosts,
        "parameter_bins": bins,
        "persona_id": persona_id,
        "source_counts": source_counts,
        "summaries": {
            profile: _summary(_entries({"parameter_bins": bins}, profile))
            for profile in PROFILE_ORDER
        },
        "variant_id": "eml",
    }


def _effective_projections(base_rows, overrides):
    override_by_persona = {row["persona_id"]: row for row in overrides}
    effective = [
        override_by_persona[row["persona_id"]] if row["variant_id"] == "eml" else row
        for row in base_rows
    ]
    family_rows = []
    persona_rows = []
    for persona_id in envelope.PERSONA_IDS:
        selected = [row for row in effective if row["persona_id"] == persona_id]
        summaries = {
            profile: _summary(
                [entry for row in selected for entry in _entries(row, profile)]
            )
            for profile in PROFILE_ORDER
        }
        persona_rows.append(
            {
                "capacity_check": {
                    "candidate_cap_bytes": aggregate.PERSONA_CANDIDATE_CAP_BYTES,
                    "hard_block_rounded_cap_bytes": aggregate.PERSONA_BLOCK_ROUNDED_CAP_BYTES,
                    "minimum_margin_bytes": aggregate.PERSONA_REQUIRED_MARGIN_BYTES,
                    "passes_hard_cap": summaries["full"]["block_rounded_payload_bytes"]
                    <= aggregate.PERSONA_BLOCK_ROUNDED_CAP_BYTES,
                    "remaining_candidate_margin_bytes": aggregate.PERSONA_CANDIDATE_CAP_BYTES
                    - summaries["full"]["block_rounded_payload_bytes"],
                },
                "persona_id": persona_id,
                "source_counts": {
                    profile: sum(row["source_counts"][profile] for row in selected)
                    for profile in PROFILE_ORDER
                },
                "summaries": summaries,
                "variant_row_count": len(selected),
            }
        )
        family = override_by_persona[persona_id]["family"]
        family_selected = [row for row in selected if row["family"] == family]
        family_rows.append(
            {
                "family": family,
                "persona_id": persona_id,
                "source_counts": {
                    profile: sum(
                        row["source_counts"][profile] for row in family_selected
                    )
                    for profile in PROFILE_ORDER
                },
                "summaries": {
                    profile: _summary(
                        [
                            entry
                            for row in family_selected
                            for entry in _entries(row, profile)
                        ]
                    )
                    for profile in PROFILE_ORDER
                },
                "variant_row_count": len(family_selected),
            }
        )
    suite_summaries = {
        profile: _summary([entry for row in effective for entry in _entries(row, profile)])
        for profile in PROFILE_ORDER
    }
    suite = {
        "capacity_check": {
            "hard_block_rounded_cap_bytes": aggregate.SUITE_BLOCK_ROUNDED_CAP_BYTES,
            "passes_hard_cap": suite_summaries["full"]["block_rounded_payload_bytes"]
            <= aggregate.SUITE_BLOCK_ROUNDED_CAP_BYTES,
            "remaining_margin_bytes": aggregate.SUITE_BLOCK_ROUNDED_CAP_BYTES
            - suite_summaries["full"]["block_rounded_payload_bytes"],
        },
        "source_counts": {
            profile: sum(row["source_counts"][profile] for row in effective)
            for profile in PROFILE_ORDER
        },
        "summaries": suite_summaries,
        "variant_row_count": len(effective),
    }
    return family_rows, persona_rows, suite


def _probe_receipts(renderer_provider, validator_provider, formula, eml_row):
    result = []
    implementation = eml_row["implementation"]
    for complexity in COMPLEXITIES:
        parameters = {"target_complexity": complexity}
        try:
            provider_rendered = renderer_provider("eml", copy.deepcopy(parameters))
            if type(provider_rendered) is not dict:
                _fail("EML renderer provider must return an object")
            rendered = copy.deepcopy(provider_rendered)
            receipt = copy.deepcopy(
                validator_provider(
                    "eml", copy.deepcopy(parameters), copy.deepcopy(rendered)
                )
            )
        except PersonaV2OverlayCompatibleByteDistributionValidationError:
            raise
        except Exception as error:
            raise PersonaV2OverlayCompatibleByteDistributionValidationError(
                "EML runtime probe provider failed"
            ) from error
        data = rendered.get("data")
        expected_bytes = _raw(formula, complexity)
        if type(data) is not bytes:
            _fail("EML renderer payload must be bytes")
        _exact(
            rendered,
            {
                "content_media_type": eml_row["content_media_type"],
                "data": data,
                "expected_kcs_path_media_type": eml_row[
                    "expected_kcs_path_media_type"
                ],
                "expected_offline_disposition": eml_row[
                    "expected_offline_disposition"
                ],
                "extension": eml_row["filename_extension"],
                "target_bytes": expected_bytes,
                "target_complexity": complexity,
            },
            "EML renderer result",
        )
        if len(data) != expected_bytes:
            _fail("EML renderer payload length differs from affine contract")
        payload_sha256 = hashlib.sha256(data).hexdigest()
        expected_receipt = {
            "input_payload_sha256": payload_sha256,
            "native_receipt": {
                "actual_chunks_attested": False,
                "attachment_count": complexity,
                "byte_length": expected_bytes,
                "identity_tokens_absent": True,
                "kcs_execution_attested": False,
                "observed_complexity_measure": "attachments",
                "observed_local_complexity": complexity,
                "structure_validated": True,
                "target_bytes": expected_bytes,
                "utf8_validated": True,
            },
            "validator_binding_id": implementation["validator_binding_id"],
            "validator_id": implementation["validator_id"],
            "validator_profile_id": implementation["validator_profile_id"],
            "validator_schema_version": implementation["validator_schema_version"],
            "variant_id": "eml",
        }
        validator_binding = {
            "binding_id": implementation["validator_binding_id"],
            "implementation_id": implementation["validator_id"],
            "implementation_pair_id": implementation["pair_id"],
            "implementation_schema_version": implementation[
                "validator_schema_version"
            ],
        }
        try:
            direct_receipt = registry_validator._direct_bound_runtime_receipt(
                implementation["pair_id"],
                "eml",
                copy.deepcopy(parameters),
                copy.deepcopy(rendered),
                validator_binding,
                implementation["validator_profile_id"],
            )
            registry_validator._validate_runtime_receipt(
                direct_receipt,
                variant_id="eml",
                validator_binding=validator_binding,
                validator_profile_id=implementation["validator_profile_id"],
                expected_complexity=complexity,
                payload_bytes=len(data),
                payload_sha256=payload_sha256,
            )
        except Exception as error:
            raise PersonaV2OverlayCompatibleByteDistributionValidationError(
                "direct EML payload validation failed"
            ) from error
        _exact(
            receipt,
            direct_receipt,
            "supplied versus direct EML validator receipt",
        )
        _exact(direct_receipt, expected_receipt, "direct EML runtime validator receipt")
        try:
            receipt_raw = artifact_common.canonical_json_bytes(
                direct_receipt,
                label="independent EML runtime receipt",
                max_bytes=128 * 1024,
            )
        except artifact_common.PersonaV2ArtifactError as error:
            raise PersonaV2OverlayCompatibleByteDistributionValidationError(
                "EML runtime validator receipt is not canonicalizable"
            ) from error
        result.append(
            {
                "bin_id": f"attachment-{complexity}",
                "payload_sha256": payload_sha256,
                "renderer_parameters": parameters,
                "target_bytes": expected_bytes,
                "target_complexity": complexity,
                "validator_accepted": True,
                "validator_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
                "variant_id": "eml",
            }
        )
    return result


def _reauth(value, opening, canonical, label):
    try:
        current = canonical(value)
    except Exception as error:
        raise PersonaV2OverlayCompatibleByteDistributionValidationError(
            f"{label} changed or became invalid during validation"
        ) from error
    if not hmac.compare_digest(current, opening):
        _fail(f"{label} changed during provider callback")


def validate_overlay_compatible_byte_distribution(
    value,
    *,
    aggregate_value=None,
    registry_value=None,
    reservation_suite_value=None,
    reservation_origin_provider=None,
    renderer_probe_provider=None,
    validator_probe_provider=None,
):
    """Validate an exact body without importing its producer."""

    if type(value) is not dict:
        _fail("overlay-compatible byte distribution must be an object")
    opening_target = _canonical(value)
    if (
        len(opening_target) != EXPECTED_CATALOG_CANONICAL_BYTES
        or hashlib.sha256(opening_target).hexdigest() != EXPECTED_CATALOG_SHA256
    ):
        _fail("overlay-compatible byte distribution differs from frozen body pin")
    if set(value) != TOP_FIELDS:
        _fail("overlay-compatible top-level fields differ from exact schema")

    try:
        aggregate_original = (
            aggregate.build_aggregate_byte_distribution_catalog()
            if aggregate_value is None
            else aggregate_value
        )
        registry_original = (
            registry.build_format_implementation_registry()
            if registry_value is None
            else registry_value
        )
        reservation_original = (
            reservation.build_overlay_reservation_suite()
            if reservation_suite_value is None
            else reservation_suite_value
        )
        opening_aggregate = aggregate.canonical_json_bytes(aggregate_original)
        opening_registry = registry.canonical_json_bytes(registry_original)
        opening_reservation = reservation.overlay_reservation_suite_bytes(
            reservation_original
        )
        aggregate_snapshot = copy.deepcopy(aggregate_original)
        registry_snapshot = copy.deepcopy(registry_original)
        reservation_snapshot = copy.deepcopy(reservation_original)

        if reservation_origin_provider is None:
            reservation_origin_provider = reservation.build_overlay_reservation_origin
        if renderer_probe_provider is None or validator_probe_provider is None:
            default_renderer, default_validator = registry._probe_providers()
            renderer_probe_provider = renderer_probe_provider or default_renderer
            validator_probe_provider = validator_probe_provider or default_validator
    except PersonaV2OverlayCompatibleByteDistributionValidationError:
        raise
    except Exception as error:
        raise PersonaV2OverlayCompatibleByteDistributionValidationError(
            "overlay-compatible byte distribution upstream setup failed"
        ) from error

    try:
        aggregate.validate_aggregate_byte_distribution_catalog(aggregate_snapshot)
        registry.validate_format_implementation_registry(registry_snapshot)
        reservation.validate_overlay_reservation_suite(reservation_snapshot)
        for upstream, label in (
            (aggregate_snapshot, "aggregate byte catalog"),
            (registry_snapshot, "implementation registry"),
            (reservation_snapshot, "overlay reservation suite"),
        ):
            _negative(upstream, label)

        bindings = [
            _binding(
                "persona-v2-aggregate-byte-distribution-catalog",
                "immutable-base-histograms-and-capacity-model",
                aggregate_snapshot,
                opening_aggregate,
            ),
            _binding(
                "persona-v2-format-implementation-registry",
                "eml-complexity-formula-and-runtime-validator-owner",
                registry_snapshot,
                opening_registry,
            ),
            _binding(
                "persona-v2-overlay-reservation-suite",
                "exact-eml-host-and-attachment-membership-owner",
                reservation_snapshot,
                opening_reservation,
            ),
        ]
        _exact(value["input_bindings"], bindings, "input bindings")
        _exact(
            value["input_binding_order"],
            [row["name"] for row in bindings],
            "input binding order",
        )
        _exact(value["artifact_kind"], ARTIFACT_KIND, "artifact kind")
        _exact(value["artifact_schema"], ARTIFACT_SCHEMA, "artifact schema")
        _exact(value["artifact_schema_version"], 2, "artifact schema version")
        _exact(value["fixture_id"], envelope.FIXTURE_ID, "fixture ID")
        _exact(value["fixture_schema_version"], 2, "fixture schema version")
        _exact(value["g0_contract_frozen"], False, "G0 status")
        if set(value["authority"]) != AUTHORITY_FIELDS or any(
            type(flag) is not bool or flag is not False
            for flag in value["authority"].values()
        ):
            _fail("authority must be the exact all-false schema")
        for field, expected in _static_fields().items():
            _exact(value[field], expected, field)

        formula, eml_row = _formula(registry_snapshot)
        base_rows = aggregate_snapshot["persona_variant_rows"]
        base_by_key = {
            (row["persona_id"], row["variant_id"]): row for row in base_rows
        }
        origin_bindings = _origin_binding_map(reservation_snapshot)
        expected_overrides = [
            _expected_override(
                persona_id,
                base_by_key[(persona_id, "eml")],
                formula,
                reservation_origin_provider,
                origin_bindings,
            )
            for persona_id in envelope.PERSONA_IDS
        ]
        _exact(value["eml_override_rows"], expected_overrides, "EML override rows")
        families, personas, suite = _effective_projections(
            base_rows, expected_overrides
        )
        _exact(
            value["effective_html_eml_family_projection_rows"],
            families,
            "effective html/eml family projections",
        )
        _exact(value["effective_persona_summaries"], personas, "persona summaries")
        _exact(value["effective_suite_summary"], suite, "suite summary")
        expected_probes = _probe_receipts(
            renderer_probe_provider, validator_probe_provider, formula, eml_row
        )
        _exact(
            value["eml_runtime_probe_receipts"],
            expected_probes,
            "EML runtime probes",
        )

        base_selectable = sorted(
            {
                item["target_complexity"]
                for persona_id in envelope.PERSONA_IDS
                for item in base_by_key[(persona_id, "eml")]["parameter_bins"]
            }
        )
        required = [
            {
                "host_member_count": complexity,
                "host_source_count": sum(
                    row["parameter_bins"][complexity]["counts"]["full"]
                    for row in expected_overrides
                ),
            }
            for complexity in COMPLEXITIES[1:]
        ]
        incompatible = 0
        for row in expected_overrides:
            base = base_by_key[(row["persona_id"], "eml")]
            for origin in ORIGIN_ORDER:
                available = {complexity: 0 for complexity in COMPLEXITIES}
                for item in base["parameter_bins"]:
                    available[item["target_complexity"]] += item["counts"][origin]
                if any(
                    row["parameter_bins"][complexity]["counts"][origin]
                    > available[complexity]
                    for complexity in COMPLEXITIES[1:]
                ):
                    incompatible += 1
        _exact(
            value["base_infeasibility_receipt"],
            {
                "base_assignment_feasible": False,
                "base_selectable_complexities": base_selectable,
                "incompatible_persona_origin_count": incompatible,
                "missing_required_complexities": [
                    row["host_member_count"]
                    for row in required
                    if row["host_source_count"]
                    and row["host_member_count"] not in base_selectable
                ],
                "required_full_host_fanout_counts": required,
            },
            "base infeasibility receipt",
        )

        base_raw = sum(
            base_by_key[(persona_id, "eml")]["summaries"]["full"]["raw_byte_sum"]
            for persona_id in envelope.PERSONA_IDS
        )
        effective_raw = sum(
            row["summaries"]["full"]["raw_byte_sum"] for row in expected_overrides
        )
        host_count = sum(row["host_source_counts"]["full"] for row in expected_overrides)
        membership_count = sum(
            row["attachment_membership_counts"]["full"] for row in expected_overrides
        )
        source_count = sum(row["source_counts"]["full"] for row in expected_overrides)
        _exact(
            value["supersession_summary"],
            {
                "base_full_eml_raw_bytes": base_raw,
                "effective_full_eml_raw_bytes": effective_raw,
                "full_eml_attachment_membership_count": membership_count,
                "full_eml_host_source_count": host_count,
                "full_eml_raw_delta": {
                    "direction": "decrease",
                    "magnitude_bytes": base_raw - effective_raw,
                },
                "full_eml_source_count": source_count,
            },
            "supersession summary",
        )

        return True
    except PersonaV2OverlayCompatibleByteDistributionValidationError:
        raise
    except Exception as error:
        raise PersonaV2OverlayCompatibleByteDistributionValidationError(
            "overlay-compatible byte distribution has malformed nested structure"
        ) from error
    finally:
        _reauth(value, opening_target, _canonical, "target catalog")
        _reauth(
            aggregate_original,
            opening_aggregate,
            aggregate.canonical_json_bytes,
            "aggregate byte catalog",
        )
        _reauth(
            registry_original,
            opening_registry,
            registry.canonical_json_bytes,
            "implementation registry",
        )
        _reauth(
            reservation_original,
            opening_reservation,
            reservation.overlay_reservation_suite_bytes,
            "overlay reservation suite",
        )


__all__ = [
    "EXPECTED_CATALOG_CANONICAL_BYTES",
    "EXPECTED_CATALOG_SHA256",
    "PersonaV2OverlayCompatibleByteDistributionValidationError",
    "validate_overlay_compatible_byte_distribution",
]
