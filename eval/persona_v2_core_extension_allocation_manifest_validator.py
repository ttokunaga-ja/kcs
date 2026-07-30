"""Producer-independent validation for the core extension allocation candidate.

The validator deliberately does not import the sibling producer.  It keeps its
own authored matrix literal and Hamilton replay, authenticates the two pinned
upstream projections, derives the descriptor/body itself, and reads an external
body provider exactly twice before accepting it.
"""

from __future__ import annotations

import copy
import base64
import hashlib
import hmac
import json
import zlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope


ARTIFACT_SCHEMA = "kio.persona.core-extension-allocation-manifest/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-core-v1-extension-allocation-manifest-candidate"
ARTIFACT_ID = "persona-core-v1-extension-allocation-manifest-v1"
BODY_ID = "persona-core-v1-extension-allocation-rows-v1"
ROW_SCHEMA = "kio.persona.core-extension-allocation-row/v1"
PROFILE_ID = "persona-core-v1"
MAX_MANIFEST_BYTES = 512 * 2**10
MAX_BODY_BYTES = 512 * 2**10
MAX_ROW_BYTES_INCLUDING_LF = 2_048
EXPECTED_BODY_BYTES = 426_889
EXPECTED_BODY_SHA256 = "a45af96c53035133fb693021a3e8134105f04f6439f91db51f3d51e0cffefcf5"
EXPECTED_ROW_COUNT = 566
EXPECTED_FULL_NONZERO_ROW_COUNT = 539
EXPECTED_MAXIMUM_ROW_BYTES = 786
EXPECTED_PHYSICAL_EXTENSION_COUNT = 39
EXPECTED_VARIANT_COUNT = 71
EXPECTED_CANONICAL_BYTES = 5_357
EXPECTED_SHA256 = "f5b63b30fa06fb230d4b58574390f0f99e2402d2b8af12e137d63406777a0436"

PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, 21))
FAMILY_ORDER = (
    "md", "txt_log", "code", "structured_text", "csv_tsv", "html_eml",
    "ipynb", "pdf_text", "pdf_scan", "docx", "xlsx", "pptx", "image",
    "media", "domain_binary",
)
CORE_MATRIX_PIN = (
    "kio.persona.core-family-count-matrix/v1", 2_410,
    "271358e948ec060238ed519a8d38ae2283e6eefce28c1075c4f02c9984d98561",
)
ENVELOPE_PIN = (
    "kio.persona.pc-envelope/v2", 2, 71_979,
    "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7",
)
FORMAT_REGISTRY_PIN = (
    "kio.persona.pc-format-implementation-registry/v2", 2, 333_881,
    "59ae0b2e5c755732e6937e70ada4b243ea2c7432a9ce654c7e9c219b4a13bc5d",
)
FORMAT_REGISTRY_PROJECTION_PIN = (
    22_639,
    "3ef3404825c89dd97e9394ef039f8c7c25e7c94ee1e2ac5465f756cff79ca9af",
)
_FROZEN_FORMAT_REGISTRY_PROJECTION_ZLIB_B64 = (
    "eNrtnO1u4yoQhu/Fv+ueNm0atbeyOrII4IStDV7A+diq935mcNKmPRti4jhaJP6lhpl5eTRjGNvqW0a0FSWhtjB0yWuSvWSvQt02XBslyW1D81Lpmthc1E3Fay4tsULJXPOFMFZv/1lNspvvTooVmMOs7GVyk301LLRam+zlx1tGVd2oVrLCtGUpNkUDTnAkq4l+ZWots39vMr5pOLWcFaosKyF5wYRplBHWec8qRUlVWL6xIKIktai2cLVm+JeouCQ1L2CQy07Np+ubbEEsBzEVh8tUSatRvvsh5q1VOvuuPHt5yzSXjGuui7mQTMhFIdjevLPKUUu+n5bvHYOzFakEIzDlhO3HvE/jd7TWgkjb2Xys4v3Gh5GNAZBFjo75of2ErK96cBOSCobLqwojRVke0rMbW1RqcQxhF+IrxUN3nGi6JHO43h/jp30wxe+mPSB2K/ByxPWPSrEbipch6vcShPWfXb8n2Fk3O+IqxgV44dGmORseVYwfI4d+oyaHC/CSW6hRwIHbqLmB/hP7xijYwG3U2EC/F1uzHQUbuI0aG+j3YtPjZJuOPNv0iWyz42CzkWOz5vSZeOBhDjrFltpWg/Ge7LGjcfQnYz9M86u6DksMFDNK1O8luamvRBIDxUwS9XtJbsm1ULpIMbN0C/C3HmY1kCV4KCx4OdaDuKF4EaL+E9v0yARt5ATtKYJ8cD0vbV0V3BXrHxHyyOuYnypjBDAyQxciZohuAV6KotnK+UCMnY8jDPeD8ULsVuDvklnZu3GBuf9rXg6v/bFdZuVlOxhwGIzuw6ZPf7ybewlsZE3gJ6hQVH+HZiiR/aFpsi6UrLYBoMAkZ4q2ODUE1he7nsDcYrzAwOOmLzHMjP1bvgNqzsURYruxSJA5tf4GpDJDcTkXx9qObiwSXE6tvxwbOxSXc3GsHruxWAoS1Xpxzes+rzBaadqmURpngCCit1+2zposjj62wgAX4eWi5DVngoQiOzTtQQ0l+x9VNYsBt3wvLnQdGS6U7C9JORoudB0ZLpTsb0xFOW5JYoDIoKFkLzSCx/mh1JycY9RI1zBEhc1p9n++I9i42DBAZNRQshfamqzGhYYBIoOGkr3QfovhJw2maiLkwcCf4GGgi8ADR6HQ0KRPXWq6FCuO008/5oW1/L4OOYh2C7EuAs8SnS/OIPhh1wejMWSbg2pnkdKvd/pZkydgAcAo4wlYELBKGZ43hL7iJpLQhaBTrQ5h9/Gh75U2CRcvqm2C6jp3qtM2EZaJwC2dUIalXjqbBCYdDEOrolSP1GO0vg42DHShZ74YLfyJr7PqA08ArBwB3d+llOudcnU6DgcB44ymjWHYxsB1kxrX8MRb4XcPNHUUQdRKJUjqI4bX7FIL07uRECW9Wg7uYv3labhTmcq2Ly+Jnzu7V/3AA1abanh4DfctX/B5HYQYKBp6FV+QKl+qiuWtQeWJYThD6DYSvDPhwXoqJnQfgGkrOcCmGK/ymlviHq+cvPvJ5kobCAb6y9mhRP/nTZRcKdNcpCgeRDml6f4WfH9rqjrd28Lqs9GKtbT/GTmx+2T3Kz35DAOmOVUaLXNIu5/AI0+dxFk3OsMNyk4n4bMBStKYpbKJ4NkEVaspz5lWTdpzw26DO3R9t9yUfx6IqX7P5Gc5qfcpmOo3qH6toK88Fe65iSfKMmVcWMatieZL1Zrdq1vA0t3+iv1/+C3MkkymTzB1+kz43XzCp3Q2nc4eJvzp+WHGZ3eEkcf55PGBkwmdPT5MyDPlT9NHOuPPdHL/PH8k9w9zOmXZ+38X8baN"
)
ROW_FIELDS = frozenset(
    {
        "schema_version", "row_schema", "row_id", "profile_id", "persona_id",
        "family_id", "family_ordinal", "variant_id", "variant_ordinal",
        "variant_weight", "filename_extension", "compound_suffix_parts", "gate_role",
        "expected_offline_disposition", "family_full_count", "full_count",
        "family_pilot_count", "pilot_count", "family_tiny_count", "tiny_count",
        "renderer_binding_id", "validator_binding_id", "format_registry_sha256",
    }
)
DESCRIPTOR_FIELDS = frozenset(
    {
        "artifact_id", "artifact_kind", "artifact_schema", "artifact_schema_version",
        "authority", "body_canonical_bytes", "body_embedded", "body_encoding",
        "body_final_lf", "body_id", "body_sha256", "canonical_limits",
        "completion_claims", "family_order", "family_totals", "first_row_id",
        "first_row_lf_bytes", "first_row_sha256", "format_registry_sha256",
        "full_nonzero_row_count", "g0_contract_frozen", "input_bindings",
        "last_row_id", "last_row_lf_bytes", "last_row_sha256",
        "maximum_lf_inclusive_row_bytes", "persona_order", "persona_totals",
        "physical_extensions", "profile_id", "role_totals", "row_count", "row_order",
        "row_schema", "suite_totals",
    }
)
AUTHORITY_FIELDS = (
    "actual_chunks_attested", "actual_payload_bytes_attested", "authorizes_evaluation",
    "authorizes_filesystem_mutation", "authorizes_g0_freeze", "authorizes_history_mutation",
    "authorizes_kio_execution", "authorizes_physical_write", "authorizes_query_plan",
    "authorizes_renderer_execution", "authorizes_replay_execution", "authorizes_solver_execution",
    "authorizes_source_instances", "authorizes_source_plan", "authorizes_source_recipes",
    "formal_capacity_gate_satisfied",
)

