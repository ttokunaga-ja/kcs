"""Exact, non-authorizing persona realism profiles for persona-PC v2.

The physical family mix is already frozen by :mod:`persona_v2_contract`.
This sidecar freezes a distinct authored stress hypothesis for OS metadata,
locale/language, time, retention, permissions, account counts, and exact
duplicate/revision/conflict/attachment *targets*.  It intentionally contains
no ``intent_key`` membership: the source-intent recipe must bind this profile
first, and a later overlay shard may then reference those intents without a
hash cycle.

These values are not observed user statistics and grant no G0, solver,
renderer, filesystem, KIO, write, or history authority.
"""

from __future__ import annotations

import copy

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_input_bindings as input_bindings
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_input_bindings as input_bindings


ARTIFACT_SCHEMA = "kio.persona.pc-realism-profile/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-realism-profile"
MAX_PROFILE_BYTES = 256 * 1024
REFERENCE_INSTANT_UTC = "2026-07-13T00:00:00Z"

RETENTION_BUCKET_ORDER = (
    "retain-1-30d",
    "retain-31-180d",
    "retain-181-365d",
    "retain-366-2555d",
    "retain-indefinite",
)
MTIME_BUCKET_ORDER = (
    "age-0-7d",
    "age-8-30d",
    "age-31-90d",
    "age-91-365d",
    "age-366-1825d",
    "age-1826-3650d",
)
PERMISSION_MODE_ORDER = (
    "0600-owner-private-rw",
    "0660-team-collaborative-rw",
    "0440-managed-readonly",
    "0444-reference-readonly",
)
PLACEMENT_CLASS_ORDER = (
    "primary-to-primary",
    "primary-to-secondary",
    "secondary-to-primary",
    "secondary-to-secondary",
)

_PERMISSION_PROFILES = (
    ("P1-collaborative", (20, 55, 15, 10)),
    ("P2-operations", (35, 40, 20, 5)),
    ("P3-managed-office", (50, 25, 20, 5)),
    ("P4-research-mixed", (30, 35, 20, 15)),
    ("P5-sensitive", (70, 15, 10, 5)),
    ("P6-restricted", (80, 10, 8, 2)),
    ("P7-field", (40, 35, 20, 5)),
    ("P8-education", (25, 35, 25, 15)),
)
_PLACEMENT_PROFILES = (
    ("E-engineering-local", (60, 25, 10, 5)),
    ("O-managed-office", (35, 35, 20, 10)),
    ("R-research", (45, 30, 15, 10)),
    ("M-mail-cloud-collaboration", (25, 40, 20, 15)),
    ("F-field", (40, 35, 15, 10)),
)

_SENSITIVITY_TIER_ORDER = ("S0", "S1", "S2", "S3")
_CASE_MODES = frozenset(
    ("case-insensitive", "case-sensitive", "portable-snapshot-case-unspecified")
)
_CASE_MODE_BY_OS_SEMANTICS = {
    "chromeos-derived-portable-snapshot": "portable-snapshot-case-unspecified",
    "macos-apfs-case-insensitive": "case-insensitive",
    "ubuntu-ext4-case-sensitive": "case-sensitive",
    "windows-ntfs-case-insensitive": "case-insensitive",
}
_PINNED_OFFSET_BY_TIMEZONE = {
    "America/Chicago": -300,
    "America/Los_Angeles": -420,
    "America/New_York": -240,
    "Asia/Tokyo": 540,
    "Europe/London": 60,
}

