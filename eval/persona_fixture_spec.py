"""Deterministic specification for twenty independent synthetic PC owners.

This is intentionally separate from the Rust-only ``kio-eval scale`` fixture.
One row here is
one person, one PC umbrella, one isolated registry, and twenty direct-file Kio
scopes.  Ratios count W0 physical files; searchable chunk targets are a
separate contract.
"""

from pathlib import PurePosixPath
import re


SCHEMA_VERSION = 1
SEED = 20260713
FIXTURE_ID = "kio-persona-pc-v1"
FORMAL_CURRENT_CHUNKS_PER_PERSON = 120_000
EXPLORATORY_MINIMUM_CHUNKS = 100_001
FORMAL_HISTORY_CHUNKS_PER_PERSON = 180_000
PILOT_RAW_FILES_PER_PERSON = 1_000
PILOT_CURRENT_CHUNKS_PER_PERSON = 12_000
# One physical file per percentage point was initially attractive, but the
# finance-controller mix then contained only 19 stable contributor sources.
# That cannot satisfy twenty non-zero leaf-scope chunk targets.  Two files per
# percentage point keeps the exact percentage matrix while making every tiny
# persona jointly allocatable across all twenty scopes.
TINY_RAW_FILES_PER_PERSON = 200
REPLAY_COUNT = 3
MAX_DIRECT_FILES_PER_SCOPE = 9_000
MAX_CONTRIBUTOR_CHUNKS_PER_FILE = 72
MIN_SCOPES_AT_DEPTH_FOUR = 60
MIN_PERSONAS_WITH_DEPTH_FIVE = 10
MIN_MAXIMUM_SCOPE_DEPTH = 6

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

FORMAT_VARIANTS = {
    "md": (("md", 70, "contract_contributor", "local_text"),
           ("markdown", 30, "contract_contributor", "local_text")),
    "txt_log": (("txt", 70, "contract_contributor", "local_text"),
                ("log", 20, "incidental_searchable", "incidental_sniff"),
                ("jsonl", 10, "incidental_searchable", "incidental_sniff")),
    "code": (("py", 34, "contract_contributor", "local_text"),
             ("rs", 33, "contract_contributor", "local_text"),
             ("ts", 33, "contract_contributor", "local_text")),
    "structured_text": (("json", 35, "incidental_searchable", "incidental_sniff"),
                        ("yaml", 25, "incidental_searchable", "incidental_sniff"),
                        ("xml", 20, "incidental_searchable", "incidental_sniff"),
                        ("sql", 20, "incidental_searchable", "incidental_sniff")),
    "csv_tsv": (("csv", 70, "incidental_searchable", "incidental_sniff"),
                ("tsv", 30, "incidental_searchable", "incidental_sniff")),
    "html_eml": (("html", 60, "incidental_searchable", "incidental_sniff"),
                 ("eml", 40, "incidental_searchable", "incidental_sniff")),
    "ipynb": (("ipynb", 100, "incidental_searchable", "incidental_sniff"),),
    "pdf_text": (("pdf-text", 100, "contract_contributor", "local_pdf_text"),),
    "pdf_scan": (("pdf-scan", 100, "raw_only", "awaiting_ocr"),),
    "docx": (("docx", 100, "raw_only", "await_conversion"),),
    "xlsx": (("xlsx", 100, "raw_only", "await_conversion"),),
    "pptx": (("pptx", 100, "raw_only", "await_conversion"),),
    "image": (("png", 100, "raw_only", "awaiting_ocr"),),
    "media": (("wav", 100, "raw_only", "unsupported_binary"),),
    "domain_binary": (("pcap", 100, "raw_only", "unsupported_binary"),),
}

PRIMARY_SCOPE_WEIGHTS_PCT = (10, 9, 8, 8, 7, 6, 6, 5, 5, 4, 4, 3)
SECONDARY_SCOPE_WEIGHTS_PCT = (5, 4, 4, 3, 3, 2, 2, 2)

SECONDARY_PATHS = (
    "desktop/working",
    "documents/reference",
    "downloads/inbox",
    "downloads/exports",
    "cloud/my-files",
    "cloud/team-shared",
    "mail/recent",
    "archive/closed",
)

# These are mutually exclusive whole-source contract-contributor cohorts, not
# physical-file percentages.  P/X/Y/N are jointly selected by indivisible
# planned source quota; U is the arithmetic control remainder.  In tiny, Y is
# the residual of the rounded W1 target so independent integer rounding cannot
# drift from the checkpoint total.
HISTORY_COHORT_KEYS = ("P", "X", "Y", "N", "U")
HISTORY_COHORT_FULL_PCT = {
    "P": 4,   # W1 edit -> W5 path purge and replacement
    "X": 10,  # W1 edit -> W3 edit -> W4 delete and replacement
    "Y": 6,   # W1 edit -> W3 edit -> remains current
    "N": 4,   # W3 edit -> W5 correction
    "U": 76,  # arithmetic control / safe same-scope sentinels
}
HISTORY_COHORT_ASSIGNMENT_EXECUTABLE = True
HISTORY_STRUCTURAL_ASSIGNMENT_EXECUTABLE = True
HISTORY_EVENT_MANIFEST_EXECUTABLE = True
HISTORY_ASSIGNMENT_EXECUTABLE = False
HISTORY_ASSIGNMENT_BLOCKER = (
    "source-level cohort and quota-neutral structural allocations are available, "
    "but W0 history preparation and the replay lock/journal/safe-mutation "
    "boundary are not executable"
)

WAVES = (
    {"id": "W0", "purpose": "baseline", "operations": ("create", "index")},
    {"id": "W1", "purpose": "daily-work", "operations": ("create", "edit", "rename", "move")},
    {"id": "W2", "purpose": "reorganization", "operations": ("rename", "move")},
    {"id": "W3", "purpose": "milestone", "operations": ("edit", "duplicate", "derive")},
    {"id": "W4", "purpose": "closure", "operations": ("archive", "delete", "create")},
    {"id": "W5", "purpose": "retention", "operations": ("edit", "restore", "purge", "create")},
)

EVENT_BOUNDARIES = ("index_auto", "purged_commit", "index_noop", "none")

# These are routing constraints, not new format ratios.  The generator scores
# scope path components against these tokens before applying stable tie-breaks.
FORMAT_ROUTE_HINTS = {
    "code": ("repos", "infrastructure", "services", "analytics", "soc", "experiments"),
    "structured_text": ("configs", "exports", "analytics", "soc", "data", "infrastructure"),
    "csv_tsv": ("exports", "results", "analytics", "reports", "surveys", "erp"),
    "html_eml": ("mail", "correspondence", "calls", "support", "customers", "sources"),
    "ipynb": ("notebooks", "analysis", "experiments", "statistics", "analytics"),
    "pdf_text": ("papers", "reports", "reference", "guidance", "contracts", "readings"),
    "pdf_scan": ("scans", "archive", "foia", "sources", "invoices", "certificates"),
    "docx": ("drafts", "proposals", "policies", "protocols", "plans", "deliverables"),
    "xlsx": ("forecasts", "budget", "close", "results", "exports", "models"),
    "pptx": ("presentations", "lectures", "qbr", "board", "deliverables", "meetings"),
    "image": ("figures", "drawings", "design", "site-reports", "sources", "findings"),
    "media": ("recordings", "transcripts", "calls", "interviews", "media"),
    "domain_binary": ("bim", "instruments", "siem", "erp", "warehouse", "drawings"),
}

# These sets describe the current production CLI's offline index accounting;
# they are not searchability claims.  In particular a text-layer PDF is both
# normalized locally and queued for optional online enhancement, so the sets
# intentionally overlap.  Persona prepare/attestation must validate these
# mixed-format counters rather than reuse the all-text scale assumptions.
OFFLINE_NORMALIZED_FAMILIES = (
    "md",
    "txt_log",
    "code",
    "structured_text",
    "csv_tsv",
    "html_eml",
    "ipynb",
    "pdf_text",
)
OFFLINE_PENDING_FAMILIES = (
    "pdf_text",
    "pdf_scan",
    "docx",
    "xlsx",
    "pptx",
    "image",
)
OFFLINE_SKIPPED_BINARY_FAMILIES = ("media", "domain_binary")


