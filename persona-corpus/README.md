# Persona corpus workspaces

This directory contains twenty independent persona workspaces. Each parent
production chat owns exactly one direct persona folder, including that
persona's `home/` and `_production/` trees. Inside that chat, artifact-producing
subagents divide the persona by its twenty fixture-defined leaf folders: one
subagent assignment owns one leaf folder plus its matching scope-control area.
Never assign two active workers to the same leaf folder.

Before starting production, read:

- [`../tasks/persona-skill-corpus/README.md`](../tasks/persona-skill-corpus/README.md)
- [`../tasks/persona-skill-corpus/COMMON_RULES.md`](../tasks/persona-skill-corpus/COMMON_RULES.md)
- [`../tasks/persona-skill-corpus/BATCH_PROTOCOL.md`](../tasks/persona-skill-corpus/BATCH_PROTOCOL.md)
- [`../tasks/persona-skill-corpus/PERSONA_INDEX.md`](../tasks/persona-skill-corpus/PERSONA_INDEX.md)
- [`../tasks/persona-skill-corpus/SESSION_HANDOFF.md`](../tasks/persona-skill-corpus/SESSION_HANDOFF.md)

Every persona folder has an immutable parent `WORKSPACE.md` pointing to its
individual brief. Final corpus files belong only under that persona's `home/`.
Parent planning and aggregates belong in `_production/`; each folder worker's
temporary renders, provenance, inventory, artifact QA, and lease belong in the
matching `_production/scopes/<scope-id>/` area.

The generated corpus and mutable production state are intentionally ignored by
Git. The folder skeleton and `WORKSPACE.md` files are tracked so sessions share
the same ownership boundaries without accidentally committing large artifacts.
