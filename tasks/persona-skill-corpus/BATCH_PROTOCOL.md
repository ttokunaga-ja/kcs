# Batch production protocol

## First physical milestone

The default first milestone is **200 final files per persona** (4,000 files
across twenty personas). Because every authoritative percentage is an integer,
the exact target for a format family is `percentage × 2`. This milestone is a
production target, not a historical renderer output: every DOCX/XLSX/PPTX/PDF/
image file must be newly authored through the routed skill workflow.

Do not attempt all 200 files in one agent turn. The parent chat first partitions
the target into the persona's twenty non-overlapping leaf folders. Each folder
assignment contains fixed relative filenames and uses batches of 5–20 artifacts,
small enough to complete generation, render inspection, provenance, inventory,
and scope-status updates in the same turn. An interrupted batch is not final.

## Batch lifecycle

1. A new parent chat selects exactly one persona with no parent `lease.json`
   (confirmed by the lease `show` command). `status.json` is a report, not the
   ownership authority.
2. The parent reads `COMMON_RULES.md`, this protocol, and the assigned persona
   brief. Before planning or creating artifacts it atomically claims the persona:

   ```bash
   python3 eval/persona_skill_corpus_lease.py claim \
     --root <production-root> --persona p01 --session <unique-session-id>
   ```

   The claim prints a one-time `release_token`. Keep it in the active parent
   chat only; do not put it in prompts, status, logs, or corpus files.
   `lease.json` is the ownership authority; `status.json.owner_session` is only
   an informational checkpoint and may lag it. An existing lease makes the
   claim fail without mutation, and `show` never discloses the release token.
3. The parent checks the persona-wide checkpoint and every scope-local
   inventory. It freezes the persona narrative anchors, then writes one exact
   assignment for each selected fixture folder: relative filenames, artifact
   IDs, format families/variants, dates, numbers, and expected cross-file links.
   Never infer progress from directory names. The scope's parent-owned
   `assignment.json` has this minimum shape:

   ```json
   {
     "schema_version": 1,
     "persona_id": "p01",
     "scope_path": "documents/work/product-alpha/architecture",
     "scope_id": "scope-<sha256>",
     "assigned_parent_session": "<parent-chat-session-id>",
     "assigned_worker_session": "<subagent-assignment-id>",
     "state": "planned",
     "files": [
       {
         "artifact_id": "<stable-id>",
         "relative_name": "adr-0042.docx",
         "format_family": "docx",
         "format_variant": "docx",
         "skill_route": "Documents",
         "narrative_anchors": ["project-alpha", "2026-07-13"],
         "cross_file_links": []
       }
     ]
   }
   ```

   `relative_name` is a direct filename in the assigned leaf folder, not a path
   into another folder. The worker treats this file list as immutable.
4. Immediately before spawning a worker, the parent claims exactly one folder
   scope on that worker's behalf, bound to the active parent persona session:

   ```bash
   python3 eval/persona_skill_corpus_lease.py scope-claim \
     --root <production-root> --persona p01 \
     --scope documents/work/product-alpha/architecture \
     --parent-session <parent-chat-session-id> \
     --worker-session <subagent-assignment-id>
   ```

   The parent retains the returned scope release token. It then spawns the
   subagent with exactly that plan-defined leaf folder, its scope-control ID,
   fixed assignment, and public worker-session ID—but never either release
   token. Two different scope leases in the same persona may be active
   concurrently; a duplicate scope claim fails.
5. Each scope worker produces ordinary text/code/data with normal file-writing
   tools and routes DOCX, XLSX, PPTX, both PDF families, and images through the
   named skills. It may not expand or change the parent's fixed assignment or
   edit `assignment.json` itself.
6. Generate and inspect in the matching
   `<persona>/_production/scopes/<scope-id>/temp` and `renders`; promote a
   reviewed final artifact only into that scope's assigned `home/` folder.
7. Append one scope-local inventory row, provenance row, and QA row per promoted
   artifact, then update the scope-local status and precise next action. A
   worker never writes persona-wide journals.