# Kept independently from the producer so validation does not inherit its data
# or allocation implementation at runtime.
_MATRIX_ROWS = (
    ("p01", 12000, (2880, 1200, 3840, 1680, 480, 600, 24, 720, 12, 24, 20, 20, 480, 0, 20)),
    ("p02", 15000, (3000, 4200, 2250, 3300, 750, 450, 0, 600, 10, 30, 20, 20, 300, 0, 70)),
    ("p03", 10000, (600, 500, 30, 1800, 1400, 1600, 0, 2400, 400, 800, 300, 20, 100, 0, 50)),
    ("p04", 10000, (1000, 400, 2500, 1400, 1600, 0, 2000, 700, 10, 20, 20, 20, 300, 0, 30)),
    ("p05", 12000, (720, 840, 1200, 2160, 3000, 30, 25, 600, 10, 25, 2640, 480, 240, 0, 30)),
    ("p06", 8000, (320, 320, 20, 400, 1600, 20, 20, 1840, 1120, 800, 640, 20, 560, 0, 320)),
    ("p07", 7000, (700, 700, 0, 210, 210, 280, 0, 1960, 1540, 980, 20, 15, 350, 20, 15)),
    ("p08", 8000, (1200, 20, 10, 240, 320, 480, 0, 1440, 15, 1760, 640, 1600, 240, 10, 25)),
    ("p09", 9000, (270, 1980, 0, 90, 540, 30, 0, 900, 360, 1170, 30, 450, 1800, 1350, 30)),
    ("p10", 11000, (220, 30, 0, 220, 770, 550, 0, 2200, 330, 1650, 2530, 2420, 30, 0, 50)),
    ("p11", 10000, (300, 500, 0, 20, 200, 2800, 0, 1800, 25, 2000, 700, 1200, 400, 20, 35)),
    ("p12", 16000, (2880, 4000, 480, 3200, 1440, 1920, 0, 800, 20, 480, 30, 20, 640, 30, 60)),
    ("p13", 7000, (210, 350, 0, 140, 15, 1260, 0, 2100, 840, 1750, 140, 20, 140, 0, 35)),
    ("p14", 13000, (260, 25, 15, 910, 2600, 390, 0, 2080, 650, 1300, 4160, 520, 25, 0, 65)),
    ("p15", 8000, (320, 320, 0, 15, 720, 1600, 0, 1920, 160, 2160, 560, 20, 160, 10, 35)),
    ("p16", 8000, (160, 160, 15, 320, 1120, 20, 0, 2080, 1280, 1280, 480, 20, 400, 25, 640)),
    ("p17", 8000, (240, 45, 0, 20, 160, 80, 0, 2000, 960, 400, 800, 240, 1600, 15, 1440)),
    ("p18", 12000, (360, 1920, 30, 480, 2400, 30, 0, 2160, 600, 1200, 2160, 60, 240, 0, 360)),
    ("p19", 9000, (720, 25, 0, 15, 180, 180, 0, 1620, 360, 1980, 540, 1800, 1080, 450, 50)),
    ("p20", 10000, (600, 2500, 20, 200, 200, 1500, 0, 2000, 1200, 300, 15, 15, 1000, 400, 50)),
)
_GOLDEN_NOT_PROVIDED = object()


