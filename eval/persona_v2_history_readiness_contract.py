"""Static, non-authorizing history-readiness runtime contract candidate.

This compact artifact fixes the *shape* of the eventual observed history
gate: three independently created replay containers with three first-in-order
container receipts, sixty persona-device roots, sixty distinct persona
registry roots, seven ordered checkpoints, 420 persona/checkpoint receipts,
21 checkpoint seals, and three replay terminals. Runtime receipts and their
hashes remain external dynamic evidence and are deliberately outside this
candidate's global body golden.

The direct dependency pins are the accepted, frozen structural history
pre-solve slice and the accepted, frozen device compositor body identity used
only to bind the exact formal replay-ID namespace.  Neither dependency is
issued by this candidate, and their acceptance grants no runtime authority.
Fast construction is pin-only; the opt-in full path independently replays the
live history body.  No query,
oracle, evaluation result, filesystem observation, history mutation, KIO
execution, or G0 authority is imported or granted.
"""

from __future__ import annotations

import copy
import hashlib
import hmac

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_device_lane_compositor as device_compositor
    from . import persona_v2_history_presolve_input_closure_slice as history_slice
    from . import persona_v2_history_readiness_contract_validator as independent
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_device_lane_compositor as device_compositor
    import persona_v2_history_presolve_input_closure_slice as history_slice
    import persona_v2_history_readiness_contract_validator as independent


ARTIFACT_SCHEMA = "kio.persona.pc-history-readiness-contract/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-static-non-authorizing-history-readiness-contract-candidate"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 512 * 2**10
TARGET_CONTRACT_BYTES = 256 * 2**10
MAX_PREFLIGHT_NODE_COUNT = 100_000
MAX_PREFLIGHT_CONTAINER_ITEMS = 1_024

# The static body is at its post-upstream-freeze measurement target.  Its own
# literal golden remains unset until that changed body is measured separately.
EXPECTED_CANONICAL_BYTES = None
EXPECTED_SHA256 = None

HISTORY_SLICE_CANONICAL_BYTES = 8_455
HISTORY_SLICE_SHA256 = (
    "2c94ae39e60af5970053ddcd205670791d6cdee6bd5bffc8cad1270c221d3ea0"
)
DEVICE_COMPOSITOR_CANONICAL_BYTES = 41_099
DEVICE_COMPOSITOR_SHA256 = (
    "eb1a82d631b810ca96d90c84f9324263b4bb1018f0cde2a8339037a183d35bdf"
)

PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, 21))
REPLAY_IDS = (
    "formal-replay-01",
    "formal-replay-02",
    "formal-replay-03",
)
CHECKPOINT_ROWS = (
    ("W0", 120_000, 0),
    ("W1", 120_000, 24_000),
    ("W2", 120_000, 24_000),
    ("W3", 120_000, 48_000),
    ("W4", 120_000, 60_000),
    ("W5-pre-purge", 124_800, 64_800),
    ("W5-final", 120_000, 60_000),
)

REPLAY_CONTAINER_RECEIPT_FIELDS = (
    "container_created_empty_before_any_persona_root",
    "container_created_exclusively",
    "container_created_fresh",
    "container_created_without_copy_clone_reflink_or_hardlink",
    "container_creation_nonce_sha256",
    "container_did_not_replace_existing_path",
    "container_path_did_not_exist_before_creation",
    "fixture_id",
    "fixture_schema_version",
    "receipt_emitted_before_any_persona_root_or_write",
    "receipt_id",
    "receipt_schema",
    "receipt_schema_version",
    "replay_container_id",
    "replay_container_path_sha256",
    "replay_id",
)

FRESH_ROOT_FIELDS = (
    "device_root_created_empty_before_registry_or_write",
    "device_root_created_without_copy_clone_or_hardlink",
    "device_root_is_strict_descendant_of_replay_container",
    "fixture_id",
    "fixture_schema_version",
    "persona_device_root_id",
    "persona_device_root_path_sha256",
    "persona_id",
    "persona_registry_root_id",
    "persona_registry_root_path_sha256",
    "receipt_id",
    "receipt_schema",
    "receipt_schema_version",
    "registry_is_strict_descendant_of_device_root",
    "registry_root_created_fresh",
    "registry_root_created_without_copy_clone_or_hardlink",
    "replay_container_id",
    "replay_container_path_sha256",
    "replay_container_receipt_id",
    "replay_container_receipt_sha256",
    "replay_id",
    "root_creation_nonce_sha256",
    "scope_count",
    "source_plan_sha256",
    "writer_plan_sha256",
)

PERSONA_CHECKPOINT_RECEIPT_FIELDS = (
    "checkpoint",
    "checkpoint_event_journal_sha256",
    "checkpoint_filesystem_snapshot_sha256",
    "checkpoint_kio_snapshot_sha256",
    "checkpoint_ordinal",
    "chunking_config_sha256",
    "compiled_history_plan_sha256",
    "contract_current_endpoint_count",
    "contract_history_only_endpoint_count",
    "current_endpoint_set_sha256",
    "current_history_sets_disjoint",
    "fail_fast_checks_passed",
    "fixture_id",
    "fixture_schema_version",
    "history_only_endpoint_set_sha256",
    "metric_id",
    "observed_after_index_before_next_mutation",
    "persona_id",
    "persona_root_identity_matches",
    "persona_root_receipt_sha256",
    "plan_identity_matches",
    "predecessor_state_sha256",
    "receipt_id",
    "receipt_schema",
    "receipt_schema_version",
    "replay_id",
    "scope_count",
    "scope_registry_sha256",
    "source_plan_sha256",
)

