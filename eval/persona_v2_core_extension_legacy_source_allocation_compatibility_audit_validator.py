"""Independent validator for the core-versus-legacy allocation count audit.

The audit is deliberately diagnostic and non-authorizing.  It compares the
frozen 566-row ``persona-core-v1`` allocation with the legacy v2 variant
marginals at the same persona/family/variant coordinates.  A mismatch is the
expected current result, not a validator failure; malformed inputs, changed
pins, or a descriptor that hides the mismatch fail closed.
"""

from __future__ import annotations

import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_core_extension_allocation_manifest_validator as core_independent
    from . import persona_v2_variant_catalog as legacy_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_core_extension_allocation_manifest_validator as core_independent
    import persona_v2_variant_catalog as legacy_catalog


ARTIFACT_SCHEMA = (
    "kio.persona.pc-core-extension-legacy-source-allocation-compatibility-audit/v1"
)
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-core-extension-legacy-source-allocation-compatibility-audit"
ARTIFACT_ID = "persona-core-v1-legacy-source-allocation-compatibility-audit-v1"
BODY_ID = "persona-core-v1-legacy-source-allocation-delta-rows-v1"
DELTA_ROW_SCHEMA = (
    "kio.persona.pc-core-extension-legacy-source-allocation-delta-row/v1"
)
PROFILE_ID = "persona-core-v1"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2

MAX_DESCRIPTOR_BYTES = 128 * 2**10
MAX_DELTA_BODY_BYTES = 512 * 2**10
MAX_DELTA_ROW_BYTES_INCLUDING_LF = 2 * 2**10
MAX_INPUT_CATALOG_BYTES = 2 * 2**20

CORE_DESCRIPTOR_BYTES = 5_357
CORE_DESCRIPTOR_SHA256 = (
    "f5b63b30fa06fb230d4b58574390f0f99e2402d2b8af12e137d63406777a0436"
)
CORE_BODY_BYTES = 426_889
CORE_BODY_SHA256 = (
    "a45af96c53035133fb693021a3e8134105f04f6439f91db51f3d51e0cffefcf5"
)
CORE_ARTIFACT_ID = "persona-core-v1-extension-allocation-manifest-v1"
CORE_BODY_ID = "persona-core-v1-extension-allocation-rows-v1"
CORE_ARTIFACT_SCHEMA = "kio.persona.core-extension-allocation-manifest/v1"
CORE_ARTIFACT_KIND = "persona-core-v1-extension-allocation-manifest-candidate"

LEGACY_CATALOG_BYTES = 211_733
LEGACY_CATALOG_SHA256 = (
    "807dd3cdd8df613ac21e6ba64877fb5abb40c72ed4949abaa0d440a449e7f9e9"
)
LEGACY_CATALOG_SCHEMA = "kio.persona.pc-variant-catalog/v2"
LEGACY_CATALOG_KIND = "persona-pc-v2-variant-catalog"

PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, 21))
FAMILY_ORDER = (
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

EXPECTED_COORDINATE_COUNT = 566
EXPECTED_FULL_TOTAL = 203_000
EXPECTED_PILOT_TOTAL = 20_300
EXPECTED_FULL_MISMATCH_COUNT = 489
EXPECTED_PILOT_MISMATCH_COUNT = 483
EXPECTED_UNION_MISMATCH_COUNT = 489
EXPECTED_FULL_ONLY_MISMATCH_COUNT = 6
EXPECTED_PILOT_ONLY_MISMATCH_COUNT = 0
EXPECTED_FULL_L1_DELTA = 70_500
EXPECTED_PILOT_L1_DELTA = 7_050

# Filled only after producer and independent-validator replay agree.  The
# candidate remains non-authorizing even when both pairs are configured.
EXPECTED_CANONICAL_BYTES = 3_500
EXPECTED_SHA256 = "f2eb954e5d097cd41ed5cd7f92904b9987f6b08eb5532a9587ea6bd6043a27b1"
EXPECTED_BODY_CANONICAL_BYTES = 236_068
EXPECTED_BODY_SHA256 = "ff2f50a342e92e8b43c4d743811ee7bddd6772c20c6e2cf0530ee160ca0385dd"

AUTHORITY_FIELDS = frozenset(
    {
        "authorizes_allocation_adoption",
        "authorizes_evaluation",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_namespace_admission",
        "authorizes_physical_write",
        "authorizes_solver_execution",
        "authorizes_source_inventory_supersession",
        "authorizes_source_plan",
    }
)

DESCRIPTOR_FIELDS = frozenset(
    {
        "artifact_id",
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "comparison_contract",
        "completion_claims",
        "core_allocation_binding",
        "delta_body",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "legacy_variant_catalog_binding",
        "profile_id",
        "result",
        "summary",
    }
)
CORE_ROW_FIELDS = frozenset(
    {
        "schema_version",
        "row_schema",
        "row_id",
        "profile_id",
        "persona_id",
        "family_id",
        "family_ordinal",
        "variant_id",
        "variant_ordinal",
        "variant_weight",
        "filename_extension",
        "compound_suffix_parts",
        "gate_role",
        "expected_offline_disposition",
        "family_full_count",
        "full_count",
        "family_pilot_count",
        "pilot_count",
        "family_tiny_count",
        "tiny_count",
        "renderer_binding_id",
        "validator_binding_id",
        "format_registry_sha256",
    }
)
LEGACY_MARGINAL_FIELDS = frozenset(
    {
        "family",
        "full_count",
        "full_minus_pilot_count",
        "persona_id",
        "pilot_count",
        "ratio_pct",
        "tiny_smoke_count",
        "variant_id",
    }
)
DELTA_ROW_FIELDS = frozenset(
    {
        "core_full_count",
        "core_pilot_count",
        "family_id",
        "full_delta_abs",
        "full_delta_direction",
        "full_equal",
        "legacy_full_count",
        "legacy_pilot_count",
        "persona_id",
        "pilot_delta_abs",
        "pilot_delta_direction",
        "pilot_equal",
        "profile_id",
        "row_id",
        "row_schema",
        "variant_id",
    }
)
_GOLDEN_NOT_PROVIDED = object()


class PersonaV2CoreExtensionLegacyAllocationCompatibilityAuditValidationError(ValueError):
    """Raised when the count-only audit differs from exact regeneration."""


def _fail(message):
    raise PersonaV2CoreExtensionLegacyAllocationCompatibilityAuditValidationError(
        message
    )


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value, *, label, maximum):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=maximum
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _parse_canonical_object(raw, *, label, maximum):
    if type(raw) is not bytes or len(raw) > maximum:
        _fail(f"{label} must be bounded exact bytes")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{label} cannot be parsed: {type(error).__name__}")
    if _canonical(value, label=label, maximum=maximum) != raw:
        _fail(f"{label} is not canonical JSON")
    return value