# Persona fidelity is planning metadata.  It records which kind of PC each
# synthetic owner is intended to resemble; it does not claim that the current
# portable renderer emulates the declared OS, observed a live user population,
# connected to a sync service, or made any raw Office/binary source searchable.
FIDELITY_SCHEMA_VERSION = 1
FIDELITY_PROFILE_KEYS = (
    "persona_id",
    "profile_id",
    "os_semantics",
    "os_execution_mode",
    "device_class",
    "locale",
    "languages",
    "work_style",
    "synthetic_snapshot_or_export_sources",
    "source_mode",
    "live_sync",
    "sensitivity_tiers",
    "nesting_model",
    "size_profile",
    "domain_binary_raw_only_profile",
    "hypothesis_only",
    "synthetic_only",
    "searchability_claim",
    "contains_real_pii",
    "contains_real_phi",
    "contains_real_credentials",
)
FIDELITY_HYPOTHESIS_STATUS = "initial-hypothesis-not-observed-user-statistics"
OS_EXECUTION_MODE = "declared-target-metadata-only-not-native-or-emulated"
SYNTHETIC_SOURCE_MODE = "synthetic-snapshot-or-export-only"
NO_SEARCHABILITY_CLAIM = "none"
SENSITIVITY_TIERS = ("S0", "S1", "S2", "S3")
OS_SEMANTICS = (
    "macos-apfs-case-insensitive",
    "ubuntu-ext4-case-sensitive",
    "windows-ntfs-case-insensitive",
    "chromeos-derived-portable-snapshot",
)

# The common envelope is a frozen initial hypothesis, not a generated or
# measured distribution.  Persona-specific overrides are deliberately still
# marked planned below, and none of these rows grants searchability to a raw
# format family.
SIZE_BUCKET_ORDER = ("small", "medium", "large", "tail")
SIZE_COMPLEXITY_PROFILE_ID = "kio-persona-common-size-complexity-v1"
_SIZE_COMPLEXITY_ROWS = (
    (
        "text_code_chunks",
        "chunks",
        ("md", "txt_log", "code", "structured_text", "csv_tsv", "html"),
        ((1, 4), (5, 20), (21, 50), (51, 72)),
        (55, 30, 12, 3),
    ),
    (
        "pdf_text_pages",
        "pages",
        ("pdf_text",),
        ((1, 5), (6, 30), (31, 200), (201, None)),
        (40, 35, 20, 5),
    ),
    (
        "eml_attachments",
        "attachments",
        ("eml",),
        ((0, 0), (1, 1), (2, 5), (6, None)),
        (65, 25, 9, 1),
    ),
    (
        "xlsx_sheets",
        "sheets",
        ("xlsx",),
        ((1, 1), (2, 5), (6, 20), (21, None)),
        (45, 40, 13, 2),
    ),
    (
        "pptx_slides",
        "slides",
        ("pptx",),
        ((1, 10), (11, 40), (41, 100), (101, None)),
        (45, 40, 13, 2),
    ),
    (
        "image_media_domain_bytes",
        "bytes",
        ("image", "media", "domain_binary"),
        (
            (0, 256 * 1024 - 1),
            (256 * 1024, 4 * 1024 * 1024 - 1),
            (4 * 1024 * 1024, 64 * 1024 * 1024 - 1),
            (64 * 1024 * 1024, 100 * 1024 * 1024),
        ),
        (35, 40, 20, 5),
    ),
)


def _size_bucket_contract(ranges, percentages):
    return tuple(
        {
            "bucket": bucket,
            "minimum_inclusive": lower,
            "maximum_inclusive": upper,
            "percentage": percentage,
        }
        for bucket, (lower, upper), percentage in zip(
            SIZE_BUCKET_ORDER, ranges, percentages
        )
    )


COMMON_SIZE_COMPLEXITY_BUCKETS = {
    profile_id: {
        "unit": unit,
        "applies_to": applies_to,
        "buckets": _size_bucket_contract(ranges, percentages),
        "hypothesis_only": True,
        "implemented_by_renderer": False,
        "searchability_claim": NO_SEARCHABILITY_CLAIM,
    }
    for profile_id, unit, applies_to, ranges, percentages
    in _SIZE_COMPLEXITY_ROWS
}


def _paths(value):
    return tuple(value.split())