CHECKPOINT_SEAL_FIELDS = (
    "all_receipts_validated",
    "checkpoint",
    "checkpoint_current_endpoint_total",
    "checkpoint_history_only_endpoint_total",
    "checkpoint_ordinal",
    "failed_receipt_count",
    "fixture_id",
    "fixture_schema_version",
    "ordered_persona_checkpoint_receipt_bodies_sha256",
    "ordered_persona_checkpoint_receipt_ids_sha256",
    "ordered_persona_root_receipt_bodies_sha256",
    "ordered_persona_root_receipt_ids_sha256",
    "predecessor_state_sha256",
    "receipt_count",
    "replay_id",
    "seal_id",
    "seal_schema",
    "seal_schema_version",
    "sealed_before_next_mutation",
)

REPLAY_TERMINAL_FIELDS = (
    "checkpoint_seal_count",
    "failed_state_count",
    "fixture_id",
    "fixture_schema_version",
    "ordered_checkpoint_seal_bodies_sha256",
    "ordered_checkpoint_seal_ids_sha256",
    "ordered_persona_root_receipt_bodies_sha256",
    "ordered_persona_root_receipt_ids_sha256",
    "persona_checkpoint_receipt_count",
    "replay_container_receipt_body_sha256",
    "replay_container_receipt_id",
    "replay_id",
    "replay_terminal",
    "roots_never_copied_cloned_or_hardlinked",
    "terminal_id",
    "terminal_schema",
    "terminal_schema_version",
    "w5_final_seal_sha256",
)

AUTHORITY_FIELDS = frozenset(
    {
        "actual_checkpoint_cardinalities_attested",
        "actual_history_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_evaluation_execution",
        "authorizes_evaluation_result_acceptance",
        "authorizes_g0_freeze",
        "authorizes_history_input_closure",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_replay_execution",
        "authorizes_runtime_receipt_issuance",
        "authorizes_solver_execution",
        "dependency_accepted",
        "dependency_frozen",
        "dependency_issued",
    }
)


class PersonaV2HistoryReadinessContractError(ValueError):
    """Raised when the static history-readiness contract is not exact."""


def _fail(message):
    raise PersonaV2HistoryReadinessContractError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return len(left) == len(right) and all(
            key in right and _strict_equal(left[key], right[key]) for key in left
        )
    if type(left) in (list, tuple):
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _expected_golden():
    byte_count_set = EXPECTED_CANONICAL_BYTES is not None
    digest_set = EXPECTED_SHA256 is not None
    if byte_count_set != digest_set:
        _fail("history-readiness golden must be entirely unset or entirely set")
    if not byte_count_set:
        return None
    if (
        type(EXPECTED_CANONICAL_BYTES) is not int
        or type(EXPECTED_CANONICAL_BYTES) is bool
        or not 1 <= EXPECTED_CANONICAL_BYTES <= TARGET_CONTRACT_BYTES
        or type(EXPECTED_SHA256) is not str
        or len(EXPECTED_SHA256) != 64
        or any(character not in "0123456789abcdef" for character in EXPECTED_SHA256)
    ):
        _fail("history-readiness golden configuration is invalid")
    return EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256


def _require_golden_parity():
    """Authenticate both optional golden configurations before live access."""

    producer_expected = _expected_golden()
    try:
        validator_expected = independent._expected_golden()
    except Exception as error:
        raise PersonaV2HistoryReadinessContractError(
            "validator history-readiness golden configuration is invalid"
        ) from error
    if not _strict_equal(producer_expected, validator_expected):
        _fail("producer and validator history-readiness goldens differ")
    return producer_expected


def _canonical(value, *, label):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _require_expected_raw(raw):
    if type(raw) is not bytes or len(raw) > MAX_CONTRACT_BYTES:
        _fail("history-readiness candidate is not bounded exact bytes")
    expected = _expected_golden()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("history-readiness candidate differs from its frozen golden")
    return raw


def _history_slice_binding():
    return {
        "artifact_kind": history_slice.ARTIFACT_KIND,
        "artifact_schema": history_slice.ARTIFACT_SCHEMA,
        "artifact_schema_version": history_slice.ARTIFACT_SCHEMA_VERSION,
        "body_opened_in_fast_candidate_build": False,
        "body_required_for_full_acceptance": True,
        "canonical_bytes": HISTORY_SLICE_CANONICAL_BYTES,
        "dependency_accepted": True,
        "dependency_frozen": True,
        "dependency_id": "history-presolve-input-closure-slice-v1",
        "dependency_issued": False,
        "dependency_role": (
            "query-independent-structural-history-demand-accepted-frozen-pin"
        ),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "pin_status": "accepted-frozen-history-slice-body-pin-not-issued",
        "sha256": HISTORY_SLICE_SHA256,
    }


