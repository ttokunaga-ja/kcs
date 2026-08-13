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
python3 eval/scaffold_persona_skill_corpus.py --root /absolute/durable/corpus/root
```

To resume an already owned scaffold without overwriting artifacts, add
`--resume`. Use
[SESSION_HANDOFF.md](SESSION_HANDOFF.md) to resume a stopped production.

The corpus itself belongs only in `devices/<pXX-role>/home/`. Production state,
receipts, prompts, temporary renders, and QA evidence belong in the sibling
`_production/<pXX-role>/` tree and must never be copied into `home/`.

Each persona is an independent synthetic PC. Produce its twelve fixture-defined
primary scopes plus the eight shared secondary scopes; retain the fixture's
75/25 primary/secondary weighting and all format percentages exactly.

Subagents have the same artifact capabilities as the parent session and can
produce routed files after reading the applicable skill instructions. They do
not provide a permanent background workforce across closed sessions: every
turn must finish or checkpoint its batch, release/retain the explicit lease as
documented, and leave the next session a complete status record.
