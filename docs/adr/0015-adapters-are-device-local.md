# ADR 0015: Adapters Are Device-local

## Status

Accepted.

## Context

KCS allows Markdown processing, Embedding processing, search-delegation Agent work, and summarization Agent work to be delegated to user-selected adapters. OCR is treated as a capability inside Markdown processing, not as a top-level peer adapter.

If shared `.kcs/` metadata carried executable adapter configuration such as commands, URLs, arguments, or credentials, importing or sharing a `.kcs/` could induce unsafe execution on another device.

## Decision

Adapter execution configuration is device-local.

Each device stores adapter configuration in its own user configuration area, such as:

```text
~/.config/kcs/
OS keychain
enterprise-managed local config
```

`.kcs/` does not manage adapters and must not share executable adapter settings. It may store only non-executable provenance and compatibility metadata such as profile hashes, dimensions, distance metric, input hashes, and output hashes.

## Consequences

Sharing `.kcs/` does not transfer commands, URLs, API keys, or credentials.

A receiving device maps stored profile metadata to its own local adapter configuration, or falls back to text search / pending tasks when no compatible adapter exists.