def _device_compositor_replay_binding():
    return {
        "artifact_kind": device_compositor.ARTIFACT_KIND,
        "artifact_schema": device_compositor.ARTIFACT_SCHEMA,
        "artifact_schema_version": device_compositor.ARTIFACT_SCHEMA_VERSION,
        "body_opened_in_fast_candidate_build": False,
        "body_required_for_full_acceptance": False,
        "binding_scope": "replay-id-order-only-no-runtime-or-path-authority",
        "canonical_bytes": DEVICE_COMPOSITOR_CANONICAL_BYTES,
        "dependency_accepted": True,
        "dependency_frozen": True,
        "dependency_id": "device-lane-compositor-v1-formal-replay-namespace",
        "dependency_issued": False,
        "dependency_role": "exact-formal-replay-id-order-and-namespace-binding",
        "expected_replay_ids": list(REPLAY_IDS),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "pin_status": (
            "accepted-frozen-compositor-replay-id-binding-not-issued"
        ),
        "sha256": DEVICE_COMPOSITOR_SHA256,
    }


def _candidate_dependency_snapshot():
    return {
        "dependency_pin": copy.deepcopy(_history_slice_binding()),
        "replay_id_dependency_pin": copy.deepcopy(
            _device_compositor_replay_binding()
        ),
    }


def _require_dependency_constant_alignment():
    if (
        history_slice.ARTIFACT_SCHEMA
        != "kio.persona.pc-history-presolve-input-closure-slice/v1"
        or history_slice.ARTIFACT_SCHEMA_VERSION != 1
        or history_slice.ARTIFACT_KIND
        != "persona-pc-v2-non-authorizing-history-presolve-input-closure-slice"
        or history_slice.EXPECTED_CANONICAL_BYTES
        != HISTORY_SLICE_CANONICAL_BYTES
        or history_slice.EXPECTED_SHA256 != HISTORY_SLICE_SHA256
        or independent.history_validator.ARTIFACT_SCHEMA
        != "kio.persona.pc-history-presolve-input-closure-slice/v1"
        or independent.history_validator.ARTIFACT_SCHEMA_VERSION != 1
        or independent.history_validator.ARTIFACT_KIND
        != "persona-pc-v2-non-authorizing-history-presolve-input-closure-slice"
        or independent.history_validator.EXPECTED_CANONICAL_BYTES
        != HISTORY_SLICE_CANONICAL_BYTES
        or independent.history_validator.EXPECTED_SHA256
        != HISTORY_SLICE_SHA256
        or device_compositor.ARTIFACT_SCHEMA
        != "kio.persona.pc-device-lane-compositor/v1"
        or device_compositor.ARTIFACT_SCHEMA_VERSION != 1
        or device_compositor.ARTIFACT_KIND
        != "persona-pc-v2-non-authorizing-device-lane-compositor-candidate"
        or device_compositor.EXPECTED_CANONICAL_BYTES
        != DEVICE_COMPOSITOR_CANONICAL_BYTES
        or device_compositor.EXPECTED_SHA256 != DEVICE_COMPOSITOR_SHA256
        or not _strict_equal(device_compositor.REPLAY_IDS, REPLAY_IDS)
        or independent.compositor_validator.ARTIFACT_SCHEMA
        != "kio.persona.pc-device-lane-compositor/v1"
        or independent.compositor_validator.ARTIFACT_SCHEMA_VERSION != 1
        or independent.compositor_validator.ARTIFACT_KIND
        != "persona-pc-v2-non-authorizing-device-lane-compositor-candidate"
        or independent.compositor_validator.EXPECTED_CANONICAL_BYTES
        != DEVICE_COMPOSITOR_CANONICAL_BYTES
        or independent.compositor_validator.EXPECTED_SHA256
        != DEVICE_COMPOSITOR_SHA256
        or not _strict_equal(independent.compositor_validator.REPLAY_IDS, REPLAY_IDS)
    ):
        _fail("history-readiness frozen dependency identity or golden drifted")


def _checkpoint_contract():
    return [
        {
            "checkpoint": checkpoint,
            "checkpoint_ordinal": ordinal,
            "current_contract_semantic_endpoints_per_persona": current_count,
            "history_only_contract_semantic_endpoints_per_persona": history_count,
            "persona_count": len(PERSONA_IDS),
            "receipt_count_per_replay": len(PERSONA_IDS),
            "total_current_contract_semantic_endpoints_per_replay": (
                current_count * len(PERSONA_IDS)
            ),
            "total_history_only_contract_semantic_endpoints_per_replay": (
                history_count * len(PERSONA_IDS)
            ),
        }
        for ordinal, (checkpoint, current_count, history_count) in enumerate(
            CHECKPOINT_ROWS
        )
    ]


def _replay_container_coordinates():
    return [
        {
            "replay_container_id": f"formal-replay-container/{replay_id}",
            "replay_id": replay_id,
            "replay_ordinal": replay_ordinal,
            "required_receipt_id": (
                f"history-readiness-container-receipt/{replay_id}"
            ),
        }
        for replay_ordinal, replay_id in enumerate(REPLAY_IDS)
    ]


def _replay_container_receipt_coordinates():
    return [
        {
            "receipt_id": f"history-readiness-container-receipt/{replay_id}",
            "replay_container_id": f"formal-replay-container/{replay_id}",
            "replay_id": replay_id,
            "replay_ordinal": replay_ordinal,
        }
        for replay_ordinal, replay_id in enumerate(REPLAY_IDS)
    ]


