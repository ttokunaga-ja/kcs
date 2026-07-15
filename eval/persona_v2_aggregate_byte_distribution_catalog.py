"""Exact aggregate byte-distribution plan for the persona-PC v2 suite.

This sidecar selects renderer-realizable *aggregate* parameter histograms for
the frozen 566 persona/variant marginal rows.  It deliberately stops before
the 203,000 physical source instances: there are no source/materialization
identifiers, paths, filenames, payload seeds, scope assignments, solver
coordinates, or write authority here.

The two immutable origins (``pilot`` and ``full-residual``) are allocated
independently.  ``full`` is their exact histogram sum; its order statistics
are recomputed from the merged histogram rather than combined from origin
quantiles.  All arithmetic is integer-only.
"""

from __future__ import annotations

import copy
import functools
import hashlib
from fractions import Fraction

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_aggregate_byte_distribution_catalog_validator as independent
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_formal_source_recipe_catalog as formal_catalog
    from . import persona_v2_format_implementation_registry as implementation_registry
    from . import persona_v2_realism_profile as realism_profile
    from . import persona_v2_source_inventory_profile as inventory_catalog
    from . import persona_v2_source_profile_catalog as historical_catalog
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_aggregate_byte_distribution_catalog_validator as independent
    import persona_v2_artifact_common as artifact_common
    import persona_v2_formal_source_recipe_catalog as formal_catalog
    import persona_v2_format_implementation_registry as implementation_registry
    import persona_v2_realism_profile as realism_profile
    import persona_v2_source_inventory_profile as inventory_catalog
    import persona_v2_source_profile_catalog as historical_catalog
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA = "kcs.persona.pc-aggregate-byte-distribution-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-aggregate-byte-distribution-catalog"
MAX_CATALOG_BYTES = 4 * 2**20
EXPECTED_PERSONA_VARIANT_ROWS = 566
EXPECTED_PERSONA_FAMILY_ROWS = 300
EXPECTED_PERSONAS = 20
EXPECTED_VARIANTS = 71
EXPECTED_PROBE_RECEIPTS = 362

ALLOCATION_QUANTUM_BYTES = 4_096
PERSONA_CANDIDATE_CAP_BYTES = 512 * 2**20
PERSONA_REQUIRED_MARGIN_BYTES = 32 * 2**20
PERSONA_BLOCK_ROUNDED_CAP_BYTES = (
    PERSONA_CANDIDATE_CAP_BYTES - PERSONA_REQUIRED_MARGIN_BYTES
)
SUITE_BLOCK_ROUNDED_CAP_BYTES = 10 * 2**30

FORMAL_ORDINARY_MIN_BYTES = 4 * 2**10
FORMAL_ORDINARY_MAX_BYTES = 512 * 2**10
FORMAL_TAIL_MIN_BYTES = 1 * 2**20
FORMAL_TAIL_MAX_BYTES = 4 * 2**20
TAIL_TARGET_CAP_BYTES = 5 * 2**19  # 2.5 MiB, exact integer.
TAIL_PILOT_PER_PERSONA = 1
TAIL_RESIDUAL_PER_PERSONA = 7
TAIL_FULL_PER_PERSONA = 8
TAIL_MAX_PER_PERSONA = 16

ORIGIN_ORDER = ("pilot", "full-residual")
PROFILE_ORDER = ("pilot", "full-residual", "full")
BIN_ORDER = ("floor", "small", "medium", "large", "ordinary-max")
ORDINARY_TARGET_CAPS = {
    "floor": 0,
    "small": 8 * 2**10,
    "medium": 32 * 2**10,
    "large": 128 * 2**10,
    "ordinary-max": FORMAL_ORDINARY_MAX_BYTES,
}
SIZE_SHAPE_WEIGHTS_BP = {
    # The lighter weights preserve a hard 32 MiB planning margin below the
    # existing 512 MiB/persona source-tree candidate cap.
    "compact": (4_000, 4_200, 1_500, 250, 50),
    "standard": (3_000, 4_300, 2_200, 400, 100),
    "heavy": (2_000, 4_000, 3_000, 800, 200),
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
    1_024,
    1_536,
    2_048,
    3_072,
    4_096,
)
MAX_RASTER_ASPECT_RATIO = 4
MAX_RASTER_PIXELS = 16_777_216
MAX_MEDIA_UNITS = 4_800_000

