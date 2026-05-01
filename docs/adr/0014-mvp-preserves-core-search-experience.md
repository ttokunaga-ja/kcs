# ADR 0014: MVP Preserves Core Search Experience

## Status

Accepted.

## Context

KCS is not primarily a storage demo. Its product value is the local knowledge search experience: cross-scope search, historical search, provenance, restore, and safe erasure boundaries.

Reducing the MVP until these behaviors disappear would make the MVP faster to build but would not validate the product.

## Decision

The MVP is the smallest complete core that preserves the intended search experience.

Initial users are CLI-comfortable developers, but the design must keep a path to UX-focused general-user workflows.

The MVP may take longer if needed, but it must not remove the basic KCS experience:

```text
content-addressed object store
normalized artifacts
chunking
search over all indexed scopes
time-travel search
evidence pointers
restore
resume / retry / repair
gc / purge safety boundaries
```

## Consequences

MVP scope is larger than a thin prototype.

Implementation milestones may still be staged, but product acceptance is based on preserving the core search experience rather than shipping a reduced search surface.