def _persona_device_root_coordinates():
    return [
        {
            "persona_device_root_id": f"persona-device-root/{replay_id}/{persona_id}",
            "persona_id": persona_id,
            "persona_ordinal": persona_ordinal,
            "replay_container_id": f"formal-replay-container/{replay_id}",
            "replay_id": replay_id,
            "replay_ordinal": replay_ordinal,
            "required_replay_container_receipt_id": (
                f"history-readiness-container-receipt/{replay_id}"
            ),
            "required_receipt_id": f"history-readiness-root-receipt/{replay_id}/{persona_id}",
        }
        for replay_ordinal, replay_id in enumerate(REPLAY_IDS)
        for persona_ordinal, persona_id in enumerate(PERSONA_IDS, start=1)
    ]


def _persona_registry_root_coordinates():
    return [
        {
            "persona_id": persona_id,
            "persona_ordinal": persona_ordinal,
            "persona_registry_root_id": f"persona-registry-root/{replay_id}/{persona_id}",
            "replay_container_id": f"formal-replay-container/{replay_id}",
            "replay_id": replay_id,
            "replay_ordinal": replay_ordinal,
            "required_replay_container_receipt_id": (
                f"history-readiness-container-receipt/{replay_id}"
            ),
            "required_receipt_id": f"history-readiness-root-receipt/{replay_id}/{persona_id}",
        }
        for replay_ordinal, replay_id in enumerate(REPLAY_IDS)
        for persona_ordinal, persona_id in enumerate(PERSONA_IDS, start=1)
    ]


def _persona_root_receipt_coordinates():
    return [
        {
            "persona_device_root_id": f"persona-device-root/{replay_id}/{persona_id}",
            "persona_id": persona_id,
            "persona_ordinal": persona_ordinal,
            "persona_registry_root_id": f"persona-registry-root/{replay_id}/{persona_id}",
            "receipt_id": f"history-readiness-root-receipt/{replay_id}/{persona_id}",
            "replay_container_id": f"formal-replay-container/{replay_id}",
            "replay_container_receipt_id": (
                f"history-readiness-container-receipt/{replay_id}"
            ),
            "replay_id": replay_id,
            "replay_ordinal": replay_ordinal,
        }
        for replay_ordinal, replay_id in enumerate(REPLAY_IDS)
        for persona_ordinal, persona_id in enumerate(PERSONA_IDS, start=1)
    ]


def _persona_receipt_coordinates():
    rows = []
    for replay_ordinal, replay_id in enumerate(REPLAY_IDS):
        for checkpoint_ordinal, (checkpoint, current_count, history_count) in enumerate(
            CHECKPOINT_ROWS
        ):
            for persona_ordinal, persona_id in enumerate(PERSONA_IDS, start=1):
                rows.append(
                    {
                        "checkpoint": checkpoint,
                        "checkpoint_ordinal": checkpoint_ordinal,
                        "expected_contract_current_endpoint_count": current_count,
                        "expected_contract_history_only_endpoint_count": history_count,
                        "persona_id": persona_id,
                        "persona_ordinal": persona_ordinal,
                        "receipt_id": (
                            f"history-readiness-persona-receipt/{replay_id}/"
                            f"{checkpoint}/{persona_id}"
                        ),
                        "replay_id": replay_id,
                        "replay_ordinal": replay_ordinal,
                    }
                )
    return rows


def _checkpoint_seal_coordinates():
    rows = []
    for replay_ordinal, replay_id in enumerate(REPLAY_IDS):
        for checkpoint_ordinal, (checkpoint, current_count, history_count) in enumerate(
            CHECKPOINT_ROWS
        ):
            rows.append(
                {
                    "checkpoint": checkpoint,
                    "checkpoint_ordinal": checkpoint_ordinal,
                    "expected_current_endpoint_total": current_count * len(PERSONA_IDS),
                    "expected_history_only_endpoint_total": history_count * len(PERSONA_IDS),
                    "expected_persona_receipt_count": len(PERSONA_IDS),
                    "predecessor_kind": (
                        "persona-root-receipt-bundle"
                        if checkpoint_ordinal == 0
                        else "checkpoint-seal"
                    ),
                    "replay_id": replay_id,
                    "replay_ordinal": replay_ordinal,
                    "seal_id": f"history-readiness-checkpoint-seal/{replay_id}/{checkpoint}",
                }
            )
    return rows


def _terminal_coordinates():
    return [
        {
            "expected_checkpoint_seal_count": len(CHECKPOINT_ROWS),
            "expected_persona_checkpoint_receipt_count": (
                len(PERSONA_IDS) * len(CHECKPOINT_ROWS)
            ),
            "replay_container_receipt_id": (
                f"history-readiness-container-receipt/{replay_id}"
            ),
            "replay_id": replay_id,
            "replay_ordinal": replay_ordinal,
            "terminal_id": f"history-readiness-replay-terminal/{replay_id}",
        }
        for replay_ordinal, replay_id in enumerate(REPLAY_IDS)
    ]