# Values are literal v2 inputs, not references to the v1 fidelity table.
# Fields after language weights are: timezone, fixed offset, work cadences,
# synthetic snapshot sources, sensitivity tiers, retention %, mtime %,
# permission profile, exact-duplicate %, near-revision %, conflict basis
# points, standalone-attachment %, cloud accounts, mail accounts, placement.
_REALISM_ROWS = (
    ("p01", "macos-apfs-case-insensitive", "development-laptop", "case-insensitive", "ja-JP", (("ja", 70), ("en", 30)), "Asia/Tokyo", 540, ("release-cycle", "asynchronous-development"), ("git-snapshot", "drive-export"), ("S1", "S2"), (10, 20, 35, 25, 10), (20, 25, 25, 20, 8, 2), "P1-collaborative", 2, 7, 50, 2, 2, 2, "E-engineering-local"),
    ("p02", "ubuntu-ext4-case-sensitive", "sre-workstation", "case-sensitive", "en-US", (("en", 100),), "America/Los_Angeles", -420, ("on-call", "append-heavy-logs"), ("git-snapshot", "server-export"), ("S2", "S3"), (15, 25, 35, 20, 5), (35, 30, 20, 10, 4, 1), "P2-operations", 3, 6, 80, 2, 1, 1, "E-engineering-local"),
    ("p03", "windows-ntfs-case-insensitive", "managed-grc-laptop", "case-insensitive", "ja-JP", (("ja", 70), ("en", 30)), "Asia/Tokyo", 540, ("audit-case", "incident-case"), ("sharepoint-export", "siem-export"), ("S3",), (5, 10, 25, 45, 15), (10, 20, 25, 25, 15, 5), "P5-sensitive", 2, 5, 60, 3, 2, 2, "O-managed-office"),
    ("p04", "ubuntu-ext4-case-sensitive", "gpu-workstation", "case-sensitive", "en-US", (("en", 100),), "America/Los_Angeles", -420, ("experiment-batch", "paper-review"), ("git-snapshot", "object-store-export"), ("S1", "S2"), (8, 15, 35, 30, 12), (25, 25, 25, 15, 8, 2), "P4-research-mixed", 2, 8, 50, 1, 2, 1, "E-engineering-local"),
    ("p05", "windows-ntfs-case-insensitive", "analytics-laptop", "case-insensitive", "ja-JP", (("ja", 75), ("en", 25)), "Asia/Tokyo", 540, ("scheduled-report", "dashboard-refresh"), ("onedrive-export", "warehouse-export"), ("S2",), (10, 20, 35, 30, 5), (20, 30, 25, 15, 8, 2), "P3-managed-office", 3, 6, 75, 2, 2, 2, "E-engineering-local"),
    ("p06", "windows-ntfs-case-insensitive", "laboratory-workstation", "case-insensitive", "en-US", (("en", 100),), "America/New_York", -240, ("protocol-run", "cohort-batch"), ("smb-snapshot", "instrument-export"), ("S2", "S3"), (5, 10, 25, 35, 25), (10, 20, 25, 25, 15, 5), "P5-sensitive", 2, 5, 50, 2, 1, 1, "E-engineering-local"),
    ("p07", "macos-apfs-case-insensitive", "humanities-laptop", "case-insensitive", "en-GB", (("en", 55), ("fr", 15), ("de", 15), ("ja", 15)), "Europe/London", 60, ("longform-writing", "archive-ocr"), ("archive-snapshot", "drive-export"), ("S0", "S1"), (3, 7, 20, 30, 40), (8, 12, 20, 25, 25, 10), "P4-research-mixed", 2, 8, 100, 2, 3, 3, "R-research"),
    ("p08", "macos-apfs-case-insensitive", "product-laptop", "case-insensitive", "ja-JP", (("ja", 70), ("en", 30)), "Asia/Tokyo", 540, ("meeting-heavy", "quarterly-roadmap"), ("drive-export", "teams-export"), ("S2",), (10, 20, 35, 25, 10), (25, 30, 20, 15, 8, 2), "P1-collaborative", 3, 7, 75, 4, 3, 2, "M-mail-cloud-collaboration"),
    ("p09", "macos-apfs-case-insensitive", "field-research-laptop", "case-insensitive", "en-US", (("en", 75), ("ja", 25)), "America/Los_Angeles", -420, ("interview-session", "media-analysis"), ("recorder-export", "research-drive-export"), ("S2", "S3"), (8, 15, 32, 30, 15), (20, 25, 25, 18, 10, 2), "P5-sensitive", 2, 6, 100, 4, 2, 2, "R-research"),
    ("p10", "windows-ntfs-case-insensitive", "consulting-vdi-export", "case-insensitive", "en-US", (("en", 100),), "America/New_York", -240, ("client-phase", "deliverable-review"), ("data-room-export", "teams-export"), ("S3",), (10, 15, 25, 40, 10), (30, 30, 20, 12, 6, 2), "P5-sensitive", 3, 8, 100, 3, 3, 2, "O-managed-office"),
    ("p11", "windows-ntfs-case-insensitive", "travel-sales-laptop", "case-insensitive", "en-US", (("en", 80), ("es", 20)), "America/Chicago", -300, ("mail-call", "proposal-cycle"), ("outlook-export", "crm-export"), ("S2",), (15, 25, 35, 20, 5), (35, 30, 18, 10, 5, 2), "P3-managed-office", 3, 6, 80, 4, 2, 3, "M-mail-cloud-collaboration"),
    ("p12", "windows-ntfs-case-insensitive", "managed-support-laptop", "case-insensitive", "ja-JP", (("ja", 75), ("en", 25)), "Asia/Tokyo", 540, ("queue-driven", "high-frequency-update"), ("ticket-export", "crm-export"), ("S2",), (20, 30, 30, 15, 5), (40, 30, 15, 8, 5, 2), "P3-managed-office", 3, 5, 75, 4, 2, 2, "M-mail-cloud-collaboration"),
    ("p13", "windows-ntfs-case-insensitive", "dlp-legal-laptop", "case-insensitive", "ja-JP", (("ja", 75), ("en", 25)), "Asia/Tokyo", 540, ("matter-case", "legal-hold-versioning"), ("dms-export", "mail-export"), ("S3",), (3, 4, 15, 38, 40), (8, 12, 20, 25, 25, 10), "P6-restricted", 2, 7, 100, 3, 2, 3, "O-managed-office"),
    ("p14", "windows-ntfs-case-insensitive", "finance-control-laptop", "case-insensitive", "ja-JP", (("ja", 80), ("en", 20)), "Asia/Tokyo", 540, ("month-close", "final-copy"), ("erp-export", "onedrive-export"), ("S3",), (5, 10, 25, 50, 10), (25, 30, 20, 15, 8, 2), "P6-restricted", 3, 8, 100, 3, 2, 2, "O-managed-office"),
    ("p15", "windows-ntfs-case-insensitive", "hr-operations-laptop", "case-insensitive", "ja-JP", (("ja", 80), ("en", 20)), "Asia/Tokyo", 540, ("requisition-case", "people-operations"), ("ats-export", "hris-export"), ("S3",), (5, 15, 30, 35, 15), (20, 25, 25, 18, 10, 2), "P6-restricted", 2, 6, 75, 3, 2, 2, "O-managed-office"),
    ("p16", "windows-ntfs-case-insensitive", "clinical-vdi", "case-insensitive", "ja-JP", (("ja", 70), ("en", 30)), "Asia/Tokyo", 540, ("protocol-append", "regulatory-review"), ("edc-export", "secure-smb-snapshot"), ("S3",), (3, 7, 20, 45, 25), (10, 15, 20, 25, 20, 10), "P6-restricted", 2, 5, 50, 2, 1, 2, "O-managed-office"),
    ("p17", "windows-ntfs-case-insensitive", "field-construction-laptop", "case-insensitive", "ja-JP", (("ja", 80), ("en", 20)), "Asia/Tokyo", 540, ("offline-field", "drawing-revision"), ("cde-snapshot",), ("S2",), (8, 12, 25, 40, 15), (20, 25, 20, 20, 12, 3), "P7-field", 3, 8, 100, 2, 2, 2, "F-field"),
    ("p18", "windows-ntfs-case-insensitive", "quality-workstation", "case-insensitive", "ja-JP", (("ja", 75), ("en", 25)), "Asia/Tokyo", 540, ("controlled-document", "production-batch"), ("qms-export", "plm-export"), ("S2",), (5, 10, 25, 45, 15), (15, 25, 25, 20, 12, 3), "P5-sensitive", 2, 7, 50, 2, 2, 2, "E-engineering-local"),
    ("p19", "chromeos-derived-portable-snapshot", "education-portable-snapshot", "portable-snapshot-case-unspecified", "ja-JP", (("ja", 75), ("en", 25)), "Asia/Tokyo", 540, ("academic-term", "bulk-lms-import"), ("drive-export", "lms-export"), ("S2",), (10, 20, 35, 25, 10), (18, 25, 25, 18, 10, 4), "P8-education", 3, 6, 100, 4, 2, 2, "R-research"),
    ("p20", "macos-apfs-case-insensitive", "encrypted-journalist-laptop", "case-insensitive", "ja-JP", (("ja", 70), ("en", 30)), "Asia/Tokyo", 540, ("deadline-driven", "evidence-chain"), ("mail-export", "foia-export", "source-drop-snapshot"), ("S3",), (5, 10, 25, 35, 25), (25, 25, 20, 15, 10, 5), "P6-restricted", 2, 7, 80, 4, 3, 4, "R-research"),
)


