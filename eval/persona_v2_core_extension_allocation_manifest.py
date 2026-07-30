"""Query-independent core extension allocation manifest candidate.

This module derives the finite ``persona-core-v1`` extension allocation from
the authored family-count matrix, the public envelope variant weights, and the
frozen implementation registry.  It emits a compact descriptor plus an
external canonical LF-JSONL body; it does not select source instances, write
files, execute KIO, mutate history, or grant G0 authority.
"""

from __future__ import annotations

import copy
import base64
import functools
import hashlib
import hmac
import json
import zlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_core_extension_allocation_manifest_validator as independent
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_core_extension_allocation_manifest_validator as independent


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

# Frozen after the independent two-read implementation review and local
# full/two-seed cold gate.  This freezes a content-only candidate descriptor;
# it does not issue a namespace entry or grant execution authority.
EXPECTED_CANONICAL_BYTES = 5_357
EXPECTED_SHA256 = "f5b63b30fa06fb230d4b58574390f0f99e2402d2b8af12e137d63406777a0436"

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

CORE_MATRIX_PIN = (
    "kio.persona.core-family-count-matrix/v1",
    2_410,
    "271358e948ec060238ed519a8d38ae2283e6eefce28c1075c4f02c9984d98561",
)
ENVELOPE_PIN = (
    "kio.persona.pc-envelope/v2",
    2,
    71_979,
    "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7",
)
FORMAT_REGISTRY_PIN = (
    "kio.persona.pc-format-implementation-registry/v2",
    2,
    333_881,
    "59ae0b2e5c755732e6937e70ada4b243ea2c7432a9ce654c7e9c219b4a13bc5d",
)
FORMAT_REGISTRY_PROJECTION_PIN = (
    22_639,
    "3ef3404825c89dd97e9394ef039f8c7c25e7c94ee1e2ac5465f756cff79ca9af",
)
# zlib/base64 is a source-literal transport for the bounded consumed
# projection only.  It is not a registry loader and cannot execute renderer
# probes.  ``source_registry_sha256`` binds this projection to the full frozen
# all-71 registry pin above.
_FROZEN_FORMAT_REGISTRY_PROJECTION_ZLIB_B64 = (
    "eNrtnO1u4yoQhu/Fv+ueNm0atbeyOrII4IStDV7A+diq935mcNKmPRti4jhaJP6lhpl5eTRjGNvqW0a0FSWhtjB0yWuSvWSvQt02XBslyW1D81Lpmthc1E3Fay4tsULJXPOFMFZv/1lNspvvTooVmMOs7GVyk301LLRam+zlx1tGVd2oVrLCtGUpNkUDTnAkq4l+ZWots39vMr5pOLWcFaosKyF5wYRplBHWec8qRUlVWL6xIKIktai2cLVm+JeouCQ1L2CQy07Np+ubbEEsBzEVh8tUSatRvvsh5q1VOvuuPHt5yzSXjGuui7mQTMhFIdjevLPKUUu+n5bvHYOzFakEIzDlhO3HvE/jd7TWgkjb2Xys4v3Gh5GNAZBFjo75of2ErK96cBOSCobLqwojRVke0rMbW1RqcQxhF+IrxUN3nGi6JHO43h/jp30wxe+mPSB2K/ByxPWPSrEbipch6vcShPWfXb8n2Fk3O+IqxgV44dGmORseVYwfI4d+oyaHC/CSW6hRwIHbqLmB/hP7xijYwG3U2EC/F1uzHQUbuI0aG+j3YtPjZJuOPNv0iWyz42CzkWOz5vSZeOBhDjrFltpWg/Ge7LGjcfQnYz9M86u6DksMFDNK1O8luamvRBIDxUwS9XtJbsm1ULpIMbN0C/C3HmY1kCV4KCx4OdaDuKF4EaL+E9v0yARt5ATtKYJ8cD0vbV0V3BXrHxHyyOuYnypjBDAyQxciZohuAV6KotnK+UCMnY8jDPeD8ULsVuDvklnZu3GBuf9rXg6v/bFdZuVlOxhwGIzuw6ZPf7ybewlsZE3gJ6hQVH+HZiiR/aFpsi6UrLYBoMAkZ4q2ODUE1he7nsDcYrzAwOOmLzHMjP1bvgNqzsURYruxSJA5tf4GpDJDcTkXx9qObiwSXE6tvxwbOxSXc3GsHruxWAoS1Xpxzes+rzBaadqmURpngCCit1+2zposjj62wgAX4eWi5DVngoQiOzTtQQ0l+x9VNYsBt3wvLnQdGS6U7C9JORoudB0ZLpTsb0xFOW5JYoDIoKFkLzSCx/mh1JycY9RI1zBEhc1p9n++I9i42DBAZNRQshfamqzGhYYBIoOGkr3QfovhJw2maiLkwcCf4GGgi8ADR6HQ0KRPXWq6FCuO008/5oW1/L4OOYh2C7EuAs8SnS/OIPhh1wejMWSbg2pnkdKvd/pZkydgAcAo4wlYELBKGZ43hL7iJpLQhaBTrQ5h9/Gh75U2CRcvqm2C6jp3qtM2EZaJwC2dUIalXjqbBCYdDEOrolSP1GO0vg42DHShZ74YLfyJr7PqA08ArBwB3d+llOudcnU6DgcB44ymjWHYxsB1kxrX8MRb4XcPNHUUQdRKJUjqI4bX7FIL07uRECW9Wg7uYv3labhTmcq2Ly+Jnzu7V/3AA1abanh4DfctX/B5HYQYKBp6FV+QKl+qiuWtQeWJYThD6DYSvDPhwXoqJnQfgGkrOcCmGK/ymlviHq+cvPvJ5kobCAb6y9mhRP/nTZRcKdNcpCgeRDml6f4WfH9rqjrd28Lqs9GKtbT/GTmx+2T3Kz35DAOmOVUaLXNIu5/AI0+dxFk3OsMNyk4n4bMBStKYpbKJ4NkEVaspz5lWTdpzw26DO3R9t9yUfx6IqX7P5Gc5qfcpmOo3qH6toK88Fe65iSfKMmVcWMatieZL1Zrdq1vA0t3+iv1/+C3MkkymTzB1+kz43XzCp3Q2nc4eJvzp+WHGZ3eEkcf55PGBkwmdPT5MyDPlT9NHOuPPdHL/PH8k9w9zOmXZ+38X8baN"
)