def _field_contracts():
    digest_rule = "exact-lowercase-hex-sha256-of-detached-canonical-or-framed-body"
    return {
        "checkpoint_seal": {
            "additional_fields_allowed": False,
            "coordinate_binding": {
                "coordinate_fields": [
                    "replay_id",
                    "checkpoint",
                    "checkpoint_ordinal",
                    "seal_id",
                ],
                "count_fields_must_equal_coordinate_literals": True,
                "ordered_persona_root_receipt_bodies_bind_exact_replay_root_set": True,
                "predecessor_is_persona_root_receipt_bundle_for_w0_else_previous_checkpoint_seal": True,
                "persona_checkpoint_receipt_ids_and_bodies_are_ordered_by_persona_id_ascii": True,
            },
            "digest_fields": [
                "ordered_persona_checkpoint_receipt_bodies_sha256",
                "ordered_persona_checkpoint_receipt_ids_sha256",
                "ordered_persona_root_receipt_bodies_sha256",
                "ordered_persona_root_receipt_ids_sha256",
                "predecessor_state_sha256",
            ],
            "digest_rule": digest_rule,
            "exact_false_or_zero_fields": {"failed_receipt_count": 0},
            "exact_true_fields": [
                "all_receipts_validated",
                "sealed_before_next_mutation",
            ],
            "required_fields": list(CHECKPOINT_SEAL_FIELDS),
            "schema_identity": {
                "fixture_id": FIXTURE_ID,
                "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
                "seal_schema": "kio.persona.pc-history-readiness-checkpoint-seal/v1",
                "seal_schema_version": 1,
            },
        },
        "replay_container_receipt": {
            "additional_fields_allowed": False,
            "coordinate_binding": {
                "coordinate_fields": [
                    "replay_id",
                    "replay_container_id",
                    "receipt_id",
                ],
                "one_receipt_per_replay_without_pooling": True,
                "receipt_is_first_runtime_artifact_for_replay": True,
            },
            "digest_fields": [
                "container_creation_nonce_sha256",
                "replay_container_path_sha256",
            ],
            "digest_rule": digest_rule,
            "exact_true_fields": [
                "container_created_empty_before_any_persona_root",
                "container_created_exclusively",
                "container_created_fresh",
                "container_created_without_copy_clone_reflink_or_hardlink",
                "container_did_not_replace_existing_path",
                "container_path_did_not_exist_before_creation",
                "receipt_emitted_before_any_persona_root_or_write",
            ],
            "required_fields": list(REPLAY_CONTAINER_RECEIPT_FIELDS),
            "schema_identity": {
                "fixture_id": FIXTURE_ID,
                "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
                "receipt_schema": "kio.persona.pc-history-readiness-replay-container-receipt/v1",
                "receipt_schema_version": 1,
            },
        },
        "persona_root_receipt": {
            "additional_fields_allowed": False,
            "coordinate_binding": {
                "coordinate_fields": [
                    "replay_id",
                    "replay_container_id",
                    "persona_id",
                    "persona_device_root_id",
                    "persona_registry_root_id",
                    "replay_container_receipt_id",
                    "receipt_id",
                ],
                "container_receipt_is_root_receipt_predecessor": True,
                "device_and_registry_root_ids_must_be_distinct": True,
                "device_and_registry_root_sets_have_exactly_60_members_each": True,
                "receipt_emitted_before_any_writer_or_kio_mutation": True,
                "scope_count": 20,
            },
            "digest_fields": [
                "persona_device_root_path_sha256",
                "persona_registry_root_path_sha256",
                "replay_container_path_sha256",
                "replay_container_receipt_sha256",
                "root_creation_nonce_sha256",
                "source_plan_sha256",
                "writer_plan_sha256",
            ],
            "digest_rule": digest_rule,
            "exact_true_fields": [
                "device_root_created_empty_before_registry_or_write",
                "device_root_created_without_copy_clone_or_hardlink",
                "device_root_is_strict_descendant_of_replay_container",
                "registry_is_strict_descendant_of_device_root",
                "registry_root_created_fresh",
                "registry_root_created_without_copy_clone_or_hardlink",
            ],
            "required_fields": list(FRESH_ROOT_FIELDS),
            "schema_identity": {
                "fixture_id": FIXTURE_ID,
                "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
                "receipt_schema": "kio.persona.pc-history-readiness-persona-root-receipt/v1",
                "receipt_schema_version": 1,
            },
        },
        "persona_checkpoint_receipt": {
            "additional_fields_allowed": False,
            "coordinate_binding": {
                "coordinate_fields": [
                    "replay_id",
                    "checkpoint",
                    "checkpoint_ordinal",
                    "persona_id",
                    "receipt_id",
                ],
                "contract_c_and_h_must_equal_coordinate_literals": True,
                "one_receipt_per_coordinate_without_pooling": True,
                "predecessor_is_persona_root_receipt_for_w0_else_previous_checkpoint_seal": True,
                "scope_count": 20,
            },
            "digest_fields": [
                "checkpoint_event_journal_sha256",
                "checkpoint_filesystem_snapshot_sha256",
                "checkpoint_kio_snapshot_sha256",
                "chunking_config_sha256",
                "compiled_history_plan_sha256",
                "current_endpoint_set_sha256",
                "history_only_endpoint_set_sha256",
                "persona_root_receipt_sha256",
                "predecessor_state_sha256",
                "scope_registry_sha256",
                "source_plan_sha256",
            ],
            "digest_rule": digest_rule,
            "exact_true_fields": [
                "current_history_sets_disjoint",
                "fail_fast_checks_passed",
                "observed_after_index_before_next_mutation",
                "persona_root_identity_matches",
                "plan_identity_matches",
            ],
            "required_fields": list(PERSONA_CHECKPOINT_RECEIPT_FIELDS),
            "schema_identity": {
                "metric_id": "search-semantic-endpoint-v1/contract-contributor",
                "fixture_id": FIXTURE_ID,
                "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
                "receipt_schema": "kio.persona.pc-history-readiness-persona-checkpoint-receipt/v1",
                "receipt_schema_version": 1,
            },
        },
        "replay_terminal": {
            "additional_fields_allowed": False,
            "coordinate_binding": {
                "checkpoint_seal_count": len(CHECKPOINT_ROWS),
                "coordinate_fields": [
                    "replay_id",
                    "replay_container_receipt_id",
                    "terminal_id",
                ],
                "ordered_seals_are_checkpoint_order": True,
                "persona_checkpoint_receipt_count": (
                    len(PERSONA_IDS) * len(CHECKPOINT_ROWS)
                ),
                "w5_final_seal_is_terminal_predecessor": True,
            },
            "digest_fields": [
                "ordered_checkpoint_seal_bodies_sha256",
                "ordered_checkpoint_seal_ids_sha256",
                "ordered_persona_root_receipt_bodies_sha256",
                "ordered_persona_root_receipt_ids_sha256",
                "replay_container_receipt_body_sha256",
                "w5_final_seal_sha256",
            ],
            "digest_rule": digest_rule,
            "exact_false_or_zero_fields": {"failed_state_count": 0},
            "exact_true_fields": [
                "replay_terminal",
                "roots_never_copied_cloned_or_hardlinked",
            ],
            "required_fields": list(REPLAY_TERMINAL_FIELDS),
            "schema_identity": {
                "fixture_id": FIXTURE_ID,
                "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
                "terminal_schema": "kio.persona.pc-history-readiness-replay-terminal/v1",
                "terminal_schema_version": 1,
            },
        },
    }


