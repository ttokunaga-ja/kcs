"""Non-authorizing machine-readable envelope for persona-PC fidelity v2.

This module freezes the already-reviewed persona, file-family, extension,
domain-variant, density, history-scale, lane, and capacity marginals.  It is
deliberately *not* the G0 root contract: the exact topology now lives in an
external sidecar, while its G0 binding, joint allocation, source recipes,
history intent, and query oracle are still missing.  Consequently every
execution/write authority stays false and :func:`require_frozen_g0_contract`
always fails closed.

The existing ``persona_fixture_spec`` remains the normative v1 implementation.
Nothing in this module changes or reinterprets a v1 artifact.
"""

import copy
import hashlib
import json
import re
import unicodedata
from types import MappingProxyType


ARTIFACT_SCHEMA = "kcs.persona.pc-envelope/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-envelope"
FIXTURE_ID = "kcs-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2

MAX_ENVELOPE_BYTES = 2 * 2**20
MAX_CANONICAL_DEPTH = 64
MAX_CANONICAL_STRING_BYTES = 4_096
APPORTIONMENT_ALGORITHM_ID = "hamilton-largest-remainder-v1"
APPORTIONMENT_TIE_BREAK = "descending-fractional-remainder-then-input-ordinal"

FORMAT_KEYS = (
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

DENSITY_BUCKET_ORDER = ("1-4", "5-20", "21-50", "51-70")
_DENSITY_BUCKET_BOUNDS = {
    "1-4": (1, 4),
    "5-20": (5, 20),
    "21-50": (21, 50),
    "51-70": (51, 70),
}
_DENSITY_PROFILES = {
    "low": (30, 50, 20, 0),
    "medium": (10, 30, 45, 15),
    "high": (3, 12, 45, 40),
    "dense-office": (1, 4, 20, 75),
}
DENSITY_BUCKET_BOUNDS = MappingProxyType(dict(_DENSITY_BUCKET_BOUNDS))
DENSITY_PROFILES = MappingProxyType(dict(_DENSITY_PROFILES))

HISTORY_COHORT_ORDER = ("P", "X", "Y", "N", "U")
REQUIRED_SCOPE_HISTORY_COHORTS = ("P", "X", "Y", "N")
REQUIRED_HISTORY_SCOPE_COUNT = 20
MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE = max(
    maximum for _, maximum in _DENSITY_BUCKET_BOUNDS.values()
)
_HISTORY_COHORT_WEIGHTS_PCT = {"P": 4, "X": 10, "Y": 6, "N": 4, "U": 76}
_PROFILE_TARGET_CHUNKS = {"pilot": 12_000, "full": 120_000}

_FAMILY_PERCENTAGE_ROWS = (
    ("p01", (22, 8, 28, 12, 3, 5, 1, 7, 1, 3, 2, 2, 3, 0, 3)),
    ("p02", (20, 22, 15, 20, 5, 3, 0, 4, 0, 2, 1, 1, 2, 0, 5)),
    ("p03", (10, 12, 8, 15, 10, 8, 0, 15, 5, 5, 4, 2, 3, 0, 3)),
    ("p04", (12, 7, 18, 10, 12, 2, 12, 12, 1, 2, 3, 3, 5, 0, 1)),
    ("p05", (8, 5, 6, 14, 20, 5, 5, 5, 1, 3, 15, 4, 3, 0, 6)),
    ("p06", (6, 6, 3, 5, 15, 2, 3, 18, 8, 8, 8, 5, 9, 0, 4)),
    ("p07", (12, 10, 0, 4, 3, 5, 0, 25, 20, 10, 1, 2, 6, 1, 1)),
    ("p08", (11, 4, 1, 5, 8, 8, 0, 13, 3, 15, 8, 15, 7, 1, 1)),
    ("p09", (8, 15, 0, 4, 8, 3, 0, 10, 4, 12, 4, 8, 15, 7, 2)),
    ("p10", (4, 4, 0, 2, 8, 6, 0, 18, 5, 12, 18, 18, 3, 0, 2)),
    ("p11", (3, 4, 0, 2, 5, 25, 0, 16, 4, 14, 7, 10, 5, 3, 2)),
    ("p12", (15, 20, 4, 15, 12, 12, 0, 5, 1, 3, 2, 1, 7, 1, 2)),
    ("p13", (3, 4, 0, 1, 2, 14, 0, 28, 15, 22, 3, 2, 3, 0, 3)),
    ("p14", (3, 3, 1, 4, 15, 5, 0, 13, 8, 8, 27, 7, 3, 0, 3)),
    ("p15", (4, 5, 0, 2, 7, 15, 0, 20, 8, 20, 8, 3, 5, 1, 2)),
    ("p16", (5, 6, 1, 4, 10, 4, 1, 24, 12, 10, 8, 5, 6, 1, 3)),
    ("p17", (5, 4, 0, 2, 5, 4, 0, 20, 12, 8, 10, 4, 12, 1, 13)),
    ("p18", (6, 12, 2, 6, 15, 3, 0, 18, 6, 8, 10, 3, 5, 0, 6)),
    ("p19", (8, 5, 0, 2, 5, 5, 0, 20, 8, 15, 7, 12, 8, 3, 2)),
    ("p20", (8, 18, 1, 3, 8, 10, 0, 16, 10, 8, 2, 2, 8, 4, 2)),
)

_PERSONA_METADATA_ROWS = (
    ("p01", "software-engineer", 12_000, 85, 4, "work/products/product-alpha/architecture", "desktop/current-patch", "adr-0042-auth-cache-rollback-v03.md", "low"),
    ("p02", "site-reliability-engineer", 15_000, 88, 5, "services/checkout/prod/oncall/operations", "downloads/exports/log-batches", "checkout-prod-incident-20260713-postmortem.md", "low"),
    ("p03", "security-grc-analyst", 10_000, 80, 4, "compliance/frameworks/soc2/control-evidence", "downloads/inbox/evidence-drops", "soc2-cc6-1-control-evidence-index-v03.csv", "medium"),
    ("p04", "ml-research-engineer", 10_000, 88, 5, "research/programs/model-alpha/experiments/results", "desktop/current-experiment", "model-alpha-exp-0042-analysis.ipynb", "medium"),
    ("p05", "bi-data-analyst", 12_000, 82, 4, "analytics/governance/lineage/warehouse", "downloads/inbox/source-extracts", "fy2026-q2-revenue-forecast-v04.xlsx", "high"),
    ("p06", "life-science-researcher", 8_000, 85, 6, "programs/study-alpha/2026/cohort-a/run-001/analysis", "downloads/inbox/instrument-drops", "study-alpha-cohort-a-assay-results-run-001.csv", "high"),
    ("p07", "humanities-researcher", 7_000, 75, 5, "research/sources/archive-alpha/box-001/ocr-transcripts", "desktop/current-chapter", "archive-alpha-box-001-item-0042-scan.pdf", "medium"),
    ("p08", "product-manager", 8_000, 75, 5, "portfolio/product-alpha/2026/q3/prds", "cloud/team-shared/product-council", "product-alpha-search-prd-v12.docx", "dense-office"),
    ("p09", "ux-researcher", 9_000, 78, 4, "research/study-alpha/2026/transcripts", "downloads/inbox/recorder-imports", "study-alpha-session-017-transcript-v03.txt", "high"),
    ("p10", "management-consultant", 11_000, 85, 6, "engagements/client-alpha/2026/phase-1/workstream-finance/deliverables", "downloads/inbox/data-room", "client-alpha-phase-1-market-sizing-v08.xlsx", "high"),
    ("p11", "account-executive", 10_000, 70, 4, "accounts/account-alpha/proposals", "downloads/crm-exports", "account-alpha-mutual-action-plan-v04.docx", "dense-office"),
    ("p12", "support-success-lead", 16_000, 85, 4, "customers/customer-alpha/cases/case-history", "desktop/active-queue", "case-1042-escalation-timeline-v05.md", "medium"),
    ("p13", "corporate-privacy-counsel", 7_000, 82, 5, "matters/matter-alpha/legal-hold/collection-01/working", "desktop/privileged-working", "matter-alpha-legal-hold-notice-v03.docx", "high"),
    ("p14", "finance-controller", 13_000, 88, 5, "finance/close/2026/q1/2026-03", "desktop/current-close", "fy2026-q1-close-reconciliation-v03.xlsx", "high"),
    ("p15", "recruiter-people-ops", 8_000, 75, 4, "recruiting/requisition-alpha/interviews/round-2", "downloads/ats-exports", "req-alpha-candidate-syn-017-scorecard-v02.docx", "dense-office"),
    ("p16", "clinical-researcher", 8_000, 86, 5, "clinical/studies/study-alpha/2026/synthetic-cases", "downloads/edc-exports", "study-alpha-subject-syn-004-series-01.dcm", "high"),
    ("p17", "construction-project-manager", 8_000, 90, 6, "portfolio/projects/project-alpha/2026/construction/drawings", "downloads/cde-exports", "project-alpha-drawing-a101-rev-b.pdf", "dense-office"),
    ("p18", "manufacturing-quality-engineer", 12_000, 88, 4, "quality/nonconformance/2026/open", "desktop/current-capa", "product-alpha-pfmea-rev-07.xlsx", "medium"),
    ("p19", "educator-instructional-designer", 9_000, 78, 6, "learning/courses/course-alpha/2026/term-1/lesson-plans", "downloads/lms-exports", "course-alpha-week-04-lesson-plan-v02.docx", "high"),
    ("p20", "investigative-journalist", 10_000, 85, 5, "newsroom/investigations/story-alpha/2026/fact-check", "downloads/foia-exports", "story-alpha-source-syn-017-interview-v03.txt", "medium"),
)

# id, md, txt/log/jsonl, code names, code ratios, structured, csv, html,
# image, media.  An empty code/media tuple means that family is absent.
_EXTENSION_PROFILE_ROWS = (
    ("p01", (85, 15), (45, 35, 20), ("py", "rs", "ts"), (25, 40, 35), (45, 35, 5, 15), (75, 25), (80, 20), (60, 25, 10, 5), ()),
    ("p02", (90, 10), (25, 55, 20), ("py", "go", "ts"), (60, 30, 10), (30, 50, 5, 15), (70, 30), (50, 50), (70, 15, 10, 5), ()),
    ("p03", (80, 20), (40, 35, 25), ("py", "go", "ts"), (70, 20, 10), (45, 20, 25, 10), (60, 40), (40, 60), (45, 15, 35, 5), ()),
    ("p04", (80, 20), (50, 20, 30), ("py", "cpp", "go"), (85, 10, 5), (55, 20, 5, 20), (80, 20), (80, 20), (60, 20, 15, 5), ()),
    ("p05", (75, 25), (55, 20, 25), ("py", "js", "ts"), (65, 5, 30), (30, 10, 10, 50), (80, 20), (65, 35), (70, 20, 5, 5), ()),
    ("p06", (70, 30), (55, 20, 25), ("py", "cpp", "ts"), (85, 10, 5), (35, 15, 35, 15), (65, 35), (70, 30), (35, 20, 40, 5), ()),
    ("p07", (60, 40), (75, 10, 15), (), (), (30, 10, 50, 10), (60, 40), (35, 65), (25, 20, 50, 5), (60, 40, 0)),
    ("p08", (70, 30), (60, 15, 25), ("py", "js", "ts"), (60, 10, 30), (50, 20, 5, 25), (75, 25), (45, 55), (55, 35, 5, 5), (70, 30, 0)),
    ("p09", (65, 35), (70, 15, 15), (), (), (45, 20, 25, 10), (65, 35), (35, 65), (35, 50, 10, 5), (70, 30, 0)),
    ("p10", (70, 30), (70, 10, 20), (), (), (35, 10, 15, 40), (75, 25), (35, 65), (50, 35, 10, 5), ()),
    ("p11", (70, 30), (70, 15, 15), (), (), (55, 10, 15, 20), (80, 20), (20, 80), (45, 45, 5, 5), (70, 30, 0)),
    ("p12", (90, 10), (35, 45, 20), ("py", "js", "ts"), (70, 10, 20), (50, 30, 5, 15), (75, 25), (35, 65), (60, 30, 5, 5), (80, 20, 0)),
    ("p13", (65, 35), (75, 10, 15), (), (), (30, 10, 45, 15), (60, 40), (25, 75), (30, 20, 45, 5), ()),
    ("p14", (70, 30), (65, 15, 20), ("py", "js", "ts"), (70, 10, 20), (25, 10, 20, 45), (85, 15), (40, 60), (55, 25, 15, 5), ()),
    ("p15", (70, 30), (70, 15, 15), (), (), (45, 10, 30, 15), (70, 30), (30, 70), (40, 45, 10, 5), (70, 30, 0)),
    ("p16", (70, 30), (70, 10, 20), ("py", "cpp", "ts"), (80, 10, 10), (30, 10, 50, 10), (70, 30), (35, 65), (25, 15, 55, 5), (80, 20, 0)),
    ("p17", (65, 35), (60, 20, 20), (), (), (25, 15, 45, 15), (60, 40), (35, 65), (35, 45, 15, 5), (80, 20, 0)),
    ("p18", (75, 25), (45, 35, 20), ("py", "cpp", "rs"), (70, 20, 10), (30, 15, 35, 20), (65, 35), (45, 55), (35, 30, 30, 5), ()),
    ("p19", (70, 30), (70, 10, 20), (), (), (40, 15, 35, 10), (70, 30), (40, 60), (45, 35, 15, 5), (55, 20, 25)),
    ("p20", (70, 30), (65, 20, 15), ("py", "js", "ts"), (80, 10, 10), (50, 15, 25, 10), (70, 30), (25, 75), (35, 50, 10, 5), (75, 25, 0)),
)

_DOMAIN_PROFILE_ROWS = (
    ("p01", (("source-export-zip", 70), ("source-ustar", 30))),
    ("p02", (("pcap", 70), ("jsonl-gzip", 30))),
    ("p03", (("pcap", 40), ("evidence-zip", 60))),
    ("p04", (("npz", 70), ("model-metadata-zip", 30))),
    ("p05", (("warehouse-zip", 60), ("csv-gzip", 40))),
    ("p06", (("instrument-export-zip", 70), ("assay-csv-gzip", 30))),
    ("p07", (("tiff-ustar", 60), ("archive-zip", 40))),
    ("p08", (("product-export-zip", 70), ("team-export-ustar", 30))),
    ("p09", (("recording-project-zip", 70), ("session-ustar", 30))),
    ("p10", (("data-room-zip", 80), ("snapshot-ustar", 20))),
    ("p11", (("crm-zip", 60), ("maildir-ustar", 40))),
    ("p12", (("ticket-zip", 70), ("crm-jsonl-gzip", 30))),
    ("p13", (("dms-zip", 70), ("legal-hold-ustar", 30))),
    ("p14", (("erp-csv-gzip", 60), ("close-package-zip", 40))),
    ("p15", (("ats-zip", 60), ("hris-jsonl-gzip", 40))),
    ("p16", (("dicom-part10", 70), ("edc-zip", 30))),
    ("p17", (("ifczip", 70), ("cde-zip", 30))),
    ("p18", (("qms-zip", 60), ("plm-ustar", 40))),
    ("p19", (("course-package-zip", 70), ("lms-ustar", 30))),
    ("p20", (("foia-zip", 70), ("source-drop-ustar", 30))),
)

_FIXED_VARIANT_PROFILES = {
    "ipynb": (("ipynb", 100),),
    "pdf_text": (("pdf-text", 100),),
    "pdf_scan": (("pdf-scan", 100),),
    "docx": (("docx", 100),),
    "xlsx": (("xlsx", 100),),
    "pptx": (("pptx", 100),),
}


class PersonaV2ContractError(ValueError):
    """Raised when the v2 envelope or a projection differs from the contract."""


def _ratio_pairs(names, ratios):
    if not names:
        if ratios:
            raise AssertionError("empty variant names require empty ratios")
        return ()
    if len(names) != len(ratios) or sum(ratios) != 100:
        raise AssertionError("variant ratios must align and sum to 100")
    return tuple(zip(names, ratios))


def _extension_profile(row):
    (
        persona_id,
        md,
        txt,
        code_names,
        code_ratios,
        structured,
        csv,
        html,
        image,
        media,
    ) = row
    return persona_id, {
        "md": _ratio_pairs(("md", "markdown"), md),
        "txt_log": _ratio_pairs(("txt", "log", "jsonl"), txt),
        "code": _ratio_pairs(code_names, code_ratios),
        "structured_text": _ratio_pairs(("json", "yaml", "xml", "sql"), structured),
        "csv_tsv": _ratio_pairs(("csv", "tsv"), csv),
        "html_eml": _ratio_pairs(("html", "eml"), html),
        "image": _ratio_pairs(("png", "jpg", "tif", "bmp"), image),
        "media": _ratio_pairs(("wav", "aiff", "mid"), media) if media else (),
    }


_FAMILY_PERCENTAGES = {
    persona_id: dict(zip(FORMAT_KEYS, values))
    for persona_id, values in _FAMILY_PERCENTAGE_ROWS
}
_EXTENSION_PROFILES = dict(_extension_profile(row) for row in _EXTENSION_PROFILE_ROWS)
_DOMAIN_PROFILES = dict(_DOMAIN_PROFILE_ROWS)


def _variant_metadata(variant_id):
    contributor = {
        "md",
        "markdown",
        "txt",
        "py",
        "rs",
        "ts",
        "go",
        "js",
        "cpp",
        "pdf-text",
    }
    incidental = {
        "log",
        "jsonl",
        "json",
        "yaml",
        "xml",
        "sql",
        "csv",
        "tsv",
        "html",
        "eml",
        "ipynb",
    }
    recognized_media = {
        "md": ("md", "text/markdown"),
        "markdown": ("markdown", "text/markdown"),
        "txt": ("txt", "text/plain"),
        "py": ("py", "text/x-code"),
        "rs": ("rs", "text/x-code"),
        "ts": ("ts", "text/x-code"),
        "go": ("go", "text/x-code"),
        "js": ("js", "text/x-code"),
        "cpp": ("cpp", "text/x-code"),
        "pdf-text": ("pdf", "application/pdf"),
        "pdf-scan": ("pdf", "application/pdf"),
        "png": ("png", "image/png"),
        "jpg": ("jpg", "image/jpeg"),
        "docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "xlsx": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    }
    extension = variant_id
    cli_media_type = "application/octet-stream"
    validator_id = f"validate-{variant_id}-v2"
    if variant_id in recognized_media:
        extension, cli_media_type = recognized_media[variant_id]
    elif variant_id in {"log", "jsonl", "json", "yaml", "xml", "sql", "csv", "tsv", "html", "eml", "ipynb", "tif", "bmp", "wav", "aiff", "mid"}:
        extension = variant_id
    elif variant_id == "pcap":
        extension = "pcap"
        validator_id = "validate-pcap-v2"
    elif variant_id == "npz":
        extension = "npz"
        validator_id = "validate-npz-v2"
    elif variant_id == "dicom-part10":
        extension = "dcm"
        validator_id = "validate-dicom-part10-v2"
    elif variant_id == "ifczip":
        extension = "ifczip"
        validator_id = "validate-ifczip-v2"
    elif variant_id.endswith("-ustar"):
        extension = "tar"
        validator_id = "validate-ustar-v2"
    elif variant_id.endswith("-gzip"):
        extension = "jsonl.gz" if "jsonl" in variant_id else "csv.gz"
        validator_id = "validate-gzip-v2"
    elif variant_id.endswith("-zip"):
        extension = "zip"
        validator_id = "validate-zip-v2"

    if variant_id in contributor:
        gate_role = "contract_contributor"
        disposition = "local_pdf_text" if variant_id == "pdf-text" else "local_text"
        feasibility = "quota-coupled-1-70"
    elif variant_id in incidental:
        gate_role = "incidental_searchable"
        disposition = "incidental_sniff"
        feasibility = "wave-incidental-upper-bounded"
    else:
        gate_role = "raw_only"
        if variant_id in {"pdf-scan", "png", "jpg"}:
            disposition = "awaiting_ocr"
        elif variant_id in {"docx", "xlsx", "pptx"}:
            disposition = "await_conversion"
        else:
            disposition = "unsupported_binary"
        feasibility = "raw-zero-chunks"
    return {
        "extension": extension,
        "implemented_by_validator": False,
        "media_type": cli_media_type,
        "expected_offline_disposition": disposition,
        "feasibility_rule_id": feasibility,
        "gate_role": gate_role,
        "implemented_by_renderer": False,
        "renderer_id": f"persona-v2-{variant_id}-planned",
        "renderer_schema_version": 2,
        "validator_id": validator_id,
        "validator_schema_version": 2,
    }


_ALL_VARIANT_IDS = set()
for profile in _EXTENSION_PROFILES.values():
    for values in profile.values():
        _ALL_VARIANT_IDS.update(variant_id for variant_id, _ in values)
for values in _FIXED_VARIANT_PROFILES.values():
    _ALL_VARIANT_IDS.update(variant_id for variant_id, _ in values)
for values in _DOMAIN_PROFILES.values():
    _ALL_VARIANT_IDS.update(variant_id for variant_id, _ in values)
_VARIANT_CATALOG = {
    variant_id: _variant_metadata(variant_id) for variant_id in sorted(_ALL_VARIANT_IDS)
}
VARIANT_CATALOG = MappingProxyType({
    variant_id: MappingProxyType(dict(metadata))
    for variant_id, metadata in _VARIANT_CATALOG.items()
})


_PERSONA_ROWS = []
for metadata in _PERSONA_METADATA_ROWS:
    (
        persona_id,
        role,
        full_raw_files,
        primary_share_pct,
        formal_dmax,
        representative_primary_scope,
        representative_secondary_scope,
        semantic_filename_example,
        density_class,
    ) = metadata
    _PERSONA_ROWS.append({
        "density_class": density_class,
        "formal_dmax": formal_dmax,
        "format_percentages": copy.deepcopy(_FAMILY_PERCENTAGES[persona_id]),
        "full_raw_files": full_raw_files,
        "persona_id": persona_id,
        "primary_share_pct": primary_share_pct,
        "representative_primary_scope": representative_primary_scope,
        "representative_secondary_scope": representative_secondary_scope,
        "role": role,
        "semantic_filename_example": semantic_filename_example,
    })
PERSONA_IDS = tuple(row["persona_id"] for row in _PERSONA_ROWS)
_PERSONA_BY_ID = {row["persona_id"]: row for row in _PERSONA_ROWS}


_HISTORY_CHECKPOINTS = {
    "full": {
        "W0": (120_000, 0),
        "W1": (120_000, 24_000),
        "W2": (120_000, 24_000),
        "W3": (120_000, 48_000),
        "W4": (120_000, 60_000),
        "W5-pre-purge": (124_800, 64_800),
        "W5-final": (120_000, 60_000),
    },
    "pilot": {
        "W0": (12_000, 0),
        "W1": (12_000, 2_400),
        "W2": (12_000, 2_400),
        "W3": (12_000, 4_800),
        "W4": (12_000, 6_000),
        "W5-pre-purge": (12_480, 6_480),
        "W5-final": (12_000, 6_000),
    },
}
HISTORY_CHECKPOINTS = MappingProxyType({
    profile: MappingProxyType(dict(checkpoints))
    for profile, checkpoints in _HISTORY_CHECKPOINTS.items()
})
_ELIGIBLE_CAPS = {
    "full": {"current": 135_000, "total": 210_000, "base_current": 15_000, "base_total": 30_000},
    "pilot": {"current": 13_500, "total": 21_000, "base_current": 1_500, "base_total": 3_000},
}


def largest_remainder(total, weights):
    """Return a stable Hamilton apportionment for integer-only contract rows."""
    if type(total) is not int or total < 0:
        raise PersonaV2ContractError("allocation total must be a non-negative integer")
    if type(weights) not in (tuple, list) or not weights:
        raise PersonaV2ContractError("allocation weights must be non-empty")
    if any(type(value) is not int or value < 0 for value in weights):
        raise PersonaV2ContractError("allocation weights must be non-negative integers")
    denominator = sum(weights)
    if denominator <= 0:
        if total == 0:
            return tuple(0 for _ in weights)
        raise PersonaV2ContractError("positive allocation requires positive weights")
    numerators = [total * weight for weight in weights]
    counts = [numerator // denominator for numerator in numerators]
    remaining = total - sum(counts)
    order = sorted(
        range(len(weights)),
        key=lambda index: (-(numerators[index] % denominator), index),
    )
    for index in order[:remaining]:
        counts[index] += 1
    return tuple(counts)


def _resolve_persona(persona_id):
    if type(persona_id) is not str or persona_id not in _PERSONA_BY_ID:
        raise PersonaV2ContractError(f"unknown v2 persona: {persona_id!r}")
    return _PERSONA_BY_ID[persona_id]


def get_persona(persona_id):
    return copy.deepcopy(_resolve_persona(persona_id))


def profile_file_count(persona_id, profile):
    persona = _resolve_persona(persona_id)
    if profile == "tiny-smoke":
        return 200
    if profile == "pilot":
        if persona["full_raw_files"] % 10:
            raise PersonaV2ContractError(
                f"pilot requires exact one-tenth file projection: {persona_id}"
            )
        return persona["full_raw_files"] // 10
    if profile == "full":
        return persona["full_raw_files"]
    raise PersonaV2ContractError(f"unknown v2 profile: {profile!r}")


def family_counts(persona_id, profile):
    persona = _resolve_persona(persona_id)
    total = profile_file_count(persona_id, profile)
    weights = tuple(persona["format_percentages"][family] for family in FORMAT_KEYS)
    return dict(zip(FORMAT_KEYS, largest_remainder(total, weights)))


def _variant_profile(persona_id, family):
    if family in _EXTENSION_PROFILES[persona_id]:
        return _EXTENSION_PROFILES[persona_id][family]
    if family in _FIXED_VARIANT_PROFILES:
        return _FIXED_VARIANT_PROFILES[family]
    if family == "domain_binary":
        return _DOMAIN_PROFILES[persona_id]
    raise PersonaV2ContractError(f"missing v2 variant profile: {persona_id}/{family}")


def variant_counts(persona_id, profile):
    _resolve_persona(persona_id)
    totals = family_counts(persona_id, profile)
    result = {}
    for family in FORMAT_KEYS:
        ratio_rows = _variant_profile(persona_id, family)
        if not ratio_rows:
            if totals[family] != 0:
                raise PersonaV2ContractError(f"non-zero family lacks variants: {persona_id}/{family}")
            result[family] = ()
            continue
        ratios = tuple(ratio for _, ratio in ratio_rows)
        if sum(ratios) != 100:
            raise PersonaV2ContractError(f"variant ratios do not sum to 100: {persona_id}/{family}")
        counts = largest_remainder(totals[family], ratios)
        if profile == "pilot":
            full_total = family_counts(persona_id, "full")[family]
            full_counts = largest_remainder(full_total, ratios)
            if any(pilot > full for pilot, full in zip(counts, full_counts)):
                raise PersonaV2ContractError(
                    f"pilot variant count exceeds full reservation: {persona_id}/{family}"
                )
        rows = []
        for (variant_id, ratio), count in zip(ratio_rows, counts):
            metadata = _VARIANT_CATALOG[variant_id]
            rows.append({
                "count": count,
                "expected_offline_disposition": metadata["expected_offline_disposition"],
                "gate_role": metadata["gate_role"],
                "ratio_pct": ratio,
                "variant_id": variant_id,
            })
        result[family] = tuple(rows)
    return result


def contributor_count(persona_id, profile):
    rows = variant_counts(persona_id, profile)
    return sum(
        row["count"]
        for family in FORMAT_KEYS
        for row in rows[family]
        if row["gate_role"] == "contract_contributor"
    )


def density_bucket_counts(persona_id, profile):
    if profile not in ("pilot", "full"):
        raise PersonaV2ContractError("density contract applies only to pilot and full")
    persona = _resolve_persona(persona_id)
    counts = largest_remainder(
        contributor_count(persona_id, profile),
        _DENSITY_PROFILES[persona["density_class"]],
    )
    return dict(zip(DENSITY_BUCKET_ORDER, counts))


def density_chunk_interval(persona_id, profile):
    counts = density_bucket_counts(persona_id, profile)
    lower = sum(counts[bucket] * _DENSITY_BUCKET_BOUNDS[bucket][0] for bucket in DENSITY_BUCKET_ORDER)
    upper = sum(counts[bucket] * _DENSITY_BUCKET_BOUNDS[bucket][1] for bucket in DENSITY_BUCKET_ORDER)
    return lower, upper


def history_cohort_chunk_counts(profile):
    if profile not in _PROFILE_TARGET_CHUNKS:
        raise PersonaV2ContractError(
            f"history cohort contract applies only to pilot/full: {profile!r}"
        )
    counts = largest_remainder(
        _PROFILE_TARGET_CHUNKS[profile],
        tuple(_HISTORY_COHORT_WEIGHTS_PCT[cohort] for cohort in HISTORY_COHORT_ORDER),
    )
    return dict(zip(HISTORY_COHORT_ORDER, counts))


def history_cohort_source_lower_bounds(profile):
    chunks = history_cohort_chunk_counts(profile)
    return {
        cohort: max(
            REQUIRED_HISTORY_SCOPE_COUNT
            if cohort in REQUIRED_SCOPE_HISTORY_COHORTS
            else 0,
            (
                chunks[cohort] + MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE - 1
            )
            // MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE,
        )
        for cohort in HISTORY_COHORT_ORDER
    }


def incidental_caps(profile, checkpoint):
    if profile not in _HISTORY_CHECKPOINTS or checkpoint not in _HISTORY_CHECKPOINTS[profile]:
        raise PersonaV2ContractError(f"unknown v2 checkpoint: {profile}/{checkpoint}")
    current, history = _HISTORY_CHECKPOINTS[profile][checkpoint]
    caps = _ELIGIBLE_CAPS[profile]
    return {
        "current": min(caps["base_current"], caps["current"] - current),
        "current_plus_history": min(caps["base_total"], caps["total"] - current - history),
    }


def _incidental_cap_contract_json():
    return {
        "eligible_caps": copy.deepcopy(_ELIGIBLE_CAPS),
        "rule_id": "min-base-and-contract-headroom-v1",
        "rules": {
            "current": "min(base_current,current_eligible-current_contract_chunks)",
            "current_plus_history": (
                "min(base_total,total_eligible-current_contract_chunks-"
                "history_only_contract_chunks)"
            ),
        },
    }


def _variant_profile_json(persona_id):
    return {
        family: [
            {"ratio_pct": ratio, "variant_id": variant_id}
            for variant_id, ratio in _variant_profile(persona_id, family)
        ]
        for family in FORMAT_KEYS
    }


def _checkpoint_json():
    return {
        profile: {
            checkpoint: {
                "current_contract_chunks": values[0],
                "history_only_contract_chunks": values[1],
            }
            for checkpoint, values in rows.items()
        }
        for profile, rows in _HISTORY_CHECKPOINTS.items()
    }


def _history_cohort_contract_json():
    profile_source_lower_bounds = {}
    for profile in ("pilot", "full"):
        chunks = history_cohort_chunk_counts(profile)
        lower = history_cohort_source_lower_bounds(profile)
        profile_source_lower_bounds[profile] = {
            "cohorts": [
                {
                    "cohort_id": cohort,
                    "contract_contributor_chunks": chunks[cohort],
                    "coverage_source_lower_bound": (
                        REQUIRED_HISTORY_SCOPE_COUNT
                        if cohort in REQUIRED_SCOPE_HISTORY_COHORTS
                        else 0
                    ),
                    "necessary_source_lower_bound": lower[cohort],
                    "quota_source_lower_bound": (
                        chunks[cohort] + MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE - 1
                    )
                    // MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE,
                }
                for cohort in HISTORY_COHORT_ORDER
            ],
            "minimum_contributor_sources": sum(lower.values()),
            "target_contract_contributor_chunks": _PROFILE_TARGET_CHUNKS[profile],
        }
    return {
        "allocation_unit": "contract_contributor_chunks",
        "cohort_order": list(HISTORY_COHORT_ORDER),
        "coverage_required_in_all_twenty_scopes": list(
            REQUIRED_SCOPE_HISTORY_COHORTS
        ),
        "max_chunks_per_contributor_source": MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE,
        "partition": "whole_source",
        "profile_source_lower_bounds": profile_source_lower_bounds,
        "profiles": ["pilot", "full"],
        "required_scope_count": REQUIRED_HISTORY_SCOPE_COUNT,
        "source_lower_bound_formula": (
            "max(required_scope_count_if_covered_else_zero,"
            "ceil(cohort_chunks/max_chunks_per_contributor_source))"
        ),
        "weights_pct": copy.deepcopy(_HISTORY_COHORT_WEIGHTS_PCT),
    }


def build_envelope_contract():
    """Build a detached, root-independent envelope; never a G0 completion receipt."""
    personas = []
    for persona_id in PERSONA_IDS:
        persona = get_persona(persona_id)
        persona["variant_profiles"] = _variant_profile_json(persona_id)
        personas.append(persona)
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "filesystem_writer_available": False,
            "formal_capacity_gate_satisfied": False,
            "history_executor_available": False,
            "kcs_execution_available": False,
            "query_instances_rendered": False,
            "query_spec_hashed": False,
            "renderer_available": False,
        },
        "apportionment_contract": {
            "algorithm_id": APPORTIONMENT_ALGORITHM_ID,
            "tie_break": APPORTIONMENT_TIE_BREAK,
        },
        "blockers": [
            "bounded_framed_loader_and_exact_dispatch_missing",
            "exact_topology_sidecar_not_bound_by_g0_root",
            "joint_scope_variant_density_quota_solver_missing",
            "persona_fidelity_realism_profile_and_overlay_missing",
            "source_recipe_fact_oracle_and_query_spec_missing",
            "root_independent_history_intent_missing",
            "variant_complexity_units_and_feasibility_parameters_missing",
            "versioned_lane_spec_hashes_missing",
        ],
        "canonical_limits": {
            "integer_only": True,
            "max_envelope_bytes": MAX_ENVELOPE_BYTES,
            "max_nesting_depth": MAX_CANONICAL_DEPTH,
            "max_string_bytes": MAX_CANONICAL_STRING_BYTES,
            "unicode_normalization": "NFC",
        },
        "capacity": {
            "byte_stress_cap_per_person": 768 * 2**20,
            "byte_stress_payload_per_person": 740 * 2**20,
            "byte_stress_suite_cap_bytes": 15 * 2**30,
            "formal_retained_suite_bytes": 88 * 2**30,
            "formal_w0_person_bytes": 512 * 2**20,
            "formal_w0_replay_bytes": 10 * 2**30,
            "pilot_byte_cap": 32 * 2**30,
            "pilot_inode_cap": 250_000,
            "pilot_reserve_bytes": 96 * 2**30,
            "w5_final_person_bytes": 5 * 2**30 // 4,
            "w5_final_replay_bytes": 25 * 2**30,
            "w5_pre_purge_person_bytes_floor": 27 * 2**30 // 20,
            "w5_pre_purge_replay_bytes": 27 * 2**30,
        },
        "density_profiles": {
            profile_id: {
                bucket: percentage
                for bucket, percentage in zip(DENSITY_BUCKET_ORDER, percentages)
            }
            for profile_id, percentages in _DENSITY_PROFILES.items()
        },
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "history_checkpoints": _checkpoint_json(),
        "history_cohort_contract": _history_cohort_contract_json(),
        "incidental_cap_contract": _incidental_cap_contract_json(),
        "lanes": {
            "formal-retrieval-history-v2": {
                "formal_chunk_eligible": True,
                "history": "W0-W5",
                "replay_count": 3,
            },
            "recursive-robustness-v1": {
                "formal_chunk_eligible": False,
                "history": "separate-intent",
                "replay_count": 1,
            },
            "byte-stress-v1": {
                "formal_chunk_eligible": False,
                "history": "none",
                "replay_count": 1,
            },
        },
        "personas": personas,
        "pilot_projection": {
            "direction": "solve-pilot-first-then-embed-unchanged-into-full",
            "full_file_total": 203_000,
            "immutable_source_fields": [
                "source_id",
                "materialization_id",
                "scope_key",
                "family",
                "variant_id",
                "gate_role",
                "density_bucket",
                "requested_contributor_chunks",
                "history_cohort",
                "recipe_references",
                "semantic_basename",
                "target_complexity",
                "target_bytes",
                "payload_seed",
            ],
            "pilot_file_total": 20_300,
            "requires_strict_source_subset": True,
        },
        "profiles": {
            "tiny-smoke": {"density_contract": False, "suite_files": 4_000, "target_kind": "three-per-contributor"},
            "pilot": {"density_contract": True, "suite_files": 20_300, "target_chunks_per_person": _PROFILE_TARGET_CHUNKS["pilot"]},
            "full": {"density_contract": True, "suite_files": 203_000, "target_chunks_per_person": _PROFILE_TARGET_CHUNKS["full"]},
        },
        "topology_status": "exact-topology-external-sidecar-not-g0-bound",
        "variant_catalog": copy.deepcopy(_VARIANT_CATALOG),
        "variant_catalog_complete": False,
    }
    return value


def _validate_canonical_value(value, depth=0):
    if depth > MAX_CANONICAL_DEPTH:
        raise PersonaV2ContractError("v2 envelope exceeds canonical nesting depth")
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        if len(value.encode("utf-8")) > MAX_CANONICAL_STRING_BYTES:
            raise PersonaV2ContractError("v2 envelope string exceeds byte bound")
        if unicodedata.normalize("NFC", value) != value:
            raise PersonaV2ContractError("v2 envelope strings must be NFC")
        return
    if type(value) is list:
        for item in value:
            _validate_canonical_value(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise PersonaV2ContractError("v2 envelope object keys must be strings")
            _validate_canonical_value(key, depth + 1)
            _validate_canonical_value(item, depth + 1)
        return
    raise PersonaV2ContractError(f"unsupported v2 envelope value type: {type(value).__name__}")


def canonical_json_bytes(value):
    _validate_canonical_value(value)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise PersonaV2ContractError("v2 envelope exceeds framed byte bound")
    return encoded


def validate_envelope_contract(value):
    if type(value) is not dict:
        raise PersonaV2ContractError("v2 envelope must be an object")
    actual_raw = canonical_json_bytes(value)
    expected = build_envelope_contract()
    if actual_raw != canonical_json_bytes(expected):
        raise PersonaV2ContractError("v2 envelope differs from canonical regeneration")
    return True


def envelope_contract_sha256(value=None):
    if value is None:
        value = build_envelope_contract()
    validate_envelope_contract(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_frozen_g0_contract():
    raise PersonaV2ContractError(
        "v2 envelope is not frozen and can never be a G0 root: topology binding, joint allocation, recipes, history intent, and oracle remain missing"
    )


def _validate_static_rows():
    if PERSONA_IDS != tuple(f"p{i:02d}" for i in range(1, 21)):
        raise AssertionError("v2 persona rows are missing or reordered")
    if set(_FAMILY_PERCENTAGES) != set(PERSONA_IDS):
        raise AssertionError("v2 family rows differ from persona rows")
    if set(_EXTENSION_PROFILES) != set(PERSONA_IDS):
        raise AssertionError("v2 extension rows differ from persona rows")
    if set(_DOMAIN_PROFILES) != set(PERSONA_IDS):
        raise AssertionError("v2 domain rows differ from persona rows")
    for persona_id in PERSONA_IDS:
        if _PERSONA_BY_ID[persona_id]["full_raw_files"] % 10:
            raise AssertionError(f"v2 pilot file projection is not exact: {persona_id}")
        if sum(_FAMILY_PERCENTAGES[persona_id].values()) != 100:
            raise AssertionError(f"v2 family ratios do not sum to 100: {persona_id}")
        for family in FORMAT_KEYS:
            ratios = _variant_profile(persona_id, family)
            if _FAMILY_PERCENTAGES[persona_id][family] and sum(value for _, value in ratios) != 100:
                raise AssertionError(f"v2 variant ratios do not sum to 100: {persona_id}/{family}")
        example = _PERSONA_BY_ID[persona_id]["semantic_filename_example"]
        if len(example.encode("ascii")) > 120 or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", example) is None:
            raise AssertionError(f"invalid v2 semantic filename example: {persona_id}")
    for profile, target in (("pilot", 12_000), ("full", 120_000)):
        cohort_source_lower = sum(
            history_cohort_source_lower_bounds(profile).values()
        )
        for persona_id in PERSONA_IDS:
            lower, upper = density_chunk_interval(persona_id, profile)
            if not lower <= target <= upper:
                raise AssertionError(f"v2 density interval is infeasible: {persona_id}/{profile}")
            if contributor_count(persona_id, profile) < cohort_source_lower:
                raise AssertionError(
                    "v2 contributor inventory cannot satisfy whole-source cohort lower: "
                    f"{persona_id}/{profile}"
                )


_validate_static_rows()
