# Batch production protocol

## First physical milestone

The default first milestone is **200 final files per persona** (4,000 files
across twenty personas). Because every authoritative percentage is an integer,
the exact target for a format family is `percentage × 2`. This milestone is a
production target, not the legacy renderer output: every DOCX/XLSX/PPTX/PDF/
image file must be newly authored through the routed skill workflow.

Do not attempt all 200 files in one agent turn. Use batches of 5–20 artifacts,
small enough to complete generation, render inspection, provenance, inventory,
and status updates in the same turn. An interrupted batch is not final.

## Batch lifecycle

1. The parent coordinator selects personas with no `lease.json` (confirmed by
   the lease `show` command) and assigns each persona to exactly one subagent.
   `status.json` is a report, not the ownership authority.
2. The owner reads `COMMON_RULES.md`, this protocol, and the assigned persona
   brief. Before creating artifacts it atomically claims the persona:

   ```bash
   python3 eval/persona_skill_corpus_lease.py claim \
     --root <production-root> --persona p01 --session <unique-session-id>
   ```

   The claim prints a one-time `release_token`. Keep it in the active parent
   session only; do not put it in prompts, status, logs, or corpus files.
   `lease.json` is the ownership authority; `status.json.owner_session` is only
   an informational checkpoint and may lag it. An existing lease makes the
   claim fail without mutation, and `show` never discloses the release token.
3. The owner checks current `inventory.jsonl` counts and writes a batch plan in
   `<persona>/_production/prompts/`. Never infer progress from directory names.
4. Produce ordinary text/code/data with normal file-writing tools. Route DOCX,
   XLSX, PPTX, both PDF families, and images through their named skills.
5. Generate and inspect in `<persona>/_production/temp` and `renders`; promote
   a reviewed final artifact into `home/` only after it passes artifact QA.
6. Append one inventory row, one provenance row, and one QA row per promoted
   artifact. Then update `status.json` counts and the precise next action.

## Count and ownership rules

- The authoritative family ratios and paths come only from
  `eval/persona_fixture_spec.py`; the persona brief is an operational view.
- At 200 files, every primary or secondary path must be represented according
  to the fixture allocation, every family count must equal `2 × ratio`, and
  variant counts/gate roles/dispositions must equal
  `format_variant_counts(persona, "tiny")`. The scaffold copies this oracle
  into each `manifest.json` as `format_variant_counts_200`.
- Embedded images do not count as independent `image` files. Only a standalone
  file below `home/` contributes one inventory item.
- A `pdf_scan` counts as one PDF artifact; its intermediate ImageGen source is
  production evidence unless the plan separately calls for a final image file.
- Assign one subagent/session to one complete persona folder. Do not subdivide
  a persona among concurrent writers: its narrative, inventory, status, and
  promotion stream are shared. Distinct persona folders can run concurrently
  without collision.
- Five persona owners may run in parallel. Complete or checkpoint those owners
  before assigning the next wave.

## Lease release and interrupted sessions

Release ownership only after the current batch has either been fully promoted
and journaled or recorded as `blocked` with an exact next action:

```bash
python3 eval/persona_skill_corpus_lease.py release \
  --root <production-root> --persona p01 --token <claim-release-token>
```

There is no time-based automatic takeover. After an interrupted session, the
next parent first runs `show`, inspects status/inventory/temp output, and asks
the user to confirm that the old writer is no longer running. Only then use the
explicit recovery authority, which records a durable receipt:

```bash
python3 eval/persona_skill_corpus_lease.py recover \
  --root <production-root> --persona p01 \
  --expected-session <session-from-show> --reason "user confirmed writer stopped"
```

Routine release requires the undisclosed token, and all claim/release/recover
transitions serialize on a descriptor-bound per-persona guard. A stale release
cannot delete a replacement lease.

This lease is a coordination mechanism against accidental duplicate parent
sessions, not a privilege boundary against another process running as the same
OS user with direct write access to the production root. `recover` is an
explicit trusted-coordinator override, not proof of authorization: invoke it
only after the user has confirmed that the named writer stopped. Its receipt
makes that exceptional decision auditable.

## Completion states

- `scaffolded`: folders and empty metadata only.
- `generating`: an owner has a current batch.
- `qa`: files exist in production work areas but are not all promoted.
- `blocked`: exact cause and resumable next action recorded.
- `complete`: target family counts, path placement, provenance, and visual/
  structural artifact QA are complete. This does **not** claim Kio search QA.