def _cross_runtime_evidence_contract():
    return {
        "checkpoint_seal_body_hashes_may_differ_across_replays": True,
        "compiled_history_plan_sha256_identical_across_all_persona_receipts": True,
        "chunking_config_sha256_identical_across_all_persona_receipts": True,
        "persona_device_and_registry_root_id_sets_are_disjoint": True,
        "persona_device_and_registry_root_path_digest_sets_are_disjoint": True,
        "persona_device_root_path_sha256_pairwise_distinct_across_all_60_roots": True,
        "persona_registry_root_path_sha256_pairwise_distinct_across_all_60_roots": True,
        "persona_root_receipt_body_sha256_pairwise_distinct_across_all_60_coordinates": True,
        "no_persona_replay_or_checkpoint_receipt_pooling": True,
        "one_persona_root_receipt_per_persona_and_replay": True,
        "one_replay_container_receipt_per_replay": True,
        "one_terminal_per_replay": True,
        "replay_container_id_set_is_disjoint_from_both_persona_root_id_sets": True,
        "replay_container_is_strict_ancestor_of_each_persona_device_root": True,
        "replay_container_creation_nonce_sha256_pairwise_distinct_across_three_replays": True,
        "replay_container_path_digest_set_is_disjoint_from_persona_device_root_path_digest_set": True,
        "replay_container_path_digest_set_is_disjoint_from_persona_registry_root_path_digest_set": True,
        "replay_container_path_sha256_identical_within_replay": True,
        "replay_container_path_sha256_in_root_receipts_equals_bound_container_receipt_path_sha256": True,
        "replay_container_path_sha256_pairwise_distinct_across_three_replays": True,
        "replay_container_receipt_body_sha256_pairwise_distinct_across_three_coordinates": True,
        "replay_container_receipt_sha256_identical_across_persona_roots_within_replay": True,
        "root_creation_nonce_sha256_pairwise_distinct_across_all_60_coordinates": True,
        "scope_registry_sha256_identical_across_checkpoints_within_each_persona_root": True,
        "source_plan_sha256_identical_across_all_replays": True,
        "terminal_body_hashes_are_not_static_contract_golden_inputs": True,
        "writer_plan_sha256_identical_across_all_replays": True,
    }