ROW_FIELDS = frozenset(
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
AUTHORITY_FIELDS = (
    "actual_chunks_attested",
    "actual_payload_bytes_attested",
    "authorizes_evaluation",
    "authorizes_filesystem_mutation",
    "authorizes_g0_freeze",
    "authorizes_history_mutation",
    "authorizes_kio_execution",
    "authorizes_physical_write",
    "authorizes_query_plan",
    "authorizes_renderer_execution",
    "authorizes_replay_execution",
    "authorizes_solver_execution",
    "authorizes_source_instances",
    "authorizes_source_plan",
    "authorizes_source_recipes",
    "formal_capacity_gate_satisfied",
)

# This is an independent literal, not a runtime read of the proposal document.
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


class PersonaV2CoreExtensionAllocationManifestError(ValueError):
    """Raised when the core extension allocation candidate is not exact."""


def _fail(message):
    raise PersonaV2CoreExtensionAllocationManifestError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value, *, label, maximum):
    try:
        return artifact_common.canonical_json_bytes(value, label=label, max_bytes=maximum)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _frozen_format_registry_projection_raw():
    """Decode the source literal without invoking any registry implementation."""
    try:
        raw = zlib.decompress(
            base64.b64decode(
                _FROZEN_FORMAT_REGISTRY_PROJECTION_ZLIB_B64.encode("ascii"),
                validate=True,
            )
        )
    except (ValueError, zlib.error) as error:
        raise PersonaV2CoreExtensionAllocationManifestError(
            "frozen format registry projection literal is invalid"
        ) from error
    if (
        len(raw) != FORMAT_REGISTRY_PROJECTION_PIN[0]
        or not hmac.compare_digest(_sha256(raw), FORMAT_REGISTRY_PROJECTION_PIN[1])
    ):
        _fail("frozen format registry projection differs from its exact pin")
    return raw