TAIL_CAPABLE_VARIANTS = frozenset(
    {"aiff", "bmp", "mid", "npz", "png", "tif", "wav"}
)

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-variant-catalog": (
        211_733,
        "abbe522ff37a9a091f28b7a230928fd598054498eb80cab99f08d21889f26cec",
    ),
    "persona-v2-format-implementation-registry": (
        333_881,
        "f585ae477daa01db4dc11bbc1edd9824696bd91eddce5870d618caaffd90c683",
    ),
    "persona-v2-formal-source-recipe-profile-catalog": (
        386_152,
        "973a31336b90abc6271165ce4a3130679f36d5a9d65b06fece6827123e5c6cc8",
    ),
    "persona-v2-realism-profile": (
        36_811,
        "a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05",
    ),
}

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


class PersonaV2AggregateByteDistributionCatalogError(ValueError):
    """Raised when aggregate byte-distribution construction drifts."""


def _fail(message):
    raise PersonaV2AggregateByteDistributionCatalogError(message)


def _canonical_fragment(value, *, label, max_bytes=128 * 1024):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        _fail(f"{label} authority must be non-empty and all false")


def _artifact_binding(name, role, value, *, canonical, validate):
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


def _hamilton(total, keys, weights, *, order):
    if type(total) is not int or total < 0:
        _fail("Hamilton total must be a nonnegative exact integer")
    keys = list(keys)
    if not keys:
        if total:
            _fail("nonzero Hamilton total has no eligible keys")
        return {}
    denominator = sum(weights[key] for key in keys)
    if denominator <= 0 or any(
        type(weights[key]) is not int or weights[key] < 0 for key in keys
    ):
        _fail("Hamilton weights must be nonnegative exact integers")
    result = {
        key: total * weights[key] // denominator
        for key in keys
    }
    remainder = total - sum(result.values())
    ranked = sorted(
        keys,
        key=lambda key: (
            -(total * weights[key] % denominator),
            order(key),
        ),
    )
    for key in ranked[:remainder]:
        result[key] += 1
    if sum(result.values()) != total:
        _fail("Hamilton allocation failed exact closure")
    return result


def _affine_parameters(normalized):
    if normalized["formula"]["formula_kind"] != "affine":
        return None
    complexity = normalized["complexity"]
    formula = normalized["formula"]["parameters"]
    minimum = complexity["inclusive_minimum"]
    maximum = complexity["inclusive_maximum"]
    base = formula.get(
        "base_bytes_at_minimum_complexity",
        formula.get("base_bytes_at_complexity_one"),
    )
    increment = formula.get("increment_bytes_per_additional_complexity")
    if any(type(value) is not int for value in (minimum, maximum, base, increment)):
        _fail("affine renderer contract lacks exact integer parameters")
    return minimum, maximum, base, increment


def _affine_bytes(affine, target_complexity):
    minimum, maximum, base, increment = affine
    if (
        type(target_complexity) is not int
        or not minimum <= target_complexity <= maximum
    ):
        _fail("affine complexity is outside its frozen domain")
    return base + increment * (target_complexity - minimum)