def _state_machine():
    state_order = [
        "replay-container-attested",
        "twenty-persona-root-pairs-attested",
    ]
    for checkpoint, _current, _history in CHECKPOINT_ROWS:
        if checkpoint == "W0":
            execution_state = "W0:initial-write-and-index-complete"
        elif checkpoint == "W5-pre-purge":
            execution_state = "W5-pre-purge:pre-purge-mutation-and-index-complete"
        elif checkpoint == "W5-final":
            execution_state = "W5-final:purge-and-final-index-complete"
        else:
            execution_state = f"{checkpoint}:mutation-and-index-complete"
        state_order.extend(
            [
                execution_state,
                f"{checkpoint}:twenty-persona-receipts-valid",
                f"{checkpoint}:checkpoint-sealed",
            ]
        )
    state_order.append("replay-terminal-sealed")
    transitions = []
    for ordinal in range(len(state_order) - 1):
        current_state = state_order[ordinal]
        next_state = state_order[ordinal + 1]
        transitions.append(
            {
                "from_state": current_state,
                "guard_failure_target": "failed-terminal-absorbing",
                "guard_id": f"history-readiness-transition-guard-{ordinal:02d}",
                "guard_must_be_exact_true": True,
                "to_state": next_state,
                "transition_ordinal": ordinal,
            }
        )
    return {
        "all_persona_w0_index_receipts_complete_before_w1_mutation": True,
        "checkpoint_receipt_accumulation_order": "persona-id-ascii-in-seal-only",
        "failure_state": "failed-terminal-absorbing",
        "failure_state_is_absorbing": True,
        "failure_stops_all_later_replay_and_checkpoint_emission": True,
        "final_evaluation_before_all_three_replay_terminals_allowed": False,
        "next_checkpoint_mutation_before_current_seal_allowed": False,
        "next_replay_container_before_current_replay_terminal_allowed": False,
        "persona_root_creation_before_replay_container_receipt_allowed": False,
        "persona_w0_creation_order": list(PERSONA_IDS),
        "replay_container_receipt_is_first_runtime_artifact": True,
        "replay_execution_order": list(REPLAY_IDS),
        "state_order_per_replay": state_order,
        "success_transitions": transitions,
        "w5_purge_before_w5_pre_purge_seal_allowed": False,
        "w0_persona_roots_written_one_at_a_time": True,
    }


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _endpoint_counting_contract():
    return {
        "chunk_id_is_chunk_hash": True,
        "contract_participation_class": "contract_contributor",
        "current_and_history_only_sets_are_disjoint": True,
        "current_state_rule": "at-least-one-live-path-binding-in-the-same-scope",
        "history_only_state_rule": (
            "zero-live-path-bindings-in-the-same-scope-and-at-least-one-"
            "reachable-nonpurged-historical-or-deleted-path-binding"
        ),
        "identity_fields": ["scope_key", "chunk_id"],
        "metric_id": "search-semantic-endpoint-v1/contract-contributor",
        "path_alias_db_row_materialization_or_inode_is_not_an_endpoint": True,
        "persona_replay_or_checkpoint_pooling_allowed": False,
        "scope_is_not_dropped_for_persona_global_dedup": True,
        "uses_current_chunking_configuration_only": True,
    }


def _expected_value(snapshot):
    receipt_coordinates = _persona_receipt_coordinates()
    seal_coordinates = _checkpoint_seal_coordinates()
    terminal_coordinates = _terminal_coordinates()
    replay_container_coordinates = _replay_container_coordinates()
    replay_container_receipt_coordinates = _replay_container_receipt_coordinates()
    device_root_coordinates = _persona_device_root_coordinates()
    registry_root_coordinates = _persona_registry_root_coordinates()
    root_receipt_coordinates = _persona_root_receipt_coordinates()
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "candidate_status": "proposal-local-golden-frozen-not-issued",
        "canonical_limits": {
            "dynamic_runtime_bodies_embedded": False,
            "max_contract_bytes": MAX_CONTRACT_BYTES,
            "max_integer_magnitude": artifact_common.MAX_INTEGER_MAGNITUDE,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_preflight_container_items": MAX_PREFLIGHT_CONTAINER_ITEMS,
            "max_preflight_node_count": MAX_PREFLIGHT_NODE_COUNT,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_negative_integer_or_container_alias_allowed": False,
            "target_contract_bytes": TARGET_CONTRACT_BYTES,
            "unicode_normalization": "NFC",
        },
        "checkpoint_contract": _checkpoint_contract(),
        "completion_claims": {
            "all_420_runtime_receipts_observed": False,
            "all_21_checkpoint_seals_observed": False,
            "all_3_replay_container_receipts_observed": False,
            "all_3_replay_containers_observed": False,
            "all_3_replay_terminals_observed": False,
            "all_60_persona_device_roots_observed": False,
            "all_60_persona_registry_roots_observed": False,
            "all_60_persona_root_receipts_observed": False,
            "dependency_accepted": True,
            "dependency_frozen": True,
            "dependency_issued": False,
            "exact_runtime_coordinate_contract_defined": True,
            "full_dependency_body_replay_passed": True,
            "global_contract_golden_frozen": True,
            "history_runtime_ready_for_evaluation": False,
            "ordered_fail_fast_state_machine_defined": True,
            "replay_id_binding_accepted": True,
            "replay_id_binding_frozen": True,
            "replay_id_binding_issued": False,
            "runtime_field_allowlists_defined": True,
            "two_hash_seed_cold_replays_passed": True,
        },
        "cross_runtime_evidence_contract": _cross_runtime_evidence_contract(),
        "dependency_exclusion_contract": {
            "evaluation_result_body_count": 0,
            "evaluation_target_resolution_body_count": 0,
            "oracle_body_count": 0,
            "query_body_count": 0,
            "runtime_checkpoint_receipt_body_count": 0,
            "runtime_checkpoint_seal_body_count": 0,
            "runtime_persona_root_receipt_body_count": 0,
            "runtime_replay_container_receipt_body_count": 0,
            "runtime_replay_terminal_body_count": 0,
        },
        "dependency_pin": copy.deepcopy(snapshot["dependency_pin"]),
        "endpoint_counting_contract": _endpoint_counting_contract(),
        "field_contracts": _field_contracts(),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "global_golden_scope": {
            "covers_static_contract_body_only": True,
            "dynamic_receipt_bytes_are_global_golden_inputs": False,
            "dynamic_receipt_hashes_are_global_golden_inputs": False,
            "runtime_evidence_is_validated_against_coordinate_and_field_contracts": True,
            "runtime_receipts_seals_and_terminals_are_external": True,
        },
        "orders": {
            "checkpoints": [row[0] for row in CHECKPOINT_ROWS],
            "personas": list(PERSONA_IDS),
            "replays": list(REPLAY_IDS),
        },
        "persona_checkpoint_receipt_coordinates": receipt_coordinates,
        "persona_device_root_coordinates": device_root_coordinates,
        "persona_registry_root_coordinates": registry_root_coordinates,
        "persona_root_receipt_coordinates": root_receipt_coordinates,
        "proposal_only": True,
        "query_oracle_evaluation_independence": {
            "evaluation_results_can_authorize_history_readiness": False,
            "oracle_fields_allowed_in_runtime_evidence": False,
            "query_fields_allowed_in_runtime_evidence": False,
            "runtime_history_receipts_depend_on_evaluation_results": False,
            "static_contract_depends_on_query_or_oracle": False,
        },
        "replay_terminal_coordinates": terminal_coordinates,
        "replay_container_coordinates": replay_container_coordinates,
        "replay_container_receipt_coordinates": replay_container_receipt_coordinates,
        "replay_id_dependency_pin": copy.deepcopy(
            snapshot["replay_id_dependency_pin"]
        ),
        "state_machine": _state_machine(),
        "summary": {
            "checkpoint_count_per_replay": len(CHECKPOINT_ROWS),
            "checkpoint_seal_count": len(seal_coordinates),
            "direct_dependency_count": 2,
            "persona_checkpoint_receipt_count": len(receipt_coordinates),
            "persona_count": len(PERSONA_IDS),
            "persona_device_root_count": len(device_root_coordinates),
            "persona_registry_root_count": len(registry_root_coordinates),
            "persona_root_receipt_count": len(root_receipt_coordinates),
            "replay_count": len(REPLAY_IDS),
            "replay_container_count": len(replay_container_coordinates),
            "replay_container_receipt_count": len(
                replay_container_receipt_coordinates
            ),
            "replay_terminal_count": len(terminal_coordinates),
            "runtime_external_artifact_count": (
                len(replay_container_receipt_coordinates)
                + len(root_receipt_coordinates)
                + len(receipt_coordinates)
                + len(seal_coordinates)
                + len(terminal_coordinates)
            ),
        },
        "checkpoint_seal_coordinates": seal_coordinates,
    }


