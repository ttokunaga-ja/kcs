"""Independent validation for aggregate persona-PC byte distributions.

This module deliberately imports neither the aggregate catalog producer nor
any renderer.  It authenticates the frozen upstream artifacts, asks the
already-independent format/recipe validators to rerun their runtime gates,
and then validates the aggregate histogram using integer arithmetic only.

The two selected-probe callbacks are untrusted.  A rendered probe is checked
against the selected parameter bin and then passed both to the supplied
validator callback and to the registry validator's directly bound validator
path.  Their receipts must be byte-identical.  All caller-owned inputs are
snapshotted before any callback and re-authenticated after every callback has
completed, closing persistent alias-mutation races.
"""

from __future__ import annotations

import copy
import hashlib
from fractions import Fraction

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_formal_source_recipe_catalog_validator as formal_validator
    from . import persona_v2_format_implementation_registry_validator as registry_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_formal_source_recipe_catalog_validator as formal_validator
    import persona_v2_format_implementation_registry_validator as registry_validator


ARTIFACT_SCHEMA = "kcs.persona.pc-aggregate-byte-distribution-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-aggregate-byte-distribution-catalog"
MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_DEPENDENCY_BYTES = 2 * 1024 * 1024
MAX_FRAGMENT_BYTES = 256 * 1024

# Installed together with the producer's final deterministic body.  These are
# body pins, never an embedded self hash.
EXPECTED_CATALOG_CANONICAL_BYTES = 1_576_125
EXPECTED_CATALOG_SHA256 = (
    "7f2fdcc823885401cb7ed1b8fc42c9010b38af63d2c58879babb28aadeb6b343"
)

EXPECTED_PERSONA_IDS = tuple(f"p{index:02d}" for index in range(1, 21))
EXPECTED_FAMILIES = (
    "md",
    "txt_log",
    "code",
    "structured_text",
    "csv_tsv",
    "html_eml",
    "ipynb",
    "pdf_text",
    "pdf_scan",
    "docx",
    "xlsx",
    "pptx",
    "image",
    "media",
    "domain_binary",
)
EXPECTED_ORIGINS = ("pilot", "full-residual", "full")
EXPECTED_PERSONA_VARIANT_ROWS = 566
EXPECTED_PERSONA_FAMILY_ROWS = 300
EXPECTED_PARAMETER_BIN_PROBES = 362
BLOCK_ROUNDING_QUANTUM_BYTES = 4096
FORMAL_ORDINARY_MAX_BYTES = 512 * 1024
FORMAL_IMAGE_MEDIA_DOMAIN_MIN_BYTES = 4 * 1024
FORMAL_TAIL_MIN_BYTES = 1024 * 1024
FORMAL_TAIL_MAX_BYTES = 4 * 1024 * 1024
FORMAL_TAIL_TARGET_CAP_BYTES = 5 * 2**19
MAX_FORMAL_TAIL_FILES_PER_PERSONA = 16
PLANNED_FORMAL_TAIL_FILES_PER_PERSONA = 8
PLANNED_PILOT_TAIL_FILES_PER_PERSONA = 1
PLANNED_RESIDUAL_TAIL_FILES_PER_PERSONA = 7
SUITE_BLOCK_ROUNDED_CAP_BYTES = 10 * 1024 * 1024 * 1024
PERSONA_CANDIDATE_CAP_BYTES = 512 * 1024 * 1024
PERSONA_REQUIRED_MARGIN_BYTES = 32 * 1024 * 1024
PERSONA_BLOCK_ROUNDED_CAP_BYTES = (
    PERSONA_CANDIDATE_CAP_BYTES - PERSONA_REQUIRED_MARGIN_BYTES
)

TAIL_VARIANTS = frozenset({"bmp", "png", "tif", "aiff", "wav", "mid", "npz"})
SIZE_SHAPE_PROFILE_IDS = frozenset(
    {
        "persona-v2-compact-byte-shape-v2",
        "persona-v2-standard-byte-shape-v2",
        "persona-v2-heavy-byte-shape-v2",
    }
)

DEPENDENCY_PINS = {
    "persona-v2-variant-catalog": (
        "persona-pc-v2-variant-catalog",
        "kcs.persona.pc-variant-catalog/v2",
        2,
        211_733,
        "abbe522ff37a9a091f28b7a230928fd598054498eb80cab99f08d21889f26cec",
        "persona-variant-source-count-and-formal-lane-owner",
    ),
    "persona-v2-format-implementation-registry": (
        "persona-pc-v2-format-implementation-registry",
        "kcs.persona.pc-format-implementation-registry/v2",
        2,
        333_881,
        "f585ae477daa01db4dc11bbc1edd9824696bd91eddce5870d618caaffd90c683",
        "all-71-renderer-formula-and-runtime-contract-owner",
    ),
    "persona-v2-formal-source-recipe-profile-catalog": (
        "persona-pc-v2-formal-source-recipe-profile-catalog",
        "kcs.persona.pc-formal-source-recipe-profile-catalog/v2",
        2,
        386_152,
        "973a31336b90abc6271165ce4a3130679f36d5a9d65b06fece6827123e5c6cc8",
        "formal-recipe-profile-and-lane-policy-owner",
    ),
    "persona-v2-realism-profile": (
        "persona-pc-v2-realism-profile",
        "kcs.persona.pc-realism-profile/v2",
        2,
        36_811,
        "a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05",
        "persona-role-and-full-denominator-owner",
    ),
}

TOP_LEVEL_KEYS = frozenset(
    {
        "allocation_model",
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "distribution_policy",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "input_binding_order",
        "input_bindings",
        "orders",
        "persona_family_projection_rows",
        "persona_summaries",
        "persona_variant_rows",
        "remaining_blockers",
        "parameter_bin_probe_receipts",
        "suite_summary",
    }
)

AUTHORITY_FIELDS = frozenset(
    {
        "actual_allocated_bytes_attested",
        "actual_chunks_attested",
        "actual_payload_bytes_attested",
        "authorizes_final_source_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kcs_execution",
        "authorizes_physical_write",
        "authorizes_query_plan",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_instances",
        "authorizes_source_plan",
        "authorizes_source_recipe_instances",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kcs_execution_available",
        "renderer_execution_environment_available",
    }
)

BIN_ORDER = ("floor", "small", "medium", "large", "ordinary-max")
ORDINARY_TARGET_CAPS = {
    "floor": 0,
    "small": 8 * 1024,
    "medium": 32 * 1024,
    "large": 128 * 1024,
    "ordinary-max": FORMAL_ORDINARY_MAX_BYTES,
}
SIZE_SHAPE_WEIGHTS_BP = {
    "compact": (4000, 4200, 1500, 250, 50),
    "standard": (3000, 4300, 2200, 400, 100),
    "heavy": (2000, 4000, 3000, 800, 200),
}
RASTER_DIMENSION_LATTICE = (
    64,
    96,
    128,
    192,
    256,
    384,
    512,
    768,
    1024,
    1536,
    2048,
    3072,
    4096,
)
MAX_RASTER_ASPECT_RATIO = 4
MIN_RASTER_PIXELS = 4_096
MAX_RASTER_PIXELS = 16_777_216
MIN_MEDIA_UNITS = 1
MAX_MEDIA_UNITS = 4_800_000

EXPECTED_ALLOCATION_MODEL = {
    "actual_filesystem_allocation_attested": False,
    "block_rounded_formula": "sum(count*ceil(raw-bytes/4096)*4096)",
    "candidate_persona_cap_bytes": PERSONA_CANDIDATE_CAP_BYTES,
    "filesystem_metadata_bytes_included": False,
    "hard_persona_block_rounded_cap_bytes": PERSONA_BLOCK_ROUNDED_CAP_BYTES,
    "hard_suite_block_rounded_cap_bytes": SUITE_BLOCK_ROUNDED_CAP_BYTES,
    "model_id": "persona-v2-4096-byte-regular-file-roundup-v2",
    "planning_allocation_quantum_bytes": BLOCK_ROUNDING_QUANTUM_BYTES,
    "required_persona_margin_bytes": PERSONA_REQUIRED_MARGIN_BYTES,
    "root_bound_capacity_projection": False,
}

