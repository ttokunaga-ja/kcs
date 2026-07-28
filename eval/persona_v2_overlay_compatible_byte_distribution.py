"""Overlay-compatible EML byte distribution for persona-PC v2.

The frozen aggregate byte catalog selected useful generic size anchors, but
its EML anchors expose only attachment complexities 0, 1, and 5.  The exact
overlay membership requires every EML host to carry its authored member count
from 1 through 5.  This downstream, non-authorizing sidecar leaves the frozen
aggregate artifact immutable and supersedes only its EML histogram:

* every tracked EML host gets ``target_complexity == host_member_count``;
* every other EML source gets ``target_complexity == 0``;
* pilot and full-residual are derived independently and full is their exact
  coordinatewise sum.

The artifact remains aggregate.  It binds no source-to-bin assignment, content
payload, decoded attachment bytes, scope, chunk quota, final identifier,
render, filesystem write, history operation, KIO execution, or G0 authority.
"""

from __future__ import annotations

import copy
import functools
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


ARTIFACT_SCHEMA = "kio.persona.pc-overlay-compatible-byte-distribution/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-overlay-compatible-byte-distribution"
MAX_CATALOG_BYTES = 2 * 2**20

ORIGIN_ORDER = ("pilot", "full-residual")
PROFILE_ORDER = ("pilot", "full-residual", "full")
EML_COMPLEXITY_ORDER = tuple(range(6))
EML_VARIANT_ID = "eml"
ALLOCATION_QUANTUM_BYTES = 4_096
EXPECTED_PERSONAS = 20
EXPECTED_EML_SOURCE_COUNT = 9_153
EXPECTED_EML_HOST_COUNT = 2_800
EXPECTED_EML_ATTACHMENT_MEMBERSHIP_COUNT = 5_690
EXPECTED_EFFECTIVE_EML_RAW_BYTES = 168_206_336
EXPECTED_BASE_EML_RAW_BYTES = 173_301_760
EXPECTED_FULL_RAW_DELTA_BYTES = -5_095_424

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-aggregate-byte-distribution-catalog": (
        1_576_125,
        "9bef8b1af10411bb1e8cc662aa95a64e155ea81e3db7e1be56433e83539450d2",
    ),
    "persona-v2-format-implementation-registry": (
        333_881,
        "59ae0b2e5c755732e6937e70ada4b243ea2c7432a9ce654c7e9c219b4a13bc5d",
    ),
    "persona-v2-overlay-reservation-suite": (
        21_680,
        "0423ed61ea7b39dd5229e2ad6f972fc12055717ad401ee9b74911dd5696f15a4",
    ),
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_allocated_bytes_attested",
        "actual_chunks_attested",
        "authorizes_final_source_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_instance_assignment",
        "authorizes_source_plan",
        "decoded_attachment_payloads_bound",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "source_instance_parameters_bound",
    }
)


class PersonaV2OverlayCompatibleByteDistributionError(ValueError):
    """Raised when the overlay-compatible histogram contract drifts."""


def _fail(message):
    raise PersonaV2OverlayCompatibleByteDistributionError(message)


def _strict_equal(value, expected):
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


def _require_exact(value, expected, *, label):
    if not _strict_equal(value, expected):
        _fail(f"{label} differs from its authenticated contract")


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        _fail(f"{label} authority must be non-empty and all false")


def _binding(name, role, value, *, validate, canonical):
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
        "name": name,
        "sha256": actual[1],
    }


def _reservation_bytes(value):
    return reservation.overlay_reservation_suite_bytes(value)


