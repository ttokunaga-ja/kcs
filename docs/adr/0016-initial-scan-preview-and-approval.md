# ADR 0016: Initial Scan Preview And Explicit Approval

## Status

Accepted

## Context

KCS defaults to all-file management and all indexed scope search. This is intentional: KCS prioritizes convenience, knowledge preservation, history search, and restore over minimal storage use.

However, KCS is not only a search index. It stores source files as content-addressed objects and may run Markdownize / Embedding adapters. Starting that work without user confirmation can surprise users and create privacy, storage, and trust problems.

## Decision

Before the first index of an unapproved scope, KCS must show a preview and require explicit approval.

The preview includes:

```text
included scopes
excluded scopes
estimated file count
estimated total bytes
large files
hidden / system / build / cache candidates
effective ignore rules
network transmission policy
adapter execution mode
```

Suggested exclusions are suggestions only. KCS must not silently narrow the default scope or automatically exclude large files without user approval.

In non-interactive environments, indexing an unapproved scope fails unless explicit approval is provided through a command option or an existing approval record.

## Consequences

KCS keeps the default all-file, all-scope experience while making the archive and storage implications visible before any raw object storage or adapter execution begins.

This decision does not reduce MVP scope. It is part of the product trust boundary for the full MVP.