EXPECTED_DISTRIBUTION_POLICY = {
    "anchor_selection_rules": {
        "affine": (
            "floor-is-least-complexity-reaching-formal-floor-then-each-"
            "capped-bin-is-greatest-complexity-not-exceeding-target-with-"
            "renderer-floor-fallback"
        ),
        "media": (
            "floor-is-least-frame-or-event-count-reaching-4096-bytes-then-"
            "each-capped-bin-is-greatest-count-not-exceeding-target-with-"
            "floor-fallback-tail-is-greatest-count-not-exceeding-tail-cap"
        ),
        "raster_capped_and_tail_tie_break": (
            "maximum-raw-bytes-then-maximum-pixels-then-minimum-width-then-"
            "minimum-height"
        ),
        "raster_floor_tie_break": (
            "minimum-raw-bytes-then-minimum-pixels-then-minimum-width-then-"
            "minimum-height"
        ),
    },
    "bin_order": list(BIN_ORDER),
    "full_order_statistics_recomputed_from_merged_histogram": True,
    "hamilton_tie_breaks": {
        "ordinary_bins": "canonical-bin-order",
        "tail_variants": "variant-id-ascii-byte-order",
    },
    "ordinary_target_caps_bytes": [
        {
            "bin_id": bin_id,
            "target_cap_bytes_with_renderer_floor_fallback": (
                ORDINARY_TARGET_CAPS[bin_id]
            ),
        }
        for bin_id in BIN_ORDER
    ],
    "persona_family_shape_assignment": (
        "per-family-exact-full-share-rank-bottom-five-compact-middle-"
        "ten-standard-top-five-heavy-persona-id-tie-break"
    ),
    "raster_dimension_lattice": list(RASTER_DIMENSION_LATTICE),
    "raster_max_aspect_ratio": MAX_RASTER_ASPECT_RATIO,
    "raster_max_pixels": MAX_RASTER_PIXELS,
    "raster_min_pixels": MIN_RASTER_PIXELS,
    "renderer_floor_fallback_when_target_below_minimum": True,
    "shape_profile_weights_bp": [
        {
            "profile_id": f"persona-v2-{tier}-byte-shape-v2",
            "weights_bp": [
                {"bin_id": bin_id, "weight_bp": weights[index]}
                for index, bin_id in enumerate(BIN_ORDER)
            ],
        }
        for tier, weights in SIZE_SHAPE_WEIGHTS_BP.items()
    ],
    "tail_capable_variants": sorted(TAIL_VARIANTS),
    "tail_full_per_persona": PLANNED_FORMAL_TAIL_FILES_PER_PERSONA,
    "tail_max_per_persona": MAX_FORMAL_TAIL_FILES_PER_PERSONA,
    "tail_pilot_per_persona": PLANNED_PILOT_TAIL_FILES_PER_PERSONA,
    "tail_residual_per_persona": PLANNED_RESIDUAL_TAIL_FILES_PER_PERSONA,
    "tail_target_cap_bytes": FORMAL_TAIL_TARGET_CAP_BYTES,
}

EXPECTED_COMPLETION_CLAIMS = {
    "aggregate_full_equals_pilot_plus_residual": True,
    "all_566_persona_variant_histograms_complete": True,
    "all_parameter_bin_runtime_probes_complete": True,
    "all_parameter_bins_runtime_validated": True,
    "all_source_instance_parameters_bound": False,
    "exact_300_persona_family_projections_complete": True,
    "exact_20_persona_and_suite_summaries_complete": True,
    "filesystem_allocation_attested": False,
    "source_instances_bound": False,
}

EXPECTED_ORDERS = {
    "parameter_bins": "five-ordinary-bin-order-then-optional-formal-tail",
    "persona_family_projection_rows": "persona-id-then-family-ascii",
    "persona_summaries": "persona-id",
    "persona_variant_rows": "exact-upstream-marginal-order",
    "parameter_bin_probe_receipts": (
        "variant-id-then-five-ordinary-bin-order-then-tail"
    ),
}
PERSONA_VARIANT_ROW_KEYS = frozenset(
    {
        "family",
        "gate_role",
        "implementation_profile_id",
        "parameter_bins",
        "persona_id",
        "recipe_profile_id",
        "size_shape_profile_id",
        "source_counts",
        "summaries",
        "variant_id",
    }
)
PARAMETER_BIN_KEYS = frozenset(
    {
        "bin_id",
        "counts",
        "exact_raw_bytes",
        "renderer_parameters",
        "size_lane",
        "target_complexity",
    }
)
SOURCE_COUNT_KEYS = frozenset(EXPECTED_ORIGINS)
SUMMARY_KEYS = frozenset(
    {
        "block_rounded_payload_bytes",
        "formal_tail_count",
        "maximum_bytes",
        "nearest_rank_p50_bytes",
        "nearest_rank_p95_bytes",
        "raw_byte_sum",
        "source_count",
        "statistics_defined",
    }
)
FORBIDDEN_INSTANCE_KEYS = frozenset(
    {
        "basename",
        "final_source_id",
        "intent_key",
        "materialization_id",
        "path",
        "payload_seed",
        "scope_key",
        "selected_basename",
        "source_id",
        "source_instance_id",
        "source_instances",
        "source_rows",
    }
)


class PersonaV2AggregateByteDistributionCatalogValidationError(ValueError):
    """Raised when independent aggregate-byte validation fails."""


def _fail(message):
    raise PersonaV2AggregateByteDistributionCatalogValidationError(message)


def _canonical(value, *, label, max_bytes=MAX_FRAGMENT_BYTES):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=max_bytes,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _exact_keys(value, expected, *, label):
    if type(value) is not dict or set(value) != set(expected):
        _fail(f"{label} schema drifted")


def _require_nonempty_string(value, *, label):
    if type(value) is not str or not value:
        _fail(f"{label} must be a non-empty string")


def _require_nonnegative_integer(value, *, label):
    if type(value) is not int or value < 0:
        _fail(f"{label} must be a non-negative exact integer")


def _require_negative_authority(value, *, label, exact_fields=None):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority:
        _fail(f"{label} authority must be a non-empty object")
    if exact_fields is not None and set(authority) != set(exact_fields):
        _fail(f"{label} authority schema drifted")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail(f"{label} authority must be all false")


def _walk_forbidden_instances(value):
    if type(value) is dict:
        for key, item in value.items():
            if key in FORBIDDEN_INSTANCE_KEYS:
                _fail(f"aggregate byte catalog embeds source-instance field: {key}")
            _walk_forbidden_instances(item)
    elif type(value) is list:
        for item in value:
            _walk_forbidden_instances(item)


def _authenticate_dependency(name, value):
    if name not in DEPENDENCY_PINS or type(value) is not dict:
        _fail(f"invalid aggregate dependency: {name}")
    kind, schema, version, expected_bytes, expected_sha, role = DEPENDENCY_PINS[name]
    raw = _canonical(value, label=name, max_bytes=MAX_DEPENDENCY_BYTES)
    if (
        value.get("artifact_kind") != kind
        or value.get("artifact_schema") != schema
        or value.get("artifact_schema_version") != version
        or value.get("fixture_id") != "kcs-persona-pc-v2"
        or value.get("fixture_schema_version") != 2
        or len(raw) != expected_bytes
        or hashlib.sha256(raw).hexdigest() != expected_sha
    ):
        _fail(f"{name} differs from its frozen body pin")
    _require_negative_authority(value, label=name)
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": version,
        "canonical_bytes": expected_bytes,
        "dependency_role": role,
        "name": name,
        "sha256": expected_sha,
    }


def _ceil_div(numerator, denominator):
    if type(numerator) is not int or numerator < 0:
        _fail("ceil numerator must be a non-negative exact integer")
    if type(denominator) is not int or denominator <= 0:
        _fail("ceil denominator must be a positive exact integer")
    return (numerator + denominator - 1) // denominator


def _observed_complexity(parameters, normalized_contract):
    shape = normalized_contract.get("parameter_shape")
    complexity = normalized_contract.get("complexity")
    if type(shape) is not dict or type(complexity) is not dict:
        _fail("implementation parameter/complexity contract is malformed")
    declared = shape.get("complexity_parameters")
    if declared == ["target_complexity"]:
        _exact_keys(parameters, {"target_complexity"}, label="renderer parameters")
        target = parameters["target_complexity"]
    elif declared == ["width", "height", "frame_or_event_count"]:
        _exact_keys(
            parameters,
            {"width", "height", "frame_or_event_count"},
            label="renderer parameters",
        )
        for field in ("width", "height", "frame_or_event_count"):
            _require_nonnegative_integer(parameters[field], label=field)
        binding = complexity.get("request_binding")
        if binding == "exact-width-times-height":
            maximum_dimension = complexity.get("raster_dimension_inclusive_maximum")
            if (
                type(maximum_dimension) is not int
                or maximum_dimension <= 0
                or parameters["width"] <= 0
                or parameters["height"] <= 0
                or parameters["width"] > maximum_dimension
                or parameters["height"] > maximum_dimension
                or parameters["frame_or_event_count"] != 0
            ):
                _fail("raster parameters violate the bound dimension contract")
            target = parameters["width"] * parameters["height"]
        elif binding == "exact-frame-or-event-count":
            if (
                parameters["width"] != 0
                or parameters["height"] != 0
                or parameters["frame_or_event_count"] <= 0
            ):
                _fail("audio/MIDI parameters violate the frame/event contract")
            target = parameters["frame_or_event_count"]
        else:
            _fail("unsupported renderer parameter binding")
    else:
        _fail("unsupported renderer parameter shape")
    _require_nonnegative_integer(target, label="target complexity")
    if (
        type(complexity.get("inclusive_minimum")) is not int
        or type(complexity.get("inclusive_maximum")) is not int
        or target < complexity["inclusive_minimum"]
        or target > complexity["inclusive_maximum"]
    ):
        _fail("target complexity is outside the implementation contract")
    return target