@functools.lru_cache(maxsize=1)
def _cached_shared_inputs():
    aggregate_value = aggregate.build_aggregate_byte_distribution_catalog()
    registry_value = registry.build_format_implementation_registry()
    reservation_value = reservation.build_overlay_reservation_suite()
    bindings = [
        _binding(
            "persona-v2-aggregate-byte-distribution-catalog",
            "immutable-base-histograms-and-capacity-model",
            aggregate_value,
            validate=aggregate.validate_aggregate_byte_distribution_catalog,
            canonical=aggregate.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-format-implementation-registry",
            "eml-complexity-formula-and-runtime-validator-owner",
            registry_value,
            validate=registry.validate_format_implementation_registry,
            canonical=registry.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-overlay-reservation-suite",
            "exact-eml-host-and-attachment-membership-owner",
            reservation_value,
            validate=reservation.validate_overlay_reservation_suite,
            canonical=_reservation_bytes,
        ),
    ]
    implementation_rows = {
        row["variant_id"]: row for row in registry_value["implementation_rows"]
    }
    if (
        len(aggregate_value["persona_variant_rows"])
        != aggregate.EXPECTED_PERSONA_VARIANT_ROWS
        or EML_VARIANT_ID not in implementation_rows
    ):
        _fail("overlay-compatible upstream coverage drifted")
    return {
        "aggregate": aggregate_value,
        "bindings": bindings,
        "registry": registry_value,
        "reservation": reservation_value,
    }


def _input_fingerprint(inputs):
    try:
        return (
            aggregate.canonical_json_bytes(inputs["aggregate"]),
            registry.canonical_json_bytes(inputs["registry"]),
            _reservation_bytes(inputs["reservation"]),
            artifact_common.canonical_json_bytes(
                inputs["bindings"],
                label="overlay-compatible detached dependency bindings",
                max_bytes=64 * 1024,
            ),
        )
    except Exception as error:
        raise PersonaV2OverlayCompatibleByteDistributionError(
            "overlay-compatible detached dependencies became invalid"
        ) from error


def _validate_shared_inputs(inputs):
    if type(inputs) is not dict or set(inputs) != {
        "aggregate",
        "bindings",
        "registry",
        "reservation",
    }:
        _fail("overlay-compatible dependency snapshot has an unexpected schema")
    reconstructed = [
        _binding(
            "persona-v2-aggregate-byte-distribution-catalog",
            "immutable-base-histograms-and-capacity-model",
            inputs["aggregate"],
            validate=aggregate.validate_aggregate_byte_distribution_catalog,
            canonical=aggregate.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-format-implementation-registry",
            "eml-complexity-formula-and-runtime-validator-owner",
            inputs["registry"],
            validate=registry.validate_format_implementation_registry,
            canonical=registry.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-overlay-reservation-suite",
            "exact-eml-host-and-attachment-membership-owner",
            inputs["reservation"],
            validate=reservation.validate_overlay_reservation_suite,
            canonical=_reservation_bytes,
        ),
    ]
    _require_exact(
        inputs["bindings"], reconstructed, label="detached dependency bindings"
    )


def _reauth_inputs(inputs, opening, *, label):
    current = _input_fingerprint(inputs)
    if len(current) != len(opening) or any(
        not hmac.compare_digest(actual, expected)
        for actual, expected in zip(current, opening)
    ):
        _fail(f"{label} changed during a provider callback")


def _base_rows(inputs):
    rows = {
        (row["persona_id"], row["variant_id"]): row
        for row in inputs["aggregate"]["persona_variant_rows"]
    }
    if len(rows) != aggregate.EXPECTED_PERSONA_VARIANT_ROWS:
        _fail("overlay-compatible base row coverage drifted")
    return rows


def _implementation(inputs):
    rows = [
        row
        for row in inputs["registry"]["implementation_rows"]
        if row["variant_id"] == EML_VARIANT_ID
    ]
    if len(rows) != 1:
        _fail("overlay-compatible registry must contain exactly one EML row")
    return rows[0]


