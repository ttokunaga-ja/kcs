# Persona-PC v2 nesting and scope-evaluation contract v1

Status: **proposal only**.  This resolves what the current 20-persona design
does and does not claim about complex PC directory trees.  It creates no roots,
files, scopes, indexes, receipts, or performance result.

## 1. Problem boundary

The active objective needs both a realistic nested PC shape and a defensible
retrieval/latency denominator.  Those are not identical under the current KCS
scope model: a formal KCS scope owns its direct-child managed files, while a
real PC also contains nested imports, cache, conflict copies, partial files,
and system-specific path phenomena.

The required design therefore has two explicit, non-substitutable lanes:

| lane | root below one persona device | contents | included in formal 100k+/M3 denominator? |
| --- | --- | --- | --- |
| formal retrieval/history | `home/` | 20 nested-path leaf scopes; managed files are direct children of each leaf | yes |
| recursive robustness | `ambient-home/` | unregistered nested candidate files and directories, including cache/partial/collision cases | no |

The formal lane still has non-flat PC topology: every one of its leaf scopes is
located beneath persona-specific directory parents.  It does **not** claim that
arbitrary files below an unregistered parent are searchable.  The ambient lane
does **not** claim that its candidates were indexed or contributed chunks.

## 2. Formal lane contract

For every replay and every `p01..p20`:

- create exactly 20 active leaf scopes: 12 primary work scopes and 8 secondary
  personal-PC scopes;
- materialize each scope at
  `devices/<persona-role>/home/<persona-specific-relative-path>/`;
- place managed formal files only as direct children of that leaf directory;
- preserve the frozen 20-person topology's per-person depth shape (formal
  D2--D6), path uniqueness, no scope ancestor/descendant relation, casefold
  uniqueness, and persona-specific load vectors;
- include only formal-lane files in the person-scoped current/history chunk
  counts, M3 latency denominator, and formal capacity denominator; and
- prove path/file counts from a post-write filesystem walk and match them to
  the source-plan and scope-registry digest.

This is sufficient to test retrieval across a deeply nested PC hierarchy while
retaining the current direct-child scope semantics.  It cannot be described as
recursive document discovery within one scope.

## 3. Ambient recursive robustness contract

For every persona, the robustness lane uses a separate `ambient-home/` child:

- 256 candidate files in 128 authored directories;
- D6--D8 candidate-parent depths, with suite-wide D6/D7/D8 coverage;
- exact categories: 102 benign nested documents, 38 exact/near/conflict
  copies, 38 cache/temp files, 26 partial downloads, 26 hidden/lock files,
  13 empty files, and 13 Unicode/case-collision candidates;
- no registered KCS scope, `.kcs` metadata, formal source ID, formal query
  answer, or formal chunk contribution; and
- native-realized and expected-failure candidate counts recorded separately for
  the target filesystem case mode.

The ambient tree tests path traversal, exclusion, containment, collision, and
clean separation from formal scopes.  Its raw/allocated bytes and inode use
must appear in a **separate** robustness capacity receipt; it must not dilute
or inflate the formal retrieval/history denominator.

The existing ambient catalog is a histogram/representative-parent plan, not
yet an exact 5,120-file manifest.  It cannot by itself prove paths, basenames,
formats, byte sizes, or native realizability for every candidate.

## 4. Required evidence after implementation

Each persona/replay needs a nested-tree receipt with these independent sections:

| section | required evidence |
| --- | --- |
| formal topology | 20 scope paths, primary/secondary count, depth histogram, prefix count, max fan-out, per-scope file counts, direct-child-only check |
| formal isolation | scope registry digest, no ancestor/descendant scope pair, no cross-person path/inode/hard-link/symlink reuse |
| ambient topology | candidate and native-realized counts by category/depth, authored-directory count, intended case-mode result |
| ambient isolation | `registered_scope=false`, no `.kcs`, no formal source/query ID, no path intersection with `home/` |
| traversal behavior | declared walker operation, observed visited/excluded/failed paths, reason codes, and bounded error output |
| capacity | bytes/inodes reported independently for formal and ambient trees, then combined only for whole-device storage planning |