def _expected_raw_bytes(variant_id, parameters, normalized_contract):
    """Independently evaluate every currently bound exact byte formula."""

    target = _observed_complexity(parameters, normalized_contract)
    formula = normalized_contract.get("formula")
    if type(formula) is not dict or type(formula.get("parameters")) is not dict:
        _fail(f"byte formula is malformed: {variant_id}")
    formula_kind = formula.get("formula_kind")
    values = formula["parameters"]
    if formula_kind == "affine":
        base = values.get(
            "base_bytes_at_minimum_complexity",
            values.get("base_bytes_at_complexity_one"),
        )
        minimum = values.get(
            "minimum_complexity",
            normalized_contract["complexity"]["inclusive_minimum"],
        )
        increment = values.get("increment_bytes_per_additional_complexity")
        if any(type(item) is not int or item < 0 for item in (base, minimum, increment)):
            _fail(f"affine byte formula contains invalid integers: {variant_id}")
        expected = base + (target - minimum) * increment
    elif formula_kind == "exact-expression":
        width = parameters.get("width", 0)
        height = parameters.get("height", 0)
        frames = parameters.get("frame_or_event_count", 0)
        if variant_id == "bmp":
            expected = 62 + 4 * _ceil_div(width, 32) * height
        elif variant_id == "jpg":
            expected = 154 + _ceil_div(_ceil_div(width, 8) * _ceil_div(height, 8), 4)
        elif variant_id == "png":
            scanline_bytes = _ceil_div(width, 8) + 1
            uncompressed = scanline_bytes * height
            expected = 63 + uncompressed + 5 * _ceil_div(uncompressed, 65_535)
        elif variant_id == "tif":
            expected = 110 + _ceil_div(width, 8) * height
        elif variant_id == "aiff":
            expected = 54 + frames + (frames % 2)
        elif variant_id == "mid":
            expected = 27 + 3 * frames
        elif variant_id == "wav":
            expected = 44 + frames + (frames % 2)
        else:
            _fail(f"unsupported exact byte expression: {variant_id}")
    else:
        _fail(f"unsupported byte formula kind: {variant_id}")
    _require_nonnegative_integer(expected, label="expected raw bytes")
    maximum = values.get("maximum_rendered_bytes")
    minimum = values.get("minimum_rendered_bytes")
    if (
        type(maximum) is not int
        or maximum < 0
        or expected > maximum
        or (
            minimum is not None
            and (type(minimum) is not int or minimum < 0 or expected < minimum)
        )
    ):
        _fail(f"derived raw bytes violate the renderer bounds: {variant_id}")
    return target, expected


def _affine_contract(normalized_contract, *, variant_id):
    formula = normalized_contract.get("formula")
    complexity = normalized_contract.get("complexity")
    if (
        type(formula) is not dict
        or formula.get("formula_kind") != "affine"
        or type(formula.get("parameters")) is not dict
        or type(complexity) is not dict
    ):
        return None
    values = formula["parameters"]
    minimum = complexity.get("inclusive_minimum")
    maximum = complexity.get("inclusive_maximum")
    base = values.get(
        "base_bytes_at_minimum_complexity",
        values.get("base_bytes_at_complexity_one"),
    )
    increment = values.get("increment_bytes_per_additional_complexity")
    if any(type(item) is not int or item < 0 for item in (minimum, maximum, base, increment)):
        _fail(f"affine anchor contract is malformed: {variant_id}")
    if minimum > maximum:
        _fail(f"affine anchor complexity interval is empty: {variant_id}")
    return minimum, maximum, base, increment


def _affine_bytes(contract, target):
    minimum, maximum, base, increment = contract
    if type(target) is not int or target < minimum or target > maximum:
        _fail("affine anchor target leaves its complexity interval")
    return base + increment * (target - minimum)


def _anchor_row(
    *,
    bin_id,
    exact_raw_bytes,
    renderer_parameters,
    size_lane,
    target_complexity,
):
    return {
        "bin_id": bin_id,
        "exact_raw_bytes": exact_raw_bytes,
        "renderer_parameters": copy.deepcopy(renderer_parameters),
        "size_lane": size_lane,
        "target_complexity": target_complexity,
    }


def _raster_anchor_candidates(variant_id, normalized_contract):
    complexity = normalized_contract.get("complexity")
    if type(complexity) is not dict:
        _fail(f"raster complexity contract is malformed: {variant_id}")
    minimum = complexity.get("inclusive_minimum")
    maximum = complexity.get("inclusive_maximum")
    maximum_dimension = complexity.get("raster_dimension_inclusive_maximum")
    if (
        type(minimum) is not int
        or type(maximum) is not int
        or type(maximum_dimension) is not int
        or minimum != MIN_RASTER_PIXELS
        or maximum < minimum
        or maximum != MAX_RASTER_PIXELS
        or maximum_dimension <= 0
    ):
        _fail(f"raster complexity bounds drifted: {variant_id}")
    result = []
    for width in RASTER_DIMENSION_LATTICE:
        for height in RASTER_DIMENSION_LATTICE:
            pixels = width * height
            if pixels < minimum or pixels > maximum:
                continue
            if width > maximum_dimension or height > maximum_dimension:
                continue
            if max(width, height) > MAX_RASTER_ASPECT_RATIO * min(width, height):
                continue
            parameters = {
                "frame_or_event_count": 0,
                "height": height,
                "width": width,
            }
            target, exact_raw_bytes = _expected_raw_bytes(
                variant_id,
                parameters,
                normalized_contract,
            )
            if target != pixels:
                _fail(f"raster target-complexity formula drifted: {variant_id}")
            result.append(
                _anchor_row(
                    bin_id="candidate",
                    exact_raw_bytes=exact_raw_bytes,
                    renderer_parameters=parameters,
                    size_lane="formal-ordinary",
                    target_complexity=pixels,
                )
            )
    if not result:
        _fail(f"raster lattice has no feasible candidates: {variant_id}")
    return result


def _media_bytes_at(variant_id, count, normalized_contract):
    parameters = {
        "frame_or_event_count": count,
        "height": 0,
        "width": 0,
    }
    target, raw_bytes = _expected_raw_bytes(
        variant_id,
        parameters,
        normalized_contract,
    )
    if target != count:
        _fail(f"media target-complexity formula drifted: {variant_id}")
    return raw_bytes


def _media_count_at_least(variant_id, byte_floor, normalized_contract):
    complexity = normalized_contract["complexity"]
    lower = complexity["inclusive_minimum"]
    upper = complexity["inclusive_maximum"]
    if lower != MIN_MEDIA_UNITS or upper != MAX_MEDIA_UNITS:
        _fail(f"media complexity bounds drifted: {variant_id}")
    if _media_bytes_at(variant_id, upper, normalized_contract) < byte_floor:
        _fail(f"media renderer cannot reach its formal floor: {variant_id}")
    while lower < upper:
        middle = (lower + upper) // 2
        if _media_bytes_at(variant_id, middle, normalized_contract) >= byte_floor:
            upper = middle
        else:
            lower = middle + 1
    return lower


def _media_count_at_most(variant_id, byte_cap, normalized_contract):
    complexity = normalized_contract["complexity"]
    lower = complexity["inclusive_minimum"]
    upper = complexity["inclusive_maximum"]
    if lower != MIN_MEDIA_UNITS or upper != MAX_MEDIA_UNITS:
        _fail(f"media complexity bounds drifted: {variant_id}")
    if _media_bytes_at(variant_id, lower, normalized_contract) > byte_cap:
        return lower
    while lower < upper:
        middle = (lower + upper + 1) // 2
        if _media_bytes_at(variant_id, middle, normalized_contract) <= byte_cap:
            lower = middle
        else:
            upper = middle - 1
    return lower


