# Persona skill corpus production

This directory is the operating runbook for producing a high-fidelity, synthetic
20-persona corpus across multiple Codex sessions. The executable authority for
persona IDs, roles, format ratios, scope paths, weights, source identities, and
count profiles is an accepted Rust `kio-eval persona plan` artifact; these
documents do not replace it.

Start with [COMMON_RULES.md](COMMON_RULES.md), choose work from the
[persona index](PERSONA_INDEX.md), and follow [BATCH_PROTOCOL.md](BATCH_PROTOCOL.md).
The historic scaffold command below is non-normative and must not be used to
derive topology or ratios. A retained filesystem boundary may consume an
accepted Rust plan artifact when materialization is separately authorized.

```text
kio-eval persona plan --profile <tiny|pilot|full> --out <absolute>
```

The legacy scaffold layout in [PRODUCTION_LAYOUT.md](PRODUCTION_LAYOUT.md) is
historical reference only. Use [SESSION_HANDOFF.md](SESSION_HANDOFF.md) only
after a retained boundary has accepted a Rust plan artifact for a separately
authorized materialization.

The production root is the repository root's `persona-corpus/` directory. It
contains exactly twenty direct persona folders, `p01-...` through `p20-...`.
The corpus itself belongs only in `<pXX-role>/home/`. Production state,
receipts, prompts, temporary renders, and QA evidence belong in that persona's
`<pXX-role>/_production/` tree and must never be copied into `home/`.

Each persona is an independent synthetic PC. Produce only the twelve primary
scopes plus eight shared secondary scopes specified by the accepted plan; retain
its frozen 75/25 primary/secondary weighting and format percentages exactly.

Ownership has two levels:

- One parent chat session coordinates exactly one complete persona folder and
  holds that persona's parent lease.
- Inside that chat, each artifact-producing subagent is assigned exactly one of
  the persona's twenty plan-defined leaf folders. It writes only the fixed
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