For the three formal fresh replays, topology and content identity must match
where root-specific values are excluded.  Native case-sensitive versus
case-insensitive ambient realization is reported as an environment result, not
silently normalized into a false success.

## 5. Required pre-materialization artifacts

The current topology sidecar and device compositor must not be treated as
implicitly joined.  The first static join is now frozen below; before any
writer is allowed, the remaining versioned, fail-closed artifacts must also
exist:

| priority | artifact / validator | required result |
| --- | --- | --- |
| P0 | formal-leaf placement binding | **static binding frozen**: exact join of 20 personas × 3 replays × 20 topology rows to `<device>/home/<relative_path>`, with a canonical scope registry and path digest; no writer/readback/KCS authority ([freeze record](persona-pc-v2-formal-leaf-placement-binding-v1-golden-freeze-record.md)) |
| P0 | direct-child writer guard | reject an unknown child directory, nested managed file, symlink/reparse point, hard link, or cross-person/replay reuse before a formal write |
| P0 | KCS direct-child regression | prove a direct child is indexable and make a nested managed file a writer error rather than allowing it to be silently omitted by the current non-recursive scanner |
| P1 | ambient-tree manifest | enumerate all 5,120 candidate files and 2,560 directories with exact relative path, parent, depth, category, basename, format, bytes, locale, collision relation, and expected disposition |
| P1 | ambient graph validator | recalculate category/depth/fan-out/Dmax, NFC/case requirements, formal/ambient disjointness, and zero undeclared entries |
| P1 | native traversal receipt | record host/target case semantics, realized versus candidate count, expected-failure reason, link/reparse/inode state, and traversal visit/exclusion result |
| P2 | lane-bound capacity receipt | retain formal and ambient storage costs separately, then combine them only for device-level capacity planning |
| P2 | ambient event manifest | record representative ambient rename/move/partial/lockfile operations separately from formal W1--W5 history |

## 6. Evaluation rules

1. M3 retrieval, 20-scope/100k+ latency, and Q_hard/baseline comparison use
   only formal roots and person-scoped formal index receipts.
2. Recursive robustness has its own pass/fail report: no scope escape, no
   traversal through prohibited path types, correct expected-failure handling,
   and no accidental registration/indexing of ambient files.
3. A successful formal performance result does not prove recursive robustness.
   A successful recursive walker result does not prove retrieval performance.
4. The Q_hard Phase 2 fixture remains a third, small evaluation artifact and
   may not be counted as either formal or ambient capacity evidence.

## 7. Escalation condition: recursive content as a formal retrieval target

If the intended Done condition is instead "files at arbitrary recursive depths
inside a persona PC must be searchable and contribute to the same 100k+
denominator," this contract is insufficient.  Before implementation, one of
the following must be selected and independently specified:

- register each applicable nested directory as an additional scope, including
  revised per-person scope/cardinality/latency gates; or
- add a recursive collection/adapter model with containment, symlink/reparse,
  duplicate, hidden-file, and identity rules plus a new chunk/latency
  denominator.

Neither option may be assumed from the existing ambient catalog.  Until such a
decision, the recommended v2 interpretation is the two-lane model above.

## 8. Existing evidence and remaining work

The static topology sidecar already contains 20 × 20 persona-specific formal
scope rows.  The frozen formal-leaf binding now joins them to the 60 planned
device `home/` roots for all three replays.  The recursive catalog still
defines only 20 × 256 ambient candidates and target depths, rather than an
exact tree.  All artifacts remain pre-materialization: write, KCS, and
observed-receipt authority are false.  The outstanding work is the remaining
P0/P1 guard and manifest work, then a writer, readback verifier, root-bound
capacity measurement, and three fresh replay executions—not a claim that
either tree currently exists.