_PERSONA_ROWS = (
    ("p01", "software-engineer", 12_000, (22, 8, 28, 12, 3, 5, 1, 7, 1, 3, 2, 2, 3, 0, 3), _paths("""
        documents/work/product-alpha/architecture documents/work/product-alpha/api-contracts
        documents/work/product-alpha/release-notes documents/work/product-beta/architecture
        documents/work/product-beta/api-contracts repos/product-alpha/docs repos/product-beta/docs
        work-items/decision-records work-items/code-reviews meetings/engineering
        vendor-docs/platforms operations/migration-notes
    """)),
    ("p02", "site-reliability-engineer", 15_000, (20, 22, 15, 20, 5, 3, 0, 4, 0, 2, 1, 1, 2, 0, 5), _paths("""
        documents/operations/runbooks documents/operations/postmortems infrastructure/kubernetes
        infrastructure/terraform services/checkout/prod/oncall/operations services/identity/prod/oncall/operations
        observability/alerts observability/dashboards observability/log-exports changes/deployments
        capacity/reports meetings/operations
    """)),
    ("p03", "security-grc-analyst", 10_000, (10, 12, 8, 15, 10, 8, 0, 15, 5, 5, 4, 2, 3, 0, 3), _paths("""
        security/threat-models security/pentest-reports security/vulnerabilities
        security/incident-reports compliance/policies compliance/control-evidence
        compliance/audit-requests vendor-risk/questionnaires soc/siem-exports
        soc/detection-rules privacy/risk-assessments meetings/security-reviews
    """)),
    ("p04", "ml-research-engineer", 10_000, (12, 7, 18, 10, 12, 2, 12, 12, 1, 2, 3, 3, 5, 0, 1), _paths("""
        research/papers research/literature-notes research/programs/model-alpha/experiments/configs
        research/programs/model-alpha/experiments/results research/programs/model-beta/experiments/configs research/programs/model-beta/experiments/results
        notebooks/exports datasets/cards models/model-cards evaluations/benchmarks
        presentations/lab-meetings repos/ml-project/docs
    """)),
    ("p05", "bi-data-analyst", 12_000, (8, 5, 6, 14, 20, 5, 5, 5, 1, 3, 15, 4, 3, 0, 6), _paths("""
        analytics/sql/production analytics/sql/ad-hoc analytics/data-dictionary analytics/lineage
        dashboards/sales dashboards/product reports/weekly reports/monthly forecasts/scenarios
        requests/stakeholder exports/warehouse meetings/metric-reviews
    """)),
    ("p06", "life-science-researcher", 8_000, (6, 6, 3, 5, 15, 2, 3, 18, 8, 8, 8, 5, 9, 0, 4), _paths("""
        lab/lab-notebooks lab/protocols programs/study-alpha/2026/cohort-a/raw-exports
        programs/study-alpha/2026/cohort-a/analysis programs/study-beta/2026/cohort-b/raw-exports
        programs/study-beta/2026/cohort-b/analysis instruments/calibration samples/manifests literature/papers
        grants/applications figures/manuscript meetings/lab
    """)),
    ("p07", "humanities-researcher", 7_000, (12, 10, 0, 4, 3, 5, 0, 25, 20, 10, 1, 2, 6, 1, 1), _paths("""
        research/primary-sources research/archive-scans research/ocr-transcripts
        research/bibliography-exports notes/source-annotations notes/literature
        dissertation/chapter-01 dissertation/chapter-02 dissertation/appendices
        translations/working conferences/presentations correspondence/archive-requests
    """)),
    ("p08", "product-manager", 8_000, (10, 4, 1, 5, 8, 8, 0, 13, 3, 15, 8, 15, 7, 1, 2), _paths("""
        portfolio/product-alpha/2026/q3/prds portfolio/product-alpha/2026/q3/discovery portfolio/product-beta/2026/q4/prds
        portfolio/product-beta/2026/q4/discovery roadmap/quarterly roadmap/dependencies
        customer-feedback/interviews customer-feedback/support-summaries analytics/product-metrics
        launches/release-plans decisions/meeting-notes research/market
    """)),
    ("p09", "ux-researcher", 9_000, (8, 15, 0, 4, 8, 3, 0, 10, 4, 12, 4, 8, 15, 7, 2), _paths("""
        research/study-alpha/plans research/study-alpha/transcripts research/study-alpha/findings
        research/study-beta/plans research/study-beta/transcripts research/study-beta/findings
        surveys/results design/prototype-specs design/figma-exports personas/journey-maps
        recordings/transcript-sidecars consent/synthetic-records
    """)),
    ("p10", "management-consultant", 7_000, (4, 4, 0, 2, 8, 6, 0, 18, 5, 12, 18, 18, 3, 0, 2), _paths("""
        engagements/client-alpha/2026/phase-1/data-room engagements/client-alpha/2026/phase-1/interviews engagements/client-alpha/2026/phase-1/analysis
        engagements/client-alpha/2026/phase-1/deliverables engagements/client-beta/2026/phase-2/data-room engagements/client-beta/2026/phase-2/interviews
        engagements/client-beta/2026/phase-2/analysis engagements/client-beta/2026/phase-2/deliverables proposals/active
        benchmarks/industry templates/consulting meetings/internal-reviews
    """)),
    ("p11", "account-executive", 10_000, (3, 4, 0, 2, 5, 25, 0, 16, 4, 14, 7, 10, 5, 3, 2), _paths("""
        accounts/account-alpha/plans accounts/account-alpha/calls accounts/account-alpha/proposals
        accounts/account-beta/plans accounts/account-beta/calls accounts/account-beta/proposals
        opportunities/pipeline rfp/responses pricing/approved contracts/drafts contracts/executed
        travel/meeting-notes
    """)),
    ("p12", "support-success-lead", 16_000, (15, 20, 4, 15, 12, 12, 0, 5, 1, 3, 2, 1, 7, 1, 2), _paths("""
        support/ticket-exports support/escalations support/known-issues knowledge-base/drafts
        knowledge-base/published customers/customer-alpha/qbr customers/customer-alpha/case-history
        customers/customer-beta/qbr customers/customer-beta/case-history logs/customer-attachments
        macros/replies incidents/support-links
    """)),
    ("p13", "corporate-privacy-counsel", 7_000, (3, 4, 0, 1, 2, 14, 0, 28, 15, 22, 3, 2, 3, 0, 3), _paths("""
        matters/matter-alpha/correspondence matters/matter-alpha/working
        matters/matter-beta/correspondence matters/matter-beta/working contracts/drafts
        contracts/executed contracts/templates regulations/guidance policies/privacy
        due-diligence/data-room legal-hold/notices board/legal-reports
    """)),
    ("p14", "finance-controller", 9_000, (3, 3, 1, 4, 15, 5, 0, 13, 8, 8, 27, 7, 3, 0, 3), _paths("""
        finance/close/2026/q1/2026-01 finance/close/2026/q1/2026-02 finance/close/2026/q1/2026-03 budget/annual forecasts/base-case
        forecasts/scenarios invoices/vendor expenses/department audit/evidence board/finance-packs
        models/operating-model erp/exports
    """)),
    ("p15", "recruiter-people-ops", 8_000, (4, 5, 0, 2, 7, 15, 0, 20, 8, 20, 8, 3, 5, 1, 2), _paths("""
        recruiting/requisition-alpha/candidates recruiting/requisition-alpha/interviews
        recruiting/requisition-beta/candidates recruiting/requisition-beta/interviews recruiting/offers
        people/policies people/headcount people/performance-synthetic people/surveys-synthetic
        learning/training compensation/bands compliance/retention
    """)),
    ("p16", "clinical-researcher", 8_000, (5, 6, 1, 4, 10, 4, 1, 24, 12, 10, 8, 5, 6, 1, 3), _paths("""
        clinical/studies/study-alpha/2026/protocols clinical/studies/study-alpha/2026/synthetic-cases clinical/studies/study-alpha/2026/results
        clinical/studies/study-beta/2026/protocols clinical/studies/study-beta/2026/synthetic-cases clinical/studies/study-beta/2026/results
        guidelines/clinical literature/papers regulatory/submissions
        safety/adverse-events-synthetic statistics/analysis presentations/grand-rounds
    """)),
    ("p17", "construction-project-manager", 8_000, (3, 4, 0, 2, 5, 4, 0, 20, 12, 8, 10, 4, 12, 1, 15), _paths("""
        portfolio/projects/project-alpha/2026/construction/drawings portfolio/projects/project-alpha/2026/construction/specifications portfolio/projects/project-alpha/2026/construction/rfi
        portfolio/projects/project-alpha/2026/construction/submittals portfolio/projects/project-alpha/2026/construction/change-orders
        portfolio/projects/project-alpha/2026/construction/site-reports portfolio/projects/project-beta/2026/construction/drawings
        portfolio/projects/project-beta/2026/construction/specifications portfolio/projects/project-beta/2026/construction/rfi portfolio/projects/project-beta/2026/construction/submittals
        bim/exports meetings/site
    """)),
    ("p18", "manufacturing-quality-engineer", 12_000, (6, 12, 2, 6, 15, 3, 0, 18, 6, 8, 10, 3, 5, 0, 6), _paths("""
        products/product-alpha/fmea products/product-alpha/test-results products/product-alpha/capa
        products/product-beta/fmea products/product-beta/test-results products/product-beta/capa
        quality/sop quality/work-instructions quality/nonconformance suppliers/audits
        suppliers/certificates engineering/change-orders
    """)),
    ("p19", "educator-instructional-designer", 9_000, (8, 5, 0, 2, 5, 5, 0, 20, 8, 15, 7, 12, 8, 3, 2), _paths("""
        learning/courses/course-alpha/2026/term-1/lesson-plans learning/courses/course-alpha/2026/term-1/readings
        learning/courses/course-alpha/2026/term-1/assignments learning/courses/course-alpha/2026/term-1/synthetic-student-work
        learning/courses/course-beta/2026/term-2/lesson-plans learning/courses/course-beta/2026/term-2/readings learning/courses/course-beta/2026/term-2/assignments
        learning/courses/course-beta/2026/term-2/synthetic-student-work assessments/item-bank lms/exports
        presentations/lectures professional-development/notes
    """)),
    ("p20", "investigative-journalist", 10_000, (8, 18, 1, 3, 8, 10, 0, 16, 10, 8, 2, 2, 8, 4, 2), _paths("""
        newsroom/investigations/story-alpha/2026/sources newsroom/investigations/story-alpha/2026/transcripts newsroom/investigations/story-alpha/2026/foia
        newsroom/investigations/story-alpha/2026/drafts newsroom/investigations/story-alpha/2026/fact-check newsroom/investigations/story-beta/2026/sources
        newsroom/investigations/story-beta/2026/transcripts newsroom/investigations/story-beta/2026/foia newsroom/investigations/story-beta/2026/drafts data/analysis
        media/transcript-sidecars pitches/research
    """)),
)


