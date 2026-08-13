# Production layout and checkpoint metadata

The production root is repository-root `persona-corpus/`. It has exactly twenty direct persona directories, with no central `devices/` or `_production/` directory:

```text
persona-corpus/
  p01-software-engineer/
    WORKSPACE.md                       # parent-chat guidance
    home/
      <12 fixture-defined primary paths>/
      <8 shared secondary paths>/
    _production/
      status.json                      # parent chat only
      lease.json                       # active parent-chat lease
      manifest.json                    # parent chat only
      inventory.jsonl                 # parent-built aggregate
      provenance.jsonl                # parent-built aggregate
      narrative.json                  # parent chat only
      qa.jsonl                         # parent-built aggregate
      lease-recovery.jsonl  .lease.lock
      prompts/                         # parent plans
      scopes/
        <stable-scope-id>/
          WORKSPACE.md                 # one exact home folder assignment
          assignment.json              # parent-owned fixed file list
          status.json
          inventory.jsonl
          provenance.jsonl
          qa.jsonl
          lease.json                   # active subagent lease
          lease-recovery.jsonl  .lease.lock
          prompts/  temp/  renders/  evidence/
  p02-site-reliability-engineer/
  ... p20-investigative-journalist/
```

The persona-level `WORKSPACE.md` is an immutable, scaffold-owned control file.
It identifies the persona, points to the common rules, batch protocol, and
persona brief, and states that one parent chat coordinates the complete persona.
Each scope-level `WORKSPACE.md` binds one stable scope ID to exactly one
fixture-defined `home/` leaf folder and states the narrower subagent boundary.
Control files never live inside `home/`, so they cannot enter the corpus.
The parent writes `assignment.json` before dispatch. Its `files` array fixes the
artifact ID, direct relative filename, family/variant, skill route, narrative
anchors, and cross-file links. Scope workers read but never modify it.

One parent chat session owns one complete persona folder `<persona>/` and holds
the lease at `<root>/<persona>/_production/`. Its subagents intentionally split
the persona by fixture-defined leaf folder. Each subagent owns one
`<persona>/home/<scope-path>/` plus the single matching
`<persona>/_production/scopes/<scope-id>/` area. Distinct leaf folders have no
ancestor/descendant overlap and may run concurrently; never assign the same
leaf folder twice.

The authoritative primary paths are `persona["primary_paths"]`; the shared
secondary paths are `SECONDARY_PATHS`. Build all twenty paths by calling the
fixture's scope helpers or by reading their output—do not maintain a duplicate
path table here. `_production/` is outside its persona's `home/` tree, so it
cannot enter corpus format ratios or evaluation scopes.

Create the complete directory skeleton before content production. The
scaffold records the reversible scope-path-to-ID mapping in each scope manifest;
workers must not invent IDs or use a non-fixture path. A persona's parent
`status.json` must at least contain `persona_id`, `role`, `owner_session`, `state`
(`scaffolded|generating|qa|blocked|complete`), `updated_at`, `next_action`,
and `blocking_issue`. `owner_session` is informational; only `lease.json` is
authoritative for parent-chat ownership. Scope status uses the corresponding
scope lease as its writer authority. Scope-local `inventory.jsonl` records every
final relative `home/`
path, scope key, format family, format variant, size, checksum, narrative/source
ID, immutable `artifact_id`, and `active` state.
`manifest.json` identifies the persona, fixture version, scope allocation, and
the inventory/provenance/QA record versions. `provenance.jsonl` records synthetic
seed, generation method/skill, inputs, and promotion time. `narrative.json` records
the approved fictional entities, timeline, terminology, and numeric anchors.
`qa.jsonl` records artifact path, required render/inspection, result, evidence
location, and reviewer/date. Only the parent chat may rebuild the persona-level
aggregate journals from scope-local records, and only while no included scope
journal is being mutated.

`artifact_id` is the join key shared by the scope-local `inventory.jsonl`,
`provenance.jsonl`, and `qa.jsonl`. An artifact counts as final only when its latest active inventory
row and latest QA row have the same `artifact_id` and checksum, and that QA row
has `result: "pass"`. Replacements receive a new `artifact_id`; the prior
inventory row is superseded rather than silently edited. `completed_artifacts`
may advance only from that joined predicate. Keep failed/replaced material under
the matching scope's `_production/scopes/<scope-id>/temp/` with its reason,
never under `home/`.

The scaffold resolves all known directories relative to retained no-follow
directory descriptors and rejects internal symlinks, non-directories, foreign
ownership, permissive directories, and non-regular/multiply-linked control
files, including parent and scope leases, on resume. The marker identifies the
layout version; it is not an authorization token. Corpus workers must preserve
the same no-link rule when promoting final artifacts.