def _expected_parameter_anchors(implementation_row):
    """Reconstruct the exact five ordinary and optional tail anchor rows."""

    variant_id = implementation_row.get("variant_id")
    family = implementation_row.get("family")
    normalized = implementation_row.get("normalized_contract")
    _require_nonempty_string(variant_id, label="anchor variant ID")
    _require_nonempty_string(family, label="anchor family")
    if type(normalized) is not dict:
        _fail(f"normalized anchor contract is absent: {variant_id}")
    affine = _affine_contract(normalized, variant_id=variant_id)
    ordinary = []
    tail = None
    if affine is not None:
        minimum, maximum, base, increment = affine
        required_floor = (
            FORMAL_IMAGE_MEDIA_DOMAIN_MIN_BYTES
            if family in {"image", "media", "domain_binary"}
            else base
        )
        floor_complexity = minimum
        if _affine_bytes(affine, floor_complexity) < required_floor:
            if increment <= 0:
                _fail(f"affine renderer cannot reach formal floor: {variant_id}")
            needed = required_floor - _affine_bytes(affine, minimum)
            floor_complexity = minimum + _ceil_div(needed, increment)
        if floor_complexity > maximum:
            _fail(f"affine formal floor exceeds complexity maximum: {variant_id}")
        for bin_id in BIN_ORDER:
            if bin_id == "floor" or increment == 0:
                target = floor_complexity
            else:
                target = minimum + (ORDINARY_TARGET_CAPS[bin_id] - base) // increment
                target = max(floor_complexity, min(maximum, target))
            raw_bytes = _affine_bytes(affine, target)
            ordinary.append(
                _anchor_row(
                    bin_id=bin_id,
                    exact_raw_bytes=raw_bytes,
                    renderer_parameters={"target_complexity": target},
                    size_lane="formal-ordinary",
                    target_complexity=target,
                )
            )
        maximum_bytes = _affine_bytes(affine, maximum)
        if variant_id in TAIL_VARIANTS and maximum_bytes >= FORMAL_TAIL_MIN_BYTES:
            if increment <= 0:
                _fail(f"tail-capable affine renderer is constant: {variant_id}")
            target = minimum + (FORMAL_TAIL_TARGET_CAP_BYTES - base) // increment
            target = min(maximum, max(minimum, target))
            raw_bytes = _affine_bytes(affine, target)
            tail = _anchor_row(
                bin_id="formal-tail",
                exact_raw_bytes=raw_bytes,
                renderer_parameters={"target_complexity": target},
                size_lane="formal-tail",
                target_complexity=target,
            )
    elif family == "image":
        candidates = _raster_anchor_candidates(variant_id, normalized)
        eligible = [
            row
            for row in candidates
            if FORMAL_IMAGE_MEDIA_DOMAIN_MIN_BYTES
            <= row["exact_raw_bytes"]
            <= FORMAL_ORDINARY_MAX_BYTES
        ]
        if not eligible:
            _fail(f"raster renderer has no formal ordinary anchor: {variant_id}")
        floor_row = min(
            eligible,
            key=lambda row: (
                row["exact_raw_bytes"],
                row["target_complexity"],
                row["renderer_parameters"]["width"],
                row["renderer_parameters"]["height"],
            ),
        )
        for bin_id in BIN_ORDER:
            if bin_id == "floor":
                selected = floor_row
            else:
                below = [
                    row
                    for row in eligible
                    if row["exact_raw_bytes"] <= ORDINARY_TARGET_CAPS[bin_id]
                ]
                selected = max(
                    below or [floor_row],
                    key=lambda row: (
                        row["exact_raw_bytes"],
                        row["target_complexity"],
                        -row["renderer_parameters"]["width"],
                        -row["renderer_parameters"]["height"],
                    ),
                )
            ordinary.append(
                _anchor_row(
                    bin_id=bin_id,
                    exact_raw_bytes=selected["exact_raw_bytes"],
                    renderer_parameters=selected["renderer_parameters"],
                    size_lane="formal-ordinary",
                    target_complexity=selected["target_complexity"],
                )
            )
        tail_candidates = [
            row
            for row in candidates
            if FORMAL_TAIL_MIN_BYTES
            <= row["exact_raw_bytes"]
            <= FORMAL_TAIL_TARGET_CAP_BYTES
        ]
        if variant_id in TAIL_VARIANTS:
            if not tail_candidates:
                _fail(f"tail-capable raster has no formal tail anchor: {variant_id}")
            selected = max(
                tail_candidates,
                key=lambda row: (
                    row["exact_raw_bytes"],
                    row["target_complexity"],
                    -row["renderer_parameters"]["width"],
                    -row["renderer_parameters"]["height"],
                ),
            )
            tail = _anchor_row(
                bin_id="formal-tail",
                exact_raw_bytes=selected["exact_raw_bytes"],
                renderer_parameters=selected["renderer_parameters"],
                size_lane="formal-tail",
                target_complexity=selected["target_complexity"],
            )
    elif family == "media":
        floor_count = _media_count_at_least(
            variant_id,
            FORMAL_IMAGE_MEDIA_DOMAIN_MIN_BYTES,
            normalized,
        )
        for bin_id in BIN_ORDER:
            target = (
                floor_count
                if bin_id == "floor"
                else max(
                    floor_count,
                    _media_count_at_most(
                        variant_id,
                        ORDINARY_TARGET_CAPS[bin_id],
                        normalized,
                    ),
                )
            )
            ordinary.append(
                _anchor_row(
                    bin_id=bin_id,
                    exact_raw_bytes=_media_bytes_at(variant_id, target, normalized),
                    renderer_parameters={
                        "frame_or_event_count": target,
                        "height": 0,
                        "width": 0,
                    },
                    size_lane="formal-ordinary",
                    target_complexity=target,
                )
            )
        if variant_id in TAIL_VARIANTS:
            target = _media_count_at_most(
                variant_id,
                FORMAL_TAIL_TARGET_CAP_BYTES,
                normalized,
            )
            tail = _anchor_row(
                bin_id="formal-tail",
                exact_raw_bytes=_media_bytes_at(variant_id, target, normalized),
                renderer_parameters={
                    "frame_or_event_count": target,
                    "height": 0,
                    "width": 0,
                },
                size_lane="formal-tail",
                target_complexity=target,
            )
    else:
        _fail(f"unsupported normalized anchor formula: {variant_id}")

    if len(ordinary) != len(BIN_ORDER):
        _fail(f"ordinary anchor cardinality drifted: {variant_id}")
    if (tail is not None) != (variant_id in TAIL_VARIANTS):
        _fail(f"tail anchor capability drifted: {variant_id}")
    result = ordinary + ([tail] if tail is not None else [])
    for row in result:
        # Recheck lane bounds and formula through the generic independent path.
        _validate_bin(
            {**copy.deepcopy(row), "counts": {origin: 0 for origin in EXPECTED_ORIGINS}},
            variant_id=variant_id,
            family=family,
            normalized_contract=normalized,
        )
    return result


def _validate_source_counts(value, *, label):
    _exact_keys(value, SOURCE_COUNT_KEYS, label=label)
    for origin in EXPECTED_ORIGINS:
        _require_nonnegative_integer(value[origin], label=f"{label}/{origin}")
    if value["full"] != value["pilot"] + value["full-residual"]:
        _fail(f"{label} pilot/residual/full closure drifted")


def _histogram_summary(bins, origin):
    histogram = {}
    tail_count = 0
    source_count = 0
    raw_byte_sum = 0
    block_rounded = 0
    for row in bins:
        count = row["counts"][origin]
        raw_bytes = row["exact_raw_bytes"]
        source_count += count
        raw_byte_sum += count * raw_bytes
        block_rounded += (
            count * _ceil_div(raw_bytes, BLOCK_ROUNDING_QUANTUM_BYTES)
            * BLOCK_ROUNDING_QUANTUM_BYTES
        )
        if row["size_lane"] == "formal-tail":
            tail_count += count
        if count:
            histogram[raw_bytes] = histogram.get(raw_bytes, 0) + count
    if source_count == 0:
        p50 = p95 = maximum = 0
        statistics_defined = False
    else:
        rank50 = _ceil_div(50 * source_count, 100)
        rank95 = _ceil_div(95 * source_count, 100)
        cumulative = 0
        p50 = p95 = 0
        for raw_bytes in sorted(histogram):
            cumulative += histogram[raw_bytes]
            if not p50 and cumulative >= rank50:
                p50 = raw_bytes
            if not p95 and cumulative >= rank95:
                p95 = raw_bytes
        maximum = max(histogram)
        statistics_defined = True
    return {
        "block_rounded_payload_bytes": block_rounded,
        "formal_tail_count": tail_count,
        "maximum_bytes": maximum,
        "nearest_rank_p50_bytes": p50,
        "nearest_rank_p95_bytes": p95,
        "raw_byte_sum": raw_byte_sum,
        "source_count": source_count,
        "statistics_defined": statistics_defined,
    }


def _merge_bins(rows):
    result = []
    for row in rows:
        result.extend(row["parameter_bins"])
    return result