# These rows intentionally vary by one synthetic owner.  They are fidelity
# hypotheses only: current source rendering and format/count allocation remain
# governed exclusively by the frozen fields in ``_PERSONA_ROWS`` above.
_PERSONA_FIDELITY_ROWS = (
    (
        "p01", "macos-apfs-case-insensitive", "macos-development-laptop",
        "ja-JP", ("ja", "en"), ("release-cycle", "asynchronous-development"),
        ("git-snapshot", "drive-export"), ("S1", "S2"),
        "product-repository", 4, False, "source-code-small-tail",
        "source-control-archive", ("git-pack-like", "source-export-zip"),
    ),
    (
        "p02", "ubuntu-ext4-case-sensitive", "sre-workstation",
        "en-US", ("en",), ("on-call", "append-heavy-logs"),
        ("git-snapshot", "server-export"), ("S2", "S3"),
        "service-environment-oncall", 5, False, "log-stream-and-runbook",
        "network-operations-capture", ("pcap", "compressed-log-export"),
    ),
    (
        "p03", "windows-ntfs-case-insensitive", "managed-grc-laptop",
        "ja-JP", ("ja", "en"), ("audit-case", "incident-case"),
        ("sharepoint-export", "siem-export"), ("S3",),
        "control-evidence", 4, True, "evidence-package",
        "security-evidence-container", ("pcap", "event-log-like-export"),
    ),
    (
        "p04", "ubuntu-ext4-case-sensitive", "gpu-research-workstation",
        "en-US", ("en",), ("experiment-batch", "paper-review"),
        ("git-snapshot", "object-store-export"), ("S1", "S2"),
        "program-model-experiment", 5, False, "notebook-model-artifact",
        "ml-artifact-container", ("parquet-like", "model-weight-container"),
    ),
    (
        "p05", "windows-ntfs-case-insensitive", "business-analytics-laptop",
        "ja-JP", ("ja", "en"), ("scheduled-report", "dashboard-refresh"),
        ("onedrive-export", "warehouse-export"), ("S2",),
        "analytics-report", 3, False, "tabular-dashboard-export",
        "analytics-export-container", ("sqlite", "parquet-like"),
    ),
    (
        "p06", "windows-ntfs-case-insensitive", "laboratory-workstation",
        "en-US", ("en",), ("protocol-run", "cohort-batch"),
        ("smb-snapshot", "instrument-export"), ("S2", "S3"),
        "study-cohort", 5, False, "assay-protocol-batch",
        "instrument-export-container",
        ("instrument-vendor-container", "compressed-assay-export"),
    ),
    (
        "p07", "macos-apfs-case-insensitive", "humanities-research-laptop",
        "en-GB", ("en", "fr", "de", "ja"),
        ("longform-writing", "archive-ocr"),
        ("archive-snapshot", "drive-export"), ("S0", "S1"),
        "source-chapter", 5, True, "longform-archive-scan",
        "humanities-archive-container", ("archival-tiff-bundle", "zip-archive"),
    ),
    (
        "p08", "macos-apfs-case-insensitive", "product-management-laptop",
        "ja-JP", ("ja", "en"), ("meeting-heavy", "quarterly-roadmap"),
        ("drive-export", "teams-export"), ("S2",),
        "product-quarter", 5, False, "roadmap-office-mix",
        "product-export-container", ("product-export-zip", "design-export-container"),
    ),
    (
        "p09", "macos-apfs-case-insensitive", "field-research-laptop",
        "en-US", ("en", "ja"), ("interview-session", "media-analysis"),
        ("recorder-export", "research-drive-export"), ("S2", "S3"),
        "study-session", 3, False, "transcript-media-session",
        "research-session-container",
        ("recording-project-container", "research-export-zip"),
    ),
    (
        "p10", "windows-ntfs-case-insensitive", "vdi-export-consulting-laptop",
        "en-US", ("en",), ("client-phase", "deliverable-review"),
        ("data-room-export", "teams-export"), ("S3",),
        "client-year-phase", 5, False, "deliverable-office-tail",
        "consulting-data-room-container", ("data-room-zip", "vdi-export-container"),
    ),
    (
        "p11", "windows-ntfs-case-insensitive", "travel-sales-laptop",
        "en-US", ("en", "es"), ("mail-call", "proposal-cycle"),
        ("outlook-export", "crm-export"), ("S2",),
        "account-opportunity", 3, False, "mail-call-proposal",
        "sales-export-container", ("crm-export-zip", "message-like-container"),
    ),
    (
        "p12", "windows-ntfs-case-insensitive", "managed-support-laptop",
        "ja-JP", ("ja", "en"), ("queue-driven", "high-frequency-update"),
        ("ticket-export", "crm-export"), ("S2",),
        "customer-case", 3, False, "high-volume-ticket-export",
        "support-export-container", ("ticket-attachment-zip", "crm-export-archive"),
    ),
    (
        "p13", "windows-ntfs-case-insensitive", "dlp-legal-laptop",
        "ja-JP", ("ja", "en"), ("matter-case", "legal-hold-versioning"),
        ("dms-export", "mail-export"), ("S3",),
        "matter-hold", 5, True, "legal-matter-document-tail",
        "legal-hold-container", ("dms-export-container", "legal-hold-archive"),
    ),
    (
        "p14", "windows-ntfs-case-insensitive", "finance-control-laptop",
        "ja-JP", ("ja", "en"), ("month-close", "final-copy"),
        ("erp-export", "onedrive-export"), ("S3",),
        "year-quarter-month", 5, False, "close-workbook-tail",
        "finance-export-container", ("sqlite", "erp-compressed-export"),
    ),
    (
        "p15", "windows-ntfs-case-insensitive", "hr-operations-laptop",
        "ja-JP", ("ja", "en"), ("requisition-case", "people-operations"),
        ("ats-export", "hris-export"), ("S3",),
        "requisition-candidate", 4, True, "candidate-case-document",
        "people-system-container", ("ats-export-archive", "hris-compressed-export"),
    ),
    (
        "p16", "windows-ntfs-case-insensitive", "clinical-vdi",
        "ja-JP", ("ja", "en"), ("protocol-append", "regulatory-review"),
        ("edc-export", "secure-smb-snapshot"), ("S3",),
        "study-year", 5, False, "protocol-regulatory-image",
        "clinical-synthetic-container",
        ("dicom-like-synthetic-container", "edc-export-archive"),
    ),
    (
        "p17", "windows-ntfs-case-insensitive", "field-construction-laptop",
        "ja-JP", ("ja", "en"), ("offline-field", "drawing-revision"),
        ("cde-snapshot",), ("S2",),
        "project-year-construction", 6, False, "drawing-bim-tail",
        "construction-model-container", ("ifc", "cde-zip"),
    ),
    (
        "p18", "windows-ntfs-case-insensitive", "quality-engineering-workstation",
        "ja-JP", ("ja", "en"), ("controlled-document", "production-batch"),
        ("qms-export", "plm-export"), ("S2",),
        "product-quality", 4, True, "controlled-quality-batch",
        "manufacturing-system-container", ("qms-export-archive", "plm-container"),
    ),
    (
        "p19", "chromeos-derived-portable-snapshot", "chromeos-education-device",
        "ja-JP", ("ja", "en"), ("academic-term", "bulk-lms-import"),
        ("drive-export", "lms-export"), ("S2",),
        "course-year-term", 6, False, "course-package-semester",
        "education-package-container", ("lms-export-zip", "course-package"),
    ),
    (
        "p20", "macos-apfs-case-insensitive", "encrypted-journalist-laptop",
        "ja-JP", ("ja", "en"), ("deadline-driven", "evidence-chain"),
        ("mail-export", "foia-export", "drop-snapshot"), ("S3",),
        "story-year-evidence", 5, False, "evidence-chain-source",
        "journalism-source-container", ("foia-archive", "encrypted-drop-like-container"),
    ),
)


def _persona_fidelity_profile(row):
    (
        person_id,
        os_semantics,
        device_class,
        locale,
        languages,
        work_style,
        sources,
        sensitivity_tiers,
        nesting_pattern,
        planned_max_depth,
        pilot_extension_required,
        size_profile_id,
        binary_profile_id,
        binary_variants,
    ) = row
    return {
        "persona_id": person_id,
        "profile_id": f"{person_id}-fidelity-v1",
        "os_semantics": os_semantics,
        "os_execution_mode": OS_EXECUTION_MODE,
        "device_class": device_class,
        "locale": locale,
        "languages": languages,
        "work_style": work_style,
        "synthetic_snapshot_or_export_sources": sources,
        "source_mode": SYNTHETIC_SOURCE_MODE,
        "live_sync": False,
        "sensitivity_tiers": sensitivity_tiers,
        "nesting_model": {
            "pattern": nesting_pattern,
            "planned_max_depth": planned_max_depth,
            "pilot_extension_required": pilot_extension_required,
        },
        "size_profile": {
            "profile_id": size_profile_id,
            "common_envelope_id": SIZE_COMPLEXITY_PROFILE_ID,
            "persona_override_status": "planned-not-implemented",
            "implemented_by_renderer": False,
            "searchability_claim": NO_SEARCHABILITY_CLAIM,
        },
        "domain_binary_raw_only_profile": {
            "profile_id": binary_profile_id,
            "planned_variants": binary_variants,
            "status": "planned-metadata-only",
            "gate_role": "raw_only",
            "expected_contributor_chunks": 0,
            "implemented_by_renderer": False,
            "searchability_claim": NO_SEARCHABILITY_CLAIM,
        },
        "hypothesis_only": True,
        "synthetic_only": True,
        "searchability_claim": NO_SEARCHABILITY_CLAIM,
        "contains_real_pii": False,
        "contains_real_phi": False,
        "contains_real_credentials": False,
    }