def _frozen_format_registry_projection():
    """Open only the bounded consumed registry projection, never a renderer."""

    raw = _frozen_format_registry_projection_raw()
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PersonaV2CoreExtensionAllocationManifestError(
            "frozen format registry projection literal is invalid"
        ) from error
    if (
        _canonical(
            value,
            label="frozen format registry consumed projection",
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


def _require_golden_parity():
    expected = _expected_golden()
    try:
        validator_expected = independent._expected_golden()
    except Exception as error:
        raise PersonaV2CoreExtensionAllocationManifestError(
            "independent validator descriptor golden configuration is invalid"
        ) from error
    if type(expected) is not type(validator_expected) or expected != validator_expected:
        _fail("producer and validator manifest descriptor goldens differ")
    return expected


def _require_external_body_pin(raw):
    if type(raw) is not bytes or len(raw) != EXPECTED_BODY_BYTES:
        _fail("extension allocation external body byte count differs from design pin")
    if not hmac.compare_digest(_sha256(raw), EXPECTED_BODY_SHA256):
        _fail("extension allocation external body digest differs from design pin")
    return raw


def _hamilton(total, weights):
    if type(total) is not int or type(total) is bool or total < 0:
        _fail("Hamilton total must be a non-negative exact integer")
    if type(weights) not in (tuple, list) or not weights or any(
        type(weight) is not int or type(weight) is bool or weight < 0
        for weight in weights
    ):
        _fail("Hamilton weights must be a non-empty exact-integer sequence")
    denominator = sum(weights)
    if denominator == 0:
        if total == 0:
            return tuple(0 for _ in weights)
        _fail("positive Hamilton allocation requires positive total weight")
    numerators = tuple(total * weight for weight in weights)
    result = [numerator // denominator for numerator in numerators]
    missing = total - sum(result)
    for ordinal in sorted(
        range(len(weights)), key=lambda index: (-(numerators[index] % denominator), index)
    )[:missing]:
        result[ordinal] += 1
    return tuple(result)


def build_core_family_count_matrix():
    """Return the bounded authored 20-person family matrix projection."""

    return {
        "family_order": list(FAMILY_ORDER),
        "profile_id": PROFILE_ID,
        "rows": [
            {"counts": list(counts), "persona_id": persona_id, "total_files": total}
            for persona_id, total, counts in _MATRIX_ROWS
        ],
        "schema": CORE_MATRIX_PIN[0],
    }


def core_family_count_matrix_sha256(value=None):
    if value is None:
        value = build_core_family_count_matrix()
    raw = _canonical(value, label="core family count matrix", maximum=64 * 1024)
    expected = _canonical(
        build_core_family_count_matrix(),
        label="core family count matrix expected",
        maximum=64 * 1024,
    )
    if raw != expected or len(raw) != CORE_MATRIX_PIN[1] or _sha256(raw) != CORE_MATRIX_PIN[2]:
        _fail("core family count matrix differs from its exact design pin")
    return _sha256(raw)


def _authenticate_upstreams():
    def exact_matrix(value):
        raw = _canonical(value, label="core family count matrix provider", maximum=64 * 1024)
        if (
            len(raw) != CORE_MATRIX_PIN[1]
            or not hmac.compare_digest(_sha256(raw), CORE_MATRIX_PIN[2])
        ):
            _fail("core family count matrix provider differs from pin")
        return raw

    def exact_envelope(value):
        raw = envelope.canonical_json_bytes(value)
        if (
            value.get("artifact_schema") != ENVELOPE_PIN[0]
            or value.get("artifact_schema_version") != ENVELOPE_PIN[1]
            or len(raw) != ENVELOPE_PIN[2]
            or not hmac.compare_digest(_sha256(raw), ENVELOPE_PIN[3])
        ):
            _fail("envelope input differs from core allocation pin")
        return raw

    def exact_registry_projection(value):
        raw = _canonical(
            value,
            label="format registry consumed projection provider",
            maximum=64 * 1024,
        )
        expected = _frozen_format_registry_projection_raw()
        if raw != expected:
            _fail("format registry consumed projection provider differs from pin")
        return raw

    def two_read(label, provider, authenticate):
        first = provider()
        first_raw = authenticate(first)
        second = provider()
        second_raw = authenticate(second)
        if first_raw != second_raw:
            _fail(f"{label} provider replay is nondeterministic")
        # Keep only an owned canonical snapshot.  Public validation can then
        # hand this exact two-read input to the independent validator without
        # reopening the backing provider.
        try:
            return json.loads(second_raw.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PersonaV2CoreExtensionAllocationManifestError(
                f"{label} canonical provider snapshot cannot be decoded"
            ) from error

    matrix = two_read("core family count matrix", build_core_family_count_matrix, exact_matrix)
    envelope_value = two_read("envelope", envelope.build_envelope_contract, exact_envelope)
    registry_value = two_read(
        "format registry consumed projection",
        _frozen_format_registry_projection,
        exact_registry_projection,
    )
    return matrix, envelope_value, registry_value


def _matrix_by_persona(matrix):
    if type(matrix) is not dict or set(matrix) != {"schema", "profile_id", "family_order", "rows"}:
        _fail("core family count matrix key set is invalid")
    if matrix["schema"] != CORE_MATRIX_PIN[0] or matrix["profile_id"] != PROFILE_ID:
        _fail("core family count matrix identity is invalid")
    if tuple(matrix["family_order"]) != FAMILY_ORDER or type(matrix["rows"]) is not list:
        _fail("core family count matrix order is invalid")
    result = {}
    for expected_persona, row in zip(PERSONA_IDS, matrix["rows"]):
        if type(row) is not dict or set(row) != {"persona_id", "total_files", "counts"}:
            _fail("core family count matrix row key set is invalid")
        if row["persona_id"] != expected_persona or type(row["total_files"]) is not int or type(row["total_files"]) is bool:
            _fail("core family count matrix row identity is invalid")
        counts = row["counts"]
        if type(counts) is not list or len(counts) != len(FAMILY_ORDER) or any(
            type(count) is not int or type(count) is bool or count < 0 for count in counts
        ):
            _fail("core family count matrix count vector is invalid")
        if sum(counts) != row["total_files"]:
            _fail("core family count matrix row total is invalid")
        result[expected_persona] = (row["total_files"], tuple(counts))
    if len(matrix["rows"]) != len(PERSONA_IDS) or sum(total for total, _ in result.values()) != 203_000:
        _fail("core family count matrix suite total is invalid")
    return result


def _variant_profiles(envelope_value, registry_value):
    personas = envelope_value.get("personas") if type(envelope_value) is dict else None
    implementation_rows = registry_value.get("implementation_rows") if type(registry_value) is dict else None
    if type(personas) is not list or len(personas) != len(PERSONA_IDS):
        _fail("envelope persona projection is invalid")
    if type(implementation_rows) is not list or len(implementation_rows) != EXPECTED_VARIANT_COUNT:
        _fail("format implementation row projection is invalid")
    by_variant = {}
    for implementation_row in implementation_rows:
        if type(implementation_row) is not dict:
            _fail("format implementation row must be an object")
        variant_id = implementation_row.get("variant_id")
        implementation = implementation_row.get("implementation")
        required = {
            "family", "filename_extension", "compound_suffix_parts", "gate_role",
            "expected_offline_disposition", "variant_id", "implementation",
        }
        if not required.issubset(implementation_row) or type(variant_id) is not str or variant_id in by_variant:
            _fail("format implementation variant IDs are invalid")
        if type(implementation) is not dict or type(implementation.get("renderer_binding_id")) is not str or type(implementation.get("validator_binding_id")) is not str:
            _fail("format implementation bindings are invalid")
        if type(implementation_row["compound_suffix_parts"]) is not list or not implementation_row["compound_suffix_parts"]:
            _fail("format implementation compound suffix is invalid")
        by_variant[variant_id] = implementation_row
    output = {}
    for expected_persona, persona in zip(PERSONA_IDS, personas):
        if type(persona) is not dict or persona.get("persona_id") != expected_persona:
            _fail("envelope persona order is invalid")
        profile = persona.get("variant_profiles")
        if type(profile) is not dict or set(profile) != set(FAMILY_ORDER):
            _fail("envelope variant profile families are invalid")
        output[expected_persona] = {}
        for family_id in FAMILY_ORDER:
            declared = profile[family_id]
            if type(declared) is not list:
                _fail("envelope variant profile must be a list")
            seen = set()
            profile_rows = []
            for variant_ordinal, row in enumerate(declared):
                if type(row) is not dict or set(row) != {"variant_id", "ratio_pct"}:
                    _fail("envelope variant profile row key set is invalid")
                variant_id, weight = row["variant_id"], row["ratio_pct"]
                if (
                    type(variant_id) is not str or variant_id in seen
                    or type(weight) is not int or type(weight) is bool or weight < 0
                    or variant_id not in by_variant or by_variant[variant_id].get("family") != family_id
                ):
                    _fail("envelope variant profile row is invalid")
                seen.add(variant_id)
                profile_rows.append((variant_id, weight, variant_ordinal, by_variant[variant_id]))
            if profile_rows and sum(item[1] for item in profile_rows) != 100:
                _fail("envelope variant profile weights must sum to 100")
            output[expected_persona][family_id] = tuple(profile_rows)
    if len(by_variant) != EXPECTED_VARIANT_COUNT:
        _fail("format implementation variant count is invalid")
    return output


def _row(persona_id, family_id, family_ordinal, profile_row, family_counts, allocation_counts):
    variant_id, weight, variant_ordinal, implementation_row = profile_row
    full_count, pilot_count, tiny_count = allocation_counts
    family_full_count, family_pilot_count, family_tiny_count = family_counts
    implementation = implementation_row["implementation"]
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
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
        "family_full_count": family_full_count,
        "full_count": full_count,
        "family_pilot_count": family_pilot_count,
        "pilot_count": pilot_count,
        "family_tiny_count": family_tiny_count,
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
        full_total, full_families = matrix_rows[persona_id]
        pilot_total = full_total // 10
        tiny_total = 200
        pilot_families = _hamilton(pilot_total, full_families)
        tiny_families = _hamilton(tiny_total, full_families)
        if sum(pilot_families) != pilot_total or sum(tiny_families) != tiny_total:
            _fail("nested family allocations do not preserve totals")
        for family_ordinal, family_id in enumerate(FAMILY_ORDER):
            declared = profiles[persona_id][family_id]
            full_family = full_families[family_ordinal]
            pilot_family = pilot_families[family_ordinal]
            tiny_family = tiny_families[family_ordinal]
            if not declared:
                if full_family or pilot_family or tiny_family:
                    _fail("positive family has no declared variants")
                continue
            weights = tuple(item[1] for item in declared)
            full_counts = _hamilton(full_family, weights)
            pilot_counts = _hamilton(pilot_family, weights)
            tiny_counts = _hamilton(tiny_family, weights)
            if any(pilot > full for pilot, full in zip(pilot_counts, full_counts)):
                _fail("pilot allocation exceeds full reservation")
            for profile_row, full_count, pilot_count, tiny_count in zip(
                declared, full_counts, pilot_counts, tiny_counts
            ):
                rows.append(
                    _row(
                        persona_id,
                        family_id,
                        family_ordinal,
                        profile_row,
                        (full_family, pilot_family, tiny_family),
                        (full_count, pilot_count, tiny_count),
                    )
                )
    if len(rows) != EXPECTED_ROW_COUNT:
        _fail("declared extension row count differs from design pin")
    return tuple(rows)


def _jsonl(rows):
    encoded_rows = []
    for row in rows:
        raw = _canonical(row, label="core extension allocation row", maximum=MAX_ROW_BYTES_INCLUDING_LF - 1)
        framed = raw + b"\n"
        if len(framed) > MAX_ROW_BYTES_INCLUDING_LF:
            _fail("core extension allocation row exceeds byte cap")
        encoded_rows.append(framed)
    body = b"".join(encoded_rows)
    if not body.endswith(b"\n"):
        _fail("core extension allocation body must end in one LF")
    return body


def _totals(rows):
    family_totals = {family_id: 0 for family_id in FAMILY_ORDER}
    role_totals = {
        "contract_contributor": 0,
        "incidental_searchable": 0,
        "raw_only": 0,
    }
    persona_totals = {persona_id: {"full_count": 0, "pilot_count": 0, "tiny_count": 0} for persona_id in PERSONA_IDS}
    physical_extensions = set()
    nonzero = 0
    variants = set()
    for row in rows:
        family_totals[row["family_id"]] += row["full_count"]
        role_totals[row["gate_role"]] += row["full_count"]
        current = persona_totals[row["persona_id"]]
        current["full_count"] += row["full_count"]
        current["pilot_count"] += row["pilot_count"]
        current["tiny_count"] += row["tiny_count"]
        physical_extensions.add(row["filename_extension"])
        variants.add(row["variant_id"])
        nonzero += int(row["full_count"] > 0)
    if (
        role_totals != {
            "contract_contributor": 68_761,
            "incidental_searchable": 62_978,
            "raw_only": 71_261,
        }
        or sum(family_totals.values()) != 203_000
        or nonzero != EXPECTED_FULL_NONZERO_ROW_COUNT
        or len(variants) != EXPECTED_VARIANT_COUNT
        or len(physical_extensions) != EXPECTED_PHYSICAL_EXTENSION_COUNT
    ):
        _fail("derived core extension totals differ from design pins")
    return family_totals, role_totals, persona_totals, tuple(sorted(physical_extensions)), nonzero


def _binding(name, schema, version, byte_count, digest, role):
    return {
        "canonical_bytes": byte_count,
        "dependency_role": role,
        "name": name,
        "schema": schema,
        "schema_version": version,
        "sha256": digest,
    }


def _descriptor(rows, body):
    _require_external_body_pin(body)
    family_totals, role_totals, persona_totals, extensions, nonzero = _totals(rows)
    line_rows = body.splitlines(keepends=True)
    if len(line_rows) != EXPECTED_ROW_COUNT:
        _fail("core extension allocation body framing count is invalid")
    maximum_row = max(len(line) for line in line_rows)
    if maximum_row != EXPECTED_MAXIMUM_ROW_BYTES:
        _fail("core extension allocation maximum row length differs from design pin")
    first, last = line_rows[0], line_rows[-1]
    return {
        "artifact_id": ARTIFACT_ID,
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in AUTHORITY_FIELDS},
        "body_canonical_bytes": len(body),
        "body_embedded": False,
        "body_encoding": "canonical-json-per-row-utf8-nfc-lf",
        "body_final_lf": True,
        "body_id": BODY_ID,
        "body_sha256": _sha256(body),
        "canonical_limits": {
            "external_body_max_bytes": MAX_BODY_BYTES,
            "maximum_lf_inclusive_row_bytes": MAX_ROW_BYTES_INCLUDING_LF,
            "max_manifest_bytes": MAX_MANIFEST_BYTES,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "actual_files_materialized": False,
            "all_inputs_frozen": False,
            "body_descriptor_golden_frozen": False,
            "g0_issued": False,
            "source_instances_issued": False,
        },
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
        "maximum_lf_inclusive_row_bytes": maximum_row,
        "persona_order": list(PERSONA_IDS),
        "persona_totals": [
            {"persona_id": persona_id, **persona_totals[persona_id]}
            for persona_id in PERSONA_IDS
        ],
        "physical_extensions": list(extensions),
        "profile_id": PROFILE_ID,
        "role_totals": role_totals,
        "row_count": len(rows),
        "row_order": "persona-ordinal-family-ordinal-family-local-variant-ordinal",
        "row_schema": ROW_SCHEMA,
        "suite_totals": {"full_count": 203_000, "pilot_count": 20_300, "tiny_count": 4_000},
    }


@functools.lru_cache(maxsize=1)
def _canonical_state():
    matrix, envelope_value, registry_value = _authenticate_upstreams()
    rows = _derive_rows(matrix, envelope_value, registry_value)
    body = _jsonl(rows)
    _require_external_body_pin(body)
    descriptor = _descriptor(rows, body)
    descriptor_raw = _canonical(descriptor, label="core extension allocation descriptor", maximum=MAX_MANIFEST_BYTES)
    expected = _expected_golden()
    if expected is not None and (
        len(descriptor_raw) != expected[0]
        or not hmac.compare_digest(_sha256(descriptor_raw), expected[1])
    ):
        _fail("core extension allocation descriptor differs from frozen golden")
    return descriptor, body, rows, matrix, envelope_value, registry_value


def _live_checked_state():
    """Re-authenticate cached output against the current golden configuration."""

    descriptor, body, rows, matrix, envelope_value, registry_value = _canonical_state()
    _require_external_body_pin(body)
    raw = _canonical(
        descriptor,
        label="cached core extension allocation descriptor",
        maximum=MAX_MANIFEST_BYTES,
    )
    expected = _expected_golden()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("cached core extension allocation descriptor differs from frozen golden")
    return descriptor, body, rows, matrix, envelope_value, registry_value


def build_core_extension_allocation_manifest():
    """Return a detached, non-authorizing external-body descriptor."""

    _require_golden_parity()
    return copy.deepcopy(_live_checked_state()[0])


def build_core_extension_allocation_rows():
    """Return detached logical rows; callers must not treat them as files."""

    _require_golden_parity()
    return copy.deepcopy(_live_checked_state()[2])


def core_extension_allocation_body_bytes():
    """Return the canonical external LF-JSONL body, not a filesystem write."""

    _require_golden_parity()
    return bytes(_live_checked_state()[1])


def canonical_json_bytes(value):
    _require_golden_parity()
    raw = _canonical(value, label="core extension allocation descriptor", maximum=MAX_MANIFEST_BYTES)
    expected = _expected_golden()
    if expected is not None and (
        len(raw) != expected[0] or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("core extension allocation descriptor differs from frozen golden")
    return raw


def validate_core_extension_allocation_manifest(value):
    """Validate the descriptor and replay its external body twice independently."""

    _require_golden_parity()
    opening_raw = canonical_json_bytes(value)
    opening_snapshot = json.loads(opening_raw.decode("utf-8", "strict"))
    (
        expected_descriptor,
        expected_body,
        _expected_rows,
        matrix,
        envelope_value,
        registry_value,
    ) = _live_checked_state()
    expected_raw = canonical_json_bytes(expected_descriptor)
    if opening_raw != expected_raw:
        _fail("core extension allocation descriptor differs from exact regeneration")
    try:
        accepted_body = independent.accepted_core_extension_allocation_body_bytes(
            opening_snapshot,
            producer_expected_golden=_expected_golden(),
            core_matrix_value=copy.deepcopy(matrix),
            envelope_value=copy.deepcopy(envelope_value),
            format_registry_value=copy.deepcopy(registry_value),
            body_provider=lambda artifact_id, body_id: (
                expected_body
                if artifact_id == ARTIFACT_ID and body_id == BODY_ID
                else (_fail("unexpected extension allocation body provider coordinates"))
            ),
        )
        _require_external_body_pin(accepted_body)
    except independent.PersonaV2CoreExtensionAllocationManifestValidationError as error:
        _fail(str(error))
    finally:
        if canonical_json_bytes(value) != opening_raw:
            _fail("caller-owned core extension allocation descriptor changed during validation")
    return True


def core_extension_allocation_manifest_sha256(value=None):
    _require_golden_parity()
    if value is None:
        value = copy.deepcopy(_live_checked_state()[0])
    opening_raw = canonical_json_bytes(value)
    try:
        validate_core_extension_allocation_manifest(value)
        return _sha256(opening_raw)
    finally:
        if canonical_json_bytes(value) != opening_raw:
            _fail("caller-owned core extension allocation descriptor changed during hashing")


def require_frozen_core_extension_allocation_manifest():
    _require_golden_parity()
    _fail(
        "the descriptor/body golden is frozen but remains an unissued content-only "
        "candidate: namespace issuance, solver, source plan, render/write, history, "
        "KIO, evaluation, and G0 authority are all absent"
    )


def require_issued_core_extension_allocation_manifest():
    """Compatibility spelling: candidate freeze is not an issuance authority."""

    require_frozen_core_extension_allocation_manifest()


__all__ = [
    "ARTIFACT_ID",
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "BODY_ID",
    "CORE_MATRIX_PIN",
    "ENVELOPE_PIN",
    "EXPECTED_BODY_BYTES",
    "EXPECTED_BODY_SHA256",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "FORMAT_REGISTRY_PIN",
    "FORMAT_REGISTRY_PROJECTION_PIN",
    "PersonaV2CoreExtensionAllocationManifestError",
    "build_core_extension_allocation_manifest",
    "build_core_extension_allocation_rows",
    "build_core_family_count_matrix",
    "canonical_json_bytes",
    "core_extension_allocation_body_bytes",
    "core_extension_allocation_manifest_sha256",
    "core_family_count_matrix_sha256",
    "require_frozen_core_extension_allocation_manifest",
    "require_issued_core_extension_allocation_manifest",
    "validate_core_extension_allocation_manifest",
]