def _image_bytes(variant_id, width, height):
    if any(type(value) is not int for value in (width, height)):
        _fail("raster parameters must be exact integers")
    if variant_id == "bmp":
        return 62 + 4 * ((width + 31) // 32) * height
    if variant_id == "jpg":
        blocks = ((width + 7) // 8) * ((height + 7) // 8)
        return 154 + (blocks + 3) // 4
    if variant_id == "png":
        raw_length = (((width + 7) // 8) + 1) * height
        blocks = (raw_length + 65_534) // 65_535
        return 63 + raw_length + 5 * blocks
    if variant_id == "tif":
        return 110 + ((width + 7) // 8) * height
    _fail("unknown exact-expression raster variant")


def _media_bytes(variant_id, count):
    if type(count) is not int or not 1 <= count <= MAX_MEDIA_UNITS:
        _fail("media frame/event count is outside its frozen domain")
    if variant_id == "aiff":
        return 54 + count + (count & 1)
    if variant_id == "mid":
        return 27 + 3 * count
    if variant_id == "wav":
        return 44 + count + (count & 1)
    _fail("unknown exact-expression media variant")


def _raster_candidates(variant_id):
    rows = []
    for width in RASTER_DIMENSION_LATTICE:
        for height in RASTER_DIMENSION_LATTICE:
            pixels = width * height
            if not 4_096 <= pixels <= MAX_RASTER_PIXELS:
                continue
            if max(width, height) > MAX_RASTER_ASPECT_RATIO * min(width, height):
                continue
            rows.append(
                {
                    "exact_raw_bytes": _image_bytes(variant_id, width, height),
                    "renderer_parameters": {
                        "frame_or_event_count": 0,
                        "height": height,
                        "width": width,
                    },
                    "target_complexity": pixels,
                }
            )
    if not rows:
        _fail(f"raster lattice is empty for {variant_id}")
    return rows


def _media_count_at_most(variant_id, byte_cap):
    lower, upper = 1, MAX_MEDIA_UNITS
    while lower < upper:
        middle = (lower + upper + 1) // 2
        if _media_bytes(variant_id, middle) <= byte_cap:
            lower = middle
        else:
            upper = middle - 1
    return lower


def _media_count_at_least(variant_id, byte_floor):
    lower, upper = 1, MAX_MEDIA_UNITS
    while lower < upper:
        middle = (lower + upper) // 2
        if _media_bytes(variant_id, middle) >= byte_floor:
            upper = middle
        else:
            lower = middle + 1
    return lower


def _ordinary_and_tail_anchors(implementation_row):
    variant_id = implementation_row["variant_id"]
    family = implementation_row["family"]
    normalized = implementation_row["normalized_contract"]
    affine = _affine_parameters(normalized)
    ordinary = []
    tail = None

    if affine is not None:
        minimum, maximum, base, increment = affine
        floor_bytes = (
            FORMAL_ORDINARY_MIN_BYTES
            if family in {"image", "media", "domain_binary"}
            else base
        )
        floor_complexity = minimum
        if _affine_bytes(affine, floor_complexity) < floor_bytes:
            if increment <= 0:
                _fail(f"{variant_id} cannot reach its formal ordinary floor")
            needed = floor_bytes - _affine_bytes(affine, minimum)
            floor_complexity = minimum + (needed + increment - 1) // increment
        if floor_complexity > maximum:
            _fail(f"{variant_id} has no formal ordinary affine request")
        for bin_id in BIN_ORDER:
            if bin_id == "floor" or increment == 0:
                target = floor_complexity
            else:
                cap = ORDINARY_TARGET_CAPS[bin_id]
                target = minimum + (cap - base) // increment
                target = max(floor_complexity, min(maximum, target))
            raw_bytes = _affine_bytes(affine, target)
            if not 1 <= raw_bytes <= FORMAL_ORDINARY_MAX_BYTES:
                _fail(f"{variant_id}/{bin_id} leaves the ordinary byte lane")
            ordinary.append(
                {
                    "bin_id": bin_id,
                    "exact_raw_bytes": raw_bytes,
                    "renderer_parameters": {"target_complexity": target},
                    "size_lane": "formal-ordinary",
                    "target_complexity": target,
                }
            )
        maximum_bytes = _affine_bytes(affine, maximum)
        if variant_id in TAIL_CAPABLE_VARIANTS and maximum_bytes >= FORMAL_TAIL_MIN_BYTES:
            if increment <= 0:
                _fail(f"{variant_id} declares an unreachable tail")
            target = minimum + (TAIL_TARGET_CAP_BYTES - base) // increment
            target = min(maximum, max(minimum, target))
            raw_bytes = _affine_bytes(affine, target)
            if not FORMAL_TAIL_MIN_BYTES <= raw_bytes <= FORMAL_TAIL_MAX_BYTES:
                _fail(f"{variant_id} affine tail leaves the formal lane")
            tail = {
                "bin_id": "formal-tail",
                "exact_raw_bytes": raw_bytes,
                "renderer_parameters": {"target_complexity": target},
                "size_lane": "formal-tail",
                "target_complexity": target,
            }
    elif family == "image":
        candidates = _raster_candidates(variant_id)
        eligible = [
            row
            for row in candidates
            if FORMAL_ORDINARY_MIN_BYTES
            <= row["exact_raw_bytes"]
            <= FORMAL_ORDINARY_MAX_BYTES
        ]
        if not eligible:
            _fail(f"{variant_id} has no ordinary raster request")
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
                {
                    "bin_id": bin_id,
                    "exact_raw_bytes": selected["exact_raw_bytes"],
                    "renderer_parameters": copy.deepcopy(
                        selected["renderer_parameters"]
                    ),
                    "size_lane": "formal-ordinary",
                    "target_complexity": selected["target_complexity"],
                }
            )
        tail_candidates = [
            row
            for row in candidates
            if FORMAL_TAIL_MIN_BYTES
            <= row["exact_raw_bytes"]
            <= min(FORMAL_TAIL_MAX_BYTES, TAIL_TARGET_CAP_BYTES)
        ]
        if variant_id in TAIL_CAPABLE_VARIANTS:
            if not tail_candidates:
                _fail(f"{variant_id} declares no reachable raster tail")
            selected = max(
                tail_candidates,
                key=lambda row: (
                    row["exact_raw_bytes"],
                    row["target_complexity"],
                    -row["renderer_parameters"]["width"],
                    -row["renderer_parameters"]["height"],
                ),
            )
            tail = {
                "bin_id": "formal-tail",
                "exact_raw_bytes": selected["exact_raw_bytes"],
                "renderer_parameters": copy.deepcopy(
                    selected["renderer_parameters"]
                ),
                "size_lane": "formal-tail",
                "target_complexity": selected["target_complexity"],
            }
    elif family == "media":
        floor_count = _media_count_at_least(
            variant_id, FORMAL_ORDINARY_MIN_BYTES
        )
        for bin_id in BIN_ORDER:
            target = (
                floor_count
                if bin_id == "floor"
                else max(
                    floor_count,
                    _media_count_at_most(
                        variant_id, ORDINARY_TARGET_CAPS[bin_id]
                    ),
                )
            )
            raw_bytes = _media_bytes(variant_id, target)
            if not FORMAL_ORDINARY_MIN_BYTES <= raw_bytes <= FORMAL_ORDINARY_MAX_BYTES:
                _fail(f"{variant_id}/{bin_id} leaves the ordinary media lane")
            ordinary.append(
                {
                    "bin_id": bin_id,
                    "exact_raw_bytes": raw_bytes,
                    "renderer_parameters": {
                        "frame_or_event_count": target,
                        "height": 0,
                        "width": 0,
                    },
                    "size_lane": "formal-ordinary",
                    "target_complexity": target,
                }
            )
        target = _media_count_at_most(variant_id, TAIL_TARGET_CAP_BYTES)
        raw_bytes = _media_bytes(variant_id, target)
        if variant_id in TAIL_CAPABLE_VARIANTS:
            if not FORMAL_TAIL_MIN_BYTES <= raw_bytes <= FORMAL_TAIL_MAX_BYTES:
                _fail(f"{variant_id} media tail leaves the formal lane")
            tail = {
                "bin_id": "formal-tail",
                "exact_raw_bytes": raw_bytes,
                "renderer_parameters": {
                    "frame_or_event_count": target,
                    "height": 0,
                    "width": 0,
                },
                "size_lane": "formal-tail",
                "target_complexity": target,
            }
    else:
        _fail(f"unsupported renderer formula shape: {variant_id}")

    if len(ordinary) != len(BIN_ORDER):
        _fail(f"{variant_id} ordinary anchor cardinality drifted")
    if (tail is not None) != (variant_id in TAIL_CAPABLE_VARIANTS):
        _fail(f"{variant_id} tail capability drifted")
    return ordinary, tail


def _size_shape_profiles(marginals):
    personas = sorted({row["persona_id"] for row in marginals})
    families = sorted({row["family"] for row in marginals})
    persona_totals = {
        persona_id: sum(
            row["full_count"]
            for row in marginals
            if row["persona_id"] == persona_id
        )
        for persona_id in personas
    }
    family_totals = {
        (persona_id, family): sum(
            row["full_count"]
            for row in marginals
            if row["persona_id"] == persona_id and row["family"] == family
        )
        for persona_id in personas
        for family in families
    }
    result = {}
    for family in families:
        ranked = sorted(
            personas,
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
            result[persona_id, family] = tier
    return result


def _tail_allocations(marginals, anchors_by_variant):
    by_persona_variant = {
        (row["persona_id"], row["variant_id"]): row
        for row in marginals
    }
    personas = sorted({row["persona_id"] for row in marginals})
    result = {}
    for persona_id in personas:
        for origin, target, count_field in (
            ("pilot", TAIL_PILOT_PER_PERSONA, "pilot_count"),
            (
                "full-residual",
                TAIL_RESIDUAL_PER_PERSONA,
                "full_minus_pilot_count",
            ),
        ):
            eligible = [
                variant_id
                for variant_id in sorted(TAIL_CAPABLE_VARIANTS)
                if (persona_id, variant_id) in by_persona_variant
                and by_persona_variant[persona_id, variant_id][count_field] > 0
                and anchors_by_variant[variant_id][1] is not None
            ]
            weights = {
                variant_id: by_persona_variant[persona_id, variant_id][count_field]
                for variant_id in eligible
            }
            allocated = _hamilton(
                target,
                eligible,
                weights,
                order=lambda variant_id: variant_id.encode("ascii"),
            )
            for variant_id, count in allocated.items():
                if count > by_persona_variant[persona_id, variant_id][count_field]:
                    _fail("tail allocation exceeds its source marginal")
                result[persona_id, variant_id, origin] = count
    return result


def _summary(entries):
    # entry = (exact_raw_bytes, count, size_lane)
    count = sum(entry[1] for entry in entries)
    raw_sum = sum(entry[0] * entry[1] for entry in entries)
    block_sum = sum(
        ((entry[0] + ALLOCATION_QUANTUM_BYTES - 1) // ALLOCATION_QUANTUM_BYTES)
        * ALLOCATION_QUANTUM_BYTES
        * entry[1]
        for entry in entries
    )
    tail_count = sum(
        entry[1] for entry in entries if entry[2] == "formal-tail"
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
    ordered = sorted(entries, key=lambda entry: entry[0])

    def nearest_rank(numerator):
        rank = (count * numerator + 99) // 100
        cumulative = 0
        for raw_bytes, cell_count, _ in ordered:
            cumulative += cell_count
            if cumulative >= rank:
                return raw_bytes
        _fail("nearest-rank selection did not terminate")

    return {
        "block_rounded_payload_bytes": block_sum,
        "formal_tail_count": tail_count,
        "maximum_bytes": max(entry[0] for entry in entries if entry[1]),
        "nearest_rank_p50_bytes": nearest_rank(50),
        "nearest_rank_p95_bytes": nearest_rank(95),
        "raw_byte_sum": raw_sum,
        "source_count": count,
        "statistics_defined": True,
    }


def _row_entries(parameter_bins, profile):
    return [
        (
            row["exact_raw_bytes"],
            row["counts"][profile],
            row["size_lane"],
        )
        for row in parameter_bins
        if row["counts"][profile]
    ]


def _distribution_rows(variant_value, registry_value, formal_value):
    implementation_rows = {
        row["variant_id"]: row for row in registry_value["implementation_rows"]
    }
    formal_rows = {
        row["variant_id"]: row for row in formal_value["recipe_profile_rows"]
    }
    anchors = {
        variant_id: _ordinary_and_tail_anchors(row)
        for variant_id, row in implementation_rows.items()
    }
    marginals = variant_value["persona_variant_marginals"]
    shape_profiles = _size_shape_profiles(marginals)
    tails = _tail_allocations(marginals, anchors)
    rows = []
    for marginal in marginals:
        persona_id = marginal["persona_id"]
        family = marginal["family"]
        variant_id = marginal["variant_id"]
        implementation = implementation_rows[variant_id]
        formal = formal_rows[variant_id]
        if (
            implementation["family"] != family
            or formal["family"] != family
            or implementation["gate_role"] != formal["gate_role"]
        ):
            _fail(f"aggregate upstream join drifted: {persona_id}/{variant_id}")
        tier = shape_profiles[persona_id, family]
        weights = SIZE_SHAPE_WEIGHTS_BP[tier]
        ordinary, tail = anchors[variant_id]
        counts_by_bin = {
            row["bin_id"]: {profile: 0 for profile in PROFILE_ORDER}
            for row in ordinary
        }
        if tail is not None:
            counts_by_bin["formal-tail"] = {
                profile: 0 for profile in PROFILE_ORDER
            }
        for origin, count_field in (
            ("pilot", "pilot_count"),
            ("full-residual", "full_minus_pilot_count"),
        ):
            total = marginal[count_field]
            tail_count = tails.get((persona_id, variant_id, origin), 0)
            ordinary_total = total - tail_count
            if ordinary_total < 0:
                _fail("tail reservation exceeds its marginal")
            allocated = _hamilton(
                ordinary_total,
                BIN_ORDER,
                {
                    bin_id: weights[index]
                    for index, bin_id in enumerate(BIN_ORDER)
                },
                order=BIN_ORDER.index,
            )
            for bin_id, count in allocated.items():
                counts_by_bin[bin_id][origin] = count
            if tail_count:
                if tail is None:
                    _fail("tail allocated to a non-tail-capable variant")
                counts_by_bin["formal-tail"][origin] = tail_count
        parameter_bins = []
        for anchor in ordinary + ([tail] if tail is not None else []):
            counts = counts_by_bin[anchor["bin_id"]]
            counts["full"] = counts["pilot"] + counts["full-residual"]
            parameter_bins.append({**copy.deepcopy(anchor), "counts": counts})
        summaries = {
            profile: _summary(_row_entries(parameter_bins, profile))
            for profile in PROFILE_ORDER
        }
        source_counts = {
            "full": marginal["full_count"],
            "full-residual": marginal["full_minus_pilot_count"],
            "pilot": marginal["pilot_count"],
        }
        if any(
            summaries[profile]["source_count"] != source_counts[profile]
            for profile in PROFILE_ORDER
        ):
            _fail(f"aggregate row count did not close: {persona_id}/{variant_id}")
        rows.append(
            {
                "family": family,
                "gate_role": implementation["gate_role"],
                "implementation_profile_id": implementation["implementation"][
                    "implementation_profile_id"
                ],
                "parameter_bins": parameter_bins,
                "persona_id": persona_id,
                "recipe_profile_id": formal["recipe_profile_id"],
                "size_shape_profile_id": f"persona-v2-{tier}-byte-shape-v2",
                "source_counts": source_counts,
                "summaries": summaries,
                "variant_id": variant_id,
            }
        )
    if len(rows) != EXPECTED_PERSONA_VARIANT_ROWS:
        _fail("persona/variant aggregate row cardinality drifted")
    return rows, anchors, shape_profiles


def _merged_summary(rows, profile):
    entries = []
    for row in rows:
        entries.extend(_row_entries(row["parameter_bins"], profile))
    return _summary(entries)


def _projections(rows):
    personas = sorted({row["persona_id"] for row in rows})
    families = sorted({row["family"] for row in rows})
    family_rows = []
    for persona_id in personas:
        for family in families:
            selected = [
                row
                for row in rows
                if row["persona_id"] == persona_id and row["family"] == family
            ]
            family_rows.append(
                {
                    "family": family,
                    "persona_id": persona_id,
                    "source_counts": {
                        profile: sum(
                            row["source_counts"][profile] for row in selected
                        )
                        for profile in PROFILE_ORDER
                    },
                    "summaries": {
                        profile: _merged_summary(selected, profile)
                        for profile in PROFILE_ORDER
                    },
                    "variant_row_count": len(selected),
                }
            )
    if len(family_rows) != EXPECTED_PERSONA_FAMILY_ROWS:
        _fail("persona/family projection cardinality drifted")
    persona_rows = []
    for persona_id in personas:
        selected = [row for row in rows if row["persona_id"] == persona_id]
        summary = {
            "persona_id": persona_id,
            "source_counts": {
                profile: sum(row["source_counts"][profile] for row in selected)
                for profile in PROFILE_ORDER
            },
            "summaries": {
                profile: _merged_summary(selected, profile)
                for profile in PROFILE_ORDER
            },
            "variant_row_count": len(selected),
        }
        full_blocks = summary["summaries"]["full"][
            "block_rounded_payload_bytes"
        ]
        summary["capacity_check"] = {
            "candidate_cap_bytes": PERSONA_CANDIDATE_CAP_BYTES,
            "hard_block_rounded_cap_bytes": PERSONA_BLOCK_ROUNDED_CAP_BYTES,
            "minimum_margin_bytes": PERSONA_REQUIRED_MARGIN_BYTES,
            "passes_hard_cap": full_blocks <= PERSONA_BLOCK_ROUNDED_CAP_BYTES,
            "remaining_candidate_margin_bytes": (
                PERSONA_CANDIDATE_CAP_BYTES - full_blocks
            ),
        }
        if not summary["capacity_check"]["passes_hard_cap"]:
            _fail(f"{persona_id} exceeds the 480 MiB block-rounded hard cap")
        persona_rows.append(summary)
    if len(persona_rows) != EXPECTED_PERSONAS:
        _fail("persona summary cardinality drifted")
    suite = {
        "capacity_check": {
            "hard_block_rounded_cap_bytes": SUITE_BLOCK_ROUNDED_CAP_BYTES,
            "passes_hard_cap": False,
            "remaining_margin_bytes": 0,
        },
        "persona_count": len(personas),
        "source_counts": {
            profile: sum(row["source_counts"][profile] for row in rows)
            for profile in PROFILE_ORDER
        },
        "summaries": {
            profile: _merged_summary(rows, profile) for profile in PROFILE_ORDER
        },
        "variant_row_count": len(rows),
    }
    suite_blocks = suite["summaries"]["full"]["block_rounded_payload_bytes"]
    suite["capacity_check"] = {
        "hard_block_rounded_cap_bytes": SUITE_BLOCK_ROUNDED_CAP_BYTES,
        "passes_hard_cap": suite_blocks <= SUITE_BLOCK_ROUNDED_CAP_BYTES,
        "remaining_margin_bytes": SUITE_BLOCK_ROUNDED_CAP_BYTES - suite_blocks,
    }
    if not suite["capacity_check"]["passes_hard_cap"]:
        _fail("suite exceeds the 10 GiB block-rounded hard cap")
    return family_rows, persona_rows, suite


def _parameter_bin_probe_receipts(anchors, renderer_provider, validator_provider):
    receipts = []
    for variant_id in sorted(anchors):
        ordinary, tail = anchors[variant_id]
        selected = list(ordinary)
        if tail is not None:
            selected.append(tail)
        for anchor in selected:
            parameters = copy.deepcopy(anchor["renderer_parameters"])
            rendered = renderer_provider(variant_id, parameters)
            if type(rendered) is not dict or type(rendered.get("data")) is not bytes:
                _fail("parameter-bin renderer provider returned an invalid payload")
            data = rendered["data"]
            if (
                rendered.get("target_bytes") != len(data)
                or rendered.get("target_bytes") != anchor["exact_raw_bytes"]
                or rendered.get("target_complexity") != anchor["target_complexity"]
            ):
                _fail(f"parameter-bin renderer result drifted: {variant_id}")
            validator_receipt = validator_provider(
                variant_id, parameters, rendered
            )
            receipt_raw = _canonical_fragment(
                validator_receipt,
                label="aggregate parameter-bin validator receipt",
            )
            native = (
                validator_receipt.get("native_receipt")
                if type(validator_receipt) is dict
                else None
            )
            if (
                type(native) is not dict
                or native.get(
                    "observed_local_complexity",
                    native.get("observed_complexity"),
                )
                != anchor["target_complexity"]
                or native.get("target_bytes") != len(data)
            ):
                _fail("parameter-bin validator receipt is not payload-bound")
            receipts.append(
                {
                    "bin_id": anchor["bin_id"],
                    "payload_sha256": hashlib.sha256(data).hexdigest(),
                    "renderer_parameters": parameters,
                    "target_bytes": len(data),
                    "target_complexity": anchor["target_complexity"],
                    "validator_accepted": True,
                    "validator_receipt_sha256": hashlib.sha256(
                        receipt_raw
                    ).hexdigest(),
                    "variant_id": variant_id,
                }
            )
    if len(receipts) != EXPECTED_PROBE_RECEIPTS:
        _fail("parameter-bin runtime probe cardinality drifted")
    return receipts


def _canonical_catalog():
    variant_value = variant_catalog.build_variant_catalog()
    registry_value = implementation_registry.build_format_implementation_registry()
    formal_value = formal_catalog.build_formal_source_recipe_catalog()
    realism_value = realism_profile.build_realism_profile()
    bindings = [
        _artifact_binding(
            "persona-v2-variant-catalog",
            "persona-variant-source-count-and-formal-lane-owner",
            variant_value,
            canonical=variant_catalog.canonical_json_bytes,
            validate=variant_catalog.validate_variant_catalog,
        ),
        _artifact_binding(
            "persona-v2-format-implementation-registry",
            "all-71-renderer-formula-and-runtime-contract-owner",
            registry_value,
            canonical=implementation_registry.canonical_json_bytes,
            validate=implementation_registry.validate_format_implementation_registry,
        ),
        _artifact_binding(
            "persona-v2-formal-source-recipe-profile-catalog",
            "formal-recipe-profile-and-lane-policy-owner",
            formal_value,
            canonical=formal_catalog.canonical_json_bytes,
            validate=formal_catalog.validate_formal_source_recipe_catalog,
        ),
        _artifact_binding(
            "persona-v2-realism-profile",
            "persona-role-and-full-denominator-owner",
            realism_value,
            canonical=realism_profile.canonical_json_bytes,
            validate=realism_profile.validate_realism_profile,
        ),
    ]
    rows, anchors, shape_profiles = _distribution_rows(
        variant_value, registry_value, formal_value
    )
    family_rows, persona_rows, suite = _projections(rows)
    renderer_provider, validator_provider = implementation_registry._probe_providers()
    probe_receipts = _parameter_bin_probe_receipts(
        anchors, renderer_provider, validator_provider
    )
    return {
        "allocation_model": {
            "actual_filesystem_allocation_attested": False,
            "block_rounded_formula": "sum(count*ceil(raw-bytes/4096)*4096)",
            "candidate_persona_cap_bytes": PERSONA_CANDIDATE_CAP_BYTES,
            "filesystem_metadata_bytes_included": False,
            "hard_persona_block_rounded_cap_bytes": (
                PERSONA_BLOCK_ROUNDED_CAP_BYTES
            ),
            "hard_suite_block_rounded_cap_bytes": SUITE_BLOCK_ROUNDED_CAP_BYTES,
            "model_id": "persona-v2-4096-byte-regular-file-roundup-v2",
            "planning_allocation_quantum_bytes": ALLOCATION_QUANTUM_BYTES,
            "required_persona_margin_bytes": PERSONA_REQUIRED_MARGIN_BYTES,
            "root_bound_capacity_projection": False,
        },
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_integer_bits": 127,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "aggregate_full_equals_pilot_plus_residual": True,
            "all_566_persona_variant_histograms_complete": True,
            "all_parameter_bins_runtime_validated": True,
            "all_source_instance_parameters_bound": False,
            "exact_300_persona_family_projections_complete": True,
            "exact_20_persona_and_suite_summaries_complete": True,
            "filesystem_allocation_attested": False,
            "all_parameter_bin_runtime_probes_complete": True,
            "source_instances_bound": False,
        },
        "completion_scope": (
            "exact-aggregate-persona-variant-byte-histograms-only-no-source-"
            "instances-no-scope-allocation-no-render-write-history-kcs-or-g0"
        ),
        "distribution_policy": {
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
            "renderer_floor_fallback_when_target_below_minimum": True,
            "persona_family_shape_assignment": (
                "per-family-exact-full-share-rank-bottom-five-compact-middle-"
                "ten-standard-top-five-heavy-persona-id-tie-break"
            ),
            "raster_dimension_lattice": list(RASTER_DIMENSION_LATTICE),
            "raster_max_aspect_ratio": MAX_RASTER_ASPECT_RATIO,
            "raster_max_pixels": MAX_RASTER_PIXELS,
            "raster_min_pixels": 4_096,
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
            "tail_capable_variants": sorted(TAIL_CAPABLE_VARIANTS),
            "tail_full_per_persona": TAIL_FULL_PER_PERSONA,
            "tail_max_per_persona": TAIL_MAX_PER_PERSONA,
            "tail_pilot_per_persona": TAIL_PILOT_PER_PERSONA,
            "tail_residual_per_persona": TAIL_RESIDUAL_PER_PERSONA,
            "tail_target_cap_bytes": TAIL_TARGET_CAP_BYTES,
        },
        "fixture_id": variant_value["fixture_id"],
        "fixture_schema_version": variant_value["fixture_schema_version"],
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
        "orders": {
            "parameter_bins": "five-ordinary-bin-order-then-optional-formal-tail",
            "persona_family_projection_rows": "persona-id-then-family-ascii",
            "persona_summaries": "persona-id",
            "persona_variant_rows": "exact-upstream-marginal-order",
            "parameter_bin_probe_receipts": (
                "variant-id-then-five-ordinary-bin-order-then-tail"
            ),
        },
        "persona_family_projection_rows": family_rows,
        "persona_summaries": persona_rows,
        "persona_variant_rows": rows,
        "remaining_blockers": [
            "203000-source-instance-parameter-expansion-and-identities-unbound",
            "scope-bucket-cohort-quota-solution-and-proof-unbound",
            "w1-w5-history-byte-amplification-and-transient-peak-unbound",
            "actual-filesystem-allocation-cas-index-and-root-capacity-unbound",
            "physical-render-write-history-kcs-and-g0-authority-absent",
        ],
        "parameter_bin_probe_receipts": probe_receipts,
        "suite_summary": suite,
    }


@functools.lru_cache(maxsize=1)
def _cached_catalog():
    value = _canonical_catalog()
    canonical_json_bytes(value)
    return value


def build_aggregate_byte_distribution_catalog():
    """Return a detached aggregate-only byte-distribution catalog."""

    return copy.deepcopy(_cached_catalog())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 aggregate byte distribution catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2AggregateByteDistributionCatalogError(str(error)) from None


def validate_aggregate_byte_distribution_catalog(value):
    try:
        artifact_common.validate_exact_regeneration(
            value,
            builder=build_aggregate_byte_distribution_catalog,
            label="persona v2 aggregate byte distribution catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2AggregateByteDistributionCatalogError(str(error)) from None
    variant_value = variant_catalog.build_variant_catalog()
    registry_value = implementation_registry.build_format_implementation_registry()
    formal_value = formal_catalog.build_formal_source_recipe_catalog()
    realism_value = realism_profile.build_realism_profile()
    inventory_value = inventory_catalog.build_source_inventory_profile_catalog()
    historical_value = historical_catalog.build_source_profile_catalog()
    semantic_value = formal_catalog._source_semantic_catalog_dependency()
    renderer_contract_provider, validator_contract_provider = (
        implementation_registry._contract_providers()
    )
    renderer_probe_provider, validator_probe_provider = (
        implementation_registry._probe_providers()
    )
    try:
        independent.validate_aggregate_byte_distribution_catalog(
            value,
            variant_catalog_value=variant_value,
            format_implementation_registry_value=registry_value,
            formal_source_recipe_catalog_value=formal_value,
            realism_profile_value=realism_value,
            historical_source_profile_value=historical_value,
            source_inventory_profile_value=inventory_value,
            source_semantic_membership_catalog_value=semantic_value,
            renderer_contract_provider=renderer_contract_provider,
            validator_contract_provider=validator_contract_provider,
            renderer_probe_provider=renderer_probe_provider,
            selected_renderer_probe_provider=renderer_probe_provider,
            selected_validator_probe_provider=validator_probe_provider,
        )
    except independent.PersonaV2AggregateByteDistributionCatalogValidationError as error:
        raise PersonaV2AggregateByteDistributionCatalogError(str(error)) from None
    return True


def aggregate_byte_distribution_catalog_sha256(value=None):
    if value is None:
        value = build_aggregate_byte_distribution_catalog()
    validate_aggregate_byte_distribution_catalog(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "MAX_CATALOG_BYTES",
    "PersonaV2AggregateByteDistributionCatalogError",
    "aggregate_byte_distribution_catalog_sha256",
    "build_aggregate_byte_distribution_catalog",
    "canonical_json_bytes",
    "validate_aggregate_byte_distribution_catalog",
]