class PersonaV2CoreExtensionAllocationManifestValidationError(ValueError):
    """Raised when independent validation fails closed."""


def _fail(message):
    raise PersonaV2CoreExtensionAllocationManifestValidationError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value, *, label, maximum):
    try:
        return artifact_common.canonical_json_bytes(value, label=label, max_bytes=maximum)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _frozen_format_registry_projection():
    """Return the bounded frozen registry projection without renderer probes."""

    try:
        raw = zlib.decompress(
            base64.b64decode(
                _FROZEN_FORMAT_REGISTRY_PROJECTION_ZLIB_B64.encode("ascii"),
                validate=True,
            )
        )
        value = json.loads(raw.decode("utf-8", "strict"))
    except (ValueError, zlib.error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PersonaV2CoreExtensionAllocationManifestValidationError(
            "frozen format registry projection literal is invalid"
        ) from error
    if (
        len(raw) != FORMAT_REGISTRY_PROJECTION_PIN[0]
        or not hmac.compare_digest(_sha256(raw), FORMAT_REGISTRY_PROJECTION_PIN[1])
        or _canonical(
            value,
            label="independent frozen format registry consumed projection",
            maximum=64 * 1024,
        )
        != raw
        or value.get("artifact_schema") != FORMAT_REGISTRY_PIN[0]
        or value.get("artifact_schema_version") != FORMAT_REGISTRY_PIN[1]
        or value.get("source_registry_sha256") != FORMAT_REGISTRY_PIN[3]
    ):
        _fail("frozen format registry projection differs from its exact pin")
    return value


def _expected_golden():
    bytes_set = EXPECTED_CANONICAL_BYTES is not None
    digest_set = EXPECTED_SHA256 is not None
    if bytes_set != digest_set:
        _fail("manifest descriptor golden must be entirely unset or entirely set")
    if not bytes_set:
        return None
    if (
        type(EXPECTED_CANONICAL_BYTES) is not int
        or type(EXPECTED_CANONICAL_BYTES) is bool
        or not 1 <= EXPECTED_CANONICAL_BYTES <= MAX_MANIFEST_BYTES
        or type(EXPECTED_SHA256) is not str
        or len(EXPECTED_SHA256) != 64
        or any(character not in "0123456789abcdef" for character in EXPECTED_SHA256)
    ):
        _fail("manifest descriptor golden configuration is invalid")
    return EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256


def _require_producer_golden_parity(producer_expected_golden):
    expected = _expected_golden()
    if producer_expected_golden is _GOLDEN_NOT_PROVIDED:
        _fail("producer manifest descriptor golden was not supplied")
    if type(producer_expected_golden) is not type(expected) or producer_expected_golden != expected:
        _fail("producer and validator manifest descriptor goldens differ")
    return expected


def _require_body_pin(raw):
    if type(raw) is not bytes or len(raw) != EXPECTED_BODY_BYTES:
        _fail("extension allocation external body byte count differs from design pin")
    if not hmac.compare_digest(_sha256(raw), EXPECTED_BODY_SHA256):
        _fail("extension allocation external body digest differs from design pin")
    return raw


def _owned_snapshot(value, *, label, maximum):
    _require_local_depth(value, label=label)
    raw = _canonical(value, label=label, maximum=maximum)
    try:
        snapshot = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_reject_duplicate_keys, parse_float=_reject_float, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{label} snapshot cannot be parsed: {type(error).__name__}")
    if _canonical(snapshot, label=f"{label} snapshot", maximum=maximum) != raw:
        _fail(f"{label} snapshot is not canonical")
    return snapshot, raw


def _require_local_depth(value, *, label):
    """Apply this manifest's tighter depth-32 and alias/cycle boundary."""

    stack = [(value, 0)]
    seen = set()
    while stack:
        current, depth = stack.pop()
        if depth > 32:
            _fail(f"{label} exceeds manifest nesting depth 32")
        if type(current) is list:
            identity = id(current)
            if identity in seen:
                _fail(f"{label} contains a repeated-container alias or cycle")
            seen.add(identity)
            stack.extend((item, depth + 1) for item in current)
        elif type(current) is dict:
            identity = id(current)
            if identity in seen:
                _fail(f"{label} contains a repeated-container alias or cycle")
            seen.add(identity)
            for key, item in current.items():
                stack.append((key, depth + 1))
                stack.append((item, depth + 1))
    return True


def _hamilton(total, weights):
    if type(total) is not int or type(total) is bool or total < 0:
        _fail("Hamilton total must be a non-negative exact integer")
    if type(weights) not in (tuple, list) or not weights or any(
        type(weight) is not int or type(weight) is bool or weight < 0 for weight in weights
    ):
        _fail("Hamilton weights must be non-empty non-negative exact integers")
    denominator = sum(weights)
    if not denominator:
        if total == 0:
            return tuple(0 for _ in weights)
        _fail("positive Hamilton allocation requires positive total weight")
    numerators = tuple(total * weight for weight in weights)
    result = [numerator // denominator for numerator in numerators]
    for ordinal in sorted(range(len(weights)), key=lambda index: (-(numerators[index] % denominator), index))[: total - sum(result)]:
        result[ordinal] += 1
    return tuple(result)


def _core_matrix():
    return {
        "family_order": list(FAMILY_ORDER),
        "profile_id": PROFILE_ID,
        "rows": [
            {"counts": list(counts), "persona_id": persona_id, "total_files": total}
            for persona_id, total, counts in _MATRIX_ROWS
        ],
        "schema": CORE_MATRIX_PIN[0],
    }


def _authenticate_matrix(value):
    snapshot, raw = _owned_snapshot(value, label="core family count matrix", maximum=64 * 1024)
    # `_read_provider_twice` owns the only provider opens.  Do not regenerate
    # the same input here: the exact canonical receipt authenticates this
    # bounded root, while `_matrix_by_persona` independently validates every
    # consumed structural field before derivation.
    if (
        type(snapshot) is not dict
        or snapshot.get("schema") != CORE_MATRIX_PIN[0]
        or len(raw) != CORE_MATRIX_PIN[1]
        or not hmac.compare_digest(_sha256(raw), CORE_MATRIX_PIN[2])
    ):
        _fail("core family count matrix differs from independent design pin")
    return snapshot, raw


def _authenticate_envelope(value):
    snapshot, raw = _owned_snapshot(value, label="core allocation envelope input", maximum=2 * 2**20)
    # The exact full-envelope receipt is stronger than a fresh call to the
    # mutable backing builder.  `_variant_profiles` later independently checks
    # every field this allocation consumes.  Keeping authentication pure here
    # prevents an authenticator from reopening a provider after its two owned
    # snapshots have already been taken.
    if (
        type(snapshot) is not dict
        or snapshot.get("artifact_schema") != ENVELOPE_PIN[0]
        or snapshot.get("artifact_schema_version") != ENVELOPE_PIN[1]
        or len(raw) != ENVELOPE_PIN[2]
        or not hmac.compare_digest(_sha256(raw), ENVELOPE_PIN[3])
    ):
        _fail("envelope input differs from exact design pin")
    return snapshot, raw


def _authenticate_registry(value):
    snapshot, raw = _owned_snapshot(value, label="core allocation registry consumed projection", maximum=64 * 1024)
    # As above, authenticate the owned provider snapshot against its immutable
    # receipt without reopening the projection builder.  `_variant_profiles`
    # validates the consumed implementation rows during independent derivation.
    if (
        type(snapshot) is not dict
        or snapshot.get("artifact_schema") != FORMAT_REGISTRY_PIN[0]
        or snapshot.get("artifact_schema_version") != FORMAT_REGISTRY_PIN[1]
        or snapshot.get("source_registry_sha256") != FORMAT_REGISTRY_PIN[3]
        or len(raw) != FORMAT_REGISTRY_PROJECTION_PIN[0]
        or not hmac.compare_digest(_sha256(raw), FORMAT_REGISTRY_PROJECTION_PIN[1])
    ):
        _fail("format registry consumed projection differs from exact design pin")
    return snapshot, raw


def _read_provider_twice(provider, *, label, authenticate, maximum):
    """Take two owned, authenticated snapshots before using an input provider."""

    if not callable(provider):
        _fail(f"{label} provider must be callable")
    first_live = provider()
    first_snapshot, first_raw = authenticate(first_live)
    second_live = provider()
    second_snapshot, second_raw = authenticate(second_live)
    if first_raw != second_raw:
        _fail(f"{label} provider replay is nondeterministic")
    return (
        second_snapshot,
        second_raw,
        (
            (f"{label} read-1", first_live, first_raw, maximum),
            (f"{label} read-2", second_live, second_raw, maximum),
        ),
    )


def _matrix_by_persona(matrix):
    if type(matrix) is not dict or set(matrix) != {"schema", "profile_id", "family_order", "rows"}:
        _fail("core family count matrix key set is invalid")
    if matrix["schema"] != CORE_MATRIX_PIN[0] or matrix["profile_id"] != PROFILE_ID or tuple(matrix["family_order"]) != FAMILY_ORDER:
        _fail("core family count matrix identity/order is invalid")
    if type(matrix["rows"]) is not list or len(matrix["rows"]) != len(PERSONA_IDS):
        _fail("core family count matrix row count is invalid")
    result = {}
    for expected_persona, row in zip(PERSONA_IDS, matrix["rows"]):
        if type(row) is not dict or set(row) != {"persona_id", "total_files", "counts"} or row["persona_id"] != expected_persona:
            _fail("core family count matrix row identity is invalid")
        if type(row["total_files"]) is not int or type(row["total_files"]) is bool:
            _fail("core family count matrix total type is invalid")
        counts = row["counts"]
        if type(counts) is not list or len(counts) != len(FAMILY_ORDER) or any(type(count) is not int or type(count) is bool or count < 0 for count in counts):
            _fail("core family count vector is invalid")
        if sum(counts) != row["total_files"]:
            _fail("core family count total is invalid")
        result[expected_persona] = (row["total_files"], tuple(counts))
    if sum(total for total, _ in result.values()) != 203_000:
        _fail("core family suite total is invalid")
    return result


def _variant_profiles(envelope_value, registry_value):
    personas = envelope_value.get("personas") if type(envelope_value) is dict else None
    implementation_rows = registry_value.get("implementation_rows") if type(registry_value) is dict else None
    if type(personas) is not list or len(personas) != len(PERSONA_IDS) or type(implementation_rows) is not list or len(implementation_rows) != EXPECTED_VARIANT_COUNT:
        _fail("upstream public projections are invalid")
    by_variant = {}
    for implementation_row in implementation_rows:
        if type(implementation_row) is not dict:
            _fail("registry implementation row is invalid")
        needed = {"family", "filename_extension", "compound_suffix_parts", "gate_role", "expected_offline_disposition", "variant_id", "implementation"}
        if not needed.issubset(implementation_row):
            _fail("registry implementation row fields are invalid")
        variant_id = implementation_row["variant_id"]
        implementation = implementation_row["implementation"]
        if type(variant_id) is not str or variant_id in by_variant or type(implementation) is not dict:
            _fail("registry implementation variant identity is invalid")
        if type(implementation.get("renderer_binding_id")) is not str or type(implementation.get("validator_binding_id")) is not str:
            _fail("registry implementation bindings are invalid")
        if type(implementation_row["compound_suffix_parts"]) is not list or not implementation_row["compound_suffix_parts"]:
            _fail("registry compound suffix is invalid")
        by_variant[variant_id] = implementation_row
    output = {}
    for expected_persona, persona in zip(PERSONA_IDS, personas):
        if type(persona) is not dict or persona.get("persona_id") != expected_persona:
            _fail("envelope persona order is invalid")
        declared_by_family = persona.get("variant_profiles")
        if type(declared_by_family) is not dict or set(declared_by_family) != set(FAMILY_ORDER):
            _fail("envelope profile families are invalid")
        output[expected_persona] = {}
        for family_id in FAMILY_ORDER:
            declared = declared_by_family[family_id]
            if type(declared) is not list:
                _fail("envelope family profile type is invalid")
            profile = []
            seen = set()
            for variant_ordinal, item in enumerate(declared):
                if type(item) is not dict or set(item) != {"variant_id", "ratio_pct"}:
                    _fail("envelope variant profile key set is invalid")
                variant_id, weight = item["variant_id"], item["ratio_pct"]
                implementation_row = by_variant.get(variant_id)
                if (
                    type(variant_id) is not str or variant_id in seen
                    or type(weight) is not int or type(weight) is bool or weight < 0
                    or implementation_row is None or implementation_row["family"] != family_id
                ):
                    _fail("envelope variant profile entry is invalid")
                seen.add(variant_id)
                profile.append((variant_id, weight, variant_ordinal, implementation_row))
            if profile and sum(item[1] for item in profile) != 100:
                _fail("envelope variant weights must sum to 100")
            output[expected_persona][family_id] = tuple(profile)
    if len(by_variant) != EXPECTED_VARIANT_COUNT:
        _fail("registry variant count is invalid")
    return output


def _make_row(persona_id, family_id, family_ordinal, declared, family_counts, counts):
    variant_id, weight, variant_ordinal, implementation_row = declared
    full_count, pilot_count, tiny_count = counts
    full_family, pilot_family, tiny_family = family_counts
    implementation = implementation_row["implementation"]
    return {
        "schema_version": 1,
        "row_schema": ROW_SCHEMA,
        "row_id": f"persona-core-v1-extension-{persona_id}-{family_id}-{variant_id}",
        "profile_id": PROFILE_ID,
        "persona_id": persona_id,
        "family_id": family_id,
        "family_ordinal": family_ordinal,
        "variant_id": variant_id,
        "variant_ordinal": variant_ordinal,
        "variant_weight": weight,
        "filename_extension": implementation_row["filename_extension"],
        "compound_suffix_parts": list(implementation_row["compound_suffix_parts"]),
        "gate_role": implementation_row["gate_role"],
        "expected_offline_disposition": implementation_row["expected_offline_disposition"],
        "family_full_count": full_family,
        "full_count": full_count,
        "family_pilot_count": pilot_family,
        "pilot_count": pilot_count,
        "family_tiny_count": tiny_family,
        "tiny_count": tiny_count,
        "renderer_binding_id": implementation["renderer_binding_id"],
        "validator_binding_id": implementation["validator_binding_id"],
        "format_registry_sha256": FORMAT_REGISTRY_PIN[3],
    }


def _derive_rows(matrix, envelope_value, registry_value):
    matrix_rows = _matrix_by_persona(matrix)
    profiles = _variant_profiles(envelope_value, registry_value)
    rows = []
    for persona_id in PERSONA_IDS:
        total, full_families = matrix_rows[persona_id]
        pilot_families = _hamilton(total // 10, full_families)
        tiny_families = _hamilton(200, full_families)
        for family_ordinal, family_id in enumerate(FAMILY_ORDER):
            declared = profiles[persona_id][family_id]
            full_family = full_families[family_ordinal]
            pilot_family = pilot_families[family_ordinal]
            tiny_family = tiny_families[family_ordinal]
            if not declared:
                if full_family or pilot_family or tiny_family:
                    _fail("positive family lacks a declared extension profile")
                continue
            weights = tuple(item[1] for item in declared)
            full_counts = _hamilton(full_family, weights)
            pilot_counts = _hamilton(pilot_family, weights)
            tiny_counts = _hamilton(tiny_family, weights)
            if any(pilot > full for pilot, full in zip(pilot_counts, full_counts)):
                _fail("pilot extension reservation exceeds full allocation")
            for declared_row, full_count, pilot_count, tiny_count in zip(declared, full_counts, pilot_counts, tiny_counts):
                rows.append(_make_row(persona_id, family_id, family_ordinal, declared_row, (full_family, pilot_family, tiny_family), (full_count, pilot_count, tiny_count)))
    if len(rows) != EXPECTED_ROW_COUNT:
        _fail("declared core extension row count differs from design pin")
    return tuple(rows)


def _jsonl(rows):
    framed = []
    for row in rows:
        raw = _canonical(row, label="independent core extension allocation row", maximum=MAX_ROW_BYTES_INCLUDING_LF - 1)
        line = raw + b"\n"
        if len(line) > MAX_ROW_BYTES_INCLUDING_LF:
            _fail("core extension allocation row exceeds configured bound")
        framed.append(line)
    body = b"".join(framed)
    _require_body_pin(body)
    return body


def _totals(rows):
    family_totals = {family: 0 for family in FAMILY_ORDER}
    role_totals = {"contract_contributor": 0, "incidental_searchable": 0, "raw_only": 0}
    persona_totals = {persona: {"full_count": 0, "pilot_count": 0, "tiny_count": 0} for persona in PERSONA_IDS}
    extensions, variants, nonzero = set(), set(), 0
    for row in rows:
        family_totals[row["family_id"]] += row["full_count"]
        if row["gate_role"] not in role_totals:
            _fail("unknown derived gate role")
        role_totals[row["gate_role"]] += row["full_count"]
        persona = persona_totals[row["persona_id"]]
        for key in ("full_count", "pilot_count", "tiny_count"):
            persona[key] += row[key]
        extensions.add(row["filename_extension"])
        variants.add(row["variant_id"])
        nonzero += int(row["full_count"] > 0)
    if role_totals != {"contract_contributor": 68_761, "incidental_searchable": 62_978, "raw_only": 71_261}:
        _fail("derived role totals differ from design pins")
    if sum(family_totals.values()) != 203_000 or nonzero != EXPECTED_FULL_NONZERO_ROW_COUNT or len(variants) != EXPECTED_VARIANT_COUNT or len(extensions) != EXPECTED_PHYSICAL_EXTENSION_COUNT:
        _fail("derived manifest totals differ from design pins")
    if sum(value["pilot_count"] for value in persona_totals.values()) != 20_300 or sum(value["tiny_count"] for value in persona_totals.values()) != 4_000:
        _fail("derived nested projection totals differ from design pins")
    return family_totals, role_totals, persona_totals, tuple(sorted(extensions)), nonzero


def _binding(name, schema, version, byte_count, digest, role):
    return {"canonical_bytes": byte_count, "dependency_role": role, "name": name, "schema": schema, "schema_version": version, "sha256": digest}


def _descriptor(rows, body):
    family_totals, role_totals, persona_totals, extensions, nonzero = _totals(rows)
    lines = body.splitlines(keepends=True)
    if len(lines) != EXPECTED_ROW_COUNT or max(len(line) for line in lines) != EXPECTED_MAXIMUM_ROW_BYTES:
        _fail("independent body receipt is invalid")
    first, last = lines[0], lines[-1]
    return {
        "artifact_id": ARTIFACT_ID,
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": 1,
        "authority": {field: False for field in AUTHORITY_FIELDS},
        "body_canonical_bytes": len(body),
        "body_embedded": False,
        "body_encoding": "canonical-json-per-row-utf8-nfc-lf",
        "body_final_lf": True,
        "body_id": BODY_ID,
        "body_sha256": _sha256(body),
        "canonical_limits": {"external_body_max_bytes": MAX_BODY_BYTES, "maximum_lf_inclusive_row_bytes": MAX_ROW_BYTES_INCLUDING_LF, "max_manifest_bytes": MAX_MANIFEST_BYTES, "unicode_normalization": "NFC"},
        "completion_claims": {"actual_files_materialized": False, "all_inputs_frozen": False, "body_descriptor_golden_frozen": False, "g0_issued": False, "source_instances_issued": False},
        "family_order": list(FAMILY_ORDER),
        "family_totals": family_totals,
        "first_row_id": rows[0]["row_id"],
        "first_row_lf_bytes": len(first),
        "first_row_sha256": _sha256(first),
        "format_registry_sha256": FORMAT_REGISTRY_PIN[3],
        "full_nonzero_row_count": nonzero,
        "g0_contract_frozen": False,
        "input_bindings": [
            _binding("core-family-count-matrix", CORE_MATRIX_PIN[0], 1, CORE_MATRIX_PIN[1], CORE_MATRIX_PIN[2], "family-counts"),
            _binding("persona-pc-envelope", ENVELOPE_PIN[0], ENVELOPE_PIN[1], ENVELOPE_PIN[2], ENVELOPE_PIN[3], "variant-weights"),
            _binding("format-implementation-registry", FORMAT_REGISTRY_PIN[0], FORMAT_REGISTRY_PIN[1], FORMAT_REGISTRY_PIN[2], FORMAT_REGISTRY_PIN[3], "format-bindings"),
        ],
        "last_row_id": rows[-1]["row_id"],
        "last_row_lf_bytes": len(last),
        "last_row_sha256": _sha256(last),
        "maximum_lf_inclusive_row_bytes": max(len(line) for line in lines),
        "persona_order": list(PERSONA_IDS),
        "persona_totals": [{"persona_id": persona, **persona_totals[persona]} for persona in PERSONA_IDS],
        "physical_extensions": list(extensions),
        "profile_id": PROFILE_ID,
        "role_totals": role_totals,
        "row_count": len(rows),
        "row_order": "persona-ordinal-family-ordinal-family-local-variant-ordinal",
        "row_schema": ROW_SCHEMA,
        "suite_totals": {"full_count": 203_000, "pilot_count": 20_300, "tiny_count": 4_000},
    }


def _validate_body_rows(raw, expected_rows):
    if type(raw) is not bytes or len(raw) > MAX_BODY_BYTES or not raw.endswith(b"\n") or b"\r" in raw:
        _fail("external allocation body framing is invalid")
    _require_body_pin(raw)
    lines = raw.splitlines(keepends=True)
    if len(lines) != EXPECTED_ROW_COUNT or any(not line.endswith(b"\n") or len(line) > MAX_ROW_BYTES_INCLUDING_LF for line in lines):
        _fail("external allocation body row framing is invalid")
    parsed = []
    for ordinal, line in enumerate(lines):
        try:
            row = json.loads(line[:-1].decode("utf-8", "strict"), object_pairs_hook=_reject_duplicate_keys, parse_float=_reject_float, parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            _fail(f"external allocation row {ordinal} is invalid: {type(error).__name__}")
        if type(row) is not dict or set(row) != ROW_FIELDS:
            _fail("external allocation row key set is invalid")
        _validate_row_types(row)
        if _canonical(row, label="parsed external allocation row", maximum=MAX_ROW_BYTES_INCLUDING_LF - 1) + b"\n" != line:
            _fail("external allocation row is not canonical")
        parsed.append(row)
    if tuple(parsed) != expected_rows:
        _fail("external allocation rows differ from independent regeneration")
    return raw


def _owned_body(value):
    """Bound a provider result before making the second owned byte buffer."""

    if type(value) is not bytes or len(value) > MAX_BODY_BYTES:
        _fail("external allocation body provider returned unbounded non-exact bytes")
    return bytes(bytearray(value))


def _validate_row_types(row):
    integers = (
        "schema_version", "family_ordinal", "variant_ordinal", "variant_weight",
        "family_full_count", "full_count", "family_pilot_count", "pilot_count",
        "family_tiny_count", "tiny_count",
    )
    if any(type(row[field]) is not int or type(row[field]) is bool or row[field] < 0 for field in integers):
        _fail("external allocation row integer field type is invalid")
    exact_strings = ("row_schema", "row_id", "profile_id", "persona_id", "family_id", "variant_id", "filename_extension", "gate_role", "expected_offline_disposition", "renderer_binding_id", "validator_binding_id", "format_registry_sha256")
    if any(type(row[field]) is not str or not row[field] for field in exact_strings):
        _fail("external allocation row string field type is invalid")
    if type(row["compound_suffix_parts"]) is not list or not row["compound_suffix_parts"] or any(type(part) is not str or not part for part in row["compound_suffix_parts"]):
        _fail("external allocation row compound suffix type is invalid")


def _check_descriptor_static(snapshot):
    if type(snapshot) is not dict or set(snapshot) != DESCRIPTOR_FIELDS:
        _fail("manifest descriptor key set is invalid")
    if (
        snapshot["artifact_id"] != ARTIFACT_ID
        or snapshot["artifact_kind"] != ARTIFACT_KIND
        or snapshot["artifact_schema"] != ARTIFACT_SCHEMA
        or snapshot["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or snapshot["profile_id"] != PROFILE_ID
        or snapshot["row_schema"] != ROW_SCHEMA
        or snapshot["body_id"] != BODY_ID
        or snapshot["body_encoding"] != "canonical-json-per-row-utf8-nfc-lf"
        or snapshot["body_canonical_bytes"] != EXPECTED_BODY_BYTES
        or snapshot["body_sha256"] != EXPECTED_BODY_SHA256
        or snapshot["format_registry_sha256"] != FORMAT_REGISTRY_PIN[3]
        or snapshot["row_count"] != EXPECTED_ROW_COUNT
        or snapshot["full_nonzero_row_count"] != EXPECTED_FULL_NONZERO_ROW_COUNT
    ):
        _fail("manifest descriptor static identity or receipt is invalid")
    authority = snapshot.get("authority")
    if type(authority) is not dict or set(authority) != set(AUTHORITY_FIELDS) or any(type(value) is not bool or value is not False for value in authority.values()):
        _fail("manifest descriptor authority must be exact all-false")
    forbidden = {"query", "history", "solution", "path", "scope", "source_id", "raw_hash", "observed_chunks"}
    if forbidden.intersection(snapshot):
        _fail("manifest descriptor contains forbidden execution-coordinate field")
    claims = snapshot.get("completion_claims")
    if (
        type(claims) is not dict
        or set(claims)
        != {
            "actual_files_materialized",
            "all_inputs_frozen",
            "body_descriptor_golden_frozen",
            "g0_issued",
            "source_instances_issued",
        }
        or any(type(value) is not bool or value is not False for value in claims.values())
        or snapshot.get("g0_contract_frozen") is not False
    ):
        _fail("manifest descriptor completion claims must be exact all-false")
    if snapshot.get("body_embedded") is not False or snapshot.get("body_final_lf") is not True:
        _fail("manifest descriptor external body boundary is invalid")


def _postflight(value, opening_raw, dependencies):
    if _canonical(value, label="caller-owned manifest postflight", maximum=MAX_MANIFEST_BYTES) != opening_raw:
        _fail("caller-owned manifest changed during validation")
    for label, dependency, opening, maximum in dependencies:
        if _canonical(dependency, label=f"caller-owned {label} postflight", maximum=maximum) != opening:
            _fail(f"caller-owned {label} changed during validation")


def validate_core_extension_allocation_manifest(
    value,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
    core_matrix_value=None,
    envelope_value=None,
    format_registry_value=None,
    core_matrix_provider=None,
    envelope_provider=None,
    format_registry_projection_provider=None,
    body_provider=None,
    _return_accepted_body=False,
):
    """Independently regenerate the descriptor and authenticate every input twice.

    Value arguments remain a compatibility adapter.  New callers should pass
    providers so the two-read boundary is explicit; each provider is opened
    exactly twice before its owned second snapshot is used.
    """

    expected_golden = _require_producer_golden_parity(producer_expected_golden)
    snapshot, opening_raw = _owned_snapshot(value, label="core extension allocation manifest", maximum=MAX_MANIFEST_BYTES)
    if expected_golden is not None and (len(opening_raw) != expected_golden[0] or not hmac.compare_digest(_sha256(opening_raw), expected_golden[1])):
        _fail("manifest descriptor differs from frozen golden")
    _check_descriptor_static(snapshot)
    if type(_return_accepted_body) is not bool:
        _fail("accepted-body return selector must be an exact boolean")
    if core_matrix_provider is None:
        core_matrix_provider = (
            _core_matrix
            if core_matrix_value is None
            else lambda: core_matrix_value
        )
    if envelope_provider is None:
        envelope_provider = (
            envelope.build_envelope_contract
            if envelope_value is None
            else lambda: envelope_value
        )
    if format_registry_projection_provider is None:
        format_registry_projection_provider = (
            _frozen_format_registry_projection
            if format_registry_value is None
            else lambda: format_registry_value
        )
    dependencies = ()
    try:
        matrix_snapshot, matrix_raw, matrix_dependencies = _read_provider_twice(
            core_matrix_provider,
            label="core family count matrix",
            authenticate=_authenticate_matrix,
            maximum=64 * 1024,
        )
        envelope_snapshot, envelope_raw, envelope_dependencies = _read_provider_twice(
            envelope_provider,
            label="envelope",
            authenticate=_authenticate_envelope,
            maximum=2 * 2**20,
        )
        registry_snapshot, registry_raw, registry_dependencies = _read_provider_twice(
            format_registry_projection_provider,
            label="format registry consumed projection",
            authenticate=_authenticate_registry,
            maximum=64 * 1024,
        )
        dependencies = matrix_dependencies + envelope_dependencies + registry_dependencies
        rows = _derive_rows(matrix_snapshot, envelope_snapshot, registry_snapshot)
        expected_body = _jsonl(rows)
        expected_descriptor = _descriptor(rows, expected_body)
        expected_raw = _canonical(expected_descriptor, label="independent expected core extension allocation manifest", maximum=MAX_MANIFEST_BYTES)
        if opening_raw != expected_raw or snapshot != expected_descriptor:
            _fail("manifest descriptor differs from independent exact regeneration")
        if body_provider is None:
            body_provider = lambda artifact_id, body_id: expected_body
        if not callable(body_provider):
            _fail("external allocation body provider must be callable")
        first = body_provider(ARTIFACT_ID, BODY_ID)
        first_owned = _owned_body(first)
        _validate_body_rows(first_owned, rows)
        second = body_provider(ARTIFACT_ID, BODY_ID)
        second_owned = _owned_body(second)
        _validate_body_rows(second_owned, rows)
        if first_owned != second_owned or second_owned != expected_body:
            _fail("external allocation body provider replay is nondeterministic")
        return second_owned if _return_accepted_body else True
    finally:
        _postflight(value, opening_raw, dependencies)


def accepted_core_extension_allocation_body_bytes(
    value,
    **kwargs,
):
    """Return the validator-owned second body read without a third provider open."""

    kwargs["_return_accepted_body"] = True
    accepted = validate_core_extension_allocation_manifest(value, **kwargs)
    if type(accepted) is not bytes:
        _fail("accepted allocation body did not remain exact bytes")
    return accepted


def validate_core_extension_allocation_manifest_bytes(
    raw,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
    core_matrix_value=None,
    envelope_value=None,
    format_registry_value=None,
    core_matrix_provider=None,
    envelope_provider=None,
    format_registry_projection_provider=None,
    body_provider=None,
):
    _require_producer_golden_parity(producer_expected_golden)
    if type(raw) is not bytes or len(raw) > MAX_MANIFEST_BYTES:
        _fail("serialized manifest descriptor must be bounded exact bytes")
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_reject_duplicate_keys, parse_float=_reject_float, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"serialized manifest descriptor is invalid: {type(error).__name__}")
    if _canonical(value, label="serialized manifest canonical check", maximum=MAX_MANIFEST_BYTES) != raw:
        _fail("serialized manifest descriptor is not exact canonical JSON")
    return validate_core_extension_allocation_manifest(
        value,
        producer_expected_golden=producer_expected_golden,
        core_matrix_value=core_matrix_value,
        envelope_value=envelope_value,
        format_registry_value=format_registry_value,
        core_matrix_provider=core_matrix_provider,
        envelope_provider=envelope_provider,
        format_registry_projection_provider=format_registry_projection_provider,
        body_provider=body_provider,
    )


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
    "ARTIFACT_KIND", "ARTIFACT_SCHEMA", "ARTIFACT_SCHEMA_VERSION", "AUTHORITY_FIELDS",
    "EXPECTED_CANONICAL_BYTES", "EXPECTED_SHA256", "MAX_MANIFEST_BYTES",
    "PersonaV2CoreExtensionAllocationManifestValidationError",
    "accepted_core_extension_allocation_body_bytes",
    "validate_core_extension_allocation_manifest",
    "validate_core_extension_allocation_manifest_bytes",
]
