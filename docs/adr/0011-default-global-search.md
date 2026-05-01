# ADR 0011: Default Search Is Global Across Indexed Scopes

## Status

Accepted.

## Context

KCS aims to redefine the local knowledge space. The product should bring a Google-like common search experience to local files by normalizing PDF / Office / image-heavy file spaces into Markdown-centered text artifacts.

Earlier notes considered defaulting search to the current folder or current folder plus descendants. That is safer by locality, but it weakens the core product promise: a unified local knowledge search experience.

## Decision

Default search targets all folders and files known to KCS, i.e. all indexed scopes.

```bash
kcs search "query"
```

means:

```text
all indexed scopes
```

Users can explicitly restrict scope.

```bash
kcs search "query" --scope .
kcs search "query" --scope . --descendants
kcs search "query" --scope ./Research
kcs search "query" --scope ./Research --descendants
```

Agent API responses must include the actual searched scopes and excluded scopes.

## Consequences

KCS provides a unified search experience by default.

Privacy and locality are handled by explicit scope filters, ignore rules, permissions, and response metadata rather than by current-directory-only defaults.

All docs that still say default search is `self + descendants` or `current folder only` are superseded by this ADR.
