# ADR 0010: Offline-first Core And Adapter Boundary

## Status

Accepted.

## Context

KCS core must preserve access to existing knowledge even when network services, cloud APIs, or device-local tools are unavailable. At the same time, Markdown processing, Embedding processing, search-delegation Agent work, and summarization Agent work may require different local, cloud, internal, or faculty services depending on the user environment.

OCR is not modeled as a top-level peer of Markdown processing. It is a capability inside Markdown processing for scanned PDFs, images, and other non-text-native inputs.

## Decision

KCS core remains offline-capable for existing snapshot / artifact exploration, restoration, and search over already built indexes.

The following work is delegated to user-selected Adapters:

```text
Markdown processing, including OCR when needed
Embedding processing
Search delegation Agent
Summarization Agent
```

All Adapters connect through the common KCS API. Executable configuration, service URLs, commands, and credentials are device-local and are not stored in shared `.kcs/` metadata.

## Consequences

KCS can continue to search and restore existing artifacts without a configured Adapter.

Adapter failure creates pending work or fallback behavior instead of making the object store unusable.

Profile hashes and artifact hashes remain the shared compatibility record; runtime details remain local to each device.
