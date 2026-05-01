# ADR 0012: History Purge For Legal And Secrecy Erasure

## Status

Accepted.

## Context

KCS normally preserves knowledge. Ordinary delete / archive removes a path from the latest view but keeps older snapshots recoverable. GC only removes unreachable objects and therefore cannot satisfy legal erasure, secrecy, or mistaken-import requirements when historical snapshots still reference the target.

## Decision

KCS provides an explicit destructive `purge` operation that removes a target file from all history.

```bash
kcs purge docs/secret.pdf --all-history --reason "legal erasure request"
kcs purge --raw-hash sha256:abc... --all-history
```

GUI must expose the same capability as:

```text
このファイルの履歴を完全削除
```

Purge rewrites or invalidates all references to the target path / raw hash, including derived normalized artifacts, prepared units, chunks, embeddings, nodes, edges, evidence, indexes, packs, and caches.

## Constraints

Purge requires an impact preview, explicit confirmation, and a reason.

Purge may leave a minimal tombstone for audit, but that tombstone must not contain body text, normalized text, secret paths, or any value that can reconstruct the removed content.

## Consequences

GC remains a storage maintenance operation.

Purge is the only operation intended to satisfy legal, secrecy, and mistaken-import erasure requirements.

Protected snapshots are protected from ordinary GC, but not from an explicitly authorized purge of a specific file.