def _expected_golden():
    descriptor_set = EXPECTED_CANONICAL_BYTES is not None
    digest_set = EXPECTED_SHA256 is not None
    body_set = EXPECTED_BODY_CANONICAL_BYTES is not None
    body_digest_set = EXPECTED_BODY_SHA256 is not None
    if descriptor_set != digest_set or body_set != body_digest_set:
        _fail("audit golden configuration must be paired")
    if descriptor_set != body_set:
        _fail("audit descriptor/body goldens must be configured together")
    if not descriptor_set:
        return None
    values = (
        (EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256, MAX_DESCRIPTOR_BYTES),
        (EXPECTED_BODY_CANONICAL_BYTES, EXPECTED_BODY_SHA256, MAX_DELTA_BODY_BYTES),
    )
    for byte_count, digest, maximum in values:
        if (
            type(byte_count) is not int
            or type(byte_count) is bool
            or not 1 <= byte_count <= maximum
            or type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            _fail("audit golden configuration is invalid")
    return (
        EXPECTED_CANONICAL_BYTES,
        EXPECTED_SHA256,
        EXPECTED_BODY_CANONICAL_BYTES,
        EXPECTED_BODY_SHA256,
    )


def _require_producer_golden_parity(producer_expected):
    expected = _expected_golden()
    if producer_expected is _GOLDEN_NOT_PROVIDED:
        _fail("producer audit goldens were not supplied")
    if type(producer_expected) is not type(expected) or producer_expected != expected:
        _fail("producer and validator audit goldens differ")
    return expected


def _read_object_provider_twice(provider, *, label, maximum):
    if not callable(provider):
        _fail(f"{label} provider must be callable")
    first_raw = _canonical(provider(), label=f"{label} first read", maximum=maximum)
    second_raw = _canonical(provider(), label=f"{label} second read", maximum=maximum)
    first = _parse_canonical_object(first_raw, label=f"{label} first read", maximum=maximum)
    second = _parse_canonical_object(second_raw, label=f"{label} second read", maximum=maximum)
    if first_raw != second_raw:
        _fail(f"{label} provider changed between reads")
    return second, second_raw


def _require_catalog(value, raw):
    if (
        len(raw) != LEGACY_CATALOG_BYTES
        or not hmac.compare_digest(_sha256(raw), LEGACY_CATALOG_SHA256)
    ):
        _fail("legacy variant catalog differs from its frozen candidate pin")
    if (
        type(value) is not dict
        or value.get("artifact_schema") != LEGACY_CATALOG_SCHEMA
        or value.get("artifact_schema_version") != 2
        or value.get("artifact_kind") != LEGACY_CATALOG_KIND
        or value.get("fixture_id") != FIXTURE_ID
        or value.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
    ):
        _fail("legacy variant catalog identity drifted")
    try:
        legacy_catalog.validate_variant_catalog(value)
    except legacy_catalog.PersonaV2VariantCatalogError as error:
        _fail(str(error))
    return value


def _accepted_core_rows(descriptor, *, core_body_provider):
    if (
        type(descriptor) is not dict
        or _canonical(
            descriptor,
            label="core allocation descriptor",
            maximum=MAX_DESCRIPTOR_BYTES,
        )
        != _canonical(
            descriptor,
            label="core allocation descriptor replay",
            maximum=MAX_DESCRIPTOR_BYTES,
        )
    ):
        _fail("core allocation descriptor is not stable")
    descriptor_raw = _canonical(
        descriptor, label="core allocation descriptor", maximum=MAX_DESCRIPTOR_BYTES
    )
    if (
        len(descriptor_raw) != CORE_DESCRIPTOR_BYTES
        or not hmac.compare_digest(_sha256(descriptor_raw), CORE_DESCRIPTOR_SHA256)
        or descriptor.get("artifact_id") != CORE_ARTIFACT_ID
        or descriptor.get("artifact_schema") != CORE_ARTIFACT_SCHEMA
        or descriptor.get("artifact_kind") != CORE_ARTIFACT_KIND
    ):
        _fail("core allocation descriptor differs from its frozen candidate pin")
    if not callable(core_body_provider):
        _fail("core allocation body provider must be callable")
    try:
        body = core_independent.accepted_core_extension_allocation_body_bytes(
            descriptor,
            producer_expected_golden=(CORE_DESCRIPTOR_BYTES, CORE_DESCRIPTOR_SHA256),
            body_provider=core_body_provider,
        )
    except core_independent.PersonaV2CoreExtensionAllocationManifestValidationError as error:
        _fail(str(error))
    if (
        type(body) is not bytes
        or len(body) != CORE_BODY_BYTES
        or not hmac.compare_digest(_sha256(body), CORE_BODY_SHA256)
        or not body.endswith(b"\n")
        or b"\r" in body
    ):
        _fail("core allocation body differs from its frozen candidate pin")
    rows = []
    for ordinal, line in enumerate(body.splitlines(keepends=True)):
        if not line.endswith(b"\n"):
            _fail("core allocation body framing drifted")
        try:
            row = json.loads(
                line[:-1].decode("utf-8", "strict"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_float=_reject_float,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            _fail(f"core allocation row {ordinal} is invalid: {type(error).__name__}")
        if (
            type(row) is not dict
            or set(row) != CORE_ROW_FIELDS
            or _canonical(
                row,
                label="core allocation row",
                maximum=MAX_DELTA_ROW_BYTES_INCLUDING_LF,
            )
            + b"\n"
            != line
        ):
            _fail("core allocation row canonical schema drifted")
        rows.append(row)
    if len(rows) != EXPECTED_COORDINATE_COUNT:
        _fail("core allocation coordinate count drifted")
    return rows, body


def _exact_nonnegative_int(value, *, label):
    if (
        type(value) is not int
        or type(value) is bool
        or value < 0
        or value > artifact_common.MAX_INTEGER_MAGNITUDE
    ):
        _fail(f"{label} must be a bounded non-boolean non-negative integer")
    return value


def _exact_text(value, *, label):
    if type(value) is not str or not value:
        _fail(f"{label} must be a non-empty exact string")
    _canonical(value, label=label, maximum=8 * 2**10)
    return value


def _direction(delta):
    if delta == 0:
        return "equal"
    return "core-greater" if delta > 0 else "legacy-greater"


def _derive(core_rows, catalog):
    family_index = {family_id: ordinal for ordinal, family_id in enumerate(FAMILY_ORDER)}
    if len(family_index) != len(FAMILY_ORDER):
        _fail("family order contains duplicates")
    core_by_coordinate = {}
    for row in core_rows:
        if row.get("profile_id") != PROFILE_ID:
            _fail("core allocation profile drifted")
        persona_id = _exact_text(row.get("persona_id"), label="core persona ID")
        family_id = _exact_text(row.get("family_id"), label="core family ID")
        variant_id = _exact_text(row.get("variant_id"), label="core variant ID")
        if persona_id not in PERSONA_IDS or family_id not in family_index:
            _fail("core allocation coordinate universe drifted")
        for field in ("full_count", "pilot_count", "tiny_count"):
            _exact_nonnegative_int(row.get(field), label=f"core {field}")
        if row["pilot_count"] > row["full_count"]:
            _fail("core pilot count exceeds full count")
        key = (persona_id, family_id, variant_id)
        if key in core_by_coordinate:
            _fail("core allocation coordinate is duplicated")
        core_by_coordinate[key] = row
    if len(core_by_coordinate) != EXPECTED_COORDINATE_COUNT:
        _fail("core allocation coordinate universe is incomplete")

    marginals = catalog.get("persona_variant_marginals")
    if type(marginals) is not list or len(marginals) != EXPECTED_COORDINATE_COUNT:
        _fail("legacy marginal coordinate count drifted")
    legacy_by_coordinate = {}
    for row in marginals:
        if type(row) is not dict or set(row) != LEGACY_MARGINAL_FIELDS:
            _fail("legacy marginal row schema drifted")
        persona_id = _exact_text(row.get("persona_id"), label="legacy persona ID")
        family_id = _exact_text(row.get("family"), label="legacy family ID")
        variant_id = _exact_text(row.get("variant_id"), label="legacy variant ID")
        if persona_id not in PERSONA_IDS or family_id not in family_index:
            _fail("legacy marginal coordinate universe drifted")
        full_count = _exact_nonnegative_int(row.get("full_count"), label="legacy full count")
        pilot_count = _exact_nonnegative_int(row.get("pilot_count"), label="legacy pilot count")
        residual = _exact_nonnegative_int(
            row.get("full_minus_pilot_count"), label="legacy full minus pilot"
        )
        if pilot_count > full_count or residual != full_count - pilot_count:
            _fail("legacy marginal count arithmetic drifted")
        key = (persona_id, family_id, variant_id)
        if key in legacy_by_coordinate:
            _fail("legacy marginal coordinate is duplicated")
        legacy_by_coordinate[key] = row
    if set(core_by_coordinate) != set(legacy_by_coordinate):
        _fail("core and legacy coordinate universes differ")

    order = lambda key: (int(key[0][1:]), family_index[key[1]], key[2].encode("ascii"))
    full_mismatch = pilot_mismatch = union_mismatch = 0
    full_only = pilot_only = full_l1 = pilot_l1 = 0
    core_full_total = legacy_full_total = core_pilot_total = legacy_pilot_total = 0
    rows = []
    for persona_id, family_id, variant_id in sorted(core_by_coordinate, key=order):
        key = (persona_id, family_id, variant_id)
        core = core_by_coordinate[key]
        legacy = legacy_by_coordinate[key]
        full_delta = core["full_count"] - legacy["full_count"]
        pilot_delta = core["pilot_count"] - legacy["pilot_count"]
        full_equal = full_delta == 0
        pilot_equal = pilot_delta == 0
        full_mismatch += int(not full_equal)
        pilot_mismatch += int(not pilot_equal)
        union_mismatch += int(not full_equal or not pilot_equal)
        full_only += int(not full_equal and pilot_equal)
        pilot_only += int(full_equal and not pilot_equal)
        full_l1 += abs(full_delta)
        pilot_l1 += abs(pilot_delta)
        core_full_total += core["full_count"]
        legacy_full_total += legacy["full_count"]
        core_pilot_total += core["pilot_count"]
        legacy_pilot_total += legacy["pilot_count"]
        if not full_equal or not pilot_equal:
            rows.append(
                {
                    "row_schema": DELTA_ROW_SCHEMA,
                    "row_id": (
                        "core-vs-legacy-allocation-"
                        f"{persona_id}-{family_id}-{variant_id}"
                    ),
                    "profile_id": PROFILE_ID,
                    "persona_id": persona_id,
                    "family_id": family_id,
                    "variant_id": variant_id,
                    "core_full_count": core["full_count"],
                    "legacy_full_count": legacy["full_count"],
                    "full_delta_abs": abs(full_delta),
                    "full_delta_direction": _direction(full_delta),
                    "full_equal": full_equal,
                    "core_pilot_count": core["pilot_count"],
                    "legacy_pilot_count": legacy["pilot_count"],
                    "pilot_delta_abs": abs(pilot_delta),
                    "pilot_delta_direction": _direction(pilot_delta),
                    "pilot_equal": pilot_equal,
                }
            )
    summary = {
        "coordinate_count": len(core_by_coordinate),
        "core_full_total": core_full_total,
        "core_pilot_total": core_pilot_total,
        "full_equal_coordinate_count": len(core_by_coordinate) - full_mismatch,
        "full_l1_delta": full_l1,
        "full_mismatch_coordinate_count": full_mismatch,
        "full_only_mismatch_coordinate_count": full_only,
        "legacy_full_total": legacy_full_total,
        "legacy_pilot_total": legacy_pilot_total,
        "pilot_equal_coordinate_count": len(core_by_coordinate) - pilot_mismatch,
        "pilot_l1_delta": pilot_l1,
        "pilot_mismatch_coordinate_count": pilot_mismatch,
        "pilot_only_mismatch_coordinate_count": pilot_only,
        "union_mismatch_coordinate_count": union_mismatch,
    }
    expected = {
        "coordinate_count": EXPECTED_COORDINATE_COUNT,
        "core_full_total": EXPECTED_FULL_TOTAL,
        "core_pilot_total": EXPECTED_PILOT_TOTAL,
        "full_equal_coordinate_count": EXPECTED_COORDINATE_COUNT - EXPECTED_FULL_MISMATCH_COUNT,
        "full_l1_delta": EXPECTED_FULL_L1_DELTA,
        "full_mismatch_coordinate_count": EXPECTED_FULL_MISMATCH_COUNT,
        "full_only_mismatch_coordinate_count": EXPECTED_FULL_ONLY_MISMATCH_COUNT,
        "legacy_full_total": EXPECTED_FULL_TOTAL,
        "legacy_pilot_total": EXPECTED_PILOT_TOTAL,
        "pilot_equal_coordinate_count": EXPECTED_COORDINATE_COUNT - EXPECTED_PILOT_MISMATCH_COUNT,
        "pilot_l1_delta": EXPECTED_PILOT_L1_DELTA,
        "pilot_mismatch_coordinate_count": EXPECTED_PILOT_MISMATCH_COUNT,
        "pilot_only_mismatch_coordinate_count": EXPECTED_PILOT_ONLY_MISMATCH_COUNT,
        "union_mismatch_coordinate_count": EXPECTED_UNION_MISMATCH_COUNT,
    }
    if summary != expected or len(rows) != EXPECTED_UNION_MISMATCH_COUNT:
        _fail("core-versus-legacy allocation comparison baseline drifted")
    return rows, summary


def _jsonl(rows):
    body = b"".join(
        _canonical(
            row,
            label="allocation compatibility delta row",
            maximum=MAX_DELTA_ROW_BYTES_INCLUDING_LF - 1,
        )
        + b"\n"
        for row in rows
    )
    if not body or len(body) > MAX_DELTA_BODY_BYTES or not body.endswith(b"\n"):
        _fail("allocation compatibility delta body framing is invalid")
    if any(
        len(line) > MAX_DELTA_ROW_BYTES_INCLUDING_LF
        for line in body.splitlines(keepends=True)
    ):
        _fail("allocation compatibility delta row exceeds bound")
    return body


def _descriptor(body, summary):
    lines = body.splitlines(keepends=True)
    return {
        "artifact_id": ARTIFACT_ID,
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "delta_body_embedded": False,
            "max_delta_body_bytes": MAX_DELTA_BODY_BYTES,
            "max_delta_row_bytes_including_lf": MAX_DELTA_ROW_BYTES_INCLUDING_LF,
            "max_descriptor_bytes": MAX_DESCRIPTOR_BYTES,
            "unicode_normalization": "NFC",
        },
        "comparison_contract": {
            "allocation_count_fields": ["full_count", "pilot_count"],
            "comparison_scope": "planned-persona-family-variant-allocation-counts-only",
            "coordinate_key": ["persona_id", "family_id", "variant_id"],
            "coordinate_order": "persona-ordinal-family-order-variant-ascii",
            "legacy_missing_coordinate_policy": "reject",
            "tiny_count_comparison": "not-applicable-legacy-has-tiny-smoke-not-core-tiny",
            "tolerance": "exact-integer-equality",
        },
        "completion_claims": {
            "additive_reuse_authorized": False,
            "allocation_adoption_selected": False,
            "allocation_compatibility_proven": False,
            "namespace_entry_issued": False,
            "source_inventory_supersession_selected": False,
        },
        "core_allocation_binding": {
            "artifact_id": CORE_ARTIFACT_ID,
            "artifact_kind": CORE_ARTIFACT_KIND,
            "artifact_schema": CORE_ARTIFACT_SCHEMA,
            "artifact_schema_version": 1,
            "body_canonical_bytes": CORE_BODY_BYTES,
            "body_id": CORE_BODY_ID,
            "body_sha256": CORE_BODY_SHA256,
            "canonical_bytes": CORE_DESCRIPTOR_BYTES,
            "sha256": CORE_DESCRIPTOR_SHA256,
        },
        "delta_body": {
            "body_canonical_bytes": len(body),
            "body_id": BODY_ID,
            "body_sha256": _sha256(body),
            "first_row_id": json.loads(lines[0])["row_id"],
            "last_row_id": json.loads(lines[-1])["row_id"],
            "maximum_lf_inclusive_row_bytes": max(len(line) for line in lines),
            "row_count": len(lines),
            "row_schema": DELTA_ROW_SCHEMA,
        },
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "legacy_variant_catalog_binding": {
            "artifact_kind": LEGACY_CATALOG_KIND,
            "artifact_schema": LEGACY_CATALOG_SCHEMA,
            "artifact_schema_version": 2,
            "canonical_bytes": LEGACY_CATALOG_BYTES,
            "sha256": LEGACY_CATALOG_SHA256,
        },
        "profile_id": PROFILE_ID,
        "result": {
            "additive_reuse_authorized": False,
            "cellwise_compatible": False,
            "compatibility_status": "incompatible",
            "legacy_source_allocation_compatibility": "unresolved",
            "legacy_source_projection_reuse_authorized": False,
        },
        "summary": summary,
    }


def _check_descriptor_static(value):
    if type(value) is not dict or set(value) != DESCRIPTOR_FIELDS:
        _fail("audit descriptor schema drifted")
    if (
        value.get("artifact_id") != ARTIFACT_ID
        or value.get("artifact_kind") != ARTIFACT_KIND
        or value.get("artifact_schema") != ARTIFACT_SCHEMA
        or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or value.get("profile_id") != PROFILE_ID
        or value.get("fixture_id") != FIXTURE_ID
        or value.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
        or value.get("g0_contract_frozen") is not False
    ):
        _fail("audit descriptor identity drifted")
    authority = value.get("authority")
    if (
        type(authority) is not dict
        or set(authority) != AUTHORITY_FIELDS
        or any(type(flag) is not bool or flag is not False for flag in authority.values())
    ):
        _fail("audit authority must be exact all-false")
    claims = value.get("completion_claims")
    if (
        type(claims) is not dict
        or set(claims)
        != {
            "additive_reuse_authorized",
            "allocation_adoption_selected",
            "allocation_compatibility_proven",
            "namespace_entry_issued",
            "source_inventory_supersession_selected",
        }
        or any(type(flag) is not bool or flag is not False for flag in claims.values())
    ):
        _fail("audit completion claims must be exact all-false")


def _read_delta_body_twice(provider, *, expected_body):
    if not callable(provider):
        _fail("delta body provider must be callable")
    reads = []
    for _ in range(2):
        value = provider(ARTIFACT_ID, BODY_ID)
        if type(value) is not bytes or not 0 < len(value) <= MAX_DELTA_BODY_BYTES:
            _fail("delta body provider returned invalid bytes")
        raw = bytes(bytearray(value))
        if not raw.endswith(b"\n") or b"\r" in raw:
            _fail("delta body framing drifted")
        parsed = []
        for line in raw.splitlines(keepends=True):
            if not line.endswith(b"\n") or len(line) > MAX_DELTA_ROW_BYTES_INCLUDING_LF:
                _fail("delta body row framing drifted")
            try:
                row = json.loads(
                    line[:-1].decode("utf-8", "strict"),
                    object_pairs_hook=_reject_duplicate_keys,
                    parse_float=_reject_float,
                    parse_constant=_reject_constant,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                _fail(f"delta body row is invalid: {type(error).__name__}")
            if type(row) is not dict or set(row) != DELTA_ROW_FIELDS:
                _fail("delta body row schema drifted")
            if (
                _canonical(
                    row,
                    label="delta body row",
                    maximum=MAX_DELTA_ROW_BYTES_INCLUDING_LF - 1,
                )
                + b"\n"
                != line
            ):
                _fail("delta body row is not canonical")
            parsed.append(row)
        reads.append(raw)
    if reads[0] != reads[1] or reads[1] != expected_body:
        _fail("delta body provider differs from independent regeneration")
    return reads[1]


def validate_core_extension_legacy_source_allocation_compatibility_audit(
    value,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
    core_descriptor_provider=None,
    core_body_provider=None,
    legacy_variant_catalog_provider=None,
    delta_body_provider=None,
):
    """Independently rebuild the non-authorizing incompatibility audit."""

    expected_golden = _require_producer_golden_parity(producer_expected_golden)
    opening_raw = _canonical(
        value, label="allocation compatibility audit", maximum=MAX_DESCRIPTOR_BYTES
    )
    snapshot = _parse_canonical_object(
        opening_raw, label="allocation compatibility audit", maximum=MAX_DESCRIPTOR_BYTES
    )
    if expected_golden is not None and (
        len(opening_raw) != expected_golden[0]
        or not hmac.compare_digest(_sha256(opening_raw), expected_golden[1])
    ):
        _fail("audit descriptor differs from frozen golden")
    _check_descriptor_static(snapshot)
    try:
        core_descriptor, _ = _read_object_provider_twice(
            core_descriptor_provider,
            label="core allocation descriptor",
            maximum=MAX_DESCRIPTOR_BYTES,
        )
        core_rows, _ = _accepted_core_rows(
            core_descriptor, core_body_provider=core_body_provider
        )
        catalog, catalog_raw = _read_object_provider_twice(
            legacy_variant_catalog_provider,
            label="legacy variant catalog",
            maximum=MAX_INPUT_CATALOG_BYTES,
        )
        catalog = _require_catalog(catalog, catalog_raw)
        rows, summary = _derive(core_rows, catalog)
        body = _jsonl(rows)
        descriptor = _descriptor(body, summary)
        expected_raw = _canonical(
            descriptor,
            label="independent allocation compatibility audit",
            maximum=MAX_DESCRIPTOR_BYTES,
        )
        if snapshot != descriptor or opening_raw != expected_raw:
            _fail("audit descriptor differs from independent regeneration")
        if expected_golden is not None and (
            len(body) != expected_golden[2]
            or not hmac.compare_digest(_sha256(body), expected_golden[3])
        ):
            _fail("audit delta body differs from frozen golden")
        _read_delta_body_twice(delta_body_provider, expected_body=body)
        return True
    finally:
        if _canonical(
            value,
            label="allocation compatibility audit postflight",
            maximum=MAX_DESCRIPTOR_BYTES,
        ) != opening_raw:
            _fail("caller-owned audit descriptor changed during validation")


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_float(token):
    _fail(f"floating-point token is forbidden: {token!r}")


def _reject_constant(token):
    _fail(f"non-JSON constant is forbidden: {token!r}")


__all__ = [
    "ARTIFACT_ID",
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "BODY_ID",
    "DELTA_ROW_SCHEMA",
    "EXPECTED_BODY_CANONICAL_BYTES",
    "EXPECTED_BODY_SHA256",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "PersonaV2CoreExtensionLegacyAllocationCompatibilityAuditValidationError",
    "validate_core_extension_legacy_source_allocation_compatibility_audit",
]