class PersonaV2RealismProfileError(ValueError):
    """Raised when the exact realism profile differs from the v2 contract."""


def _bp(values, *, label, expected_length):
    if type(values) is not tuple or not values:
        raise PersonaV2RealismProfileError(f"{label} must be a non-empty tuple")
    if type(expected_length) is not int or expected_length <= 0:
        raise PersonaV2RealismProfileError(
            f"{label} expected length must be a positive exact integer"
        )
    if len(values) != expected_length:
        raise PersonaV2RealismProfileError(
            f"{label} must contain exactly {expected_length} values"
        )
    if any(type(value) is not int or value < 0 for value in values):
        raise PersonaV2RealismProfileError(f"{label} values must be non-negative integers")
    if sum(values) != 100:
        raise PersonaV2RealismProfileError(f"{label} percentages must sum to 100")
    return [value * 100 for value in values]


def _exact_count(denominator, basis_points, *, label):
    numerator = denominator * basis_points
    if numerator % 10_000:
        raise PersonaV2RealismProfileError(
            f"{label} is not exactly integral for denominator {denominator}"
        )
    return numerator // 10_000


def _catalogs():
    permission_ids = [row[0] for row in _PERMISSION_PROFILES]
    placement_ids = [row[0] for row in _PLACEMENT_PROFILES]
    if len(permission_ids) != len(set(permission_ids)):
        raise PersonaV2RealismProfileError("permission profile IDs must be unique")
    if len(placement_ids) != len(set(placement_ids)):
        raise PersonaV2RealismProfileError("placement profile IDs must be unique")
    catalogs = {
        "content_relation_axis": [
            "independent",
            "anchor",
            "exact-duplicate",
            "near-revision",
            "conflict-copy",
        ],
        "eight_axis_ledger_order": [
            "physical-materialization",
            "logical-document",
            "gate-search-role-and-chunks",
            "container-member-and-attachment",
            "current-and-history-version",
            "content-relation-cluster",
            "allocated-bytes",
            "host-metadata-and-exclusion",
        ],
        "mtime_bucket_order": list(MTIME_BUCKET_ORDER),
        "mtime_buckets": [
            {"bucket_id": "age-0-7d", "inclusive_max_days": 7, "inclusive_min_days": 0},
            {"bucket_id": "age-8-30d", "inclusive_max_days": 30, "inclusive_min_days": 8},
            {"bucket_id": "age-31-90d", "inclusive_max_days": 90, "inclusive_min_days": 31},
            {"bucket_id": "age-91-365d", "inclusive_max_days": 365, "inclusive_min_days": 91},
            {"bucket_id": "age-366-1825d", "inclusive_max_days": 1_825, "inclusive_min_days": 366},
            {"bucket_id": "age-1826-3650d", "inclusive_max_days": 3_650, "inclusive_min_days": 1_826},
        ],
        "permission_mode_order": list(PERMISSION_MODE_ORDER),
        "permission_profiles": [
            {
                "permission_profile_id": profile_id,
                "weights_bp": _bp(
                    weights,
                    label=profile_id,
                    expected_length=len(PERMISSION_MODE_ORDER),
                ),
            }
            for profile_id, weights in _PERMISSION_PROFILES
        ],
        "placement_class_order": list(PLACEMENT_CLASS_ORDER),
        "placement_profiles": [
            {
                "placement_profile_id": profile_id,
                "weights_bp": _bp(
                    weights,
                    label=profile_id,
                    expected_length=len(PLACEMENT_CLASS_ORDER),
                ),
            }
            for profile_id, weights in _PLACEMENT_PROFILES
        ],
        "retention_bucket_order": list(RETENTION_BUCKET_ORDER),
        "retention_buckets": [
            {"bucket_id": "retain-1-30d", "inclusive_max_days": 30, "inclusive_min_days": 1},
            {"bucket_id": "retain-31-180d", "inclusive_max_days": 180, "inclusive_min_days": 31},
            {"bucket_id": "retain-181-365d", "inclusive_max_days": 365, "inclusive_min_days": 181},
            {"bucket_id": "retain-366-2555d", "inclusive_max_days": 2_555, "inclusive_min_days": 366},
            {"bucket_id": "retain-indefinite", "inclusive_min_days": 2_556, "upper_bound": "unbounded"},
        ],
        "sensitivity_tier_order": list(_SENSITIVITY_TIER_ORDER),
    }
    if [row["bucket_id"] for row in catalogs["retention_buckets"]] != list(
        RETENTION_BUCKET_ORDER
    ):
        raise PersonaV2RealismProfileError(
            "retention bucket definitions must match their exact order"
        )
    if [row["bucket_id"] for row in catalogs["mtime_buckets"]] != list(
        MTIME_BUCKET_ORDER
    ):
        raise PersonaV2RealismProfileError(
            "mtime bucket definitions must match their exact order"
        )
    return catalogs


