# ADR 0010: Offline-first Core And Adapter Boundary

## Status

Accepted.

## Context

KCS core must preserve access to existing knowledge even when online APIs, offline APIs, or device-local tools are unavailable. At the same time, Prepare, Markdownize, multimodal Embedding, and optional Summary / Classification / Rerank work may use different execution modes depending on the user environment: online APIs such as hosted LLMs, offline APIs such as local LLM servers, or deterministic libraries.

OCR is not modeled as a top-level peer of Markdownize. It is a capability inside Markdownize for scanned PDFs, images, and other non-text-native inputs.

## Decision

KCS core remains offline-capable for existing snapshot / artifact exploration, restoration, and search over already built indexes.

The following work is delegated to user-selected Adapters:

```text
Prepare
Markdownize, including OCR when needed
Multimodal Embedding
Summary optional
Classification optional
Rerank optional
```

All Adapters connect through the common KCS API. Executable configuration, service URLs, commands, and credentials are device-local and are not stored in shared `.kcs/` metadata.

## Consequences

KCS can continue to search and restore existing artifacts without a configured Adapter.

Adapter failure creates pending work or fallback behavior instead of making the object store unusable.

Profile hashes and artifact hashes remain the shared compatibility record; runtime details remain local to each device.