_PERSONA_FIDELITY_ROW_BY_ID = {row[0]: row for row in _PERSONA_FIDELITY_ROWS}
_PERSONA_FIDELITY_BY_ID = {
    person_id: _persona_fidelity_profile(row)
    for person_id, row in _PERSONA_FIDELITY_ROW_BY_ID.items()
}


PERSONAS = tuple(
    {
        "id": person_id,
        "role": role,
        "full_raw_files": full_raw_files,
        "format_percentages": dict(zip(FORMAT_KEYS, ratios)),
        "primary_paths": primary_paths,
        # Keep the published row detached from the private canonical value so
        # validation still detects an in-process mutation of ``PERSONAS``.
        "fidelity": _persona_fidelity_profile(
            _PERSONA_FIDELITY_ROW_BY_ID[person_id]
        ),
    }
    for person_id, role, full_raw_files, ratios, primary_paths in _PERSONA_ROWS
)


_PORTABLE_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PORTABLE_SOURCE_BASENAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_FIDELITY_TOKEN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_LOCALE_TAG = re.compile(r"^[a-z]{2,3}-[A-Z]{2}$")
_LANGUAGE_TAG = re.compile(r"^[a-z]{2,3}$")
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
}
MAX_SOURCE_BASENAME_BYTES = 120
_SENSITIVE_BASENAME_TERMS = (
    "apikey",
    "credential",
    "password",
    "secret",
    "token",
)
_SENSITIVE_SOURCE_SUFFIXES = (".env", ".key", ".p12", ".pem", ".tfstate")


def validate_relative_scope(relative_path):
    """Validate one portable POSIX scope path and return its components."""
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("scope path must be a non-empty string")
    if len(relative_path.encode("ascii", errors="ignore")) != len(relative_path):
        raise ValueError(f"scope path must be ASCII: {relative_path!r}")
    if len(relative_path) > 240:
        raise ValueError(f"scope path exceeds 240 characters: {relative_path!r}")
    path = PurePosixPath(relative_path)
    if path.is_absolute() or str(path) != relative_path:
        raise ValueError(f"scope path is not canonical relative POSIX: {relative_path!r}")
    components = path.parts
    if len(components) < 2:
        raise ValueError(f"scope path must exercise at least one parent: {relative_path!r}")
    for component in components:
        if len(component) > 80 or not _PORTABLE_COMPONENT.fullmatch(component):
            raise ValueError(f"non-portable scope component: {component!r}")
        if component.split(".", 1)[0].casefold() in _WINDOWS_RESERVED:
            raise ValueError(f"Windows-reserved scope component: {component!r}")
    return components


def validate_source_basename(file_name):
    """Validate an ASCII W0 managed source name on all target platforms."""
    if not isinstance(file_name, str) or not file_name:
        raise ValueError("source basename must be a non-empty string")
    try:
        encoded = file_name.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError(f"source basename must be ASCII: {file_name!r}") from error
    if len(encoded) > MAX_SOURCE_BASENAME_BYTES:
        raise ValueError(f"source basename exceeds {MAX_SOURCE_BASENAME_BYTES} bytes")
    if _PORTABLE_SOURCE_BASENAME.fullmatch(file_name) is None:
        raise ValueError(f"non-portable source basename: {file_name!r}")
    if file_name.endswith((".", " ")):
        raise ValueError(f"source basename has a non-portable suffix: {file_name!r}")
    stem = file_name.split(".", 1)[0].casefold()
    if stem in _WINDOWS_RESERVED:
        raise ValueError(f"Windows-reserved source basename: {file_name!r}")
    folded = file_name.casefold()
    if any(term in folded for term in _SENSITIVE_BASENAME_TERMS):
        raise ValueError(f"source basename enters a sensitive-name tier: {file_name!r}")
    if any(folded == suffix or folded.endswith(suffix) for suffix in _SENSITIVE_SOURCE_SUFFIXES):
        raise ValueError(f"source basename has a sensitive suffix: {file_name!r}")
    return file_name


