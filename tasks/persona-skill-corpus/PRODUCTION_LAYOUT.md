# Production layout and checkpoint metadata

For a production root `<root>`, use only this shape:

```text
<root>/
  devices/
    p01-software-engineer/
      home/
        <12 fixture-defined primary paths>/
        desktop/working/                 # shared secondary paths (8 total)
        documents/reference/
        downloads/inbox/  downloads/exports/
        cloud/my-files/  cloud/team-shared/
        mail/recent/  archive/closed/
    p02-site-reliability-engineer/
    ... p20-investigative-journalist/
  _production/
    p01-software-engineer/
      status.json
      lease.json                         # present only while exclusively claimed
      manifest.json
      inventory.jsonl
      provenance.jsonl
      narrative.json
      qa.jsonl
      lease-recovery.jsonl
      .lease.lock
      prompts/  temp/  renders/  evidence/
```

The authoritative primary paths are `persona["primary_paths"]`; the shared
secondary paths are `SECONDARY_PATHS`. Build all twenty paths by calling the
fixture's scope helpers or by reading their output—do not maintain a duplicate
path table here. `_production/` is deliberately outside all `home/` trees so
it cannot enter the corpus, format ratios, or evaluation scopes.

Create the complete directory skeleton before content production. A persona's
`status.json` must at least contain `persona_id`, `role`, `owner_session`, `state`
(`scaffolded|generating|qa|blocked|complete`), `updated_at`, `next_action`,
and `blocking_issue`. `owner_session` is informational; only `lease.json` is
authoritative for writer ownership. `inventory.jsonl` records every final relative `home/`
path, scope key, format family, format variant, size, checksum, narrative/source
ID, immutable `artifact_id`, and `active` state.
`manifest.json` identifies the persona, fixture version, scope allocation, and
the inventory/provenance/QA record versions. `provenance.jsonl` records synthetic
seed, generation method/skill, inputs, and promotion time. `narrative.json` records the approved fictional entities,
timeline, terminology, and numeric anchors. `qa.jsonl` records artifact path,
required render/inspection, result, evidence location, and reviewer/date.

`artifact_id` is the join key shared by `inventory.jsonl`, `provenance.jsonl`,
and `qa.jsonl`. An artifact counts as final only when its latest active inventory
row and latest QA row have the same `artifact_id` and checksum, and that QA row
has `result: "pass"`. Replacements receive a new `artifact_id`; the prior
inventory row is superseded rather than silently edited. `completed_artifacts`
may advance only from that joined predicate.
Keep failed/replaced material under `_production/<persona>/temp/` with its
reason, never under `home/`.

The scaffold resolves all known directories relative to retained no-follow
directory descriptors and rejects internal symlinks, non-directories, foreign
ownership, permissive directories, and non-regular/multiply-linked control
files, including any active lease, on resume. The marker identifies the layout version; it is not an
authorization token. Corpus workers must preserve the same no-link rule when
promoting final artifacts.
