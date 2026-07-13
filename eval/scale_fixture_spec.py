"""Deterministic specification for the independent 120k-chunk scale fixture.

This module deliberately does not import ``corpus_spec``.  The existing
200-500-file Recall corpus is frozen; this fixture exists only to exercise the
20-scope / 100k-plus performance contract without changing Recall inputs.
"""

import hashlib


SCHEMA_VERSION = 1
SEED = 20260713
FIXTURE_ID = "kcs-scale-120k-v1"
QUERY_WORKLOAD_ID = "exact-reference-v1"
GENERATOR_ID = "eval/generate_scale_corpus.py"
MANIFEST_NAME = "scale-corpus-manifest.json"
OWNER_MARKER_NAME = ".kcs-scale-owner.json"
LOCK_NAME = ".kcs-scale.lock"
DEVICE_DIR_NAME = ".kcs-eval-device"
ATTESTATION_NAME = "scale-attestation.json"
PREPARE_REPORT_NAME = "scale-prepare-report.json"

CHUNKING_STRATEGY = "heading"
CHUNKING_MAX_CHARS = 6000
CHUNKING_CONFIG_HASH = (
    "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea"
)
MINIMUM_CURRENT_CHUNKS = 100_001


# ASCII-only portable leaves.  Each scope is a direct-child folder and KCS only
# indexes files directly below it (docs/03-data-model.md section 3).
SCOPES = (
    {
        "name": "engineering-architecture",
        "persona": "software-engineer",
        "use_case": "architecture-and-adr",
        "terms": ("architecture", "decision", "dependency", "migration"),
    },
    {
        "name": "engineering-api-specs",
        "persona": "software-engineer",
        "use_case": "api-contracts",
        "terms": ("endpoint", "schema", "pagination", "compatibility"),
    },
    {
        "name": "engineering-incidents",
        "persona": "site-reliability-engineer",
        "use_case": "incident-response",
        "terms": ("incident", "latency", "mitigation", "timeline"),
    },
    {
        "name": "engineering-runbooks",
        "persona": "site-reliability-engineer",
        "use_case": "operations-runbooks",
        "terms": ("runbook", "alert", "rollback", "verification"),
    },
    {
        "name": "engineering-releases",
        "persona": "release-engineer",
        "use_case": "release-and-migration-notes",
        "terms": ("release", "version", "upgrade", "deprecation"),
    },
    {
        "name": "research-papers",
        "persona": "academic-researcher",
        "use_case": "paper-library",
        "terms": ("method", "dataset", "result", "limitation"),
    },
    {
        "name": "research-lab-notes",
        "persona": "academic-researcher",
        "use_case": "laboratory-notebook",
        "terms": ("observation", "protocol", "sample", "calibration"),
    },
    {
        "name": "research-experiments",
        "persona": "academic-researcher",
        "use_case": "experiment-results",
        "terms": ("experiment", "baseline", "metric", "variance"),
    },
    {
        "name": "research-grants",
        "persona": "principal-investigator",
        "use_case": "grant-and-budget-records",
        "terms": ("milestone", "budget", "deliverable", "review"),
    },
    {
        "name": "research-literature",
        "persona": "graduate-student",
        "use_case": "literature-notes",
        "terms": ("citation", "hypothesis", "evidence", "comparison"),
    },
    {
        "name": "ml-model-evaluations",
        "persona": "machine-learning-engineer",
        "use_case": "model-evaluation",
        "terms": ("model", "recall", "precision", "benchmark"),
    },
    {
        "name": "data-dictionaries",
        "persona": "data-engineer",
        "use_case": "data-dictionary",
        "terms": ("column", "type", "constraint", "lineage"),
    },
    {
        "name": "data-dashboard-reports",
        "persona": "data-analyst",
        "use_case": "dashboard-reports",
        "terms": ("dashboard", "segment", "trend", "forecast"),
    },
    {
        "name": "ml-notebook-exports",
        "persona": "machine-learning-engineer",
        "use_case": "notebook-exports",
        "terms": ("notebook", "feature", "training", "validation"),
    },
    {
        "name": "product-meetings",
        "persona": "product-manager",
        "use_case": "meeting-decisions",
        "terms": ("meeting", "decision", "owner", "deadline"),
    },
    {
        "name": "product-requirements",
        "persona": "product-manager",
        "use_case": "requirements-and-research",
        "terms": ("requirement", "customer", "workflow", "acceptance"),
    },
    {
        "name": "product-roadmaps",
        "persona": "engineering-manager",
        "use_case": "roadmap-and-planning",
        "terms": ("roadmap", "priority", "capacity", "risk"),
    },
    {
        "name": "security-compliance",
        "persona": "security-engineer",
        "use_case": "security-and-compliance",
        "terms": ("control", "audit", "threat", "remediation"),
    },
    {
        "name": "client-deliverables",
        "persona": "consultant",
        "use_case": "client-deliverables",
        "terms": ("client", "finding", "recommendation", "outcome"),
    },
    {
        "name": "downloads-inbox",
        "persona": "knowledge-worker",
        "use_case": "downloads-and-inbox",
        "terms": ("download", "reference", "summary", "followup"),
    },
)


