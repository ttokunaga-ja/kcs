# Persona skill corpus production

This directory is the operating runbook for producing a high-fidelity, synthetic
20-persona corpus across multiple Codex sessions. The executable authority for
persona IDs, roles, format ratios, scope paths, weights, and count profiles is
[`eval/persona_fixture_spec.py`](../../eval/persona_fixture_spec.py); these
documents do not replace it.

Start with [COMMON_RULES.md](COMMON_RULES.md), choose work from the
[persona index](PERSONA_INDEX.md), and follow [BATCH_PROTOCOL.md](BATCH_PROTOCOL.md).
Then scaffold exactly the layout in [PRODUCTION_LAYOUT.md](PRODUCTION_LAYOUT.md)
with:

```bash
python3 eval/scaffold_persona_skill_corpus.py --root "$(pwd)/persona-corpus"
```

To resume an already owned scaffold without overwriting artifacts, add
`--resume`. Use
[SESSION_HANDOFF.md](SESSION_HANDOFF.md) to resume a stopped production.

The production root is the repository root's `persona-corpus/` directory. It
contains exactly twenty direct persona folders, `p01-...` through `p20-...`.
The corpus itself belongs only in `<pXX-role>/home/`. Production state,
receipts, prompts, temporary renders, and QA evidence belong in that persona's
`<pXX-role>/_production/` tree and must never be copied into `home/`.

Each persona is an independent synthetic PC. Produce its twelve fixture-defined
primary scopes plus the eight shared secondary scopes; retain the fixture's
75/25 primary/secondary weighting and all format percentages exactly.

Ownership has two levels:

- One parent chat session coordinates exactly one complete persona folder and
  holds that persona's parent lease.
- Inside that chat, each artifact-producing subagent is assigned exactly one of
  the persona's twenty fixture-defined leaf folders. It writes only the fixed
  files in that folder and that folder's matching production-control area.

Different folder assignments inside the same persona may run concurrently.
Never assign two active subagents to the same leaf folder, and never let a
subagent append to persona-wide shared journals. The parent chat owns narrative
decisions, assignment planning, persona-wide status, and deterministic
aggregation of the folder journals. Subagents have the same artifact
capabilities as the parent session and may produce routed files after reading
the applicable skill instructions. They do not provide a permanent background
workforce across closed sessions: every turn must finish or checkpoint its
folder batch and leave complete scope-local status.
