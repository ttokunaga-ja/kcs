# ADR 0013: KCS Metadata Is Folder-local

## Status

Accepted.

## Context

Some design notes can be misread as if `.kcs/` exists only once at a knowledge scope root. That is not the intended model.

KCS should feel closer to `.DS_Store` than to a single repository-root `.git/` directory. Every folder can have its own hidden `.kcs/` metadata directory.

## Decision

`.kcs/` is folder-local metadata. It is generated as a hidden directory in each folder that KCS tracks or indexes.

```text
folder/
  .kcs/
  child/
    .kcs/
    grandchild/
      .kcs/
```

Each `.kcs/` manages only:

```text
files directly under its folder
child folder links
folder-local metadata and indexes
```

Child and grandchild folder contents are managed by their own `.kcs/` directories.

## Consequences

Docs and implementation must not assume that child or grandchild folders lack `.kcs/`.

Default search can still be global across all indexed scopes. Global search is implemented by the search runner using a scope registry or discovered `.kcs/` list, not by making one parent `.kcs/` own all descendants.

Export, purge, restore, and repair must account for multiple `.kcs/` directories across the folder tree.

Content-addressed deduplication is guaranteed only within one `.kcs/objects` store. The same raw hash may be stored separately in different `.kcs/` directories. This duplication is accepted to preserve folder-local ownership and to keep export, partial sync, purge, restore, and GC independent per `.kcs/`.
