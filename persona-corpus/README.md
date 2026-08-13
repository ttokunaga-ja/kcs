# Persona corpus workspaces

This directory contains twenty independent persona workspaces. Each production
session owns exactly one direct child folder, including that persona's `home/`
and `_production/` trees. Different persona folders may be worked on in
parallel; never assign two active sessions to the same persona.

Before starting production, read:

- [`../tasks/persona-skill-corpus/README.md`](../tasks/persona-skill-corpus/README.md)
- [`../tasks/persona-skill-corpus/COMMON_RULES.md`](../tasks/persona-skill-corpus/COMMON_RULES.md)
- [`../tasks/persona-skill-corpus/BATCH_PROTOCOL.md`](../tasks/persona-skill-corpus/BATCH_PROTOCOL.md)
- [`../tasks/persona-skill-corpus/PERSONA_INDEX.md`](../tasks/persona-skill-corpus/PERSONA_INDEX.md)
- [`../tasks/persona-skill-corpus/SESSION_HANDOFF.md`](../tasks/persona-skill-corpus/SESSION_HANDOFF.md)

Every persona folder has an immutable `WORKSPACE.md` pointing to its individual
brief. Final corpus files belong only under that persona's `home/`. Temporary
renders, prompts, provenance, inventory, and artifact QA belong under that
persona's `_production/`.

The generated corpus and mutable production state are intentionally ignored by
Git. The folder skeleton and `WORKSPACE.md` files are tracked so sessions share
the same ownership boundaries without accidentally committing large artifacts.