def _require_snapshot(snapshot):
    if not _strict_equal(snapshot, _candidate_dependency_snapshot()):
        _fail("history-readiness dependency snapshot differs from candidate pin")


def _build_from_snapshot(snapshot):
    _require_golden_parity()
    _require_dependency_constant_alignment()
    _require_snapshot(snapshot)
    value = _expected_value(snapshot)
    raw = _canonical(value, label="history-readiness static contract candidate")
    if len(raw) > TARGET_CONTRACT_BYTES:
        _fail("history-readiness candidate exceeds its target byte budget")
    _require_expected_raw(raw)
    return value


def build_history_readiness_contract():
    """Build the detached static contract without opening dependency bodies."""

    return copy.deepcopy(_build_from_snapshot(_candidate_dependency_snapshot()))


def canonical_json_bytes(value):
    _require_golden_parity()
    try:
        _detached, raw = independent._snapshot_candidate(value)
    except independent.PersonaV2HistoryReadinessContractValidationError as error:
        _fail(str(error))
    return _require_expected_raw(raw)


def validate_history_readiness_contract(value):
    _require_golden_parity()
    try:
        result = independent.validate_history_readiness_contract(value)
    except independent.PersonaV2HistoryReadinessContractValidationError as error:
        _fail(str(error))
    if result is not True:
        _fail("independent history-readiness validator was not exact true")
    return True


def history_readiness_contract_sha256(value=None):
    _require_golden_parity()
    if value is None:
        value = build_history_readiness_contract()
    try:
        _opening_value, opening = independent._snapshot_candidate(value)
    except independent.PersonaV2HistoryReadinessContractValidationError as error:
        _fail(str(error))
    validate_history_readiness_contract(value)
    try:
        _closing_value, closing = independent._snapshot_candidate(value)
    except independent.PersonaV2HistoryReadinessContractValidationError as error:
        _fail(str(error))
    if not hmac.compare_digest(opening, closing):
        _fail("history-readiness candidate changed during validation-to-hash")
    return _sha256(opening)


def require_full_history_readiness_contract():
    """Replay the live upstream body once through the independent validator."""

    producer_expected = _require_golden_parity()
    value = _build_from_snapshot(_candidate_dependency_snapshot())
    try:
        result = independent.validate_history_readiness_contract_full(
            value,
            producer_expected_golden=producer_expected,
        )
    except independent.PersonaV2HistoryReadinessContractValidationError as error:
        _fail(str(error))
    if result is not True:
        _fail("full independent history-readiness validation was not exact true")
    return copy.deepcopy(value)


def require_authoritative_history_readiness_contract():
    """Fail closed: the candidate contains no observed runtime evidence."""

    raise PersonaV2HistoryReadinessContractError(
        "the static candidate defines receipt coordinates and schemas only; "
        "it has no container, persona-root, checkpoint, seal, terminal, evaluation, "
        "or G0 authority"
    )


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "CHECKPOINT_ROWS",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_CONTRACT_BYTES",
    "PERSONA_IDS",
    "PersonaV2HistoryReadinessContractError",
    "REPLAY_IDS",
    "build_history_readiness_contract",
    "canonical_json_bytes",
    "history_readiness_contract_sha256",
    "require_authoritative_history_readiness_contract",
    "require_full_history_readiness_contract",
    "validate_history_readiness_contract",
]
