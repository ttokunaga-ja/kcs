"""Literal project/case themes for the persona-PC v2 fact-graph leaf.

This module is data only.  The themes are authored benchmark hypotheses, not
observed user records and not rendered prose.  Every project/case identifier
is synthetic, globally unique in the suite, and follows ``*-syn-NNN``.
"""

from __future__ import annotations


# Persona order is part of the fixture contract.  Each nested row is
# (project_or_case_id, graph_kind).  Suffixes 001..080 are suite-global.
GRAPH_THEME_ROWS = (
    ("p01", (
        ("release-syn-001", "project"),
        ("incident-syn-002", "case"),
        ("migration-syn-003", "project"),
        ("dependency-syn-004", "case"),
    )),
    ("p02", (
        ("outage-syn-005", "case"),
        ("capacity-syn-006", "project"),
        ("handoff-syn-007", "case"),
        ("rollback-syn-008", "case"),
    )),
    ("p03", (
        ("audit-syn-009", "case"),
        ("evidence-syn-010", "case"),
        ("control-exception-syn-011", "case"),
        ("vendor-risk-syn-012", "case"),
    )),
    ("p04", (
        ("experiment-syn-013", "project"),
        ("dataset-revision-syn-014", "project"),
        ("paper-review-syn-015", "project"),
        ("cluster-run-syn-016", "project"),
    )),
    ("p05", (
        ("dashboard-syn-017", "project"),
        ("forecast-syn-018", "project"),
        ("data-quality-syn-019", "case"),
        ("metric-definition-syn-020", "project"),
    )),
    ("p06", (
        ("protocol-syn-021", "project"),
        ("instrument-run-syn-022", "project"),
        ("sample-batch-syn-023", "project"),
        ("manuscript-syn-024", "project"),
    )),
    ("p07", (
        ("archive-collection-syn-025", "project"),
        ("translation-syn-026", "project"),
        ("manuscript-syn-027", "project"),
        ("citation-provenance-syn-028", "case"),
    )),
    ("p08", (
        ("roadmap-syn-029", "project"),
        ("launch-syn-030", "project"),
        ("user-feedback-syn-031", "case"),
        ("quarterly-metrics-syn-032", "project"),
    )),
    ("p09", (
        ("interview-study-syn-033", "project"),
        ("synthesis-syn-034", "project"),
        ("usability-syn-035", "case"),
        ("media-analysis-syn-036", "project"),
    )),
    ("p10", (
        ("workstream-syn-037", "project"),
        ("due-diligence-syn-038", "case"),
        ("workshop-syn-039", "project"),
        ("deliverable-syn-040", "project"),
    )),
    ("p11", (
        ("account-syn-041", "project"),
        ("proposal-syn-042", "project"),
        ("renewal-syn-043", "project"),
        ("call-followup-syn-044", "case"),
    )),
    ("p12", (
        ("escalation-syn-045", "case"),
        ("support-incident-syn-046", "case"),
        ("onboarding-syn-047", "project"),
        ("advisory-syn-048", "project"),
    )),
    ("p13", (
        ("matter-syn-049", "case"),
        ("policy-review-syn-050", "case"),
        ("data-request-syn-051", "case"),
        ("legal-hold-syn-052", "case"),
    )),
    ("p14", (
        ("close-syn-053", "project"),
        ("variance-syn-054", "case"),
        ("reconciliation-syn-055", "case"),
        ("forecast-syn-056", "project"),
    )),
    ("p15", (
        ("requisition-syn-057", "case"),
        ("candidate-loop-syn-058", "case"),
        ("onboarding-syn-059", "project"),
        ("policy-case-syn-060", "case"),
    )),
    ("p16", (
        ("clinical-protocol-syn-061", "project"),
        ("site-query-syn-062", "case"),
        ("safety-review-syn-063", "case"),
        ("submission-syn-064", "project"),
    )),
    ("p17", (
        ("drawing-package-syn-065", "project"),
        ("rfi-syn-066", "case"),
        ("change-order-syn-067", "case"),
        ("inspection-syn-068", "case"),
    )),
    ("p18", (
        ("capa-syn-069", "case"),
        ("batch-deviation-syn-070", "case"),
        ("audit-syn-071", "case"),
        ("work-instruction-syn-072", "project"),
    )),
    ("p19", (
        ("course-syn-073", "project"),
        ("lesson-syn-074", "project"),
        ("assessment-syn-075", "project"),
        ("accommodation-syn-076", "case"),
    )),
    ("p20", (
        ("investigation-syn-077", "case"),
        ("claim-syn-078", "case"),
        ("information-request-syn-079", "case"),
        ("fact-check-syn-080", "case"),
    )),
)


PREDICATE_ROWS = (
    ("predicate-owner-unit-syn-001", "entity-reference"),
    ("predicate-contact-email-syn-002", "email"),
    ("predicate-endpoint-ip-syn-003", "documentation-ip"),
    ("predicate-status-syn-004", "synthetic-token"),
    ("predicate-priority-syn-005", "unsigned-integer"),
    ("predicate-measure-syn-006", "scaled-integer"),
    ("predicate-effective-day-syn-007", "logical-day-offset"),
)


CHECKPOINT_ROWS = (
    ("W0", 0),
    ("W1", 7),
    ("W2", 14),
    ("W3", 30),
    ("W4", 60),
    ("W5-pre-purge", 90),
    ("W5-final", 91),
)


REFERENCE_INSTANT_ID = "reference-instant-syn-001"
REFERENCE_INSTANT_UTC = "2026-07-13T00:00:00Z"
MEASURE_UNIT_ID = "measure-unit-syn-001"