def largest_remainder(total, weights):
    """Allocate an integer total with stable Hamilton tie-breaking."""
    if type(total) is not int or total < 0:
        raise ValueError("total must be a non-negative integer")
    if not weights or any(type(weight) is not int or weight < 0 for weight in weights):
        raise ValueError("weights must be non-negative integers")
    denominator = sum(weights)
    if denominator <= 0:
        raise ValueError("weights must have a positive sum")
    base = [(total * weight) // denominator for weight in weights]
    remainders = [(total * weight) % denominator for weight in weights]
    missing = total - sum(base)
    order = sorted(range(len(weights)), key=lambda index: (-remainders[index], index))
    for index in order[:missing]:
        base[index] += 1
    return tuple(base)


def get_persona(persona_id):
    for value in PERSONAS:
        if value["id"] == persona_id:
            return value
    raise KeyError(persona_id)


def all_scope_paths(persona):
    return tuple(persona["primary_paths"]) + SECONDARY_PATHS


def scope_specs(persona):
    paths = all_scope_paths(persona)
    weights = PRIMARY_SCOPE_WEIGHTS_PCT + SECONDARY_SCOPE_WEIGHTS_PCT
    result = []
    for index, (relative_path, weight) in enumerate(zip(paths, weights), start=1):
        kind = "primary" if index <= len(PRIMARY_SCOPE_WEIGHTS_PCT) else "secondary"
        result.append({
            "scope_key": f"{persona['id']}-{kind}-{index if kind == 'primary' else index - 12:02d}",
            "kind": kind,
            "relative_path": relative_path,
            "contributor_weight_pct": weight,
        })
    return tuple(result)


def raw_file_count(persona, profile_name):
    if profile_name == "tiny":
        return TINY_RAW_FILES_PER_PERSON
    if profile_name == "pilot":
        return PILOT_RAW_FILES_PER_PERSON
    if profile_name == "full":
        return persona["full_raw_files"]
    raise ValueError(f"unknown persona profile: {profile_name}")


def format_file_counts(persona, profile_name):
    total = raw_file_count(persona, profile_name)
    percentages = tuple(persona["format_percentages"][key] for key in FORMAT_KEYS)
    return dict(zip(FORMAT_KEYS, largest_remainder(total, percentages)))


def format_variant_counts(persona, profile_name):
    """Allocate every family total to deterministic source-level variants."""
    family_counts = format_file_counts(persona, profile_name)
    result = {}
    for family in FORMAT_KEYS:
        variants = FORMAT_VARIANTS[family]
        allocations = largest_remainder(
            family_counts[family], tuple(variant[1] for variant in variants)
        )
        result[family] = tuple(
            {
                "variant": variant,
                "count": count,
                "gate_role": gate_role,
                "expected_disposition": disposition,
            }
            for (variant, _, gate_role, disposition), count in zip(variants, allocations)
        )
    return result


def expected_offline_index_counts(persona, profile_name):
    """Return the production CLI counter oracle for one mixed-format person."""
    counts = format_file_counts(persona, profile_name)
    return {
        "physical_files": sum(counts.values()),
        "normalized_files": sum(counts[key] for key in OFFLINE_NORMALIZED_FAMILIES),
        "pending_online_tasks": sum(counts[key] for key in OFFLINE_PENDING_FAMILIES),
        "skipped_unrecognized_binary_files": sum(
            counts[key] for key in OFFLINE_SKIPPED_BINARY_FAMILIES
        ),
        "failed_files": 0,
        "pending_files": 0,
        "skipped_oversized_files": 0,
        "completed_online_tasks": 0,
        "external_cost_microusd": 0,
    }


def suite_expected_offline_index_counts(profile_name):
    """Sum the per-person offline CLI oracle without assuming disjoint sets."""
    rows = [expected_offline_index_counts(persona, profile_name) for persona in PERSONAS]
    return {key: sum(row[key] for row in rows) for key in rows[0]}


def scope_file_counts(persona, profile_name):
    """Return frozen per-leaf capacities for the two-dimensional router.

    Format variants are routed *within* these column marginals; the router may
    not move capacity between leaves.  The same direct-file ceiling is checked
    again after routing and every history wave.
    """
    total = raw_file_count(persona, profile_name)
    weights = PRIMARY_SCOPE_WEIGHTS_PCT + SECONDARY_SCOPE_WEIGHTS_PCT
    scopes = scope_specs(persona)
    return {
        scope["scope_key"]: count
        for scope, count in zip(scopes, largest_remainder(total, weights))
    }


def scope_contributor_chunk_targets(persona, profile_name):
    """Return the exact 75/25 contributor load targets for each leaf scope."""
    scopes = scope_specs(persona)
    weights = PRIMARY_SCOPE_WEIGHTS_PCT + SECONDARY_SCOPE_WEIGHTS_PCT
    if profile_name in ("tiny", "pilot"):
        target = contributor_plan(persona, profile_name)["target_chunks"]
    elif profile_name == "full":
        target = FORMAL_CURRENT_CHUNKS_PER_PERSON
    else:
        raise ValueError(f"unknown persona profile: {profile_name}")
    return {
        scope["scope_key"]: count
        for scope, count in zip(scopes, largest_remainder(target, weights))
    }


def scope_contributor_file_minima(persona, profile_name):
    """Minimum stable-variant files needed in each scope at the density cap."""
    return {
        scope_key: (target + MAX_CONTRIBUTOR_CHUNKS_PER_FILE - 1)
        // MAX_CONTRIBUTOR_CHUNKS_PER_FILE
        for scope_key, target in scope_contributor_chunk_targets(
            persona, profile_name
        ).items()
    }


def history_cohort_chunk_targets(persona, profile_name):
    """Return exact whole-source contributor targets for P/X/Y/N/U.

    The formal/pilot targets are exact 4/10/6/4/76 percentages.  Tiny targets
    use the same one-time floor as the executable wave deltas and make Y the
    residual of W1's 20-percent target.  N equals P so W5 can be net-zero.
    """
    current = contributor_plan(persona, profile_name)["target_chunks"]
    edit = current * 20 // 100
    p = current * 4 // 100
    x = current * 10 // 100
    y = edit - p - x
    n = p
    u = current - p - x - y - n
    result = {"P": p, "X": x, "Y": y, "N": n, "U": u}
    if y <= 0 or u <= 0 or sum(result.values()) != current:
        raise ValueError("history cohort targets do not partition current chunks")
    return result


def history_wave_chunk_targets(persona, profile_name):
    """Return exact contract-contributor C/H targets for W0-W5."""
    current = contributor_plan(persona, profile_name)["target_chunks"]
    cohorts = history_cohort_chunk_targets(persona, profile_name)
    edit = cohorts["P"] + cohorts["X"] + cohorts["Y"]
    major = cohorts["X"] + cohorts["Y"] + cohorts["N"]
    delete = cohorts["X"]
    history = {
        "W0": 0,
        "W1": edit,
        "W2": edit,
        "W3": edit + major,
        "W4": edit + major + delete,
        "W5": edit + major + delete,
    }
    return {
        wave_id: {
            "current_contract_contributor_chunks": current,
            "history_only_contract_contributor_chunks": value,
            "current_plus_history_contract_contributor_chunks": current + value,
        }
        for wave_id, value in history.items()
    }


def history_event_plan(persona, profile_name):
    """Return cohort-level chunk projection; source IDs come from the allocator."""
    cohorts = history_cohort_chunk_targets(persona, profile_name)
    current = contributor_plan(persona, profile_name)["target_chunks"]
    total = raw_file_count(persona, profile_name)
    edit = cohorts["P"] + cohorts["X"] + cohorts["Y"]
    major = cohorts["X"] + cohorts["Y"] + cohorts["N"]
    formal_boundaries = 20 if profile_name == "full" else None
    return {
        "W0": {"create": total, "index_auto_boundaries": 20},
        "W1": {
            "edit_contract_chunks": edit,
            "index_auto_boundaries": formal_boundaries,
            "new_history_contract_chunks": edit,
        },
        "W2": {
            "positive_quota_cross_scope_moves": 0,
            "structural_assignment_required": True,
            "index_auto_boundaries": formal_boundaries,
            "new_history_contract_chunks": 0,
        },
        "W3": {
            "major_edit_contract_chunks": major,
            "structural_assignment_required": True,
            "index_auto_boundaries": formal_boundaries,
            "new_history_contract_chunks": major,
        },
        "W4": {
            "deleted_current_contract_chunks": cohorts["X"],
            "replacement_current_contract_chunks": cohorts["X"],
            "structural_assignment_required": True,
            "index_auto_boundaries": formal_boundaries,
            "new_history_contract_chunks": cohorts["X"],
        },
        "W5": {
            "correction_history_contract_chunks": cohorts["N"],
            "purged_current_contract_chunks": cohorts["P"],
            "purged_history_contract_chunks": cohorts["P"],
            "purged_total_contract_version_chunks": cohorts["P"] * 2,
            "replacement_current_contract_chunks": cohorts["P"],
            "pre_purge_current_contract_chunks": current + cohorts["P"],
            "pre_purge_history_contract_chunks": (
                edit + major + cohorts["X"] + cohorts["N"]
            ),
            "structural_assignment_required": True,
            "index_auto_boundaries": formal_boundaries,
            "purged_commit_boundaries_from_source_allocator": True,
            "index_noop_boundaries": formal_boundaries,
            "new_history_contract_chunks_net": 0,
        },
    }


def require_executable_history_cohort_assignment():
    """Require the source-level P/X/Y/N cohort allocator."""
    if not HISTORY_COHORT_ASSIGNMENT_EXECUTABLE:
        raise ValueError("history cohort assignment is not executable")


def require_executable_history_structural_assignment():
    """Require the canonical quota-neutral structural allocator."""
    if not HISTORY_STRUCTURAL_ASSIGNMENT_EXECUTABLE:
        raise ValueError("history structural assignment is not executable")


def require_executable_history_event_manifest():
    """Require the canonical root-independent planned event manifest."""
    if not HISTORY_EVENT_MANIFEST_EXECUTABLE:
        raise ValueError("history event manifest is not executable")


def require_executable_history_assignment():
    """Fail closed until the complete immutable W1-W5 assignment exists."""
    if not HISTORY_ASSIGNMENT_EXECUTABLE:
        raise ValueError(HISTORY_ASSIGNMENT_BLOCKER)


def contributor_plan(persona, profile_name):
    variants = format_variant_counts(persona, profile_name)
    files = sum(
        entry["count"]
        for family in FORMAT_KEYS
        for entry in variants[family]
        if entry["gate_role"] == "contract_contributor"
    )
    if profile_name == "tiny":
        target = files * 3
    elif profile_name == "pilot":
        target = PILOT_CURRENT_CHUNKS_PER_PERSON
    elif profile_name == "full":
        target = FORMAL_CURRENT_CHUNKS_PER_PERSON
    else:
        raise ValueError(f"unknown persona profile: {profile_name}")
    quotient, remainder = divmod(target, files)
    return {
        "contributor_files": files,
        "target_chunks": target,
        # These describe only the persona-wide arithmetic average.  The
        # executable plan allocates contributors and exact 1..72 quotas inside
        # each scope; discrete scope targets can legitimately exceed this
        # average ceiling for an individual source.
        "persona_average_chunks_per_file_floor": quotient,
        "persona_average_chunks_per_file_ceiling": quotient + bool(remainder),
        "persona_files_above_average_floor": remainder,
    }


def validate_size_complexity_buckets(contract=None):
    """Validate the frozen, hypothesis-only common size envelope.

    The function accepts an explicit value so callers and tests can validate a
    serialized copy before trusting it.  Integer checks deliberately exclude
    ``bool`` because JSON/Python truth values must never pass as percentages or
    numeric range endpoints.
    """
    if contract is None:
        contract = COMMON_SIZE_COMPLEXITY_BUCKETS
    expected_ids = tuple(row[0] for row in _SIZE_COMPLEXITY_ROWS)
    if type(contract) is not dict or tuple(contract) != expected_ids:
        raise ValueError("size complexity profiles are missing, unknown, or reordered")
    row_keys = {
        "unit",
        "applies_to",
        "buckets",
        "hypothesis_only",
        "implemented_by_renderer",
        "searchability_claim",
    }
    bucket_keys = {
        "bucket",
        "minimum_inclusive",
        "maximum_inclusive",
        "percentage",
    }
    for profile_id, unit, applies_to, expected_ranges, expected_percentages in (
        _SIZE_COMPLEXITY_ROWS
    ):
        row = contract[profile_id]
        if type(row) is not dict or set(row) != row_keys:
            raise ValueError(f"invalid size complexity profile shape: {profile_id}")
        if row["unit"] != unit or row["applies_to"] != applies_to:
            raise ValueError(f"size complexity profile target drifted: {profile_id}")
        if row["hypothesis_only"] is not True:
            raise ValueError(f"size profile must remain hypothesis-only: {profile_id}")
        if row["implemented_by_renderer"] is not False:
            raise ValueError(f"size profile cannot claim renderer implementation: {profile_id}")
        if row["searchability_claim"] != NO_SEARCHABILITY_CLAIM:
            raise ValueError(f"size profile cannot grant searchability: {profile_id}")
        buckets = row["buckets"]
        if type(buckets) is not tuple or len(buckets) != len(SIZE_BUCKET_ORDER):
            raise ValueError(f"size profile requires four ordered buckets: {profile_id}")
        observed_ranges = []
        observed_percentages = []
        previous_upper = None
        for index, (bucket, expected_bucket) in enumerate(
            zip(buckets, SIZE_BUCKET_ORDER)
        ):
            if type(bucket) is not dict or set(bucket) != bucket_keys:
                raise ValueError(f"invalid size bucket shape: {profile_id}/{expected_bucket}")
            if bucket["bucket"] != expected_bucket:
                raise ValueError(f"size buckets are not in canonical order: {profile_id}")
            lower = bucket["minimum_inclusive"]
            upper = bucket["maximum_inclusive"]
            percentage = bucket["percentage"]
            if type(lower) is not int or lower < 0:
                raise ValueError(f"invalid size bucket minimum: {profile_id}/{expected_bucket}")
            if upper is not None and (type(upper) is not int or upper < lower):
                raise ValueError(f"invalid size bucket maximum: {profile_id}/{expected_bucket}")
            if type(percentage) is not int or percentage < 0:
                raise ValueError(f"invalid size bucket percentage: {profile_id}/{expected_bucket}")
            if index and (previous_upper is None or lower != previous_upper + 1):
                raise ValueError(f"size bucket ranges must be contiguous: {profile_id}")
            previous_upper = upper
            observed_ranges.append((lower, upper))
            observed_percentages.append(percentage)
        if tuple(observed_ranges) != expected_ranges:
            raise ValueError(f"size bucket ranges drifted: {profile_id}")
        if tuple(observed_percentages) != expected_percentages:
            raise ValueError(f"size bucket percentages drifted: {profile_id}")
        if sum(observed_percentages) != 100:
            raise ValueError(f"size bucket percentages must sum to 100: {profile_id}")


def _validate_fidelity_token_tuple(value, label, minimum_length=1):
    if type(value) is not tuple or len(value) < minimum_length:
        raise ValueError(f"{label} must be an ordered non-empty tuple")
    if any(type(item) is not str or _FIDELITY_TOKEN.fullmatch(item) is None for item in value):
        raise ValueError(f"{label} contains an invalid token")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate tokens")


def _frozen_fidelity_value(value):
    if type(value) is dict:
        return tuple(
            (key, _frozen_fidelity_value(value[key])) for key in sorted(value)
        )
    if type(value) is tuple:
        return tuple(_frozen_fidelity_value(item) for item in value)
    return value


def validate_persona_fidelity(personas=None):
    """Validate twenty identity-bound, non-live synthetic PC hypotheses."""
    if personas is None:
        personas = PERSONAS
    if type(personas) not in (tuple, list) or len(personas) != 20:
        raise ValueError("persona fidelity contract requires exactly 20 rows")
    expected_ids = tuple(row[0] for row in _PERSONA_ROWS)
    observed_ids = tuple(
        persona.get("id") if type(persona) is dict else None
        for persona in personas
    )
    if observed_ids != expected_ids:
        raise ValueError("persona fidelity rows are missing, unknown, or reordered")

    profile_keys = set(FIDELITY_PROFILE_KEYS)
    nesting_keys = {"pattern", "planned_max_depth", "pilot_extension_required"}
    size_profile_keys = {
        "profile_id",
        "common_envelope_id",
        "persona_override_status",
        "implemented_by_renderer",
        "searchability_claim",
    }
    binary_profile_keys = {
        "profile_id",
        "planned_variants",
        "status",
        "gate_role",
        "expected_contributor_chunks",
        "implemented_by_renderer",
        "searchability_claim",
    }
    fingerprints = set()
    size_profile_ids = set()
    binary_profile_ids = set()
    for persona in personas:
        person_id = persona["id"]
        profile = persona.get("fidelity")
        if type(profile) is not dict or set(profile) != profile_keys:
            raise ValueError(f"fidelity attributes are missing or unknown: {person_id}")
        if profile["persona_id"] != person_id:
            raise ValueError(f"fidelity identity differs from persona: {person_id}")
        if profile["profile_id"] != f"{person_id}-fidelity-v1":
            raise ValueError(f"invalid fidelity profile identity: {person_id}")
        if profile["os_semantics"] not in OS_SEMANTICS:
            raise ValueError(f"unknown simulated OS semantics: {person_id}")
        if profile["os_execution_mode"] != OS_EXECUTION_MODE:
            raise ValueError(f"OS execution mode overclaims fidelity: {person_id}")
        if (
            type(profile["device_class"]) is not str
            or _FIDELITY_TOKEN.fullmatch(profile["device_class"]) is None
        ):
            raise ValueError(f"invalid device class: {person_id}")
        if (
            type(profile["locale"]) is not str
            or _LOCALE_TAG.fullmatch(profile["locale"]) is None
        ):
            raise ValueError(f"invalid locale: {person_id}")
        languages = profile["languages"]
        if (
            type(languages) is not tuple
            or not languages
            or any(
                type(language) is not str
                or _LANGUAGE_TAG.fullmatch(language) is None
                for language in languages
            )
            or len(set(languages)) != len(languages)
        ):
            raise ValueError(f"languages must be ordered unique language tags: {person_id}")
        _validate_fidelity_token_tuple(
            profile["work_style"], f"work_style for {person_id}", minimum_length=2
        )
        sources = profile["synthetic_snapshot_or_export_sources"]
        _validate_fidelity_token_tuple(sources, f"synthetic sources for {person_id}")
        if any(
            not source.endswith(("-snapshot", "-export"))
            or "live" in source
            or "sync" in source
            for source in sources
        ):
            raise ValueError(f"fidelity sources must be synthetic snapshots/exports: {person_id}")
        if profile["source_mode"] != SYNTHETIC_SOURCE_MODE:
            raise ValueError(f"source mode must remain synthetic-only: {person_id}")
        if type(profile["live_sync"]) is not bool or profile["live_sync"]:
            raise ValueError(f"live sync is forbidden: {person_id}")

        tiers = profile["sensitivity_tiers"]
        if (
            type(tiers) is not tuple
            or not tiers
            or any(type(tier) is not str or tier not in SENSITIVITY_TIERS for tier in tiers)
            or len(set(tiers)) != len(tiers)
            or tuple(sorted(tiers, key=SENSITIVITY_TIERS.index)) != tiers
        ):
            raise ValueError(f"invalid sensitivity tiers: {person_id}")

        nesting = profile["nesting_model"]
        if type(nesting) is not dict or set(nesting) != nesting_keys:
            raise ValueError(f"invalid nesting model shape: {person_id}")
        if (
            type(nesting["pattern"]) is not str
            or _FIDELITY_TOKEN.fullmatch(nesting["pattern"]) is None
        ):
            raise ValueError(f"invalid nesting model pattern: {person_id}")
        depth = nesting["planned_max_depth"]
        if type(depth) is not int or not 2 <= depth <= 12:
            raise ValueError(f"invalid planned nesting depth: {person_id}")
        if type(nesting["pilot_extension_required"]) is not bool:
            raise ValueError(f"invalid pilot nesting flag: {person_id}")

        size_profile = profile["size_profile"]
        if type(size_profile) is not dict or set(size_profile) != size_profile_keys:
            raise ValueError(f"invalid persona size profile shape: {person_id}")
        if (
            type(size_profile["profile_id"]) is not str
            or _FIDELITY_TOKEN.fullmatch(size_profile["profile_id"]) is None
            or size_profile["profile_id"] in size_profile_ids
        ):
            raise ValueError(f"invalid or cloned persona size profile: {person_id}")
        size_profile_ids.add(size_profile["profile_id"])
        if (
            size_profile["common_envelope_id"] != SIZE_COMPLEXITY_PROFILE_ID
            or size_profile["persona_override_status"] != "planned-not-implemented"
            or type(size_profile["implemented_by_renderer"]) is not bool
            or size_profile["implemented_by_renderer"]
            or size_profile["searchability_claim"] != NO_SEARCHABILITY_CLAIM
        ):
            raise ValueError(f"persona size profile overclaims implementation: {person_id}")

        binary_profile = profile["domain_binary_raw_only_profile"]
        if type(binary_profile) is not dict or set(binary_profile) != binary_profile_keys:
            raise ValueError(f"invalid domain-binary profile shape: {person_id}")
        if (
            type(binary_profile["profile_id"]) is not str
            or _FIDELITY_TOKEN.fullmatch(binary_profile["profile_id"]) is None
            or binary_profile["profile_id"] in binary_profile_ids
        ):
            raise ValueError(f"invalid or cloned domain-binary profile: {person_id}")
        binary_profile_ids.add(binary_profile["profile_id"])
        _validate_fidelity_token_tuple(
            binary_profile["planned_variants"],
            f"domain-binary variants for {person_id}",
        )
        if (
            binary_profile["status"] != "planned-metadata-only"
            or binary_profile["gate_role"] != "raw_only"
            or type(binary_profile["expected_contributor_chunks"]) is not int
            or binary_profile["expected_contributor_chunks"] != 0
            or type(binary_profile["implemented_by_renderer"]) is not bool
            or binary_profile["implemented_by_renderer"]
            or binary_profile["searchability_claim"] != NO_SEARCHABILITY_CLAIM
        ):
            raise ValueError(f"domain-binary profile must remain planned raw-only: {person_id}")

        if (
            profile["hypothesis_only"] is not True
            or profile["synthetic_only"] is not True
            or profile["searchability_claim"] != NO_SEARCHABILITY_CLAIM
            or profile["contains_real_pii"] is not False
            or profile["contains_real_phi"] is not False
            or profile["contains_real_credentials"] is not False
        ):
            raise ValueError(
                f"fidelity must remain hypothetical/synthetic/non-searchable and free of real sensitive data: {person_id}"
            )

        fingerprint = _frozen_fidelity_value({
            key: value
            for key, value in profile.items()
            if key not in ("persona_id", "profile_id")
        })
        if fingerprint in fingerprints:
            raise ValueError(f"cloned persona fidelity attribute row: {person_id}")
        fingerprints.add(fingerprint)
        if profile != _PERSONA_FIDELITY_BY_ID[person_id]:
            raise ValueError(f"persona fidelity hypothesis drifted: {person_id}")


def validate_spec():
    validate_size_complexity_buckets()
    validate_persona_fidelity()
    if len(FORMAT_KEYS) != 15 or len(set(FORMAT_KEYS)) != 15:
        raise ValueError("format family contract must contain exactly 15 unique keys")
    if len(PERSONAS) != 20:
        raise ValueError("persona fixture requires exactly 20 people")
    if REPLAY_COUNT != 3:
        raise ValueError("persona fixture requires exactly three fresh replays")
    if sum(persona["full_raw_files"] for persona in PERSONAS) != 195_000:
        raise ValueError("formal suite must contain exactly 195000 W0 raw files")
    if (
        FORMAL_CURRENT_CHUNKS_PER_PERSON != 120_000
        or FORMAL_HISTORY_CHUNKS_PER_PERSON != 180_000
    ):
        raise ValueError("formal current/history chunk constants drifted")
    if tuple(FORMAT_VARIANTS) != FORMAT_KEYS:
        raise ValueError("every canonical family must have ordered variant policy")
    for family, variants in FORMAT_VARIANTS.items():
        if sum(variant[1] for variant in variants) != 100:
            raise ValueError(f"format variants must sum to 100: {family}")
        if len({variant[0] for variant in variants}) != len(variants):
            raise ValueError(f"format variants must be unique: {family}")
    if sum(PRIMARY_SCOPE_WEIGHTS_PCT) != 75 or sum(SECONDARY_SCOPE_WEIGHTS_PCT) != 25:
        raise ValueError("primary/secondary contributor weights must be 75/25")
    if (
        tuple(HISTORY_COHORT_FULL_PCT) != HISTORY_COHORT_KEYS
        or sum(HISTORY_COHORT_FULL_PCT.values()) != 100
    ):
        raise ValueError("history cohort percentages must partition 100 percent")
    if tuple(wave["id"] for wave in WAVES) != tuple(f"W{i}" for i in range(6)):
        raise ValueError("history waves must be W0 through W5")

    ids = set()
    roles = set()
    matrices = set()
    primary_matrices = set()
    scope_depths = []
    personas_with_depth_five = set()
    for persona in PERSONAS:
        if persona["id"] in ids or persona["role"] in roles:
            raise ValueError("persona ids and roles must be unique")
        ids.add(persona["id"])
        roles.add(persona["role"])
        if type(persona["full_raw_files"]) is not int or persona["full_raw_files"] % 100:
            raise ValueError(f"full raw files must be a multiple of 100: {persona['id']}")
        percentages = tuple(persona["format_percentages"].get(key) for key in FORMAT_KEYS)
        if any(type(value) is not int or value < 0 for value in percentages):
            raise ValueError(f"invalid format percentage: {persona['id']}")
        if sum(percentages) != 100:
            raise ValueError(f"format percentages do not sum to 100: {persona['id']}")
        if percentages in matrices:
            raise ValueError(f"cloned format matrix: {persona['id']}")
        matrices.add(percentages)
        if len(persona["primary_paths"]) != 12:
            raise ValueError(f"persona must have exactly 12 primary paths: {persona['id']}")
        primary_matrix = tuple(persona["primary_paths"])
        if primary_matrix in primary_matrices:
            raise ValueError(f"cloned primary scope matrix: {persona['id']}")
        primary_matrices.add(primary_matrix)
        paths = all_scope_paths(persona)
        if len(paths) != 20 or len({path.casefold() for path in paths}) != 20:
            raise ValueError(f"persona scope paths must be 20 portable-unique leaves: {persona['id']}")
        components = [validate_relative_scope(path) for path in paths]
        scope_depths.extend(len(value) for value in components)
        if any(len(value) >= 5 for value in components):
            personas_with_depth_five.add(persona["id"])
        for left_index, left in enumerate(components):
            for right_index, right in enumerate(components):
                if left_index != right_index and len(left) < len(right) and right[:len(left)] == left:
                    raise ValueError(
                        f"scope leaf cannot be an ancestor of another scope: {persona['id']}"
                    )
        files = scope_file_counts(persona, "full")
        if max(files.values()) >= MAX_DIRECT_FILES_PER_SCOPE:
            raise ValueError(f"scope direct-file headroom violated: {persona['id']}")
        plan = contributor_plan(persona, "full")
        if plan["target_chunks"] > (
            plan["contributor_files"] * MAX_CONTRIBUTOR_CHUNKS_PER_FILE
        ):
            raise ValueError(f"contributor chunk capacity too low: {persona['id']}")
        minima = scope_contributor_file_minima(persona, "full")
        if sum(minima.values()) > plan["contributor_files"]:
            raise ValueError(f"not enough stable variants for per-scope targets: {persona['id']}")
        if any(minima[key] > files[key] for key in files):
            raise ValueError(f"neutral scope capacity cannot host contributor floor: {persona['id']}")
        history = history_wave_chunk_targets(persona, "full")
        if (
            history["W5"]["current_plus_history_contract_contributor_chunks"]
            != FORMAL_HISTORY_CHUNKS_PER_PERSON
        ):
            raise ValueError(f"formal W5 history target mismatch: {persona['id']}")
        events = history_event_plan(persona, "full")
        if events["W5"]["purged_current_contract_chunks"] < len(paths):
            raise ValueError(f"formal purge quota cannot cover every scope: {persona['id']}")
    if sum(depth >= 4 for depth in scope_depths) < MIN_SCOPES_AT_DEPTH_FOUR:
        raise ValueError("suite nesting complexity fell below the depth-four floor")
    if len(personas_with_depth_five) < MIN_PERSONAS_WITH_DEPTH_FIVE:
        raise ValueError("too few personas exercise depth-five scope paths")
    if max(scope_depths) < MIN_MAXIMUM_SCOPE_DEPTH:
        raise ValueError("suite maximum nesting depth regressed")


validate_spec()
