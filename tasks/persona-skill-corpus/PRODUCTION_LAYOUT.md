# Production layout and checkpoint metadata

The production root is repository-root `persona-corpus/`. It has exactly twenty direct persona directories, with no central `devices/` or `_production/` directory:

```text
persona-corpus/
  p01-software-engineer/
    WORKSPACE.md                       # immutable scaffold guidance
    home/
      <12 fixture-defined primary paths>/
      <8 shared secondary paths>/
    _production/
      status.json
      lease.json                       # present only while exclusively claimed
      manifest.json
      inventory.jsonl
      provenance.jsonl
      narrative.json
      qa.jsonl
      lease-recovery.jsonl
      .lease.lock
      prompts/  temp/  renders/  evidence/
  p02-site-reliability-engineer/
  ... p20-investigative-journalist/
```

Each `WORKSPACE.md` is an immutable, scaffold-owned control file. It identifies
the persona, points to the common rules, batch protocol, and persona brief, and
states that its session owns only that complete persona folder.

One subagent/session owns one complete persona folder `<persona>/`: its `home/` and
`_production/` trees together. Distinct persona folders may run concurrently
without collision. Never split a persona folder between writers. Its lease and
control files are at `<root>/<persona>/_production/`.

The authoritative primary paths are `persona["primary_paths"]`; the shared
secondary paths are `SECONDARY_PATHS`. Build all twenty paths by calling the
fixture's scope helpers or by reading their output—do not maintain a duplicate
path table here. `_production/` is outside its persona's `home/` tree, so it
cannot enter corpus format ratios or evaluation scopes.

Create the complete directory skeleton before content production. A persona's
`status.json` must at least contain `persona_id`, `role`, `owner_session`, `state`
(`scaffolded|generating|qa|blocked|complete`), `updated_at`, `next_action`,
and `blocking_issue`. `owner_session` is informational; only `lease.json` is
authoritative for writer ownership. `inventory.jsonl` records every final relative `home/`
path, scope key, format family, format variant, size, checksum, narrative/source
ID, immutable `artifact_id`, and `active` state.
`manifest.json` identifies the persona, fixture version, scope allocation, and
the inventory/provenance/QA record versions. `provenance.jsonl` records synthetic
seed, generation method/skill, inputs, and promotion time. `narrative.json` records
the approved fictional entities, timeline, terminology, and numeric anchors.
`qa.jsonl` records artifact path, required render/inspection, result, evidence
location, and reviewer/date.

`artifact_id` is the join key shared by `inventory.jsonl`, `provenance.jsonl`,
and `qa.jsonl`. An artifact counts as final only when its latest active inventory
row and latest QA row have the same `artifact_id` and checksum, and that QA row
has `result: "pass"`. Replacements receive a new `artifact_id`; the prior
inventory row is superseded rather than silently edited. `completed_artifacts`
may advance only from that joined predicate. Keep failed/replaced material under
`<persona>/_production/temp/` with its reason, never under `home/`.

The scaffold resolves all known directories relative to retained no-follow
directory descriptors and rejects internal symlinks, non-directories, foreign
ownership, permissive directories, and non-regular/multiply-linked control
files, including any active lease, on resume. The marker identifies the layout
version; it is not an authorization token. Corpus workers must preserve the
same no-link rule when promoting final artifacts.