def _eml_formula(inputs):
    normalized = _implementation(inputs)["normalized_contract"]
    if (
        normalized["complexity"]
        != {
            "counting_rule": "attachment-parts-excluding-primary-body",
            "inclusive_maximum": 5,
            "inclusive_minimum": 0,
            "measure": "attachments",
        }
        or normalized["formula"]["formula_kind"] != "affine"
    ):
        _fail("EML complexity contract drifted")
    formula = normalized["formula"]["parameters"]
    expected = {
        "base_bytes_at_minimum_complexity": 8_192,
        "increment_bytes_per_additional_complexity": 16_384,
        "maximum_rendered_bytes": 90_112,
        "minimum_complexity": 0,
        "minimum_rendered_bytes": 8_192,
        "selection_phase": "solved-source-recipe-instance-not-this-contract",
    }
    if formula != expected:
        _fail("EML affine byte formula drifted")
    return formula


def _raw_bytes(complexity, formula):
    if type(complexity) is not int or complexity not in EML_COMPLEXITY_ORDER:
        _fail("EML attachment complexity must be an exact integer in 0..5")
    return formula["base_bytes_at_minimum_complexity"] + (
        complexity - formula["minimum_complexity"]
    ) * formula["increment_bytes_per_additional_complexity"]


def _summary(entries):
    count = sum(item[1] for item in entries)
    raw_sum = sum(raw * cell_count for raw, cell_count in entries)
    block_sum = sum(
        ((raw + ALLOCATION_QUANTUM_BYTES - 1) // ALLOCATION_QUANTUM_BYTES)
        * ALLOCATION_QUANTUM_BYTES
        * cell_count
        for raw, cell_count in entries
    )
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
    ordered = sorted(entries)

    def nearest_rank(percent):
        target = (count * percent + 99) // 100
        cumulative = 0
        for raw, cell_count in ordered:
            cumulative += cell_count
            if cumulative >= target:
                return raw
        _fail("nearest-rank selection did not terminate")

    return {
        "block_rounded_payload_bytes": block_sum,
        "formal_tail_count": 0,
        "maximum_bytes": max(raw for raw, cell_count in entries if cell_count),
        "nearest_rank_p50_bytes": nearest_rank(50),
        "nearest_rank_p95_bytes": nearest_rank(95),
        "raw_byte_sum": raw_sum,
        "source_count": count,
        "statistics_defined": True,
    }


def _origin_binding_map(inputs):
    rows = inputs["reservation"].get("origin_bindings")
    if type(rows) is not list or len(rows) != 40:
        _fail("overlay reservation suite must bind exactly forty origins")
    result = {}
    for row in rows:
        key = (row.get("persona_id"), row.get("origin"))
        if key in result:
            _fail("overlay reservation suite repeats an origin binding")
        result[key] = row
    return result


def _host_fanout(persona_id, origin, origin_provider, origin_bindings):
    try:
        manifest = copy.deepcopy(origin_provider(persona_id, origin))
        reservation.validate_overlay_reservation_origin(persona_id, origin, manifest)
        manifest_raw = reservation.canonical_json_bytes(manifest)
    except Exception as error:
        raise PersonaV2OverlayCompatibleByteDistributionError(
            "overlay reservation origin provider failed authentication"
        ) from error
    binding = origin_bindings.get((persona_id, origin))
    if (
        type(binding) is not dict
        or type(binding.get("canonical_bytes")) is not int
        or binding["canonical_bytes"] != len(manifest_raw)
        or binding.get("sha256") != hashlib.sha256(manifest_raw).hexdigest()
    ):
        _fail("overlay reservation origin differs from its suite binding")
    hosts = {}
    member_ordinals = {}
    for row in manifest["reservation_rows"]:
        if row["row_kind"] != "attachment-membership-reservation":
            continue
        if row["host_variant_id"] != EML_VARIANT_ID:
            _fail("attachment host is not EML")
        key = row["host_intent_key"]
        count = row["host_member_count"]
        if key in hosts and hosts[key] != count:
            _fail("one EML host declares inconsistent member counts")
        hosts[key] = count
        member_ordinals.setdefault(key, set()).add(row["member_ordinal"])
    for key, count in hosts.items():
        if member_ordinals[key] != set(range(1, count + 1)):
            _fail("EML host member ordinals do not close exactly")
    fanout = {complexity: 0 for complexity in EML_COMPLEXITY_ORDER}
    for count in hosts.values():
        if count not in EML_COMPLEXITY_ORDER[1:]:
            _fail("EML overlay host member count leaves 1..5")
        fanout[count] += 1
    return fanout, sum(fanout.values()), sum(
        complexity * count for complexity, count in fanout.items()
    )


def _override_row(
    persona_id,
    *,
    base_rows,
    formula,
    origin_provider,
    origin_bindings,
):
    base = base_rows[(persona_id, EML_VARIANT_ID)]
    origin_fanouts = {}
    host_counts = {}
    attachment_counts = {}
    for origin in ORIGIN_ORDER:
        fanout, hosts, attachments = _host_fanout(
            persona_id, origin, origin_provider, origin_bindings
        )
        total = base["source_counts"][origin]
        if hosts > total:
            _fail("EML overlay hosts exceed the physical EML source marginal")
        fanout[0] = total - hosts
        origin_fanouts[origin] = fanout
        host_counts[origin] = hosts
        attachment_counts[origin] = attachments
    full = {
        complexity: origin_fanouts["pilot"][complexity]
        + origin_fanouts["full-residual"][complexity]
        for complexity in EML_COMPLEXITY_ORDER
    }
    host_counts["full"] = host_counts["pilot"] + host_counts["full-residual"]
    attachment_counts["full"] = (
        attachment_counts["pilot"] + attachment_counts["full-residual"]
    )
    parameter_bins = []
    for complexity in EML_COMPLEXITY_ORDER:
        counts = {
            "pilot": origin_fanouts["pilot"][complexity],
            "full-residual": origin_fanouts["full-residual"][complexity],
            "full": full[complexity],
        }
        parameter_bins.append(
            {
                "bin_id": f"attachment-{complexity}",
                "counts": counts,
                "exact_raw_bytes": _raw_bytes(complexity, formula),
                "renderer_parameters": {"target_complexity": complexity},
                "size_lane": "formal-ordinary",
                "target_complexity": complexity,
            }
        )
    source_counts = {
        "pilot": base["source_counts"]["pilot"],
        "full-residual": base["source_counts"]["full-residual"],
        "full": base["source_counts"]["full"],
    }
    summaries = {
        profile: _summary(
            [
                (row["exact_raw_bytes"], row["counts"][profile])
                for row in parameter_bins
            ]
        )
        for profile in PROFILE_ORDER
    }
    if any(summaries[p]["source_count"] != source_counts[p] for p in PROFILE_ORDER):
        _fail("EML overlay-compatible source counts do not close")
    return {
        "attachment_membership_counts": attachment_counts,
        "base_implementation_profile_id": base["implementation_profile_id"],
        "base_recipe_profile_id": base["recipe_profile_id"],
        "family": base["family"],
        "gate_role": base["gate_role"],
        "host_source_counts": host_counts,
        "parameter_bins": parameter_bins,
        "persona_id": persona_id,
        "source_counts": source_counts,
        "summaries": summaries,
        "variant_id": EML_VARIANT_ID,
    }


def _entries(row, profile):
    return [
        (
            item["exact_raw_bytes"],
            item["counts"][profile],
            item.get("size_lane", "formal-ordinary"),
        )
        for item in row["parameter_bins"]
        if item["counts"][profile]
    ]


def _aggregate_summary(entries):
    projected = _summary([(raw, count) for raw, count, _ in entries])
    projected["formal_tail_count"] = sum(
        count for _, count, lane in entries if lane == "formal-tail"
    )
    return projected


def _effective_projections(overrides, inputs):
    override_by_persona = {row["persona_id"]: row for row in overrides}
    effective_rows = []
    for row in inputs["aggregate"]["persona_variant_rows"]:
        effective_rows.append(
            override_by_persona[row["persona_id"]]
            if row["variant_id"] == EML_VARIANT_ID
            else row
        )
    persona_summaries = []
    html_eml_family_summaries = []
    for persona_id in envelope.PERSONA_IDS:
        selected = [row for row in effective_rows if row["persona_id"] == persona_id]
        summaries = {
            profile: _aggregate_summary(
                [entry for row in selected for entry in _entries(row, profile)]
            )
            for profile in PROFILE_ORDER
        }
        persona_summaries.append(
            {
                "capacity_check": {
                    "candidate_cap_bytes": aggregate.PERSONA_CANDIDATE_CAP_BYTES,
                    "hard_block_rounded_cap_bytes": (
                        aggregate.PERSONA_BLOCK_ROUNDED_CAP_BYTES
                    ),
                    "minimum_margin_bytes": aggregate.PERSONA_REQUIRED_MARGIN_BYTES,
                    "passes_hard_cap": (
                        summaries["full"]["block_rounded_payload_bytes"]
                        <= aggregate.PERSONA_BLOCK_ROUNDED_CAP_BYTES
                    ),
                    "remaining_candidate_margin_bytes": (
                        aggregate.PERSONA_CANDIDATE_CAP_BYTES
                        - summaries["full"]["block_rounded_payload_bytes"]
                    ),
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
        eml_family = override_by_persona[persona_id]["family"]
        family_selected = [row for row in selected if row["family"] == eml_family]
        html_eml_family_summaries.append(
            {
                "family": eml_family,
                "persona_id": persona_id,
                "source_counts": {
                    profile: sum(
                        row["source_counts"][profile] for row in family_selected
                    )
                    for profile in PROFILE_ORDER
                },
                "summaries": {
                    profile: _aggregate_summary(
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
        profile: _aggregate_summary(
            [entry for row in effective_rows for entry in _entries(row, profile)]
        )
        for profile in PROFILE_ORDER
    }
    suite = {
        "capacity_check": {
            "hard_block_rounded_cap_bytes": aggregate.SUITE_BLOCK_ROUNDED_CAP_BYTES,
            "passes_hard_cap": (
                suite_summaries["full"]["block_rounded_payload_bytes"]
                <= aggregate.SUITE_BLOCK_ROUNDED_CAP_BYTES
            ),
            "remaining_margin_bytes": (
                aggregate.SUITE_BLOCK_ROUNDED_CAP_BYTES
                - suite_summaries["full"]["block_rounded_payload_bytes"]
            ),
        },
        "source_counts": {
            profile: sum(row["source_counts"][profile] for row in effective_rows)
            for profile in PROFILE_ORDER
        },
        "summaries": suite_summaries,
        "variant_row_count": len(effective_rows),
    }
    return html_eml_family_summaries, persona_summaries, suite


def _probe_receipts(inputs, formula, renderer_provider, validator_provider):
    rows = []
    implementation_row = _implementation(inputs)
    implementation = implementation_row["implementation"]
    for complexity in EML_COMPLEXITY_ORDER:
        parameters = {"target_complexity": complexity}
        try:
            provider_rendered = renderer_provider(
                EML_VARIANT_ID, copy.deepcopy(parameters)
            )
            if type(provider_rendered) is not dict:
                _fail("EML renderer provider must return an object")
            rendered = copy.deepcopy(provider_rendered)
            receipt = copy.deepcopy(
                validator_provider(
                    EML_VARIANT_ID,
                    copy.deepcopy(parameters),
                    copy.deepcopy(rendered),
                )
            )
        except PersonaV2OverlayCompatibleByteDistributionError:
            raise
        except Exception as error:
            raise PersonaV2OverlayCompatibleByteDistributionError(
                "EML runtime probe provider failed"
            ) from error
        data = rendered.get("data")
        target_bytes = _raw_bytes(complexity, formula)
        if type(data) is not bytes:
            _fail("EML renderer provider must return bytes payload data")
        _require_exact(
            rendered,
            {
                "content_media_type": implementation_row["content_media_type"],
                "data": data,
                "expected_kio_path_media_type": implementation_row[
                    "expected_kio_path_media_type"
                ],
                "expected_offline_disposition": implementation_row[
                    "expected_offline_disposition"
                ],
                "extension": implementation_row["filename_extension"],
                "target_bytes": target_bytes,
                "target_complexity": complexity,
            },
            label="EML renderer result",
        )
        if len(data) != target_bytes:
            _fail("EML renderer payload length differs from its affine byte formula")
        payload_sha256 = hashlib.sha256(data).hexdigest()
        expected_receipt = {
            "input_payload_sha256": payload_sha256,
            "native_receipt": {
                "actual_chunks_attested": False,
                "attachment_count": complexity,
                "byte_length": target_bytes,
                "identity_tokens_absent": True,
                "kio_execution_attested": False,
                "observed_complexity_measure": "attachments",
                "observed_local_complexity": complexity,
                "structure_validated": True,
                "target_bytes": target_bytes,
                "utf8_validated": True,
            },
            "validator_binding_id": implementation["validator_binding_id"],
            "validator_id": implementation["validator_id"],
            "validator_profile_id": implementation["validator_profile_id"],
            "validator_schema_version": implementation["validator_schema_version"],
            "variant_id": EML_VARIANT_ID,
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
                EML_VARIANT_ID,
                copy.deepcopy(parameters),
                copy.deepcopy(rendered),
                validator_binding,
                implementation["validator_profile_id"],
            )
            registry_validator._validate_runtime_receipt(
                direct_receipt,
                variant_id=EML_VARIANT_ID,
                validator_binding=validator_binding,
                validator_profile_id=implementation["validator_profile_id"],
                expected_complexity=complexity,
                payload_bytes=len(data),
                payload_sha256=payload_sha256,
            )
        except Exception as error:
            raise PersonaV2OverlayCompatibleByteDistributionError(
                "direct EML payload validation failed"
            ) from error
        _require_exact(
            receipt, direct_receipt, label="supplied versus direct EML validator receipt"
        )
        _require_exact(
            direct_receipt,
            expected_receipt,
            label="direct EML runtime validator receipt",
        )
        try:
            receipt_raw = artifact_common.canonical_json_bytes(
                direct_receipt,
                label="persona v2 EML overlay-compatible validator receipt",
                max_bytes=128 * 1024,
            )
        except artifact_common.PersonaV2ArtifactError as error:
            raise PersonaV2OverlayCompatibleByteDistributionError(str(error)) from None
        rows.append(
            {
                "bin_id": f"attachment-{complexity}",
                "payload_sha256": payload_sha256,
                "renderer_parameters": parameters,
                "target_bytes": target_bytes,
                "target_complexity": complexity,
                "validator_accepted": True,
                "validator_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
                "variant_id": EML_VARIANT_ID,
            }
        )
    return rows


def _base_infeasibility_receipt(overrides, base_rows):
    incompatible = 0
    selectable = set()
    required_full = {complexity: 0 for complexity in EML_COMPLEXITY_ORDER[1:]}
    for override in overrides:
        persona_id = override["persona_id"]
        base = base_rows[(persona_id, EML_VARIANT_ID)]
        selectable.update(row["target_complexity"] for row in base["parameter_bins"])
        override_bins = {
            row["target_complexity"]: row for row in override["parameter_bins"]
        }
        for complexity in required_full:
            required_full[complexity] += override_bins[complexity]["counts"]["full"]
        for origin in ORIGIN_ORDER:
            available = {complexity: 0 for complexity in EML_COMPLEXITY_ORDER}
            for row in base["parameter_bins"]:
                available[row["target_complexity"]] += row["counts"][origin]
            if any(
                override_bins[complexity]["counts"][origin] > available[complexity]
                for complexity in EML_COMPLEXITY_ORDER[1:]
            ):
                incompatible += 1
    missing = [
        complexity
        for complexity, count in required_full.items()
        if count and complexity not in selectable
    ]
    if incompatible != len(envelope.PERSONA_IDS) * len(ORIGIN_ORDER):
        _fail("base EML infeasibility no longer covers all forty coordinates")
    return {
        "base_assignment_feasible": False,
        "base_selectable_complexities": sorted(selectable),
        "incompatible_persona_origin_count": incompatible,
        "missing_required_complexities": missing,
        "required_full_host_fanout_counts": [
            {"host_member_count": complexity, "host_source_count": required_full[complexity]}
            for complexity in EML_COMPLEXITY_ORDER[1:]
        ],
    }


def _build_catalog(
    inputs, *, origin_provider, renderer_provider, validator_provider
):
    base_rows = _base_rows(inputs)
    formula = _eml_formula(inputs)
    origin_bindings = _origin_binding_map(inputs)
    overrides = [
        _override_row(
            persona_id,
            base_rows=base_rows,
            formula=formula,
            origin_provider=origin_provider,
            origin_bindings=origin_bindings,
        )
        for persona_id in envelope.PERSONA_IDS
    ]
    html_eml_family_summaries, persona_summaries, suite_summary = (
        _effective_projections(overrides, inputs)
    )
    base_eml_raw = sum(
        base_rows[(persona_id, EML_VARIANT_ID)]["summaries"]["full"][
            "raw_byte_sum"
        ]
        for persona_id in envelope.PERSONA_IDS
    )
    effective_eml_raw = sum(
        row["summaries"]["full"]["raw_byte_sum"] for row in overrides
    )
    host_count = sum(row["host_source_counts"]["full"] for row in overrides)
    membership_count = sum(
        row["attachment_membership_counts"]["full"] for row in overrides
    )
    source_count = sum(row["source_counts"]["full"] for row in overrides)
    if (
        source_count != EXPECTED_EML_SOURCE_COUNT
        or host_count != EXPECTED_EML_HOST_COUNT
        or membership_count != EXPECTED_EML_ATTACHMENT_MEMBERSHIP_COUNT
        or base_eml_raw != EXPECTED_BASE_EML_RAW_BYTES
        or effective_eml_raw != EXPECTED_EFFECTIVE_EML_RAW_BYTES
        or effective_eml_raw - base_eml_raw != EXPECTED_FULL_RAW_DELTA_BYTES
    ):
        _fail("EML overlay-compatible suite totals drifted")
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "base_infeasibility_receipt": _base_infeasibility_receipt(
            overrides, base_rows
        ),
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
            "source_instance_assignment_complete": False,
            "host_to_source_parameter_assignment_complete": False,
        },
        "effective_html_eml_family_projection_rows": html_eml_family_summaries,
        "completion_scope": (
            "aggregate-eml-overlay-compatible-parameter-histogram-supersession-"
            "only-no-source-assignment-no-content-no-render-write-history-kio-or-g0"
        ),
        "effective_persona_summaries": persona_summaries,
        "effective_suite_summary": suite_summary,
        "eml_override_rows": overrides,
        "eml_runtime_probe_receipts": _probe_receipts(
            inputs, formula, renderer_provider, validator_provider
        ),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in inputs["bindings"]],
        "input_bindings": copy.deepcopy(inputs["bindings"]),
        "orders": {
            "eml_override_rows": "persona-id",
            "eml_parameter_bins": "attachment-complexity-0-through-5",
            "eml_runtime_probe_receipts": "attachment-complexity-0-through-5",
            "effective_persona_summaries": "persona-id",
            "effective_html_eml_family_projection_rows": "persona-id",
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
            "base_variant_overrides": [EML_VARIANT_ID],
            "decoded_payload_policy": "not-bound-by-this-aggregate-sidecar",
            "effective_row_rule": (
                "use-eml-override-row-for-eml-otherwise-use-exact-base-persona-variant-row"
            ),
            "full_composition_rule": "full-equals-pilot-plus-full-residual",
            "host_rule": "target-complexity-equals-exact-host-member-count-1-through-5",
            "nonhost_rule": "target-complexity-equals-zero-no-untracked-attachments",
        },
        "supersession_summary": {
            "base_full_eml_raw_bytes": base_eml_raw,
            "effective_full_eml_raw_bytes": effective_eml_raw,
            "full_eml_attachment_membership_count": membership_count,
            "full_eml_host_source_count": host_count,
            "full_eml_raw_delta": {
                "direction": "decrease",
                "magnitude_bytes": base_eml_raw - effective_eml_raw,
            },
            "full_eml_source_count": source_count,
        },
    }
    canonical_json_bytes(value)
    return value


@functools.lru_cache(maxsize=1)
def _canonical_catalog():
    try:
        cached_inputs = _cached_shared_inputs()
        opening_cached = _input_fingerprint(cached_inputs)
        inputs = copy.deepcopy(cached_inputs)
        _validate_shared_inputs(inputs)
        _reauth_inputs(
            cached_inputs,
            opening_cached,
            label="cached dependency bodies during snapshot validation",
        )
        opening_inputs = _input_fingerprint(inputs)
    except Exception:
        _cached_shared_inputs.cache_clear()
        raise
    try:
        origin_provider = reservation.build_overlay_reservation_origin
        renderer_provider, validator_provider = registry._probe_providers()
        return _build_catalog(
            inputs,
            origin_provider=origin_provider,
            renderer_provider=renderer_provider,
            validator_provider=validator_provider,
        )
    finally:
        try:
            _reauth_inputs(inputs, opening_inputs, label="detached dependencies")
            _reauth_inputs(
                cached_inputs, opening_cached, label="cached dependency bodies"
            )
        except Exception:
            _cached_shared_inputs.cache_clear()
            raise


def build_overlay_compatible_byte_distribution():
    return copy.deepcopy(_canonical_catalog())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 overlay-compatible byte distribution",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayCompatibleByteDistributionError(str(error)) from None


def validate_overlay_compatible_byte_distribution(value):
    try:
        from . import persona_v2_overlay_compatible_byte_distribution_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        import persona_v2_overlay_compatible_byte_distribution_validator as independent
    try:
        independent.validate_overlay_compatible_byte_distribution(value)
    except independent.PersonaV2OverlayCompatibleByteDistributionValidationError as error:
        raise PersonaV2OverlayCompatibleByteDistributionError(str(error)) from None
    return True


def overlay_compatible_byte_distribution_sha256(value=None):
    if value is None:
        value = build_overlay_compatible_byte_distribution()
    validate_overlay_compatible_byte_distribution(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_source_instance_parameter_assignment():
    raise PersonaV2OverlayCompatibleByteDistributionError(
        "the EML aggregate is now overlay-compatible, but all 203,000 source "
        "assignments, exact-duplicate coassignment, semantic payloads, solution, "
        "rendering, writes, history, KIO, capacity readback, and G0 remain absent"
    )


__all__ = [
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "ARTIFACT_KIND",
    "AUTHORITY_FIELDS",
    "EML_COMPLEXITY_ORDER",
    "MAX_CATALOG_BYTES",
    "PersonaV2OverlayCompatibleByteDistributionError",
    "build_overlay_compatible_byte_distribution",
    "canonical_json_bytes",
    "overlay_compatible_byte_distribution_sha256",
    "require_source_instance_parameter_assignment",
    "validate_overlay_compatible_byte_distribution",
]
