"""Incomplete, non-authorizing semantic-projection derivation inventory.

The inventory receipts existing external content-only projection bodies.  It
does not embed those bodies and deliberately covers only three of the twelve
minimum production projection classes.  Consequently it cannot issue the
corpus semantic namespace or authorize source identities, solving, G0, or
execution.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_lifecycle_effective_membership_reconciliation as effective
    from . import persona_v2_source_matched_lifecycle_inventory as matched
    from . import persona_v2_source_inventory_package as source_inventory
    from . import persona_v2_source_semantic_membership_package as base_semantic
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_lifecycle_effective_membership_reconciliation as effective
    import persona_v2_source_matched_lifecycle_inventory as matched
    import persona_v2_source_inventory_package as source_inventory
    import persona_v2_source_semantic_membership_package as base_semantic


SUITE_SCHEMA = "kio.persona.pc-semantic-projection-derivation-inventory/v1"
SUITE_KIND = "persona-pc-v2-semantic-projection-derivation-inventory"
RECEIPT_SCHEMA = "kio.persona.pc-semantic-projection-derivation-receipt/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_SCHEMA = SUITE_SCHEMA
ARTIFACT_KIND = SUITE_KIND

BASE_PROJECTION_SCHEMA = (
    "kio.persona.pc-base-source-content-context-shard-projection/v1"
)
BASE_PROJECTION_KIND = "persona-pc-v2-base-source-content-context-shard-projection"

MAX_SUITE_BYTES = 1 * 2**20
MAX_RECEIPT_COUNT = 113
MAX_JSONL_PROJECTION_BYTES = 4 * 2**20
MAX_JSON_PROJECTION_BYTES = 384 * 2**10
TARGET_JSON_PROJECTION_BYTES = 256 * 2**10
MAX_JSONL_ROWS = 4_096
MAX_JSONL_ROW_BYTES_INCLUDING_LF = 768
MAX_CUMULATIVE_PROJECTION_BYTES = 144 * 2**20

TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "derivation_receipts",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "missing_projection_class_ledger",
        "orders",
        "projection_class_registry",
        "remaining_blockers",
        "summary",
        "upstream_suite_bindings",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "coordinates",
        "direct_body_pins",
        "full_owner_pins",
        "projection_class_id",
        "projection_pin",
        "projector",
        "receipt_id",
        "row_kind",
        "row_schema",
        "validation",
    }
)
AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_lifecycle_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_corpus_semantic_namespace",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_namespace_completion",
        "authorizes_physical_write",
        "authorizes_query_rendering",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_identity_derivation",
        "authorizes_source_plan",
        "compiled_history_plan_available",
        "corpus_semantic_namespace_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "physical_materialization_observed",
        "solver_solution_available",
        "source_identity_namespace_authoritative",
    }
)

PROJECTION_CLASS_ORDER = (
    "topology-path-load",
    "realism-locale-security",
    "route-scores",
    "primary-use-case-corpus-half",
    "recipe-content-filename-policy",
    "fact-graph",
    "base-source-content-context",
    "effective-source-membership",
    "concrete-overlay-relations",
    "source-instance-parameters",
    "query-independent-lifecycle-fact-rendition-rules",
    "payload-equivalence-rules",
)
COVERED_CLASS_ORDER = (
    "base-source-content-context",
    "effective-source-membership",
    "query-independent-lifecycle-fact-rendition-rules",
)
MISSING_CLASS_ORDER = tuple(
    class_id for class_id in PROJECTION_CLASS_ORDER if class_id not in COVERED_CLASS_ORDER
)

EXPECTED_RECEIPT_COUNTS = {
    "base-source-content-context": 73,
    "effective-source-membership": 20,
    "query-independent-lifecycle-fact-rendition-rules": 20,
}

SOURCE_SEMANTIC_SUITE_BYTES = 49_837
SOURCE_SEMANTIC_SUITE_SHA256 = (
    "6027147bff72129aa308daa79c10581f6eceec9b04eb4667dbe72c0194ac6072"
)
MATCHED_SUITE_BYTES = 14_605
MATCHED_SUITE_SHA256 = (
    "b2ec04ef66476cc71b4ae1fb3275b8d5787eb560b5a7a7e2a3f03d690b77688b"
)
EFFECTIVE_SUITE_BYTES = 69_195
EFFECTIVE_SUITE_SHA256 = (
    "a624066396a534308c58cffe4f827160ea6d5f726c9507d9115e0ddb18752a29"
)

EXPECTED_SUITE_CANONICAL_BYTES = 293_285
EXPECTED_SUITE_SHA256 = (
    "e06e66901e24fda63a097dd2a5625cc562ea80008e8e6f5b961ce3c7a792dcdb"
)
EXPECTED_CUMULATIVE_PROJECTION_BYTES = 128_144_827
EXPECTED_ORDERED_PROJECTION_PINS_SHA256 = (
    "a909168390dbc7426d5ac21a36a5720c378e0d3281f852dcd90e40344e8cb83d"
)
EXPECTED_CLASS_MAXIMUM_BODY_BYTES = {
    "base-source-content-context": 2_484_590,
    "effective-source-membership": 103_840,
    "query-independent-lifecycle-fact-rendition-rules": 256_800,
}


class PersonaV2SemanticProjectionDerivationInventoryError(ValueError):
    """Raised when the bounded partial derivation inventory is invalid."""


def _fail(message):
    raise PersonaV2SemanticProjectionDerivationInventoryError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical_fragment(value, *, label, max_bytes=MAX_SUITE_BYTES):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=max_bytes,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def canonical_json_bytes(value):
    """Canonicalize the inventory descriptor, never an external projection."""

    if type(value) is not dict or value.get("artifact_schema") != SUITE_SCHEMA:
        _fail("semantic projection derivation inventory must use its exact schema")
    return _canonical_fragment(
        value,
        label="persona v2 semantic projection derivation inventory",
        max_bytes=MAX_SUITE_BYTES,
    )


def _negative_authority():
    return {
        "actual_chunks_attested": False,
        "actual_lifecycle_receipts_attested": False,
        "authorizes_compiled_history_plan": False,
        "authorizes_corpus_semantic_namespace": False,
        "authorizes_final_identifiers": False,
        "authorizes_g0_freeze": False,
        "authorizes_history_mutation": False,
        "authorizes_kio_execution": False,
        "authorizes_namespace_completion": False,
        "authorizes_physical_write": False,
        "authorizes_query_rendering": False,
        "authorizes_renderer_execution": False,
        "authorizes_solver_execution": False,
        "authorizes_source_identity_derivation": False,
        "authorizes_source_plan": False,
        "compiled_history_plan_available": False,
        "corpus_semantic_namespace_available": False,
        "filesystem_writer_available": False,
        "formal_capacity_gate_satisfied": False,
        "history_executor_available": False,
        "kio_execution_available": False,
        "physical_materialization_observed": False,
        "solver_solution_available": False,
        "source_identity_namespace_authoritative": False,
    }


def _generic_pin(
    *,
    artifact_kind,
    artifact_schema,
    artifact_schema_version,
    body_framing,
    canonical_bytes,
    sha256,
):
    return {
        "artifact_kind": artifact_kind,
        "artifact_schema": artifact_schema,
        "artifact_schema_version": artifact_schema_version,
        "body_framing": body_framing,
        "canonical_bytes": canonical_bytes,
        "sha256": sha256,
    }


def _artifact_pin(value, *, canonical, body_framing="canonical-json"):
    raw = canonical(value)
    return _generic_pin(
        artifact_kind=value["artifact_kind"],
        artifact_schema=value["artifact_schema"],
        artifact_schema_version=value["artifact_schema_version"],
        body_framing=body_framing,
        canonical_bytes=len(raw),
        sha256=_sha256(raw),
    )


def _full_owner_pin(
    value,
    *,
    canonical,
    coordinates,
    owner_id,
    owner_role,
    body_framing="canonical-json",
):
    pin = _artifact_pin(value, canonical=canonical, body_framing=body_framing)
    return {
        **pin,
        "coordinates": copy.deepcopy(coordinates),
        "owner_id": owner_id,
        "owner_role": owner_role,
    }


def _full_owner_pin_from_generic(pin, *, coordinates, owner_id, owner_role):
    return {
        **copy.deepcopy(pin),
        "coordinates": copy.deepcopy(coordinates),
        "owner_id": owner_id,
        "owner_role": owner_role,
    }


def _direct_body_pin(raw, *, direct_pin_id, direct_pin_role, body_framing):
    if type(raw) is not bytes or not raw:
        _fail("direct body pins require non-empty exact built-in bytes")
    return {
        "body_framing": body_framing,
        "canonical_bytes": len(raw),
        "direct_pin_id": direct_pin_id,
        "direct_pin_role": direct_pin_role,
        "sha256": _sha256(raw),
    }


SOURCE_SEMANTIC_SUITE_PIN = _generic_pin(
    artifact_kind=base_semantic.SUITE_ARTIFACT_KIND,
    artifact_schema=base_semantic.SUITE_ARTIFACT_SCHEMA,
    artifact_schema_version=base_semantic.ARTIFACT_SCHEMA_VERSION,
    body_framing="canonical-json",
    canonical_bytes=SOURCE_SEMANTIC_SUITE_BYTES,
    sha256=SOURCE_SEMANTIC_SUITE_SHA256,
)
MATCHED_SUITE_PIN = _generic_pin(
    artifact_kind=matched.SUITE_KIND,
    artifact_schema=matched.SUITE_SCHEMA,
    artifact_schema_version=matched.ARTIFACT_SCHEMA_VERSION,
    body_framing="canonical-json",
    canonical_bytes=MATCHED_SUITE_BYTES,
    sha256=MATCHED_SUITE_SHA256,
)
EFFECTIVE_SUITE_PIN = _generic_pin(
    artifact_kind=effective.SUITE_KIND,
    artifact_schema=effective.SUITE_SCHEMA,
    artifact_schema_version=effective.ARTIFACT_SCHEMA_VERSION,
    body_framing="canonical-json",
    canonical_bytes=EFFECTIVE_SUITE_BYTES,
    sha256=EFFECTIVE_SUITE_SHA256,
)


def _require_frozen_pin(actual, expected, *, label):
    if actual != expected:
        _fail(f"{label} differs from its frozen canonical suite pin")


def _require_true(result, *, label):
    if result is not True:
        _fail(f"{label} validator did not return exact True")


@functools.lru_cache(maxsize=1)
def _source_semantic_suite():
    value = base_semantic.build_source_semantic_membership_suite_descriptor()
    _require_true(
        base_semantic.validate_source_semantic_membership_suite_descriptor(value),
        label="source semantic membership suite",
    )
    _require_frozen_pin(
        _artifact_pin(value, canonical=base_semantic.canonical_json_bytes),
        SOURCE_SEMANTIC_SUITE_PIN,
        label="source semantic membership suite",
    )
    return value


@functools.lru_cache(maxsize=1)
def _matched_suite():
    value = matched.build_source_matched_lifecycle_suite_descriptor()
    _require_true(
        matched.validate_source_matched_lifecycle_suite_descriptor(value),
        label="source-matched lifecycle suite",
    )
    _require_frozen_pin(
        _artifact_pin(value, canonical=matched.canonical_json_bytes),
        MATCHED_SUITE_PIN,
        label="source-matched lifecycle suite",
    )
    return value


@functools.lru_cache(maxsize=1)
def _effective_suite():
    value = effective.build_lifecycle_effective_membership_suite_descriptor()
    _require_true(
        effective.validate_lifecycle_effective_membership_suite_descriptor(value),
        label="lifecycle effective-membership suite",
    )
    _require_frozen_pin(
        _artifact_pin(value, canonical=effective.canonical_json_bytes),
        EFFECTIVE_SUITE_PIN,
        label="lifecycle effective-membership suite",
    )
    return value


def _only_row(rows, *, label, predicate):
    matches = [row for row in rows if predicate(row)]
    if len(matches) != 1:
        _fail(f"{label} must resolve to exactly one row")
    return matches[0]


def _receipt(
    *,
    coordinates,
    direct_body_pins,
    full_owner_pins,
    projection_class_id,
    projection_pin,
    projector_id,
    receipt_id,
):
    return {
        "coordinates": copy.deepcopy(coordinates),
        "direct_body_pins": copy.deepcopy(direct_body_pins),
        "full_owner_pins": copy.deepcopy(full_owner_pins),
        "projection_class_id": projection_class_id,
        "projection_pin": copy.deepcopy(projection_pin),
        "projector": {
            "projector_id": projector_id,
            "projector_version": 1,
        },
        "receipt_id": receipt_id,
        "row_kind": "semantic-projection-derivation-receipt",
        "row_schema": RECEIPT_SCHEMA,
        "validation": {
            "independent_derivation_validation_required": True,
            "projection_pin_matches_external_body": True,
            "upstream_owner_validation_result": True,
            "upstream_projection_validation_result": True,
        },
    }


def _base_projection_receipts():
    suite_owner = _full_owner_pin_from_generic(
        SOURCE_SEMANTIC_SUITE_PIN,
        coordinates={},
        owner_id="persona-v2-source-semantic-membership-suite",
        owner_role="full-suite-owner-pin",
    )
    receipts = []
    for persona_id in envelope.PERSONA_IDS:
        for origin in base_semantic.ORIGIN_ORDER:
            origin_value = base_semantic.build_source_semantic_membership_origin_manifest(
                persona_id, origin
            )
            _require_true(
                base_semantic.validate_source_semantic_membership_origin_manifest(
                    persona_id, origin, origin_value
                ),
                label="source semantic membership origin",
            )
            origin_owner = _full_owner_pin(
                origin_value,
                canonical=base_semantic.canonical_json_bytes,
                coordinates={"origin": origin, "persona_id": persona_id},
                owner_id=(
                    f"persona-v2-source-semantic-membership-origin-{persona_id}-{origin}"
                ),
                owner_role="full-origin-owner-pin",
            )
            compact_body = base_semantic.source_semantic_membership_origin_body_bytes(
                persona_id, origin
            )
            range_rows = [
                row
                for row in base_semantic.iter_source_semantic_membership_origin_rows(
                    persona_id, origin
                )
                if row["row_kind"] == "source-shard-total-projection"
            ]
            for source_shard_ordinal, range_row in enumerate(range_rows, start=1):
                body = base_semantic.expanded_content_context_shard_body_bytes(
                    persona_id, origin, source_shard_ordinal
                )
                if (
                    len(body) != range_row["expanded_content_context_body_bytes"]
                    or _sha256(body)
                    != range_row["expanded_content_context_sha256"]
                ):
                    _fail("base content-context projection differs from owner receipt")
                range_raw = _canonical_fragment(
                    range_row,
                    label="source semantic shard total-projection receipt",
                )
                coordinates = {
                    "origin": origin,
                    "persona_id": persona_id,
                    "source_shard_id": range_row["source_shard_id"],
                    "source_shard_ordinal": source_shard_ordinal,
                }
                projection_pin = _generic_pin(
                    artifact_kind=BASE_PROJECTION_KIND,
                    artifact_schema=BASE_PROJECTION_SCHEMA,
                    artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
                    body_framing="canonical-jsonl-lf",
                    canonical_bytes=len(body),
                    sha256=_sha256(body),
                )
                receipts.append(
                    _receipt(
                        coordinates=coordinates,
                        direct_body_pins=[
                            _direct_body_pin(
                                compact_body,
                                direct_pin_id=(
                                    f"source-semantic-compact-origin-body-{persona_id}-{origin}"
                                ),
                                direct_pin_role="compact-origin-owner-body",
                                body_framing="canonical-jsonl-lf",
                            ),
                            _direct_body_pin(
                                range_raw,
                                direct_pin_id=(
                                    f"source-semantic-total-projection-receipt-"
                                    f"{persona_id}-{origin}-{source_shard_ordinal:03d}"
                                ),
                                direct_pin_role="matching-shard-total-projection-receipt",
                                body_framing="canonical-json",
                            ),
                        ],
                        full_owner_pins=[suite_owner, origin_owner],
                        projection_class_id="base-source-content-context",
                        projection_pin=projection_pin,
                        projector_id="base-source-content-context-shard-projector",
                        receipt_id=(
                            f"projection-derivation-base-content-context-"
                            f"{persona_id}-{origin}-{source_shard_ordinal:03d}"
                        ),
                    )
                )
    if len(receipts) != EXPECTED_RECEIPT_COUNTS["base-source-content-context"]:
        _fail("base content-context receipt cardinality drifted")
    # Verify the frozen suite only after the 40 origin manifests and 73
    # projections have been consumed, so its cache-release step cannot force a
    # second cold expansion of the source domain.  Then attach its exact
    # origin-binding row ahead of each already constructed direct owner chain.
    suite = _source_semantic_suite()
    suite_bindings = {
        (row["persona_id"], row["origin"]): row
        for row in suite["origin_manifest_bindings"]
    }
    if len(suite_bindings) != 40:
        _fail("source semantic suite origin binding cardinality drifted")
    for receipt in receipts:
        coordinates = receipt["coordinates"]
        persona_id = coordinates["persona_id"]
        origin = coordinates["origin"]
        binding = suite_bindings.get((persona_id, origin))
        if binding is None:
            _fail("base receipt lacks its source semantic suite origin binding")
        origin_owner = receipt["full_owner_pins"][1]
        if (
            binding.get("canonical_bytes") != origin_owner["canonical_bytes"]
            or binding.get("sha256") != origin_owner["sha256"]
            or binding.get("artifact_schema") != origin_owner["artifact_schema"]
        ):
            _fail("source semantic suite origin binding differs from full owner pin")
        binding_raw = _canonical_fragment(
            binding,
            label="source semantic suite origin binding",
        )
        receipt["direct_body_pins"].insert(
            0,
            _direct_body_pin(
                binding_raw,
                direct_pin_id=(
                    f"source-semantic-suite-origin-binding-{persona_id}-{origin}"
                ),
                direct_pin_role="suite-origin-binding-row",
                body_framing="canonical-json",
            ),
        )
    return receipts


def _effective_projection_receipts():
    suite = _effective_suite()
    suite_owner = _full_owner_pin_from_generic(
        EFFECTIVE_SUITE_PIN,
        coordinates={},
        owner_id="persona-v2-lifecycle-effective-membership-suite",
        owner_role="full-suite-and-direct-projection-owner-pin",
    )
    receipts = []
    for persona_id in envelope.PERSONA_IDS:
        projection = effective.build_lifecycle_effective_membership_content_projection(
            persona_id
        )
        _require_true(
            effective.validate_lifecycle_effective_membership_content_projection(
                persona_id, projection
            ),
            label="lifecycle effective-membership content projection",
        )
        body = effective.canonical_json_bytes(projection)
        binding = _only_row(
            suite["content_projection_bindings"],
            label="effective-membership suite content-projection binding",
            predicate=lambda row, p=persona_id: row.get("persona_id") == p,
        )
        if (
            binding.get("canonical_bytes") != len(body)
            or binding.get("sha256") != _sha256(body)
            or binding.get("artifact_schema") != effective.PROJECTION_SCHEMA
        ):
            _fail("effective-membership suite projection binding drifted")
        binding_raw = _canonical_fragment(
            binding,
            label="effective-membership suite content-projection binding",
        )
        receipts.append(
            _receipt(
                coordinates={"persona_id": persona_id},
                direct_body_pins=[
                    _direct_body_pin(
                        binding_raw,
                        direct_pin_id=(
                            f"effective-membership-suite-projection-binding-{persona_id}"
                        ),
                        direct_pin_role="suite-direct-projection-binding-row",
                        body_framing="canonical-json",
                    )
                ],
                full_owner_pins=[suite_owner],
                projection_class_id="effective-source-membership",
                projection_pin=_artifact_pin(
                    projection, canonical=effective.canonical_json_bytes
                ),
                projector_id="lifecycle-effective-membership-content-projector",
                receipt_id=(
                    f"projection-derivation-effective-membership-{persona_id}"
                ),
            )
        )
    if len(receipts) != EXPECTED_RECEIPT_COUNTS["effective-source-membership"]:
        _fail("effective-membership receipt cardinality drifted")
    return receipts


def _matched_lifecycle_projection_receipts():
    suite = _matched_suite()
    suite_owner = _full_owner_pin_from_generic(
        MATCHED_SUITE_PIN,
        coordinates={},
        owner_id="persona-v2-source-matched-lifecycle-suite",
        owner_role="full-suite-containing-persona-binding-pin",
    )
    receipts = []
    for persona_id in envelope.PERSONA_IDS:
        persona = matched.build_source_matched_lifecycle_persona(persona_id)
        _require_true(
            matched.validate_source_matched_lifecycle_persona(persona_id, persona),
            label="source-matched lifecycle persona",
        )
        persona_owner = _full_owner_pin(
            persona,
            canonical=matched.canonical_json_bytes,
            coordinates={"persona_id": persona_id},
            owner_id=f"persona-v2-source-matched-lifecycle-persona-{persona_id}",
            owner_role="full-persona-projection-and-event-receipt-owner-pin",
        )
        persona_binding = _only_row(
            suite["persona_bindings"],
            label="source-matched lifecycle suite persona binding",
            predicate=lambda row, p=persona_id: row.get("persona_id") == p,
        )
        persona_raw = matched.canonical_json_bytes(persona)
        if (
            persona_binding.get("canonical_bytes") != len(persona_raw)
            or persona_binding.get("sha256") != _sha256(persona_raw)
            or persona_binding.get("artifact_schema") != matched.PERSONA_SCHEMA
        ):
            _fail("source-matched lifecycle suite persona binding drifted")
        persona_binding_raw = _canonical_fragment(
            persona_binding,
            label="source-matched lifecycle suite persona binding",
        )
        event_receipt_raw = _canonical_fragment(
            persona["event_receipt"],
            label="source-matched lifecycle persona event receipt",
        )
        event_body = matched.source_matched_lifecycle_event_body_bytes(persona_id)
        if (
            persona["event_receipt"]["body_bytes"] != len(event_body)
            or persona["event_receipt"]["body_sha256"] != _sha256(event_body)
        ):
            _fail("source-matched lifecycle event body differs from persona receipt")
        projection = matched.build_source_matched_lifecycle_content_projection(
            persona_id
        )
        _require_true(
            matched.validate_source_matched_lifecycle_content_projection(
                persona_id, projection
            ),
            label="source-matched lifecycle content projection",
        )
        receipts.append(
            _receipt(
                coordinates={"persona_id": persona_id},
                direct_body_pins=[
                    _direct_body_pin(
                        persona_binding_raw,
                        direct_pin_id=(
                            f"source-matched-suite-persona-binding-{persona_id}"
                        ),
                        direct_pin_role="suite-persona-binding-row",
                        body_framing="canonical-json",
                    ),
                    _direct_body_pin(
                        event_receipt_raw,
                        direct_pin_id=(
                            f"source-matched-persona-event-receipt-{persona_id}"
                        ),
                        direct_pin_role="persona-event-receipt-row",
                        body_framing="canonical-json",
                    ),
                    _direct_body_pin(
                        event_body,
                        direct_pin_id=f"source-matched-event-body-{persona_id}",
                        direct_pin_role="receipt-authenticated-event-jsonl-body",
                        body_framing="canonical-jsonl-lf",
                    ),
                ],
                full_owner_pins=[suite_owner, persona_owner],
                projection_class_id=(
                    "query-independent-lifecycle-fact-rendition-rules"
                ),
                projection_pin=_artifact_pin(
                    projection, canonical=matched.canonical_json_bytes
                ),
                projector_id="source-matched-lifecycle-content-projector",
                receipt_id=f"projection-derivation-lifecycle-rules-{persona_id}",
            )
        )
    expected = EXPECTED_RECEIPT_COUNTS[
        "query-independent-lifecycle-fact-rendition-rules"
    ]
    if len(receipts) != expected:
        _fail("source-matched lifecycle receipt cardinality drifted")
    return receipts


def _projection_class_registry():
    rows = []
    for ordinal, projection_class_id in enumerate(PROJECTION_CLASS_ORDER, start=1):
        count = EXPECTED_RECEIPT_COUNTS.get(projection_class_id, 0)
        rows.append(
            {
                "coverage_status": (
                    "covered-local-derivation"
                    if count
                    else "missing-required-projection"
                ),
                "derivation_receipt_count": count,
                "inventory_ordinal": ordinal,
                "projection_class_id": projection_class_id,
            }
        )
    return rows


def _missing_projection_class_ledger():
    return [
        {
            "blocker_id": f"missing-semantic-projection-{projection_class_id}",
            "projection_class_id": projection_class_id,
            "required_for_minimum_inventory": True,
            "status": "active-g0",
        }
        for projection_class_id in MISSING_CLASS_ORDER
    ]


@functools.lru_cache(maxsize=1)
def _canonical_inventory():
    receipts = [
        *_base_projection_receipts(),
        *_effective_projection_receipts(),
        *_matched_lifecycle_projection_receipts(),
    ]
    if len(receipts) != MAX_RECEIPT_COUNT:
        _fail("semantic projection derivation receipt count drifted")
    if len({row["receipt_id"] for row in receipts}) != len(receipts):
        _fail("semantic projection derivation receipt IDs must be unique")
    projection_body_identities = {
        (
            row["projection_pin"]["sha256"],
            row["projection_pin"]["canonical_bytes"],
        )
        for row in receipts
    }
    if len(projection_body_identities) != MAX_RECEIPT_COUNT:
        _fail("semantic projection bodies must be unique across all coordinates")
    for row in receipts:
        if set(row) != RECEIPT_FIELDS:
            _fail("semantic projection derivation receipt schema drifted")
    cumulative_bytes = sum(
        row["projection_pin"]["canonical_bytes"] for row in receipts
    )
    if cumulative_bytes != EXPECTED_CUMULATIVE_PROJECTION_BYTES:
        _fail("external projection body byte total drifted from its frozen pin")
    if cumulative_bytes > MAX_CUMULATIVE_PROJECTION_BYTES:
        _fail("external projection bodies exceed their cumulative hard cap")
    class_maximum_body_bytes = {
        projection_class_id: max(
            row["projection_pin"]["canonical_bytes"]
            for row in receipts
            if row["projection_class_id"] == projection_class_id
        )
        for projection_class_id in COVERED_CLASS_ORDER
    }
    if class_maximum_body_bytes != EXPECTED_CLASS_MAXIMUM_BODY_BYTES:
        _fail("external projection class maximum body bytes drifted")
    ordered_pin_rows = [
        {
            "canonical_bytes": row["projection_pin"]["canonical_bytes"],
            "receipt_id": row["receipt_id"],
            "sha256": row["projection_pin"]["sha256"],
        }
        for row in receipts
    ]
    ordered_pin_raw = _canonical_fragment(
        ordered_pin_rows,
        label="ordered semantic projection pin rows",
    )
    if _sha256(ordered_pin_raw) != EXPECTED_ORDERED_PROJECTION_PINS_SHA256:
        _fail("ordered semantic projection pin digest drifted")
    class_counts = {
        projection_class_id: sum(
            row["projection_class_id"] == projection_class_id for row in receipts
        )
        for projection_class_id in COVERED_CLASS_ORDER
    }
    if class_counts != EXPECTED_RECEIPT_COUNTS:
        _fail("covered semantic projection class counts drifted")
    projection_class_registry = _projection_class_registry()
    missing_ledger = _missing_projection_class_ledger()
    value = {
        "artifact_kind": SUITE_KIND,
        "artifact_schema": SUITE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "external_projection_bodies_embedded": False,
            "max_cumulative_external_projection_bytes": MAX_CUMULATIVE_PROJECTION_BYTES,
            "max_json_projection_bytes": MAX_JSON_PROJECTION_BYTES,
            "max_jsonl_projection_bytes": MAX_JSONL_PROJECTION_BYTES,
            "max_jsonl_projection_row_bytes_including_lf": MAX_JSONL_ROW_BYTES_INCLUDING_LF,
            "max_jsonl_projection_rows": MAX_JSONL_ROWS,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_receipt_count": MAX_RECEIPT_COUNT,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "max_suite_bytes": MAX_SUITE_BYTES,
            "self_hash_embedded": False,
            "target_json_projection_bytes": TARGET_JSON_PROJECTION_BYTES,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_113_receipts_bound": True,
            "corpus_semantic_namespace_issued": False,
            "future_source_id_namespace_eligible": False,
            "local_three_class_derivation_complete": True,
            "minimum_projection_inventory_complete": False,
            "query_semantics_absence_proved": False,
            "semantic_payload_projection_bound": False,
        },
        "derivation_receipts": receipts,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-projection-derivation-evidence-not-observed-user-data"
        ),
        "missing_projection_class_ledger": missing_ledger,
        "orders": {
            "covered_projection_classes": list(COVERED_CLASS_ORDER),
            "derivation_receipts": (
                "base-content-context-persona-origin-shard-then-effective-"
                "membership-persona-then-source-matched-lifecycle-persona"
            ),
            "minimum_projection_classes": list(PROJECTION_CLASS_ORDER),
            "persona": list(envelope.PERSONA_IDS),
            "upstream_suite_bindings": [
                "source-semantic-membership",
                "lifecycle-effective-membership",
                "source-matched-lifecycle",
            ],
        },
        "projection_class_registry": projection_class_registry,
        "remaining_blockers": [
            "nine-minimum-semantic-projection-classes-not-derived",
            "complete-independent-projection-derivation-validation-not-yet-authoritative",
            "corpus-semantic-namespace-not-issued",
            "corpus-input-closure-and-blocker-resolution-ledger-not-complete",
            "joint-solver-solution-proof-and-final-source-plan-not-built",
            "compiled-history-physical-materialization-capacity-kio-and-g0-not-observed",
        ],
        "summary": {
            "covered_projection_class_count": len(COVERED_CLASS_ORDER),
            "cumulative_external_projection_bytes": cumulative_bytes,
            "derivation_receipt_count": len(receipts),
            "external_projection_body_count": len(receipts),
            "json_projection_body_count": sum(
                row["projection_pin"]["body_framing"] == "canonical-json"
                for row in receipts
            ),
            "jsonl_projection_body_count": sum(
                row["projection_pin"]["body_framing"] == "canonical-jsonl-lf"
                for row in receipts
            ),
            "minimum_projection_class_count": len(PROJECTION_CLASS_ORDER),
            "missing_projection_class_count": len(MISSING_CLASS_ORDER),
            "persona_count": len(envelope.PERSONA_IDS),
            "receipt_counts_by_projection_class": class_counts,
        },
        "upstream_suite_bindings": [
            copy.deepcopy(SOURCE_SEMANTIC_SUITE_PIN),
            copy.deepcopy(EFFECTIVE_SUITE_PIN),
            copy.deepcopy(MATCHED_SUITE_PIN),
        ],
    }
    if set(value) != TOP_LEVEL_FIELDS:
        _fail("semantic projection derivation inventory top-level schema drifted")
    if set(value["authority"]) != AUTHORITY_FIELDS or any(
        value["authority"].values()
    ):
        _fail("semantic projection derivation inventory gained authority")
    raw = canonical_json_bytes(value)
    if (
        len(raw) != EXPECTED_SUITE_CANONICAL_BYTES
        or _sha256(raw) != EXPECTED_SUITE_SHA256
    ):
        _fail("semantic projection derivation inventory canonical pin drifted")
    return value


def build_semantic_projection_derivation_inventory():
    """Return a detached descriptor for the exact 113 external projections."""

    return copy.deepcopy(_canonical_inventory())


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail("projection receipt persona_id is outside the exact suite")


def _require_exact_inventory_receipt(receipt):
    projection_class_id = receipt.get("projection_class_id")
    receipt_id = receipt.get("receipt_id")
    if (
        projection_class_id not in COVERED_CLASS_ORDER
        or type(receipt_id) is not str
        or not receipt_id
    ):
        _fail("projection body provider receipt identity is invalid")
    matches = [
        row
        for row in _canonical_inventory()["derivation_receipts"]
        if row["receipt_id"] == receipt_id
    ]
    if len(matches) != 1:
        _fail("projection body provider receipt is outside the exact inventory")
    supplied_raw = _canonical_fragment(
        receipt,
        label="projection body provider supplied receipt",
    )
    expected_raw = _canonical_fragment(
        matches[0],
        label="projection body provider expected receipt",
    )
    if not hmac.compare_digest(supplied_raw, expected_raw):
        _fail("projection body provider receipt differs from the exact inventory")


def projection_body_provider(receipt):
    """Regenerate one external projection body selected by an exact receipt.

    The returned body is never read from or embedded in the inventory.  The
    independent validator calls this provider twice and authenticates both
    results against the receipt's exact body pin.
    """

    if type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS:
        _fail("projection body provider requires one exact derivation receipt")
    projection_class_id = receipt["projection_class_id"]
    coordinates = receipt["coordinates"]
    if type(coordinates) is not dict:
        _fail("projection receipt coordinates must be an object")
    if projection_class_id == "base-source-content-context":
        if set(coordinates) != {
            "origin",
            "persona_id",
            "source_shard_id",
            "source_shard_ordinal",
        }:
            _fail("base projection coordinates drifted")
        persona_id = coordinates["persona_id"]
        origin = coordinates["origin"]
        source_shard_ordinal = coordinates["source_shard_ordinal"]
        _require_persona_id(persona_id)
        if origin not in base_semantic.ORIGIN_ORDER:
            _fail("base projection origin is invalid")
        if type(source_shard_ordinal) is not int or source_shard_ordinal <= 0:
            _fail("base projection shard ordinal is invalid")
        source_manifest = source_inventory.build_source_intent_origin_manifest(
            persona_id, origin
        )
        _require_true(
            source_inventory.validate_source_intent_origin_manifest(
                persona_id, origin, source_manifest
            ),
            label="source inventory origin manifest",
        )
        descriptors = source_manifest["shard_descriptors"]
        if source_shard_ordinal > len(descriptors):
            _fail("base projection shard ordinal is out of range")
        descriptor = descriptors[source_shard_ordinal - 1]
        if (
            descriptor["shard_ordinal"] != source_shard_ordinal
            or descriptor["shard_id"] != coordinates["source_shard_id"]
        ):
            _fail("base projection source_shard_id differs from its exact ordinal")
        expected_receipt_id = (
            f"projection-derivation-base-content-context-{persona_id}-{origin}-"
            f"{source_shard_ordinal:03d}"
        )
        if receipt["receipt_id"] != expected_receipt_id:
            _fail("base projection receipt ID differs from its coordinates")
        _require_exact_inventory_receipt(receipt)
        body = base_semantic.expanded_content_context_shard_body_bytes(
            persona_id, origin, source_shard_ordinal
        )
        if len(body) > MAX_JSONL_PROJECTION_BYTES:
            _fail("base projection body exceeds its hard cap")
        return body
    if projection_class_id == "effective-source-membership":
        if set(coordinates) != {"persona_id"}:
            _fail("effective-membership projection coordinates drifted")
        persona_id = coordinates["persona_id"]
        _require_persona_id(persona_id)
        if receipt["receipt_id"] != (
            f"projection-derivation-effective-membership-{persona_id}"
        ):
            _fail("effective-membership receipt ID differs from its coordinates")
        _require_exact_inventory_receipt(receipt)
        value = effective.build_lifecycle_effective_membership_content_projection(
            persona_id
        )
        _require_true(
            effective.validate_lifecycle_effective_membership_content_projection(
                persona_id, value
            ),
            label="lifecycle effective-membership content projection",
        )
        body = effective.canonical_json_bytes(value)
        if len(body) > MAX_JSON_PROJECTION_BYTES:
            _fail("effective-membership projection exceeds its hard cap")
        return body
    if projection_class_id == (
        "query-independent-lifecycle-fact-rendition-rules"
    ):
        if set(coordinates) != {"persona_id"}:
            _fail("source-matched lifecycle projection coordinates drifted")
        persona_id = coordinates["persona_id"]
        _require_persona_id(persona_id)
        if receipt["receipt_id"] != (
            f"projection-derivation-lifecycle-rules-{persona_id}"
        ):
            _fail("source-matched lifecycle receipt ID differs from its coordinates")
        _require_exact_inventory_receipt(receipt)
        value = matched.build_source_matched_lifecycle_content_projection(persona_id)
        _require_true(
            matched.validate_source_matched_lifecycle_content_projection(
                persona_id, value
            ),
            label="source-matched lifecycle content projection",
        )
        body = matched.canonical_json_bytes(value)
        if len(body) > MAX_JSON_PROJECTION_BYTES:
            _fail("source-matched lifecycle projection exceeds its hard cap")
        return body
    _fail("projection body provider received an uncovered projection class")


def _independent_validator():
    try:
        from . import persona_v2_semantic_projection_derivation_inventory_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_semantic_projection_derivation_inventory_validator as independent
        except ImportError:
            independent = None
    return independent


def _require_independent_validator():
    independent = _independent_validator()
    if independent is None:
        _fail("independent semantic projection derivation validator is unavailable")
    return independent


def validate_semantic_projection_derivation_inventory(
    value,
    projection_body_provider=None,
):
    """Validate through the producer-independent, provider-replaying boundary."""

    raw = canonical_json_bytes(value)
    snapshot = json.loads(raw)
    independent = _require_independent_validator()
    provider = (
        globals()["projection_body_provider"]
        if projection_body_provider is None
        else projection_body_provider
    )
    try:
        result = independent.validate_semantic_projection_derivation_inventory(
            snapshot,
            projection_body_provider=provider,
        )
    except independent.PersonaV2SemanticProjectionDerivationInventoryValidationError as error:
        _fail(str(error))
    finally:
        try:
            closing_raw = canonical_json_bytes(value)
        except Exception as error:
            raise PersonaV2SemanticProjectionDerivationInventoryError(
                "semantic projection derivation inventory changed during validation"
            ) from error
        if not hmac.compare_digest(raw, closing_raw):
            _fail("semantic projection derivation inventory changed during validation")
    if result is not True:
        _fail("independent semantic projection derivation validator did not return True")
    return True


def semantic_projection_derivation_inventory_sha256(
    value=None,
    projection_body_provider=None,
):
    """Hash exactly the detached opening bytes accepted by the validator."""

    if value is None:
        value = build_semantic_projection_derivation_inventory()
    raw = canonical_json_bytes(value)
    snapshot = json.loads(raw)
    try:
        validate_semantic_projection_derivation_inventory(
            snapshot,
            projection_body_provider=projection_body_provider,
        )
    finally:
        try:
            closing_raw = canonical_json_bytes(value)
        except Exception as error:
            raise PersonaV2SemanticProjectionDerivationInventoryError(
                "semantic projection derivation inventory changed while hashing"
            ) from error
        if not hmac.compare_digest(raw, closing_raw):
            _fail("semantic projection derivation inventory changed while hashing")
    return _sha256(raw)


def require_complete_semantic_projection_inventory():
    raise PersonaV2SemanticProjectionDerivationInventoryError(
        "three local semantic projection classes have 113 exact derivation "
        "receipts, but nine required classes, namespace issuance, corpus/evaluation "
        "closures, solving, history, physical execution, observations, and G0 remain "
        "downstream"
    )


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "BASE_PROJECTION_KIND",
    "BASE_PROJECTION_SCHEMA",
    "COVERED_CLASS_ORDER",
    "EFFECTIVE_SUITE_BYTES",
    "EFFECTIVE_SUITE_SHA256",
    "EXPECTED_CLASS_MAXIMUM_BODY_BYTES",
    "EXPECTED_CUMULATIVE_PROJECTION_BYTES",
    "EXPECTED_ORDERED_PROJECTION_PINS_SHA256",
    "EXPECTED_RECEIPT_COUNTS",
    "EXPECTED_SUITE_CANONICAL_BYTES",
    "EXPECTED_SUITE_SHA256",
    "MATCHED_SUITE_BYTES",
    "MATCHED_SUITE_SHA256",
    "MAX_CUMULATIVE_PROJECTION_BYTES",
    "MAX_JSONL_PROJECTION_BYTES",
    "MAX_JSONL_ROWS",
    "MAX_JSONL_ROW_BYTES_INCLUDING_LF",
    "MAX_JSON_PROJECTION_BYTES",
    "MAX_RECEIPT_COUNT",
    "MAX_SUITE_BYTES",
    "MISSING_CLASS_ORDER",
    "PROJECTION_CLASS_ORDER",
    "PersonaV2SemanticProjectionDerivationInventoryError",
    "RECEIPT_FIELDS",
    "RECEIPT_SCHEMA",
    "SOURCE_SEMANTIC_SUITE_BYTES",
    "SOURCE_SEMANTIC_SUITE_SHA256",
    "SUITE_KIND",
    "SUITE_SCHEMA",
    "TARGET_JSON_PROJECTION_BYTES",
    "TOP_LEVEL_FIELDS",
    "build_semantic_projection_derivation_inventory",
    "canonical_json_bytes",
    "projection_body_provider",
    "require_complete_semantic_projection_inventory",
    "semantic_projection_derivation_inventory_sha256",
    "validate_semantic_projection_derivation_inventory",
]