PROFILES = {
    # Same 20 scopes as full, so ordinary CI exercises registry enumeration.
    "tiny": {
        "files_per_scope": 1,
        "sections_per_file": 3,
        "body_chars": 420,
    },
    "full": {
        "files_per_scope": 200,
        "sections_per_file": 30,
        "body_chars": 1_800,
    },
}


def profile(name):
    """Return a validated profile copy with all derived counts."""
    if name not in PROFILES:
        raise ValueError(f"unknown scale profile: {name}")
    value = dict(PROFILES[name])
    value["name"] = name
    value["scope_count"] = len(SCOPES)
    value["expected_files"] = len(SCOPES) * value["files_per_scope"]
    value["expected_current_chunks"] = (
        value["expected_files"] * value["sections_per_file"]
    )
    value["minimum_current_chunks"] = (
        MINIMUM_CURRENT_CHUNKS if name == "full" else value["expected_current_chunks"]
    )
    return value


def document_name(file_index):
    return f"document-{file_index:04d}.md"


def section_heading(scope_index, file_index, section_index):
    return (
        f"Scale record S{scope_index:02d} F{file_index:04d} C{section_index:02d}"
    )


def section_needle(scope_index, file_index, section_index):
    # Words and digits (rather than punctuation-heavy UUIDs) remain friendly to
    # both the trigram tokenizer and future baseline tools.
    return f"scale needle s{scope_index:02d} f{file_index:04d} c{section_index:02d}"


def _reference_token(scope_index, file_index, section_index, sentence_index):
    return hashlib.sha256(
        (
            f"{SEED}:{scope_index}:{file_index}:{section_index}:{sentence_index}"
        ).encode("ascii")
    ).hexdigest()[:12]


def section_query(scope_index, file_index, section_index):
    """Return a tokenizer-stable token unique to the expected section."""
    return _reference_token(scope_index, file_index, section_index, 0)


def _sentence(scope, scope_index, file_index, section_index, sentence_index):
    terms = scope["terms"]
    first = terms[sentence_index % len(terms)]
    second = terms[(sentence_index + 1) % len(terms)]
    digest = _reference_token(
        scope_index, file_index, section_index, sentence_index
    )
    measure = 100 + ((scope_index * 7919 + file_index * 101 + section_index * 17
                      + sentence_index) % 9_800)
    return (
        f"The {scope['persona']} {first} record links {second} evidence to "
        f"measure {measure} under deterministic reference {digest}."
    )


def render_document(scope_index, file_index, profile_name):
    """Render one LF-only Markdown file with one chunk per ATX section."""
    selected = profile(profile_name)
    scope = SCOPES[scope_index]
    sections = []
    for section_index in range(selected["sections_per_file"]):
        heading = section_heading(scope_index, file_index, section_index)
        needle = section_needle(scope_index, file_index, section_index)
        paragraphs = [
            (
                f"{needle}. This synthetic {scope['use_case']} section belongs to "
                f"{scope['name']} and is safe to publish."
            )
        ]
        sentence_index = 0
        while sum(len(value) for value in paragraphs) < selected["body_chars"]:
            group = []
            for _ in range(3):
                group.append(
                    _sentence(
                        scope,
                        scope_index,
                        file_index,
                        section_index,
                        sentence_index,
                    )
                )
                sentence_index += 1
            paragraphs.append(" ".join(group))
        section = f"## {heading}\n\n" + "\n\n".join(paragraphs) + "\n\n"
        if len(section) >= CHUNKING_MAX_CHARS:
            raise AssertionError(
                f"rendered section exceeds one-chunk bound: {len(section)}"
            )
        sections.append(section)
    return "".join(sections)


def validate_spec():
    names = [scope["name"] for scope in SCOPES]
    if len(names) != 20 or len(set(names)) != 20:
        raise AssertionError("scale fixture must define exactly 20 unique scopes")
    for name in names:
        if not name or any(not (ch.isascii() and (ch.isalnum() or ch == "-")) for ch in name):
            raise AssertionError(f"scope name is not a portable ASCII leaf: {name}")
    full = profile("full")
    if full["expected_current_chunks"] != 120_000:
        raise AssertionError("full scale profile must produce exactly 120,000 chunks")
    if full["expected_current_chunks"] < MINIMUM_CURRENT_CHUNKS:
        raise AssertionError("full scale profile must exceed 100,000 chunks")


validate_spec()
