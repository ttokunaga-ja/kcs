"""Producer-independent validation for the history-readiness contract.

This module intentionally does not import the sibling producer.  It owns the
entire static contract, the accepted frozen history pre-solve and compositor
pins, and the all-false authority boundary as independent policy.  Neither
dependency is issued.  Fast validation is pin-only.  Opt-in full validation
replays the upstream history body and authenticates it before returning the
unchanged non-authorizing candidate.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_device_lane_compositor as device_compositor
    from . import persona_v2_device_lane_compositor_validator as compositor_validator
    from . import persona_v2_history_presolve_input_closure_slice as history_slice
    from . import persona_v2_history_presolve_input_closure_slice_validator as history_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_device_lane_compositor as device_compositor
    import persona_v2_device_lane_compositor_validator as compositor_validator
    import persona_v2_history_presolve_input_closure_slice as history_slice
    import persona_v2_history_presolve_input_closure_slice_validator as history_validator


ARTIFACT_SCHEMA = "kio.persona.pc-history-readiness-contract/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-static-non-authorizing-history-readiness-contract-candidate"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 512 * 2**10
TARGET_CONTRACT_BYTES = 256 * 2**10
MAX_PREFLIGHT_NODE_COUNT = 100_000
MAX_PREFLIGHT_CONTAINER_ITEMS = 1_024

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

TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "candidate_status",
        "canonical_limits",
        "checkpoint_contract",
        "checkpoint_seal_coordinates",
        "completion_claims",
        "cross_runtime_evidence_contract",
        "dependency_exclusion_contract",
        "dependency_pin",
        "endpoint_counting_contract",
        "field_contracts",
        "fixture_id",
        "fixture_schema_version",
        "global_golden_scope",
        "orders",
        "persona_checkpoint_receipt_coordinates",
        "persona_device_root_coordinates",
        "persona_registry_root_coordinates",
        "persona_root_receipt_coordinates",
        "proposal_only",
        "query_oracle_evaluation_independence",
        "replay_container_coordinates",
        "replay_container_receipt_coordinates",
        "replay_id_dependency_pin",
        "replay_terminal_coordinates",
        "state_machine",
        "summary",
    }
)


class PersonaV2HistoryReadinessContractValidationError(ValueError):
    """Raised when independent history-readiness validation fails closed."""


def _fail(message):
    raise PersonaV2HistoryReadinessContractValidationError(message)


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


_GOLDEN_NOT_PROVIDED = object()


def _require_producer_golden_parity(producer_expected):
    """Reject missing/drifted producer golden before any live dependency."""

    validator_expected = _expected_golden()
    if producer_expected is _GOLDEN_NOT_PROVIDED:
        _fail("producer history-readiness golden was not supplied")
    if producer_expected is not None and (
        type(producer_expected) is not tuple
        or len(producer_expected) != 2
        or type(producer_expected[0]) is not int
        or type(producer_expected[0]) is bool
        or not 1 <= producer_expected[0] <= TARGET_CONTRACT_BYTES
        or type(producer_expected[1]) is not str
        or len(producer_expected[1]) != 64
        or any(character not in "0123456789abcdef" for character in producer_expected[1])
    ):
        _fail("producer history-readiness golden is invalid")
    if not _strict_equal(producer_expected, validator_expected):
        _fail("producer and validator history-readiness goldens differ")
    return validator_expected


def _structural_preflight(value, *, label, maximum_bytes):
    """Bound structure before normalization, encoding, copying, or providers."""

    if type(label) is not str or not label:
        _fail("preflight label must be a non-empty exact string")
    if type(maximum_bytes) is not int or type(maximum_bytes) is bool or maximum_bytes <= 0:
        _fail("preflight byte bound must be a positive exact integer")
    stack = [(value, 0)]
    seen_containers = set()
    node_count = 0
    expanded_upper_bound = 0
    while stack:
        current, depth = stack.pop()
        node_count += 1
        if node_count > MAX_PREFLIGHT_NODE_COUNT:
            _fail(f"{label} exceeds structural node bound")
        if depth > artifact_common.MAX_CANONICAL_DEPTH:
            _fail(f"{label} exceeds structural depth bound")
        if type(current) is bool:
            expanded_upper_bound += 5
        elif type(current) is int:
            if current < 0 or current > artifact_common.MAX_INTEGER_MAGNITUDE:
                _fail(f"{label} integer exceeds checked range")
            expanded_upper_bound += 40
        elif type(current) is str:
            # Bound exact pre-normalization UTF-8 bytes without calling encode.
            # This keeps canonicalization and every provider unreachable for a
            # short-codepoint-count string whose UTF-8 representation is too
            # large (and rejects lone surrogates before the encoder sees them).
            if len(current) > artifact_common.MAX_CANONICAL_STRING_BYTES:
                _fail(f"{label} string exceeds codepoint bound")
            utf8_bytes = 0
            for character in current:
                codepoint = ord(character)
                if codepoint <= 0x7F:
                    utf8_bytes += 1
                elif codepoint <= 0x7FF:
                    utf8_bytes += 2
                elif 0xD800 <= codepoint <= 0xDFFF:
                    _fail(f"{label} string contains a lone surrogate")
                elif codepoint <= 0xFFFF:
                    utf8_bytes += 3
                else:
                    utf8_bytes += 4
                if utf8_bytes > artifact_common.MAX_CANONICAL_STRING_BYTES:
                    _fail(f"{label} string exceeds UTF-8 byte bound")
            expanded_upper_bound += 2 + 6 * len(current)
        elif type(current) is list:
            identity = id(current)
            if identity in seen_containers:
                _fail(f"{label} contains a repeated-container alias or cycle")
            seen_containers.add(identity)
            if len(current) > MAX_PREFLIGHT_CONTAINER_ITEMS:
                _fail(f"{label} list exceeds item bound")
            expanded_upper_bound += 2 + len(current)
            stack.extend((item, depth + 1) for item in reversed(current))
        elif type(current) is dict:
            identity = id(current)
            if identity in seen_containers:
                _fail(f"{label} contains a repeated-container alias or cycle")
            seen_containers.add(identity)
            if len(current) > MAX_PREFLIGHT_CONTAINER_ITEMS:
                _fail(f"{label} object exceeds item bound")
            expanded_upper_bound += 2 + len(current)
            for key, item in current.items():
                if type(key) is not str:
                    _fail(f"{label} object keys must be exact strings")
                stack.append((item, depth + 1))
                stack.append((key, depth + 1))
        else:
            _fail(f"unsupported {label} value type: {type(current).__name__}")
        if expanded_upper_bound > 8 * maximum_bytes:
            _fail(f"{label} exceeds conservative expanded byte bound")
    return True


def _canonical(value, *, label, maximum=MAX_CONTRACT_BYTES):
    _structural_preflight(value, label=label, maximum_bytes=maximum)
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=maximum,
        )
    except (RecursionError, artifact_common.PersonaV2ArtifactError) as error:
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
        "artifact_kind": "persona-pc-v2-non-authorizing-history-presolve-input-closure-slice",
        "artifact_schema": "kio.persona.pc-history-presolve-input-closure-slice/v1",
        "artifact_schema_version": 1,
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
        "artifact_kind": "persona-pc-v2-non-authorizing-device-lane-compositor-candidate",
        "artifact_schema": "kio.persona.pc-device-lane-compositor/v1",
        "artifact_schema_version": 1,
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
        or history_validator.ARTIFACT_SCHEMA
        != "kio.persona.pc-history-presolve-input-closure-slice/v1"
        or history_validator.ARTIFACT_SCHEMA_VERSION != 1
        or history_validator.ARTIFACT_KIND
        != "persona-pc-v2-non-authorizing-history-presolve-input-closure-slice"
        or history_slice.EXPECTED_CANONICAL_BYTES
        != HISTORY_SLICE_CANONICAL_BYTES
        or history_slice.EXPECTED_SHA256 != HISTORY_SLICE_SHA256
        or history_validator.EXPECTED_CANONICAL_BYTES
        != HISTORY_SLICE_CANONICAL_BYTES
        or history_validator.EXPECTED_SHA256 != HISTORY_SLICE_SHA256
        or device_compositor.ARTIFACT_SCHEMA
        != "kio.persona.pc-device-lane-compositor/v1"
        or device_compositor.ARTIFACT_SCHEMA_VERSION != 1
        or device_compositor.ARTIFACT_KIND
        != "persona-pc-v2-non-authorizing-device-lane-compositor-candidate"
        or device_compositor.EXPECTED_CANONICAL_BYTES
        != DEVICE_COMPOSITOR_CANONICAL_BYTES
        or device_compositor.EXPECTED_SHA256 != DEVICE_COMPOSITOR_SHA256
        or not _strict_equal(device_compositor.REPLAY_IDS, REPLAY_IDS)
        or compositor_validator.ARTIFACT_SCHEMA
        != "kio.persona.pc-device-lane-compositor/v1"
        or compositor_validator.ARTIFACT_SCHEMA_VERSION != 1
        or compositor_validator.ARTIFACT_KIND
        != "persona-pc-v2-non-authorizing-device-lane-compositor-candidate"
        or compositor_validator.EXPECTED_CANONICAL_BYTES
        != DEVICE_COMPOSITOR_CANONICAL_BYTES
        or compositor_validator.EXPECTED_SHA256 != DEVICE_COMPOSITOR_SHA256
        or not _strict_equal(compositor_validator.REPLAY_IDS, REPLAY_IDS)
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
            "total_current_contract_semantic_endpoints_per_replay": current_count * len(PERSONA_IDS),
            "total_history_only_contract_semantic_endpoints_per_replay": history_count * len(PERSONA_IDS),
        }
        for ordinal, (checkpoint, current_count, history_count) in enumerate(CHECKPOINT_ROWS)
    ]


def _replay_container_coordinates():
    return [
        {
            "replay_container_id": f"formal-replay-container/{replay_id}",
            "replay_id": replay_id,
            "replay_ordinal": replay_ordinal,
            "required_receipt_id": f"history-readiness-container-receipt/{replay_id}",
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
            "required_replay_container_receipt_id": f"history-readiness-container-receipt/{replay_id}",
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
            "required_replay_container_receipt_id": f"history-readiness-container-receipt/{replay_id}",
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
            "replay_container_receipt_id": f"history-readiness-container-receipt/{replay_id}",
            "replay_id": replay_id,
            "replay_ordinal": replay_ordinal,
        }
        for replay_ordinal, replay_id in enumerate(REPLAY_IDS)
        for persona_ordinal, persona_id in enumerate(PERSONA_IDS, start=1)
    ]


def _persona_receipt_coordinates():
    rows = []
    for replay_ordinal, replay_id in enumerate(REPLAY_IDS):
        for checkpoint_ordinal, (checkpoint, current_count, history_count) in enumerate(CHECKPOINT_ROWS):
            for persona_ordinal, persona_id in enumerate(PERSONA_IDS, start=1):
                rows.append(
                    {
                        "checkpoint": checkpoint,
                        "checkpoint_ordinal": checkpoint_ordinal,
                        "expected_contract_current_endpoint_count": current_count,
                        "expected_contract_history_only_endpoint_count": history_count,
                        "persona_id": persona_id,
                        "persona_ordinal": persona_ordinal,
                        "receipt_id": f"history-readiness-persona-receipt/{replay_id}/{checkpoint}/{persona_id}",
                        "replay_id": replay_id,
                        "replay_ordinal": replay_ordinal,
                    }
                )
    return rows


def _checkpoint_seal_coordinates():
    rows = []
    for replay_ordinal, replay_id in enumerate(REPLAY_IDS):
        for checkpoint_ordinal, (checkpoint, current_count, history_count) in enumerate(CHECKPOINT_ROWS):
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
            "expected_persona_checkpoint_receipt_count": len(PERSONA_IDS) * len(CHECKPOINT_ROWS),
            "replay_container_receipt_id": f"history-readiness-container-receipt/{replay_id}",
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
            "exact_true_fields": ["all_receipts_validated", "sealed_before_next_mutation"],
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
                "persona_checkpoint_receipt_count": len(PERSONA_IDS) * len(CHECKPOINT_ROWS),
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
            "exact_true_fields": ["replay_terminal", "roots_never_copied_cloned_or_hardlinked"],
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
    transitions = [
        {
            "from_state": state_order[ordinal],
            "guard_failure_target": "failed-terminal-absorbing",
            "guard_id": f"history-readiness-transition-guard-{ordinal:02d}",
            "guard_must_be_exact_true": True,
            "to_state": state_order[ordinal + 1],
            "transition_ordinal": ordinal,
        }
        for ordinal in range(len(state_order) - 1)
    ]
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


def _require_static_candidate(snapshot):
    if (
        type(snapshot) is not dict
        or snapshot.get("artifact_kind") != ARTIFACT_KIND
        or snapshot.get("artifact_schema") != ARTIFACT_SCHEMA
        or snapshot.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or snapshot.get("fixture_id") != FIXTURE_ID
        or snapshot.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
        or snapshot.get("candidate_status")
        != "proposal-local-golden-frozen-not-issued"
        or snapshot.get("proposal_only") is not True
    ):
        _fail("history-readiness static identity drifted")
    authority = snapshot.get("authority")
    if authority != _negative_authority() or any(
        type(flag) is not bool or flag is not False for flag in (authority or {}).values()
    ):
        _fail("history-readiness authority must be exact all-false")
    dependency = snapshot.get("dependency_pin")
    if (
        type(dependency) is not dict
        or dependency.get("dependency_accepted") is not True
        or dependency.get("dependency_frozen") is not True
        or dependency.get("dependency_issued") is not False
    ):
        _fail("history pre-solve frozen dependency state drifted")
    replay_binding = snapshot.get("replay_id_dependency_pin")
    if (
        type(replay_binding) is not dict
        or replay_binding.get("expected_replay_ids") != list(REPLAY_IDS)
        or replay_binding.get("dependency_accepted") is not True
        or replay_binding.get("dependency_frozen") is not True
        or replay_binding.get("dependency_issued") is not False
    ):
        _fail("formal replay compositor frozen binding drifted")
    claims = snapshot.get("completion_claims")
    if type(claims) is not dict:
        _fail("history-readiness completion claims are malformed")
    for field in (
        "all_420_runtime_receipts_observed",
        "all_21_checkpoint_seals_observed",
        "all_3_replay_container_receipts_observed",
        "all_3_replay_containers_observed",
        "all_3_replay_terminals_observed",
        "all_60_persona_device_roots_observed",
        "all_60_persona_registry_roots_observed",
        "all_60_persona_root_receipts_observed",
        "dependency_issued",
        "history_runtime_ready_for_evaluation",
        "replay_id_binding_issued",
    ):
        if claims.get(field) is not False:
            _fail("history-readiness runtime or issuance completion was overstated")
    for field in (
        "dependency_accepted",
        "dependency_frozen",
        "exact_runtime_coordinate_contract_defined",
        "full_dependency_body_replay_passed",
        "global_contract_golden_frozen",
        "ordered_fail_fast_state_machine_defined",
        "replay_id_binding_accepted",
        "replay_id_binding_frozen",
        "runtime_field_allowlists_defined",
        "two_hash_seed_cold_replays_passed",
    ):
        if claims.get(field) is not True:
            _fail("history-readiness frozen local completion state drifted")
    exclusions = snapshot.get("dependency_exclusion_contract")
    if type(exclusions) is not dict or not exclusions or any(
        type(count) is not int or type(count) is bool or count != 0
        for count in exclusions.values()
    ):
        _fail("history-readiness dynamic/query/evaluation exclusion boundary drifted")
    golden_scope = snapshot.get("global_golden_scope")
    if golden_scope != {
        "covers_static_contract_body_only": True,
        "dynamic_receipt_bytes_are_global_golden_inputs": False,
        "dynamic_receipt_hashes_are_global_golden_inputs": False,
        "runtime_evidence_is_validated_against_coordinate_and_field_contracts": True,
        "runtime_receipts_seals_and_terminals_are_external": True,
    }:
        _fail("history-readiness global golden scope drifted")


def _snapshot_candidate(value):
    """Authenticate and detach caller state before dependency access."""

    _expected_golden()
    if type(value) is not dict or len(value) != len(TOP_LEVEL_FIELDS):
        _fail("history-readiness candidate has an inexact top-level shape")
    # Reject non-exact keys, cycles, aliases, and expansion bombs before any
    # attacker-controlled key can participate in fixed-field membership.
    _structural_preflight(
        value,
        label="history-readiness candidate top-level preflight",
        maximum_bytes=MAX_CONTRACT_BYTES,
    )
    if any(field not in value for field in TOP_LEVEL_FIELDS):
        _fail("history-readiness candidate has an inexact top-level shape")
    raw = _canonical(value, label="history-readiness candidate opening body")
    _require_expected_raw(raw)
    live_reauthentication = _canonical(
        value, label="history-readiness candidate opening reauthentication"
    )
    if not hmac.compare_digest(raw, live_reauthentication):
        _fail("history-readiness candidate changed while snapshotted")
    try:
        detached = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("history-readiness candidate snapshot failed closed")
    _require_static_candidate(detached)
    expected = _expected_value(_candidate_dependency_snapshot())
    expected_raw = _canonical(expected, label="independent expected history-readiness contract")
    if len(expected_raw) > TARGET_CONTRACT_BYTES:
        _fail("independent expected history-readiness contract exceeds target budget")
    _require_expected_raw(expected_raw)
    if not hmac.compare_digest(raw, expected_raw):
        _fail("history-readiness candidate differs from independent regeneration")
    return detached, raw


def _strict_parse_integer(token):
    if not token or token[0] == "-" or (len(token) > 1 and token[0] == "0"):
        _fail("history-readiness JSON integer is not canonical")
    try:
        value = int(token)
    except ValueError:
        _fail("history-readiness JSON integer is invalid")
    if value > artifact_common.MAX_INTEGER_MAGNITUDE:
        _fail("history-readiness JSON integer exceeds checked range")
    return value


def _reject_constant(token):
    _fail(f"history-readiness JSON constant is forbidden: {token}")


def _pairs_to_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("history-readiness JSON contains a duplicate object key")
        result[key] = value
    return result


def strict_load_canonical_json_bytes(raw):
    """Parse only exact bounded canonical bytes before any live dependency."""

    _expected_golden()
    if type(raw) is not bytes:
        _fail("history-readiness serialized candidate must be exact bytes")
    if len(raw) > MAX_CONTRACT_BYTES:
        _fail("history-readiness serialized candidate exceeds byte cap")
    _require_expected_raw(raw)
    try:
        text = raw.decode("utf-8", "strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_to_object,
            parse_int=_strict_parse_integer,
            parse_float=lambda _token: _fail("history-readiness JSON floats are forbidden"),
            parse_constant=_reject_constant,
        )
    except PersonaV2HistoryReadinessContractValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
        _fail("history-readiness serialized candidate is not strict JSON")
    canonical = _canonical(value, label="strictly loaded history-readiness candidate")
    if not hmac.compare_digest(raw, canonical):
        _fail("history-readiness serialized candidate is not canonical JSON")
    _detached, verified_raw = _snapshot_candidate(value)
    if not hmac.compare_digest(raw, verified_raw):
        _fail("history-readiness serialized candidate changed during validation")
    return value


def _pin_from_body(value, raw):
    if type(value) is not dict or type(raw) is not bytes:
        _fail("live history pre-solve dependency body is malformed")
    actual = {
        "artifact_kind": value.get("artifact_kind"),
        "artifact_schema": value.get("artifact_schema"),
        "artifact_schema_version": value.get("artifact_schema_version"),
        "body_opened_in_fast_candidate_build": False,
        "body_required_for_full_acceptance": True,
        "canonical_bytes": len(raw),
        "dependency_accepted": True,
        "dependency_frozen": True,
        "dependency_id": "history-presolve-input-closure-slice-v1",
        "dependency_issued": False,
        "dependency_role": (
            "query-independent-structural-history-demand-accepted-frozen-pin"
        ),
        "fixture_id": value.get("fixture_id"),
        "fixture_schema_version": value.get("fixture_schema_version"),
        "pin_status": "accepted-frozen-history-slice-body-pin-not-issued",
        "sha256": _sha256(raw),
    }
    if not _strict_equal(actual, _history_slice_binding()):
        _fail("live history pre-solve dependency differs from candidate pin")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        _fail("live history pre-solve dependency escalated authority")
    claims = value.get("completion_claims")
    if type(claims) is not dict or any(
        claims.get(field) is not False
        for field in (
            "authoritative_history_input_closure_ready",
            "history_runtime_receipts_bound",
            "physical_files_written",
            "production_history_input_closure_complete",
        )
    ):
        _fail("live history pre-solve dependency overstated runtime completion")
    return actual


def _live_dependency_snapshot(*, full=False):
    """Return the pin-only snapshot, or replay one live upstream body."""

    _expected_golden()
    _require_dependency_constant_alignment()
    if not full:
        return _candidate_dependency_snapshot()
    try:
        value = history_slice.require_full_history_presolve_input_closure_slice()
        opening_raw = history_slice.canonical_json_bytes(value)
        pin = _pin_from_body(value, opening_raw)
        if history_validator.validate_history_presolve_input_closure_slice(value) is not True:
            _fail("live history pre-solve independent validation was not exact true")
        closing_raw = history_slice.canonical_json_bytes(value)
    except PersonaV2HistoryReadinessContractValidationError:
        raise
    except Exception:
        _fail("live history pre-solve dependency replay failed closed")
    if not hmac.compare_digest(opening_raw, closing_raw):
        _fail("live history pre-solve dependency changed during replay")
    snapshot = {
        "dependency_pin": pin,
        "replay_id_dependency_pin": copy.deepcopy(
            _device_compositor_replay_binding()
        ),
    }
    if not _strict_equal(snapshot, _candidate_dependency_snapshot()):
        _fail("live history pre-solve snapshot differs from candidate metadata")
    return snapshot


def _snapshot_dependencies(provider, dependency_observer=None):
    if not callable(provider):
        _fail("history-readiness dependency provider must be callable")
    try:
        opening_value = provider()
        opening_raw = _canonical(
            opening_value,
            label="history-readiness dependency opening snapshot",
            maximum=64 * 2**10,
        )
        if not _strict_equal(opening_value, _candidate_dependency_snapshot()):
            _fail("history-readiness dependency opening snapshot drifted")
        detached = json.loads(opening_raw.decode("utf-8", "strict"))
        live_reauthentication = _canonical(
            opening_value,
            label="history-readiness dependency opening reauthentication",
            maximum=64 * 2**10,
        )
        if not hmac.compare_digest(opening_raw, live_reauthentication):
            _fail("history-readiness dependency changed while snapshotted")
        if dependency_observer is not None:
            if not callable(dependency_observer):
                _fail("history-readiness dependency observer must be callable")
            dependency_observer(opening_value)
            observed_raw = _canonical(
                opening_value,
                label="history-readiness dependency observed snapshot",
                maximum=64 * 2**10,
            )
            if not hmac.compare_digest(opening_raw, observed_raw):
                _fail("history-readiness dependency changed during validation")
        closing_value = provider()
        closing_raw = _canonical(
            closing_value,
            label="history-readiness dependency closing snapshot",
            maximum=64 * 2**10,
        )
        if not _strict_equal(closing_value, _candidate_dependency_snapshot()):
            _fail("history-readiness dependency closing snapshot drifted")
    except PersonaV2HistoryReadinessContractValidationError:
        raise
    except (MemoryError, RecursionError, RuntimeError, TypeError, ValueError):
        _fail("history-readiness dependency provider failed closed")
    if not hmac.compare_digest(opening_raw, closing_raw):
        _fail("history-readiness dependency changed between validation reads")
    return detached


def _validate(value, *, dependency_snapshot_provider=None, dependency_observer=None):
    _expected_golden()
    _require_dependency_constant_alignment()
    _detached, opening_raw = _snapshot_candidate(value)
    if dependency_snapshot_provider is None:
        snapshot = _live_dependency_snapshot(full=False)

        def provider():
            return copy.deepcopy(snapshot)

    else:
        provider = dependency_snapshot_provider
    dependency_snapshot = _snapshot_dependencies(provider, dependency_observer)
    expected = _expected_value(dependency_snapshot)
    expected_raw = _canonical(expected, label="history-readiness post-provider regeneration")
    _require_expected_raw(expected_raw)
    if not hmac.compare_digest(opening_raw, expected_raw):
        _fail("history-readiness candidate differs after dependency authentication")
    _closing_value, closing_raw = _snapshot_candidate(value)
    if not hmac.compare_digest(opening_raw, closing_raw):
        _fail("history-readiness candidate changed during dependency validation")
    return True


def validate_history_readiness_contract(value):
    _expected_golden()
    return _validate(value)


def validate_history_readiness_contract_full(
    value,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
):
    _require_producer_golden_parity(producer_expected_golden)
    _require_dependency_constant_alignment()
    _snapshot_candidate(value)
    snapshot = _live_dependency_snapshot(full=True)
    return _validate(
        value,
        dependency_snapshot_provider=lambda: copy.deepcopy(snapshot),
    )


def validate_history_readiness_contract_bytes(raw):
    _expected_golden()
    value = strict_load_canonical_json_bytes(raw)
    return validate_history_readiness_contract(value)


__all__ = [
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_CONTRACT_BYTES",
    "PersonaV2HistoryReadinessContractValidationError",
    "strict_load_canonical_json_bytes",
    "validate_history_readiness_contract",
    "validate_history_readiness_contract_bytes",
    "validate_history_readiness_contract_full",
]