def _validate_summaries(value, bins, source_counts, *, label):
    _exact_keys(value, EXPECTED_ORIGINS, label=f"{label} summaries")
    for origin in EXPECTED_ORIGINS:
        summary = value[origin]
        _exact_keys(summary, SUMMARY_KEYS, label=f"{label}/{origin} summary")
        expected = _histogram_summary(bins, origin)
        if summary != expected:
            _fail(f"{label}/{origin} summary differs from its exact histogram")
        if summary["source_count"] != source_counts[origin]:
            _fail(f"{label}/{origin} source count differs from its projection")
    for field in (
        "block_rounded_payload_bytes",
        "formal_tail_count",
        "raw_byte_sum",
        "source_count",
    ):
        if value["full"][field] != value["pilot"][field] + value[
            "full-residual"
        ][field]:
            _fail(f"{label} additive {field} closure drifted")


def _validate_bin(row, *, variant_id, family, normalized_contract):
    _exact_keys(row, PARAMETER_BIN_KEYS, label="parameter bin")
    _require_nonempty_string(row["bin_id"], label="bin ID")
    if row["size_lane"] not in {"formal-ordinary", "formal-tail"}:
        _fail(f"invalid size lane: {variant_id}")
    _validate_source_counts(row["counts"], label="parameter-bin counts")
    _require_nonnegative_integer(row["target_complexity"], label="target complexity")
    _require_nonnegative_integer(row["exact_raw_bytes"], label="exact raw bytes")
    target, expected_bytes = _expected_raw_bytes(
        variant_id,
        row["renderer_parameters"],
        normalized_contract,
    )
    if row["target_complexity"] != target or row["exact_raw_bytes"] != expected_bytes:
        _fail(f"selected complexity/raw bytes differ from exact formula: {variant_id}")
    if row["size_lane"] == "formal-tail":
        if (
            variant_id not in TAIL_VARIANTS
            or expected_bytes < FORMAL_TAIL_MIN_BYTES
            or expected_bytes > FORMAL_TAIL_MAX_BYTES
            or expected_bytes > FORMAL_TAIL_TARGET_CAP_BYTES
        ):
            _fail(f"formal tail bin violates eligibility or byte bounds: {variant_id}")
    else:
        if expected_bytes > FORMAL_ORDINARY_MAX_BYTES:
            _fail(f"formal ordinary bin exceeds its byte cap: {variant_id}")
        if (
            family in {"image", "media", "domain_binary"}
            and expected_bytes < FORMAL_IMAGE_MEDIA_DOMAIN_MIN_BYTES
        ):
            _fail(f"formal image/media/domain ordinary bin is below 4 KiB: {variant_id}")


def _exact_unique_map(rows, key, *, count, label):
    if type(rows) is not list or len(rows) != count:
        _fail(f"{label} cardinality drifted")
    result = {}
    for row in rows:
        if type(row) is not dict:
            _fail(f"{label} must contain only objects")
        identity = row.get(key)
        _require_nonempty_string(identity, label=f"{label}/{key}")
        if identity in result:
            _fail(f"{label} repeats {key}: {identity}")
        result[identity] = row
    return result