def _persona_row(row):
    if type(row) is not tuple or len(row) != 21:
        raise PersonaV2RealismProfileError(
            "each authored realism row must be an exact 21-field tuple"
        )
    (
        persona_id,
        os_semantics_id,
        device_class_id,
        case_mode,
        locale,
        language_weights,
        timezone_label,
        utc_offset_minutes,
        work_cadence_ids,
        snapshot_sources,
        sensitivity_tiers,
        retention_weights,
        mtime_weights,
        permission_profile_id,
        duplicate_pct,
        near_pct,
        conflict_bp,
        attachment_pct,
        cloud_accounts,
        mail_accounts,
        placement_profile_id,
    ) = row
    required_strings = {
        "persona_id": persona_id,
        "os_semantics_id": os_semantics_id,
        "device_class_id": device_class_id,
        "case_mode": case_mode,
        "locale": locale,
        "timezone_iana_label": timezone_label,
        "permission_profile_id": permission_profile_id,
        "placement_profile_id": placement_profile_id,
    }
    for field, value in required_strings.items():
        if type(value) is not str or not value:
            raise PersonaV2RealismProfileError(
                f"{field} must be a non-empty exact string"
            )
    if case_mode not in _CASE_MODES:
        raise PersonaV2RealismProfileError(f"{persona_id} has an invalid case mode")
    if _CASE_MODE_BY_OS_SEMANTICS.get(os_semantics_id) != case_mode:
        raise PersonaV2RealismProfileError(
            f"{persona_id} OS semantics and case mode disagree"
        )
    if type(utc_offset_minutes) is not int or not -840 <= utc_offset_minutes <= 840:
        raise PersonaV2RealismProfileError(
            f"{persona_id} UTC offset must be an exact integer in -840..840"
        )
    if _PINNED_OFFSET_BY_TIMEZONE.get(timezone_label) != utc_offset_minutes:
        raise PersonaV2RealismProfileError(
            f"{persona_id} timezone and pinned reference offset disagree"
        )
    for label, values in (
        ("work cadence", work_cadence_ids),
        ("snapshot source", snapshot_sources),
        ("sensitivity tier", sensitivity_tiers),
    ):
        if (
            type(values) is not tuple
            or not values
            or any(type(value) is not str or not value for value in values)
            or len(values) != len(set(values))
        ):
            raise PersonaV2RealismProfileError(
                f"{persona_id} {label} values must be unique non-empty strings"
            )
    sensitivity_indices = []
    for tier in sensitivity_tiers:
        if tier not in _SENSITIVITY_TIER_ORDER:
            raise PersonaV2RealismProfileError(
                f"{persona_id} references an unknown sensitivity tier"
            )
        sensitivity_indices.append(_SENSITIVITY_TIER_ORDER.index(tier))
    if sensitivity_indices != sorted(sensitivity_indices):
        raise PersonaV2RealismProfileError(
            f"{persona_id} sensitivity tiers must follow canonical order"
        )
    if permission_profile_id not in {row[0] for row in _PERMISSION_PROFILES}:
        raise PersonaV2RealismProfileError(
            f"{persona_id} references an unknown permission profile"
        )
    if placement_profile_id not in {row[0] for row in _PLACEMENT_PROFILES}:
        raise PersonaV2RealismProfileError(
            f"{persona_id} references an unknown placement profile"
        )
    if type(language_weights) is not tuple or not language_weights:
        raise PersonaV2RealismProfileError(
            f"{persona_id} language weights must be a non-empty tuple"
        )
    languages = []
    language_percentages = []
    for item in language_weights:
        if type(item) is not tuple or len(item) != 2:
            raise PersonaV2RealismProfileError(
                f"{persona_id} language entries must be exact pairs"
            )
        language, weight = item
        if type(language) is not str or not language:
            raise PersonaV2RealismProfileError(
                f"{persona_id} language IDs must be non-empty exact strings"
            )
        languages.append(language)
        language_percentages.append(weight)
    if len(languages) != len(set(languages)):
        raise PersonaV2RealismProfileError(
            f"{persona_id} language IDs must be unique"
        )
    language_weights_bp = _bp(
        tuple(language_percentages),
        label=f"{persona_id}/language",
        expected_length=len(language_weights),
    )
    _bp(
        retention_weights,
        label=f"{persona_id}/retention",
        expected_length=len(RETENTION_BUCKET_ORDER),
    )
    _bp(
        mtime_weights,
        label=f"{persona_id}/mtime",
        expected_length=len(MTIME_BUCKET_ORDER),
    )
    rate_contracts = (
        ("exact duplicate percent", duplicate_pct, 1, 3),
        ("near revision percent", near_pct, 3, 8),
        ("conflict basis points", conflict_bp, 20, 100),
        ("standalone attachment percent", attachment_pct, 1, 4),
    )
    for label, value, lower, upper in rate_contracts:
        if type(value) is not int or not lower <= value <= upper:
            raise PersonaV2RealismProfileError(
                f"{persona_id} {label} must be an exact integer in {lower}..{upper}"
            )
    for label, value in (
        ("cloud account count", cloud_accounts),
        ("mail account count", mail_accounts),
    ):
        if type(value) is not int or not 0 <= value <= 16:
            raise PersonaV2RealismProfileError(
                f"{persona_id} {label} must be an exact integer in 0..16"
            )
    persona = envelope.get_persona(persona_id)
    full_denominator = envelope.profile_file_count(persona_id, "full")
    pilot_denominator = envelope.profile_file_count(persona_id, "pilot")
    rates = {
        "conflict_copy_bp": conflict_bp,
        "exact_duplicate_bp": duplicate_pct * 100,
        "near_revision_bp": near_pct * 100,
        "standalone_attachment_bp": attachment_pct * 100,
    }

    def counts(denominator, profile):
        values = {
            key.removesuffix("_bp"): _exact_count(
                denominator,
                value,
                label=f"{persona_id}/{profile}/{key}",
            )
            for key, value in rates.items()
        }
        values["relation_cluster_count"] = (
            values["exact_duplicate"]
            + values["near_revision"]
            + values["conflict_copy"]
        )
        values["required_relation_endpoint_count"] = 2 * values[
            "relation_cluster_count"
        ]
        return values

    pilot_counts = counts(pilot_denominator, "pilot")
    full_counts = counts(full_denominator, "full")
    attachment_overlap_pilot = pilot_counts["standalone_attachment"] // 4
    attachment_overlap_full = attachment_overlap_pilot * 10
    for profile, profile_counts, overlap in (
        ("pilot", pilot_counts, attachment_overlap_pilot),
        ("full", full_counts, attachment_overlap_full),
    ):
        if overlap > min(
            profile_counts["exact_duplicate"],
            profile_counts["standalone_attachment"],
        ):
            raise PersonaV2RealismProfileError(
                f"{persona_id}/{profile} attachment/exact overlap exceeds either set"
            )
        searchable_capacity = envelope.contributor_count(persona_id, profile)
        for family_rows in envelope.variant_counts(persona_id, profile).values():
            for variant_count in family_rows:
                if variant_count["gate_role"] == "incidental_searchable":
                    searchable_capacity += variant_count["count"]
        required_searchable_capacity = (
            profile_counts["required_relation_endpoint_count"]
            + profile_counts["standalone_attachment"]
            - overlap
        )
        if required_searchable_capacity > searchable_capacity:
            raise PersonaV2RealismProfileError(
                f"{persona_id}/{profile} lacks searchable overlay capacity"
            )

    return {
        "case_mode": case_mode,
        "device_class_id": device_class_id,
        "language_weights_bp": [
            {"language": language, "weight_bp": weight_bp}
            for language, weight_bp in zip(languages, language_weights_bp)
        ],
        "locale": locale,
        "mtime_weights_bp": _bp(
            mtime_weights,
            label=f"{persona_id}/mtime",
            expected_length=len(MTIME_BUCKET_ORDER),
        ),
        "os_execution_mode": "declared-target-metadata-only-not-native-or-emulated",
        "os_semantics_id": os_semantics_id,
        "overlay_targets": {
            "attachment_exact_duplicate_overlap": {
                "full_count": attachment_overlap_full,
                "pilot_count": attachment_overlap_pilot,
            },
            "full": full_counts,
            "pilot": pilot_counts,
            "rates": rates,
        },
        "permission_profile_id": permission_profile_id,
        "persona_id": persona_id,
        "placement_profile_id": placement_profile_id,
        "profile_id": f"{persona_id}-realism-profile-v2",
        "retention_weights_bp": _bp(
            retention_weights,
            label=f"{persona_id}/retention",
            expected_length=len(RETENTION_BUCKET_ORDER),
        ),
        "role": persona["role"],
        "sensitivity_tiers": list(sensitivity_tiers),
        "snapshot_account_counts": {
            "cloud_accounts": cloud_accounts,
            "mail_accounts": mail_accounts,
        },
        "synthetic_snapshot_source_kinds": list(snapshot_sources),
        "timezone_iana_label": timezone_label,
        "utc_offset_minutes_magnitude": abs(utc_offset_minutes),
        "utc_offset_sign": "minus" if utc_offset_minutes < 0 else "plus",
        "w0_physical_denominators": {
            "full": full_denominator,
            "pilot": pilot_denominator,
        },
        "work_cadence_ids": list(work_cadence_ids),
    }


