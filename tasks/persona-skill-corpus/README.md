# Persona skill corpus production

This is an operational runbook for a synthetic 20-persona corpus. The only
authority for persona IDs, roles, scope IDs, home paths, ratios, sources, and
counts is the accepted Rust plan. These documents are not an alternate schema,
parser, generator, renderer, or scaffold contract.

Create all four canonical artifacts with Rust, then create new roots only with
the Rust create-only commands:

```bash
kio-eval persona plan --profile <tiny|pilot|full> --out <absolute-plan>
kio-eval persona schedule --plan <absolute-plan> --out <absolute-schedule>
kio-eval persona render --plan <absolute-plan> --out <absolute-render>
kio-eval persona materialize \
  --plan <absolute-plan> --schedule <absolute-schedule> \
  --render <absolute-render> --destination <absolute-artifact-root> \
  --replay-id <id>
kio-eval persona scaffold --plan <absolute-plan> --root <absolute-workspace-root>
```

`materialize` publishes exactly the canonical plan, schedule, render, and its
Rust materialization record. `scaffold` creates the workspace topology and its
Rust workspace-owner record. Both reject existing destinations; create new
workspace roots outside the repository and never adopt,
mutate, or infer a workspace from the checked-in historical `persona-corpus/`
skeleton.

The scaffolded content path for a given plan row is
`people/<persona-id>-<role>/home/<scope-path>`. The lease API never accepts that
path: it accepts the distinct Rust `scope_id`, and writes coordination state
only beneath `_control/`. Do not derive a scope ID from a path.

Rust also owns bounded duplicate-writer coordination and filesystem
attestation. Use `persona lease claim`, `persona lease scope claim`, `persona
lease scope release`, and `persona lease release` against the plan-derived
workspace; use `persona attest` against the materialized root. These commands
derive record bindings internally: they accept neither caller-supplied owner
nor materialization digests. Attestation keeps Kio evidence and history
readiness claims false. They accept no second caller-provided plan, do not
reconstruct topology outside the stored canonical Rust plan, do not
prepare/replay Kio, and make no search/history claim.

Production work is plan-authoritative. A parent owns one persona lease; a
worker owns one plan-defined leaf scope at a time. Worker output belongs only
under that row's `home/<scope-path>`; the control scope is identified by its
Rust `scope_id`. Read [BATCH_PROTOCOL.md](BATCH_PROTOCOL.md) and
[SESSION_HANDOFF.md](SESSION_HANDOFF.md) before starting work.