def _hamilton(total, keys, weights, *, order):
    _require_nonnegative_integer(total, label="Hamilton total")
    keys = list(keys)
    if not keys:
        if total:
            _fail("nonzero Hamilton total has no eligible cells")
        return {}
    if any(type(weights.get(key)) is not int or weights[key] < 0 for key in keys):
        _fail("Hamilton weights must be non-negative exact integers")
    denominator = sum(weights[key] for key in keys)
    if denominator <= 0:
        _fail("Hamilton denominator must be positive")
    result = {key: total * weights[key] // denominator for key in keys}
    remainder = total - sum(result.values())
    ranked = sorted(
        keys,
        key=lambda key: (-(total * weights[key] % denominator), order(key)),
    )
    for key in ranked[:remainder]:
        result[key] += 1
    if sum(result.values()) != total:
        _fail("Hamilton allocation did not close")
    return result


def _expected_size_shape_profiles(marginals):
    persona_totals = {
        persona_id: sum(
            row["full_count"]
            for row in marginals
            if row["persona_id"] == persona_id
        )
        for persona_id in EXPECTED_PERSONA_IDS
    }
    if any(total <= 0 for total in persona_totals.values()):
        _fail("persona denominator for size-shape ranking must be positive")
    family_totals = {
        (persona_id, family): sum(
            row["full_count"]
            for row in marginals
            if row["persona_id"] == persona_id and row["family"] == family
        )
        for persona_id in EXPECTED_PERSONA_IDS
        for family in EXPECTED_FAMILIES
    }
    result = {}
    for family in sorted(EXPECTED_FAMILIES):
        ranked = sorted(
            EXPECTED_PERSONA_IDS,
            key=lambda persona_id: (
                Fraction(
                    family_totals[persona_id, family],
                    persona_totals[persona_id],
                ),
                persona_id,
            ),
        )
        for ordinal, persona_id in enumerate(ranked):
            tier = "compact" if ordinal < 5 else "heavy" if ordinal >= 15 else "standard"
            result[persona_id, family] = (
                f"persona-v2-{tier}-byte-shape-v2"
            )
    return result


def _expected_tail_allocations(marginals):
    by_persona_variant = {
        (row["persona_id"], row["variant_id"]): row for row in marginals
    }
    result = {}
    for persona_id in EXPECTED_PERSONA_IDS:
        for origin, total, count_field in (
            ("pilot", PLANNED_PILOT_TAIL_FILES_PER_PERSONA, "pilot_count"),
            (
                "full-residual",
                PLANNED_RESIDUAL_TAIL_FILES_PER_PERSONA,
                "full_minus_pilot_count",
            ),
        ):
            eligible = [
                variant_id
                for variant_id in sorted(TAIL_VARIANTS)
                if (persona_id, variant_id) in by_persona_variant
                and by_persona_variant[persona_id, variant_id][count_field] > 0
            ]
            allocation = _hamilton(
                total,
                eligible,
                {
                    variant_id: by_persona_variant[persona_id, variant_id][count_field]
                    for variant_id in eligible
                },
                order=lambda variant_id: variant_id.encode("ascii"),
            )
            for variant_id, count in allocation.items():
                result[persona_id, variant_id, origin] = count
    return result


def _validate_persona_variant_rows(
    rows,
    *,
    variant_catalog_value,
    registry_value,
    formal_value,
):
    if type(rows) is not list or len(rows) != EXPECTED_PERSONA_VARIANT_ROWS:
        _fail("persona-variant row cardinality drifted")
    marginals = variant_catalog_value.get("persona_variant_marginals")
    if type(marginals) is not list or len(marginals) != EXPECTED_PERSONA_VARIANT_ROWS:
        _fail("upstream persona-variant marginal cardinality drifted")
    registry_by_variant = _exact_unique_map(
        registry_value.get("implementation_rows"),
        "variant_id",
        count=71,
        label="registry implementation rows",
    )
    formal_by_variant = _exact_unique_map(
        formal_value.get("recipe_profile_rows"),
        "variant_id",
        count=71,
        label="formal recipe profile rows",
    )
    expected_shape_profiles = _expected_size_shape_profiles(marginals)
    expected_tail_allocations = _expected_tail_allocations(marginals)
    expected_anchors_by_variant = {
        variant_id: _expected_parameter_anchors(implementation_row)
        for variant_id, implementation_row in registry_by_variant.items()
    }
    if sum(len(rows) for rows in expected_anchors_by_variant.values()) != 362:
        _fail("independently reconstructed parameter-anchor count must be 362")
    seen = set()
    bin_definitions = {}
    for index, (row, marginal) in enumerate(zip(rows, marginals)):
        _exact_keys(row, PERSONA_VARIANT_ROW_KEYS, label="persona-variant row")
        identity = (row["persona_id"], row["family"], row["variant_id"])
        expected_identity = (
            marginal.get("persona_id"),
            marginal.get("family"),
            marginal.get("variant_id"),
        )
        if identity != expected_identity or identity in seen:
            _fail(f"persona-variant identity/order drifted at row {index}")
        seen.add(identity)
        persona_id, family, variant_id = identity
        if persona_id not in EXPECTED_PERSONA_IDS or family not in EXPECTED_FAMILIES:
            _fail("persona-variant row uses an unknown persona/family")
        implementation_row = registry_by_variant.get(variant_id)
        recipe_row = formal_by_variant.get(variant_id)
        if implementation_row is None or recipe_row is None:
            _fail(f"persona-variant row has an unknown variant: {variant_id}")
        implementation = implementation_row.get("implementation")
        if type(implementation) is not dict:
            _fail(f"implementation binding missing: {variant_id}")
        expected_counts = {
            "pilot": marginal.get("pilot_count"),
            "full-residual": marginal.get("full_minus_pilot_count"),
            "full": marginal.get("full_count"),
        }
        if (
            row["gate_role"] != implementation_row.get("gate_role")
            or row["gate_role"] != recipe_row.get("gate_role")
            or row["family"] != implementation_row.get("family")
            or row["recipe_profile_id"] != recipe_row.get("recipe_profile_id")
            or row["implementation_profile_id"]
            != implementation.get("implementation_profile_id")
            or row["source_counts"] != expected_counts
        ):
            _fail(f"persona-variant upstream projection drifted: {variant_id}")
        _validate_source_counts(row["source_counts"], label="persona-variant counts")
        if (
            row["size_shape_profile_id"] not in SIZE_SHAPE_PROFILE_IDS
            or row["size_shape_profile_id"]
            != expected_shape_profiles[persona_id, family]
        ):
            _fail(f"size-shape profile rank drifted: {persona_id}/{family}")
        bins = row["parameter_bins"]
        if type(bins) is not list or not bins:
            _fail(f"parameter bins must be non-empty: {persona_id}/{variant_id}")
        bin_ids = []
        normalized_contract = implementation_row.get("normalized_contract")
        if type(normalized_contract) is not dict:
            _fail(f"normalized contract missing: {variant_id}")
        for bin_row in bins:
            _validate_bin(
                bin_row,
                variant_id=variant_id,
                family=family,
                normalized_contract=normalized_contract,
            )
            bin_ids.append(bin_row["bin_id"])
            definition = {
                key: copy.deepcopy(bin_row[key])
                for key in PARAMETER_BIN_KEYS - {"counts"}
            }
            previous = bin_definitions.setdefault(
                (variant_id, bin_row["bin_id"]), definition
            )
            if previous != definition:
                _fail(f"variant parameter-bin definition drifted by persona: {variant_id}")
        if len(bin_ids) != len(set(bin_ids)):
            _fail(f"parameter bin IDs repeat: {persona_id}/{variant_id}")
        expected_bin_ids = list(BIN_ORDER) + (
            ["formal-tail"] if variant_id in TAIL_VARIANTS else []
        )
        if bin_ids != expected_bin_ids:
            _fail(f"parameter bin order/cardinality drifted: {persona_id}/{variant_id}")
        actual_anchors = [
            {
                key: copy.deepcopy(bin_row[key])
                for key in PARAMETER_BIN_KEYS - {"counts"}
            }
            for bin_row in bins
        ]
        if actual_anchors != expected_anchors_by_variant[variant_id]:
            _fail(
                f"parameter anchors differ from independent reconstruction: "
                f"{persona_id}/{variant_id}"
            )
        bins_by_id = {item["bin_id"]: item for item in bins}
        floor_bytes = bins_by_id["floor"]["exact_raw_bytes"]
        previous_bytes = 0
        for bin_id in BIN_ORDER:
            raw_bytes = bins_by_id[bin_id]["exact_raw_bytes"]
            allowed = max(floor_bytes, ORDINARY_TARGET_CAPS[bin_id])
            if raw_bytes > allowed or raw_bytes < previous_bytes:
                _fail(
                    f"ordinary bin target cap/order drifted: {persona_id}/{variant_id}"
                )
            previous_bytes = raw_bytes
        tier = row["size_shape_profile_id"].removeprefix(
            "persona-v2-"
        ).removesuffix("-byte-shape-v2")
        weights = SIZE_SHAPE_WEIGHTS_BP.get(tier)
        if weights is None:
            _fail(f"size-shape profile cannot select weights: {persona_id}/{family}")
        for origin in ("pilot", "full-residual"):
            tail_count = expected_tail_allocations.get(
                (persona_id, variant_id, origin), 0
            )
            ordinary_total = row["source_counts"][origin] - tail_count
            if ordinary_total < 0:
                _fail("tail allocation exceeds its persona-variant source count")
            expected_ordinary = _hamilton(
                ordinary_total,
                BIN_ORDER,
                {
                    bin_id: weights[position]
                    for position, bin_id in enumerate(BIN_ORDER)
                },
                order=BIN_ORDER.index,
            )
            for bin_id in BIN_ORDER:
                if bins_by_id[bin_id]["counts"][origin] != expected_ordinary[bin_id]:
                    _fail(f"ordinary Hamilton allocation drifted: {persona_id}/{variant_id}")
            if variant_id in TAIL_VARIANTS and bins_by_id["formal-tail"][
                "counts"
            ][origin] != tail_count:
                _fail(f"tail Hamilton allocation drifted: {persona_id}/{variant_id}")
        for origin in EXPECTED_ORIGINS:
            if sum(item["counts"][origin] for item in bins) != row["source_counts"][origin]:
                _fail(f"parameter-bin counts do not close: {persona_id}/{variant_id}")
        _validate_summaries(
            row["summaries"],
            bins,
            row["source_counts"],
            label=f"{persona_id}/{variant_id}",
        )
    return bin_definitions


def _projection_counts_and_summaries(rows):
    bins = _merge_bins(rows)
    source_counts = {
        origin: sum(row["source_counts"][origin] for row in rows)
        for origin in EXPECTED_ORIGINS
    }
    return source_counts, {
        origin: _histogram_summary(bins, origin) for origin in EXPECTED_ORIGINS
    }


def _validate_projection_rows(family_rows, persona_rows, suite, variant_rows):
    expected_family_keys = {
        (persona_id, family)
        for persona_id in EXPECTED_PERSONA_IDS
        for family in EXPECTED_FAMILIES
    }
    if type(family_rows) is not list or len(family_rows) != EXPECTED_PERSONA_FAMILY_ROWS:
        _fail("persona-family projection cardinality drifted")
    family_by_key = {}
    for row in family_rows:
        _exact_keys(
            row,
            {
                "persona_id",
                "family",
                "source_counts",
                "summaries",
                "variant_row_count",
            },
            label="persona-family projection",
        )
        key = (row["persona_id"], row["family"])
        if key not in expected_family_keys or key in family_by_key:
            _fail("persona-family projection identity drifted")
        family_by_key[key] = row
    if set(family_by_key) != expected_family_keys:
        _fail("persona-family projection coverage drifted")
    if [
        (row["persona_id"], row["family"]) for row in family_rows
    ] != sorted(expected_family_keys):
        _fail("persona-family projection order drifted")
    for key, projection in family_by_key.items():
        selected = [
            row
            for row in variant_rows
            if (row["persona_id"], row["family"]) == key
        ]
        counts, summaries = _projection_counts_and_summaries(selected)
        if (
            projection["source_counts"] != counts
            or projection["summaries"] != summaries
            or projection["variant_row_count"] != len(selected)
        ):
            _fail(f"persona-family histogram projection drifted: {key[0]}/{key[1]}")
        _validate_source_counts(projection["source_counts"], label="family counts")
        _validate_summaries(
            projection["summaries"],
            _merge_bins(selected),
            projection["source_counts"],
            label=f"{key[0]}/{key[1]}",
        )

    if type(persona_rows) is not list or len(persona_rows) != len(EXPECTED_PERSONA_IDS):
        _fail("persona summary cardinality drifted")
    persona_by_id = {}
    for row in persona_rows:
        _exact_keys(
            row,
            {
                "capacity_check",
                "persona_id",
                "source_counts",
                "summaries",
                "variant_row_count",
            },
            label="persona summary",
        )
        persona_id = row["persona_id"]
        if persona_id not in EXPECTED_PERSONA_IDS or persona_id in persona_by_id:
            _fail("persona summary identity drifted")
        persona_by_id[persona_id] = row
    if tuple(persona_by_id) != EXPECTED_PERSONA_IDS:
        _fail("persona summary order drifted")
    for persona_id, projection in persona_by_id.items():
        selected = [row for row in variant_rows if row["persona_id"] == persona_id]
        counts, summaries = _projection_counts_and_summaries(selected)
        full_blocks = summaries["full"]["block_rounded_payload_bytes"]
        expected_capacity = {
            "candidate_cap_bytes": PERSONA_CANDIDATE_CAP_BYTES,
            "hard_block_rounded_cap_bytes": PERSONA_BLOCK_ROUNDED_CAP_BYTES,
            "minimum_margin_bytes": PERSONA_REQUIRED_MARGIN_BYTES,
            "passes_hard_cap": full_blocks <= PERSONA_BLOCK_ROUNDED_CAP_BYTES,
            "remaining_candidate_margin_bytes": (
                PERSONA_CANDIDATE_CAP_BYTES - full_blocks
            ),
        }
        if (
            projection["source_counts"] != counts
            or projection["summaries"] != summaries
            or projection["variant_row_count"] != len(selected)
            or projection["capacity_check"] != expected_capacity
        ):
            _fail(f"persona histogram projection drifted: {persona_id}")
        _validate_source_counts(projection["source_counts"], label="persona counts")
        _validate_summaries(
            projection["summaries"],
            _merge_bins(selected),
            projection["source_counts"],
            label=persona_id,
        )
        tail = projection["summaries"]
        if (
            tail["pilot"]["formal_tail_count"] != PLANNED_PILOT_TAIL_FILES_PER_PERSONA
            or tail["full-residual"]["formal_tail_count"]
            != PLANNED_RESIDUAL_TAIL_FILES_PER_PERSONA
            or tail["full"]["formal_tail_count"]
            != PLANNED_FORMAL_TAIL_FILES_PER_PERSONA
            or tail["full"]["formal_tail_count"] > MAX_FORMAL_TAIL_FILES_PER_PERSONA
        ):
            _fail(f"persona formal-tail allocation drifted: {persona_id}")
        if (
            projection["summaries"]["full"]["block_rounded_payload_bytes"]
            > PERSONA_BLOCK_ROUNDED_CAP_BYTES
        ):
            _fail(f"persona block-rounded payload exceeds planning cap: {persona_id}")

    _exact_keys(
        suite,
        {
            "capacity_check",
            "persona_count",
            "source_counts",
            "summaries",
            "variant_row_count",
        },
        label="suite summary",
    )
    counts, summaries = _projection_counts_and_summaries(variant_rows)
    suite_blocks = summaries["full"]["block_rounded_payload_bytes"]
    expected_suite_capacity = {
        "hard_block_rounded_cap_bytes": SUITE_BLOCK_ROUNDED_CAP_BYTES,
        "passes_hard_cap": suite_blocks <= SUITE_BLOCK_ROUNDED_CAP_BYTES,
        "remaining_margin_bytes": SUITE_BLOCK_ROUNDED_CAP_BYTES - suite_blocks,
    }
    if (
        suite["source_counts"] != counts
        or suite["summaries"] != summaries
        or suite["persona_count"] != len(EXPECTED_PERSONA_IDS)
        or suite["variant_row_count"] != len(variant_rows)
        or suite["capacity_check"] != expected_suite_capacity
    ):
        _fail("suite histogram projection drifted")
    _validate_source_counts(suite["source_counts"], label="suite counts")
    _validate_summaries(
        suite["summaries"],
        _merge_bins(variant_rows),
        suite["source_counts"],
        label="suite",
    )
    if suite["source_counts"] != {
        "pilot": 20_300,
        "full-residual": 182_700,
        "full": 203_000,
    }:
        _fail("suite source-count totals drifted")
    if suite["summaries"]["full"]["formal_tail_count"] != 160:
        _fail("suite formal-tail count drifted")
    if (
        suite["summaries"]["full"]["block_rounded_payload_bytes"]
        > SUITE_BLOCK_ROUNDED_CAP_BYTES
    ):
        _fail("suite block-rounded payload exceeds planning cap")


def _validate_probe_receipts(
    receipts,
    *,
    bin_definitions,
    registry_value,
    selected_renderer_probe_provider,
    selected_validator_probe_provider,
):
    if not callable(selected_renderer_probe_provider) or not callable(
        selected_validator_probe_provider
    ):
        _fail("selected probe providers must be callable")
    if type(receipts) is not list or len(receipts) != EXPECTED_PARAMETER_BIN_PROBES:
        _fail("parameter-bin probe receipt cardinality drifted")
    registry_by_variant = _exact_unique_map(
        registry_value.get("implementation_rows"),
        "variant_id",
        count=71,
        label="registry implementation rows",
    )
    expected_receipt_keys = {
        "bin_id",
        "payload_sha256",
        "renderer_parameters",
        "target_bytes",
        "target_complexity",
        "validator_accepted",
        "validator_receipt_sha256",
        "variant_id",
    }
    expected_rendered_keys = {
        "content_media_type",
        "data",
        "expected_kcs_path_media_type",
        "expected_offline_disposition",
        "extension",
        "target_bytes",
        "target_complexity",
    }
    seen = set()
    ordinary_variants = set()
    tail_variants = set()
    expected_receipt_order = []
    for variant_id in sorted(registry_by_variant):
        expected_receipt_order.extend(
            (variant_id, bin_id) for bin_id in BIN_ORDER
        )
        if variant_id in TAIL_VARIANTS:
            expected_receipt_order.append((variant_id, "formal-tail"))
    if [
        (row.get("variant_id"), row.get("bin_id"))
        for row in receipts
        if type(row) is dict
    ] != expected_receipt_order:
        _fail("parameter-bin probe order or selection drifted")
    for receipt in receipts:
        _exact_keys(receipt, expected_receipt_keys, label="parameter-bin probe receipt")
        variant_id = receipt["variant_id"]
        bin_id = receipt["bin_id"]
        key = (variant_id, bin_id)
        if key in seen or key not in bin_definitions:
            _fail("parameter-bin probe receipt is duplicate or unbound")
        seen.add(key)
        definition = bin_definitions[key]
        if (
            receipt["renderer_parameters"] != definition["renderer_parameters"]
            or receipt["target_complexity"] != definition["target_complexity"]
            or receipt["target_bytes"] != definition["exact_raw_bytes"]
            or receipt["validator_accepted"] is not True
            or type(receipt["payload_sha256"]) is not str
            or len(receipt["payload_sha256"]) != 64
            or type(receipt["validator_receipt_sha256"]) is not str
            or len(receipt["validator_receipt_sha256"]) != 64
        ):
            _fail(f"parameter-bin probe receipt drifted: {variant_id}/{bin_id}")
        if definition["size_lane"] == "formal-tail":
            tail_variants.add(variant_id)
        else:
            ordinary_variants.add(variant_id)
        implementation_row = registry_by_variant.get(variant_id)
        if implementation_row is None:
            _fail(f"probe uses an unknown variant: {variant_id}")
        parameters = copy.deepcopy(receipt["renderer_parameters"])
        try:
            rendered = selected_renderer_probe_provider(variant_id, parameters)
        except Exception as error:
            _fail(f"selected renderer probe failed: {variant_id}/{type(error).__name__}")
        _exact_keys(rendered, expected_rendered_keys, label="selected renderer result")
        data = rendered["data"]
        if (
            type(data) is not bytes
            or type(rendered["target_bytes"]) is not int
            or type(rendered["target_complexity"]) is not int
            or type(rendered["extension"]) is not str
            or type(rendered["content_media_type"]) is not str
            or type(rendered["expected_kcs_path_media_type"]) is not str
            or type(rendered["expected_offline_disposition"]) is not str
            or rendered["target_bytes"] != len(data)
            or rendered["target_bytes"] != receipt["target_bytes"]
            or rendered["target_complexity"] != receipt["target_complexity"]
            or rendered["extension"] != implementation_row["filename_extension"]
            or rendered["content_media_type"] != implementation_row["content_media_type"]
            or rendered["expected_kcs_path_media_type"]
            != implementation_row["expected_kcs_path_media_type"]
            or rendered["expected_offline_disposition"]
            != implementation_row["expected_offline_disposition"]
            or hashlib.sha256(data).hexdigest() != receipt["payload_sha256"]
        ):
            _fail(f"selected renderer result drifted: {variant_id}/{bin_id}")
        implementation = implementation_row["implementation"]
        validator_binding = {
            "binding_id": implementation["validator_binding_id"],
            "implementation_id": implementation["validator_id"],
            "implementation_pair_id": implementation["pair_id"],
            "implementation_schema_version": implementation[
                "validator_schema_version"
            ],
        }
        try:
            supplied_receipt = selected_validator_probe_provider(
                variant_id,
                copy.deepcopy(receipt["renderer_parameters"]),
                copy.deepcopy(rendered),
            )
        except Exception as error:
            _fail(f"selected validator probe failed: {variant_id}/{type(error).__name__}")
        try:
            direct_receipt = registry_validator._direct_bound_runtime_receipt(
                implementation["pair_id"],
                variant_id,
                copy.deepcopy(receipt["renderer_parameters"]),
                copy.deepcopy(rendered),
                validator_binding,
                implementation["validator_profile_id"],
            )
        except Exception as error:
            _fail(f"direct selected validator failed: {variant_id}/{type(error).__name__}")
        supplied_raw = _canonical(
            supplied_receipt,
            label="supplied selected validator receipt",
            max_bytes=MAX_FRAGMENT_BYTES,
        )
        direct_raw = _canonical(
            direct_receipt,
            label="direct selected validator receipt",
            max_bytes=MAX_FRAGMENT_BYTES,
        )
        if supplied_raw != direct_raw:
            _fail(f"selected validator receipt differs from direct binding: {variant_id}")
        try:
            registry_validator._validate_runtime_receipt(
                direct_receipt,
                variant_id=variant_id,
                validator_binding=validator_binding,
                validator_profile_id=implementation["validator_profile_id"],
                expected_complexity=receipt["target_complexity"],
                payload_bytes=len(data),
                payload_sha256=receipt["payload_sha256"],
            )
        except registry_validator.PersonaV2FormatImplementationRegistryValidationError:
            _fail(f"direct selected validator receipt was rejected: {variant_id}")
        if hashlib.sha256(direct_raw).hexdigest() != receipt[
            "validator_receipt_sha256"
        ]:
            _fail(f"selected validator receipt pin drifted: {variant_id}/{bin_id}")
    if ordinary_variants != set(registry_by_variant) or tail_variants != set(TAIL_VARIANTS):
        _fail("parameter-bin probes must cover all 71 variants and exact seven tails")


def _validate_static_contract_fields(value, expected_bindings):
    _exact_keys(value, TOP_LEVEL_KEYS, label="aggregate byte distribution catalog")
    if (
        value["artifact_kind"] != ARTIFACT_KIND
        or value["artifact_schema"] != ARTIFACT_SCHEMA
        or value["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or value["fixture_id"] != "kcs-persona-pc-v2"
        or value["fixture_schema_version"] != 2
        or value["g0_contract_frozen"] is not False
    ):
        _fail("aggregate byte distribution artifact identity drifted")
    _require_negative_authority(
        value,
        label="aggregate byte distribution catalog",
        exact_fields=AUTHORITY_FIELDS,
    )
    if value["input_binding_order"] != [row["name"] for row in expected_bindings]:
        _fail("aggregate dependency binding order drifted")
    if value["input_bindings"] != expected_bindings:
        _fail("aggregate dependency binding pins or roles drifted")
    canonical_limits = value["canonical_limits"]
    if canonical_limits != {
        "max_body_bytes": MAX_CATALOG_BYTES,
        "max_integer_bits": artifact_common.MAX_INTEGER_BITS,
        "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
        "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
        "self_hash_embedded": False,
        "unicode_normalization": "NFC",
    }:
        _fail("aggregate canonical limits drifted")
    if value["allocation_model"] != EXPECTED_ALLOCATION_MODEL:
        _fail("aggregate allocation model drifted")
    if value["completion_claims"] != EXPECTED_COMPLETION_CLAIMS:
        _fail("aggregate completion claims drifted or overclaim authority")
    for label in ("completion_scope",):
        _require_nonempty_string(value[label], label=label)
    if value["orders"] != EXPECTED_ORDERS:
        _fail("aggregate order contracts drifted")
    if value["distribution_policy"] != EXPECTED_DISTRIBUTION_POLICY:
        _fail("aggregate distribution policy drifted")
    if (
        type(value["remaining_blockers"]) is not list
        or not value["remaining_blockers"]
        or any(type(item) is not str or not item for item in value["remaining_blockers"])
    ):
        _fail("remaining blockers must be non-empty strings")


def validate_aggregate_byte_distribution_catalog(
    value,
    *,
    variant_catalog_value,
    format_implementation_registry_value,
    formal_source_recipe_catalog_value,
    realism_profile_value,
    historical_source_profile_value,
    source_inventory_profile_value,
    source_semantic_membership_catalog_value,
    renderer_contract_provider,
    validator_contract_provider,
    renderer_probe_provider,
    selected_renderer_probe_provider,
    selected_validator_probe_provider,
):
    """Validate the frozen aggregate histogram and all transitive bindings."""

    if type(value) is not dict:
        _fail("aggregate byte distribution catalog must be an object")
    actual_raw = _canonical(
        value,
        label="persona v2 aggregate byte distribution catalog",
        max_bytes=MAX_CATALOG_BYTES,
    )
    if EXPECTED_CATALOG_CANONICAL_BYTES <= 0 or EXPECTED_CATALOG_SHA256 == "0" * 64:
        _fail("aggregate byte distribution catalog final pins are not installed")
    if (
        len(actual_raw) != EXPECTED_CATALOG_CANONICAL_BYTES
        or hashlib.sha256(actual_raw).hexdigest() != EXPECTED_CATALOG_SHA256
    ):
        _fail("aggregate byte distribution catalog body pin drifted")

    frozen_value = copy.deepcopy(value)
    frozen_variant = copy.deepcopy(variant_catalog_value)
    frozen_registry = copy.deepcopy(format_implementation_registry_value)
    frozen_formal = copy.deepcopy(formal_source_recipe_catalog_value)
    frozen_realism = copy.deepcopy(realism_profile_value)
    frozen_historical = copy.deepcopy(historical_source_profile_value)
    frozen_inventory = copy.deepcopy(source_inventory_profile_value)
    frozen_semantic = copy.deepcopy(source_semantic_membership_catalog_value)

    dependencies = (
        ("persona-v2-variant-catalog", frozen_variant),
        ("persona-v2-format-implementation-registry", frozen_registry),
        ("persona-v2-formal-source-recipe-profile-catalog", frozen_formal),
        ("persona-v2-realism-profile", frozen_realism),
    )
    expected_bindings = [
        _authenticate_dependency(name, dependency)
        for name, dependency in dependencies
    ]
    _validate_static_contract_fields(frozen_value, expected_bindings)
    _walk_forbidden_instances(frozen_value)

    # This one call authenticates and independently reconstructs the formal
    # profile catalog, while transitively running the independent registry
    # validator and all 213 minimum/midpoint/maximum runtime probes.
    try:
        formal_validator.validate_formal_source_recipe_catalog(
            frozen_formal,
            variant_catalog_value=frozen_variant,
            source_inventory_profile_value=frozen_inventory,
            format_implementation_registry_value=frozen_registry,
            source_semantic_membership_catalog_value=frozen_semantic,
            historical_source_profile_value=frozen_historical,
            renderer_contract_provider=renderer_contract_provider,
            validator_contract_provider=validator_contract_provider,
            renderer_probe_provider=renderer_probe_provider,
        )
    except formal_validator.PersonaV2FormalSourceRecipeCatalogValidationError as error:
        _fail(f"formal recipe dependency validation failed: {error}")

    bin_definitions = _validate_persona_variant_rows(
        frozen_value["persona_variant_rows"],
        variant_catalog_value=frozen_variant,
        registry_value=frozen_registry,
        formal_value=frozen_formal,
    )
    _validate_projection_rows(
        frozen_value["persona_family_projection_rows"],
        frozen_value["persona_summaries"],
        frozen_value["suite_summary"],
        frozen_value["persona_variant_rows"],
    )
    _validate_probe_receipts(
        frozen_value["parameter_bin_probe_receipts"],
        bin_definitions=bin_definitions,
        registry_value=frozen_registry,
        selected_renderer_probe_provider=selected_renderer_probe_provider,
        selected_validator_probe_provider=selected_validator_probe_provider,
    )

    # Re-authenticate every caller-owned object after all untrusted callbacks.
    final_raw = _canonical(
        value,
        label="aggregate byte distribution catalog after callbacks",
        max_bytes=MAX_CATALOG_BYTES,
    )
    if final_raw != actual_raw:
        _fail("aggregate byte distribution catalog mutated during validation")
    for name, dependency in (
        ("persona-v2-variant-catalog", variant_catalog_value),
        (
            "persona-v2-format-implementation-registry",
            format_implementation_registry_value,
        ),
        (
            "persona-v2-formal-source-recipe-profile-catalog",
            formal_source_recipe_catalog_value,
        ),
        ("persona-v2-realism-profile", realism_profile_value),
    ):
        _authenticate_dependency(name, dependency)
    try:
        formal_validator._authenticate_dependency(
            "persona-v2-source-inventory-profile-catalog",
            source_inventory_profile_value,
        )
        formal_validator._authenticate_dependency(
            "persona-v2-source-semantic-membership-catalog",
            source_semantic_membership_catalog_value,
        )
        registry_validator._validate_upstream_binding(
            historical_source_profile_value,
            registry_validator.EXPECTED_INPUT_BINDINGS[1],
            label="historical source profile catalog after aggregate callbacks",
        )
    except (
        formal_validator.PersonaV2FormalSourceRecipeCatalogValidationError,
        registry_validator.PersonaV2FormatImplementationRegistryValidationError,
    ):
        _fail("transitive dependency mutated during aggregate validation")
    return True


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "EXPECTED_CATALOG_CANONICAL_BYTES",
    "EXPECTED_CATALOG_SHA256",
    "MAX_CATALOG_BYTES",
    "PersonaV2AggregateByteDistributionCatalogValidationError",
    "validate_aggregate_byte_distribution_catalog",
]