def _canonical_profile_value():
    personas = [_persona_row(row) for row in _REALISM_ROWS]
    if len(_REALISM_ROWS) != len(envelope.PERSONA_IDS):
        raise PersonaV2RealismProfileError(
            "realism table must contain exactly one row per persona"
        )
    if [row["persona_id"] for row in personas] != list(envelope.PERSONA_IDS):
        raise PersonaV2RealismProfileError("realism persona rows are missing or reordered")
    catalogs = _catalogs()
    declared_permission_ids = {
        row["permission_profile_id"] for row in catalogs["permission_profiles"]
    }
    declared_placement_ids = {
        row["placement_profile_id"] for row in catalogs["placement_profiles"]
    }
    used_permission_ids = {row["permission_profile_id"] for row in personas}
    used_placement_ids = {row["placement_profile_id"] for row in personas}
    used_sensitivity_tiers = {
        tier for row in personas for tier in row["sensitivity_tiers"]
    }
    if used_permission_ids != declared_permission_ids:
        raise PersonaV2RealismProfileError(
            "permission profile catalog must be exact and fully referenced"
        )
    if used_placement_ids != declared_placement_ids:
        raise PersonaV2RealismProfileError(
            "placement profile catalog must be exact and fully referenced"
        )
    if used_sensitivity_tiers != set(catalogs["sensitivity_tier_order"]):
        raise PersonaV2RealismProfileError(
            "sensitivity tier catalog must be exact and fully referenced"
        )
    full_totals = {
        key: sum(row["overlay_targets"]["full"][key] for row in personas)
        for key in (
            "exact_duplicate",
            "near_revision",
            "conflict_copy",
            "standalone_attachment",
            "relation_cluster_count",
        )
    }
    pilot_totals = {
        key: sum(row["overlay_targets"]["pilot"][key] for row in personas)
        for key in full_totals
    }
    expected_full = {
        "conflict_copy": 1_560,
        "exact_duplicate": 5_080,
        "near_revision": 13_230,
        "relation_cluster_count": 19_870,
        "standalone_attachment": 5_690,
    }
    expected_pilot = {key: value // 10 for key, value in expected_full.items()}
    if full_totals != expected_full or pilot_totals != expected_pilot:
        raise PersonaV2RealismProfileError("suite overlay target totals drifted")
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "filesystem_writer_available": False,
            "formal_capacity_gate_satisfied": False,
            "history_executor_available": False,
            "kio_execution_available": False,
            "query_instances_rendered": False,
            "query_spec_hashed": False,
            "renderer_available": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_PROFILE_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_or_float_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "catalogs": catalogs,
        "completion_scope": (
            "exact-authored-persona-metadata-and-overlay-count-targets-only-"
            "no-intent-membership-no-review-no-solver-no-g0"
        ),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-user-statistics",
        "input_bindings": input_bindings.build_upstream_bindings(),
        "eight_axis_ledger_contract_complete": False,
        "overlay_membership_complete": False,
        "overlay_marginal_targets_complete": True,
        "overlay_scoring_and_search_semantics_complete": False,
        "placement_integer_allocation_complete": False,
        "personas": personas,
        "policy": {
            "anchor_reuse_across_content_relation_clusters_allowed": False,
            "attachment_exact_duplicate_overlap_rule": {
                "full": "exactly-ten-times-pilot-overlap",
                "pilot": "floor-standalone-attachment-count-divided-by-four",
            },
            "attachment_axis_is_orthogonal_to_content_relation": True,
            "attachment_overlap_target_is_exact_duplicate_only": True,
            "content_relation_cluster_cardinality": "exactly-two-physical-materializations",
            "content_relation_clusters_are_physical-member-disjoint": True,
            "exact_near_conflict_are_mutually_exclusive_derivative_roles": True,
            "formal_lane_unreadable_files_allowed": False,
            "live_sync_allowed": False,
            "membership_requires_future_intent_keys": True,
            "overlay_may_change_family_or_variant_marginals": False,
            "overlay_may_change_physical_totals": False,
            "overlay_may_change_target_contract_chunks": False,
            "placement_weights_are_source_recipe_routing_hypotheses_only": True,
            "real_credentials_or_personal_data_allowed": False,
            "reference_instant_utc": REFERENCE_INSTANT_UTC,
            "timezone_offset_is_pinned_without_tzdb_lookup": True,
        },
        "profile_vectors_complete": True,
        "realism_input_closure_complete": False,
        "remaining_blockers": [
            "source-intent-recipe-not-bound",
            "overlay-intent-memberships-not-present",
            "overlay-placement-integer-allocation-not-bound",
            "logical-document-scoring-and-search-participation-not-bound",
            "eight-axis-ledger-contract-not-bound",
            "near-and-conflict-renderer-transforms-not-bound",
            "realism-independent-review-receipt-not-bound",
            "bounded-framed-loader-not-implemented",
            "joint-refinement-feasibility-not-proved",
        ],
        "suite_overlay_targets": {
            "full": full_totals,
            "pilot": pilot_totals,
        },
    }


def build_realism_profile():
    """Return a detached exact profile; never source-intent membership."""

    return copy.deepcopy(_canonical_profile_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 realism profile",
            max_bytes=MAX_PROFILE_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RealismProfileError(str(error)) from None


def validate_realism_profile(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_realism_profile,
            label="persona v2 realism profile",
            max_bytes=MAX_PROFILE_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RealismProfileError(str(error)) from None


def realism_profile_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_realism_profile,
            label="persona v2 realism profile",
            max_bytes=MAX_PROFILE_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RealismProfileError(str(error)) from None


def get_persona_realism_profile(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2RealismProfileError(f"unknown persona: {persona_id!r}")
    for row in build_realism_profile()["personas"]:
        if row["persona_id"] == persona_id:
            return row
    raise AssertionError("validated persona profile disappeared")


def require_realism_input_closure():
    raise PersonaV2RealismProfileError(
        "realism profile targets are exact, but source-intent membership, review, "
        "and joint refinement remain absent"
    )