8. After the active folder workers finish or checkpoint, the parent validates
   their assignment bounds and QA joins, reconciles narrative consistency, and
   deterministically rebuilds the persona-wide aggregate checkpoint.

## Count and ownership rules

- The authoritative family ratios and paths come only from
  an accepted Rust `kio-eval persona plan` artifact; the persona brief is an
  operational, non-authoritative view.
- At 200 files, every primary or secondary path must be represented according
  to the fixture allocation, every family count must equal `2 × ratio`, and
  variant counts/gate roles/dispositions must equal
  `format_variant_counts(persona, "tiny")`. The scaffold copies this oracle
  into each `manifest.json` as `format_variant_counts_200`.
- Embedded images do not count as independent `image` files. Only a standalone
  file below `home/` contributes one inventory item.
- A `pdf_scan` counts as one PDF artifact; its intermediate ImageGen source is
  production evidence unless the plan separately calls for a final image file.
- One parent chat owns one complete persona. It is the only writer of
  persona-wide narrative, assignment planning, status, and aggregate journals.
- One subagent assignment owns one plan-defined leaf folder plus its matching
  scope-control directory. Never split one leaf folder between active workers.
- Distinct leaf folders are disjoint and may run concurrently. A worker must
  finish/checkpoint before it can receive another folder assignment; the parent
  then releases that worker's scope lease.
- Dispatch folder workers in waves sized to the available subagent slots. Keep
  the parent chat free for planning, cross-folder consistency, conflict
  resolution, validation, and aggregation.

## Lease release and interrupted sessions

Each subagent reports completion only after its folder batch has either been
fully promoted and journaled or recorded as `blocked` with an exact next
action. The parent then validates the checkpoint and releases the scope lease.
The parent releases the persona lease only after every child scope lease is gone
and the persona-wide checkpoint has been rebuilt:

```bash
python3 eval/persona_skill_corpus_lease.py release \
  --root <production-root> --persona p01 --token <claim-release-token>
```

The parent releases each finished folder assignment with its separate one-time
scope token:

```bash
python3 eval/persona_skill_corpus_lease.py scope-release \
  --root <production-root> --persona p01 \
  --scope documents/work/product-alpha/architecture \
  --parent-session <parent-chat-session-id> \
  --token <scope-release-token>
```

Scope tokens stay with the active parent chat and must not be written into a
subagent prompt or production metadata. Parent `release` and `recover` fail
closed while any child scope lease remains active.

There is no time-based automatic takeover. After an interrupted session, the
next parent first runs `show` and `scope-show`, inspects persona and scope
status/inventory/temp output, and asks the user to confirm that the old writer
is no longer running. Only then use the corresponding explicit recovery
authority, which records a durable receipt:

```bash
python3 eval/persona_skill_corpus_lease.py recover \
  --root <production-root> --persona p01 \
  --expected-session <session-from-show> --reason "user confirmed writer stopped"
```

For one interrupted folder assignment, use:

```bash
python3 eval/persona_skill_corpus_lease.py scope-recover \
  --root <production-root> --persona p01 \
  --scope documents/work/product-alpha/architecture \
  --parent-session <parent-chat-session-id> \
  --expected-worker-session <worker-from-scope-show> \
  --reason "user confirmed folder worker stopped"
```

Routine release requires the undisclosed token, and all claim/release/recover
transitions serialize on a descriptor-bound per-persona guard. A stale release
cannot delete a replacement lease.

These leases are coordination mechanisms against accidental duplicate parent
chats or folder workers, not privilege boundaries against another process
running as the same OS user with direct write access to the production root.
`recover` and `scope-recover` are explicit trusted-coordinator overrides, not
proof of authorization: invoke them only after the user confirms that the named
writer stopped. Their receipts make that exceptional decision auditable.

## Completion states

- `scaffolded`: folders and empty metadata only.
- `generating`: an owner has a current batch.
- `qa`: files exist in production work areas but are not all promoted.
- `blocked`: exact cause and resumable next action recorded.
- `complete`: target family counts, path placement, provenance, and visual/
  structural artifact QA are complete. This does **not** claim Kio search QA.
