# Persona-PC environmental suite contract (v1)

Status: partial implementation.  W0 tiny publication, contributor/structural
allocators, the root-independent planned event manifest, and the twenty-person
suite schedule exist.  Persona fidelity/size hypotheses, bounded one-person
planning, the full planned-count oracle, read-only root lease, partial semantic
attestation, canonical non-executing prepare-receipt composition, and
fail-closed capacity/storage/runner boundaries also exist;
W0 history prepare, replay, and pilot/full physical publication remain blocked.  This
suite is additive to the frozen Recall corpus and Decision 90's balanced
20-scope scale control.

## 1. Objective

Reproduce twenty independent synthetic people rather than twenty use-case
folders.  Each person owns one nested PC tree, one isolated Kio device
registry, twenty active direct-file scopes, mixed raw formats, and W0-W5
history.  The full profile must attest more than 100,000 current searchable
chunks for **every** person; pooling twenty smaller people is invalid.

No personal data, ambient credential, external API call, release, merge, or
tag operation belongs to this suite.

## 2. Non-substitution

- `eval/golden-queries.jsonl`, `eval/corpus-fixture.json`, and
  `eval/history-plan.json` remain the frozen Recall/history inputs.
- Rust `kio-eval scale generate|prepare|attest|benchmark` is the balanced
  one-device current-text control. Persona-PC results never relabel its
  current-only M3-2/M3-3 numbers as formal history latency.
- A tiny or pilot profile is progress and CI coverage, not evidence for the
  full 100k-plus gate.
- Raw Office, scan, image, container, and domain binary files never count as
  searchable chunks merely because the generator created them.

## 3. Profiles

| profile | people | scopes/person | raw-file purpose | current-chunk purpose |
| --- | ---: | ---: | --- | --- |
| `tiny` | 20 | 20 | 200 files/person; exact integer format percentages and a stable contributor in every scope | routing/topology smoke only |
| `pilot` | 20 | 20 | 1,000 files/person | 12,000 planned contributor chunks/person; calibrate bytes/chunk |
| `full` | 20 | 20 | persona-specific full file counts | 120,000 contract contributor chunks/person |

`full` is manual-only.  A formal full run requires exactly 120,000 attested
contract-contributor chunks per person and 2,400,000 for the suite at both W0
and W5.  The 100,001 value is only an exploratory fail-fast floor and can never
be reported as a passing full result.  All current eligible chunks may be
higher because incidental UTF-8 formats can also be indexed by the current
implementation.  W4 deletion and W5 purge events therefore include planned
replacement/correction sources in the same wave so the contributor target is
net-zero; history growth is not obtained by shrinking the current corpus.

The common eight secondary paths and 75/25 contributor weights form the v1
**formal control lane**, retained so per-person latency remains comparable.
They are not a claim that twenty real PCs share one topology.  A separate
persona-fidelity/recursive-robustness lane may vary secondary paths, weights,
registered-scope count, ambient folders, and naming disorder, but its chunks
cannot substitute for the formal gate until a new versioned contract freezes
those marginals.

## 4. One-person layout and identity

```text
<suite>/devices/<persona-id>-<slug>/
  persona-manifest.json
  home/
    <nested portable parents>/
      <direct-file leaf scope>/
  .kio-eval-device/{config,data,cache}/    # prepare phase; absent at W0 create
  oracle/{events,expected-states,queries}/ # history/query phase; absent at W0
```

The immutable fixture identity is `scope_key`, never Kio `scope_id`.  A prepare
receipt binds `scope_key` to the observed root-specific `scope_id`.  Specs store
POSIX relative paths; generation converts individual validated components to
native paths.  Parent collection directories are not scopes.  Only the listed
leaf directories contain managed direct files.

The generator never runs `kio init` or `kio index` at the PC umbrella or any
intermediate parent.  Each listed leaf is initialized independently, contains
managed files only as direct children, and contains no managed nested
directory.  This is required by Kio's direct-file scope semantics and prevents
one persona from silently becoming more or fewer than twenty active scopes.

Every person has twelve role-specific primary scopes and the same eight
secondary PC scopes (Desktop, Reference, Downloads Inbox/Exports, Cloud
MyFiles/TeamShared, Mail, and Archive).  Primary scope chunk weights sum to 75%
and secondary weights to 25%.  All twenty participate in that person's global
search; ambient/noise directories do not.

`eval/persona_fixture_spec.py` is the normative machine-readable matrix for
the twenty archetypes, twelve primary paths/person, exact format percentages,
full physical-file counts, format-to-scope routing constraints, contributor weights, and
history targets.  Validation must reject a missing row, cloned scope matrix,
ratio total other than 100, or a persona/scope allocation that differs from
that matrix.  The common 75/25 split is a workload envelope, not permission to
make the twenty role-specific trees identical.

Limits:

- exactly 20 people and 20 active scopes/person;
- fewer than 9,000 direct files/scope (below Kio's 10,000 soft limit);
- portable ASCII scope components, at most 80 characters/component and 240
  characters/root-relative scope path;
- no `.`/`..`, separator, control, Windows-forbidden character, trailing
  dot/space, reserved Windows stem, or case-insensitive sibling collision;
- W0 managed source basenames are bounded lowercase ASCII.  Unicode NFC
  portability fixtures remain separate from this large corpus and do not alter
  its format ratios.

The suite must retain a meaningful hierarchy rather than only two-component
paths: at least 60 of the 400 scope paths have depth four or greater, at least
10 personas have a depth-five path, and the suite maximum depth is at least
six.  Managed files remain direct children of the leaf despite deeper parents.

Before writing, generation emits a plan containing projected physical files,
logical members, current/history chunks, raw bytes, Kio CAS/index bytes, inode
count, staging peak, and the multiplier for every requested replay.  Full
generation requires explicit byte/inode caps and reserve headroom.  The writer
uses an owned-root marker, refuses `/`, a home directory, the repository, any
of their ancestors, and an unowned non-empty destination, publishes W0
atomically, and resumes later waves from bounded journals.  It never creates
cross-replay hard links.  Per-file 512 MiB, per-scope 4 GiB, and peak per-wave
direct-file limits are preflighted before each mutation wave.
Capacity bytes include a filesystem-allocation allowance of at least one
measured allocation unit per retained inode; apparent payload length alone is
not a safe cap.  The capacity receipt binds the final destination, filesystem
device/allocation unit, explicit limits, plan, and suite manifest through a
root binding used by the owner marker.  Physical publication on Windows is
blocked until native directory-handle durability can be confirmed; plan
generation remains portable.

The v1 matrix totals 195,000 W0 physical files and 400 scopes per replay.
Structural lifecycle additions finish at 195,080 active files/replay, so three
full replays plan 585,000 W0 files and 585,240 final active files, 1,200 scopes,
7.2 million W0/W5 current contributor chunks, and at least 10.8 million
current-plus-historical chunks after W5.  Byte caps are deliberately not
guessed from these cardinalities: the pilot profile must measure renderer,
CAS, SQLite/FTS, and history amplification before a full-run byte limit is
approved.

## 5. Three ledgers

W0 generation records three immutable, pre-index ledgers:

1. **physical raw** — path, bytes, raw SHA-256, format family;
2. **logical item** — message/attachment/page/sheet/slide membership;
3. **search plan** — planned contract chunks and the post-index policy that the
   later Kio attestor must prove.

Actual HEAD/current-config chunk identities are a separate root-specific
prepare/attestation receipt.  The W0 search-plan ledger is never evidence that
Kio produced the planned count.

Required source fields include stable `source_id`, `persona_id`, `scope_key`,
direct-child `file_name`, `format_family`, `raw_sha256`, `bytes`,
`logical_members`, `extension`, `variant`, `media_type`,
`renderer_id`, `renderer_schema_version`, `expected_contract_chunks`,
`expected_disposition`, and `gate_role`.

`gate_role` values:

- `contract_contributor`: Markdown, plain text, recognized code, or text-layer
  PDF deliberately used to prove the 120k floor;
- `incidental_searchable`: valid structured/mail text that current octet-stream
  sniffing may index but is not a stable format-parser contract;
- `raw_only`: pending enrichment or unsupported/noise, expected to contribute
  zero current chunks offline.

Every W0 raw hash is unique across the suite.  Exact and near duplicates are
introduced only by an explicit W3 event and separately counted in the physical
history ledger; they never create searchable identity by assertion alone.

Search-ready attestation proves, per person:

```text
contract_contributor_chunks == 120000
all_current_eligible_chunks >= contract_contributor_chunks
raw_only_chunks == 0
all_current_eligible_chunks == contributor + incidental
```

The same assertions are checkpoints at W0 and W5.  In addition, the full
history attestation requires at least 180,000 eligible current-plus-historical
chunks per person after W5, with non-zero edited-old, renamed, moved, deleted,
restored, and purged populations reported separately.  A current-only corpus
cannot satisfy this history gate.

Raw-file percentages are independent from chunk weights.  Integer file counts
use largest-remainder allocation with format-key order as the stable tie-break.
The format-ratio denominator is the person's W0 physical direct-child file
count.  The 75/25 scope weights apply to contract-contributor chunks.  Chunk
counts use distinct `(scope_key, chunk_id)` identities at the named
checkpoint; duplicate paths remain separate only in physical counts.
The W0 generator must persist a deterministic two-dimensional format-by-scope
allocation whose row and column marginals equal the independently attested
persona format totals and scope capacities.  The current specification freezes
those marginals, routing hints, and per-scope minimum stable-variant capacity.
The joint allocator recomputes and validates the canonical min-cost route; each
persisted contributor source then receives a deterministic per-scope quota in
the inclusive range 1–72 whose scope sum is exact.
Scope-category routing keeps,
for example, code in repository/build scopes, EML in Mail, Office/PDF in
project/reference scopes, and export artifacts in Downloads/Exports while
preserving the persona-level marginals.

The v1 family percentages are stress-design weights, not an observed-user
distribution.  Before pilot/full approval, the plan must add persona-specific
raw scope-size weights, extension/domain-binary profiles, and physical
size/logical-complexity buckets.  A single shared `.pcap` profile for every
persona and minimum-valid rich files are insufficient byte/fidelity evidence.

## 6. Format families

The canonical format keys are:

```text
md, txt_log, code, structured_text, csv_tsv, html_eml, ipynb,
pdf_text, pdf_scan, docx, xlsx, pptx, image, media, domain_binary
```

| family | core variants | deterministic minimum | baseline role |
| --- | --- | --- | --- |
| `md` | `.md`, `.markdown` | NFC/LF headings and paragraphs | contributor |
| `txt_log` | `.txt`, `.log`, `.jsonl` | plain text or timestamped/JSON lines | mixed by variant |
| `code` | `.py`, `.rs`, `.ts` | syntactically valid function/comment records | contributor when recognized |
| `structured_text` | JSON, YAML, XML, SQL | parseable records/schema/query | incidental |
| `csv_tsv` | `.csv`, `.tsv` | header plus quoted rows | incidental |
| `html_eml` | `.html`, `.eml` | valid HTML or RFC-style UTF-8 mail | incidental |
| `ipynb` | `.ipynb` | nbformat 4 Markdown/code cells | incidental |
| `pdf_text` | `.pdf` | valid xref and text operators per page | contributor |
| `pdf_scan` | `.pdf` | image XObjects, no text operator | raw-only / awaiting OCR |
| `docx` | `.docx` | minimal valid WordprocessingML package | raw-only / conversion |
| `xlsx` | `.xlsx` | workbook, worksheet, rels, inline strings | raw-only / conversion |
| `pptx` | `.pptx` | slide, master, layout, theme, all rels | raw-only / conversion |
| `image` | `.png` | CRC-valid deterministic RGB PNG | raw-only / awaiting OCR |
| `media` | `.wav` | valid deterministic PCM RIFF/WAVE | raw-only / unsupported |
| `domain_binary` | `.pcap` initially | valid header and synthetic packet | raw-only / unsupported |

The standard-library core renderer may create UTF-8 text, deterministic JSON,
CSV, HTML/XML, SQL/log, notebook JSON, classic text-layer PDF, simple PNG, and
minimal validated OOXML packages.  A PPTX includes slide master, layout, theme,
and complete relationships, whether generated directly or derived from a
sanitized fixed-hash template; an invalid ZIP renamed to `.pptx` is forbidden.
Optional rich-local rendering and D1 byte-volume/OCR-quality measurements are
separate profiles.

All renderers are functions of `(schema version, persona_id, scope_key,
family, variant, source_id, version, requested contributor chunks)` and produce
byte-identical output.  Text is UTF-8 NFC with LF and a
final newline.  OOXML ZIP entries use lexical order, the fixed 1980 epoch, and
`ZIP_STORED`; package XML, content types, relationships, and referenced parts
are validated before publication.

Current offline expectations:

- stable local contributor: `md`, `txt_log`, recognized `code`, `pdf_text`;
- incidental: structured text, CSV/TSV, HTML/EML, notebook JSON when the current
  printable UTF-8 sniff accepts it;
- raw-only: scan PDF, OOXML, images, media, and domain binaries unless a
  separately approved deterministic fixture adapter supplies normalized output.

Gate role is assigned per source variant, not inferred solely from the grouped
family.  For example `.txt` may be a stable contributor while `.log` or
`.jsonl` in `txt_log` is incidental, and only explicitly recognized code
extensions are contributors.  Attestation reports exact source and chunk
counts for local-done, incidental-sniff, pending-OCR, awaiting-conversion, and
unsupported dispositions.

## 7. History waves

Waves are immutable ordered event manifests applied in place to the same
person root:

| wave | purpose | representative operations |
| --- | --- | --- |
| W0 | baseline | create, init, offline index |
| W1 | daily work | edit, create, small rename/move |
| W2 | reorganization | project/account rename and cross-scope move |
| W3 | milestone | major edit, exact/near duplicate, derived format |
| W4 | closure | archive move and delete |
| W5 | correction/retention | correction, restore, regulated purge |

Every event has a unique ID, stable logical time, complete before/after source
state, affected scope keys, and typed scope effects.  Events, boundaries, and
the execution schedule are separate immutable tables.  A boundary has one
kind from `index_auto`, `purged_commit`, or `index_noop`, one scope key, and all
participating event IDs.  The `none` kind is an event-side command effect and
does not invent a commit boundary.  Thus one cross-scope move references two
scope boundaries while several events in one scope share exactly one ordinary
index.  Restore's source command effect is `none`; only its existing active
destination scope participates in the following `index_auto`.

Every event in a wave is preflighted before the first mutation.  Writes are
atomic; rename/move require matching source hash and absent destination;
symlink, reparse point, special file, and all fixture/Kio metadata paths are
rejected.

Ordinary working-tree changes use the affected scope's normal offline `index`
auto-snapshot.  No redundant explicit snapshot is added.  Each affected scope
has at most one mutating ordinary index per wave.  W5 additionally has one
asserted post-purge `index_noop` per purge-affected scope.  Each path purge uses
its own forced `purged_commit`.

History arithmetic is defined over contract contributors, not over every
incidental locally searchable format.  At checkpoint `w`, let:

```text
C_w = distinct (scope_key, chunk_id) reachable from every scope HEAD
A_w = distinct (scope_key, chunk_id) reachable from all HEAD ancestors,
      after purge filtering
H_w = A_w - C_w
```

The exact 120,000/60,000 contract below applies to contributor identities.
Attestation separately proves that all eligible current/history sets are
supersets and reports incidental identities; incidental history cannot be used
to make the contributor gate pass.  A source is indivisible because `raw_hash`
participates in every chunk identity: any edit creates a new version of every
chunk in that source even if only one byte changed.

The normative full allocation uses five mutually exclusive whole-source
contributor cohorts, selected jointly by source quota and scope:

| cohort | W0 contributor weight | operations |
| --- | ---: | --- |
| P | 4% | W1 edit; W5 path purge both versions and replace with P' |
| X | 10% | W1 edit; W3 edit; W4 delete and replace with X' |
| Y | 6% | W1 edit; W3 edit; remain current |
| N | 4% | W3 edit; W5 correction |
| U | 76% | arithmetic control; safe members may carry rename/alias sentinels |

P, X, Y, and N are chunk-weight cohorts, not raw-file percentages.  P/X/Y/N
source IDs are disjoint.  All four cover all twenty scopes with positive
quota in full.  Exact sums are person-global; per-scope percentages are not a
contract because the indivisible `q/q+1` source quotas make many scope cells
arithmetically impossible.  Deterministic hash-spread selection additionally caps one scope at 20% of that
cohort plus one 72-chunk indivisible-source allowance, preventing nominal
coverage with a nearly single-scope workload.  Tiny uses `E=20% target`, `P=4%`, `X=10%`,
`Y=E-P-X`, and `N=P` to avoid independent-floor drift.  Only full requires
twenty-scope event coverage.

Independent quota-zero raw-only sentinels exercise cross-scope move/archive,
restore, near duplicate, derived format, and create without changing C/H.
Same-scope rename and exact same-scope duplicate may use safe U contributors.
P may never be renamed, moved, duplicated, or reused under another live path.
Quota-zero cross-scope sentinels prove structural and CLI lifecycle behavior,
not searchable move/restore Recall.  A future searchable cross-scope lane must
declare the extra source-scope historical identity instead of reusing the flat
W2 target.

The frozen structural inventory is eleven events/person in tiny and pilot,
and thirty events/person in full:

| wave | tiny/pilot | full | operation set |
| --- | ---: | ---: | --- |
| W1 | 3 | 3 | one U rename, one raw-only cross-scope move, one raw-only create |
| W2 | 2 | 21 | second U rename(s), plus one raw-only cross-scope move |
| W3 | 3 | 3 | exact U alias, one-channel near PNG, PNG-derived scan PDF |
| W4 | 2 | 2 | traveler move to active `archive/closed`, created-source delete |
| W5 | 1 | 1 | path restore into a different existing active scope |

Full W2 uses one safe U contributor per scope, so all twenty scopes receive a
real mutating boundary; tiny/pilot retain the eleven-event behavioral smoke.
The move traveler, create/delete/restore source, and two PNG transform parents
are distinct.  Raw-only means the conjunction of contributor quota zero,
`gate_role=raw_only`, and later attestation of zero actual chunks; incidental
quota-zero files do not satisfy this condition.

`source_id`, `source_version`, and `materialization_id` are independent.
Rename/move/archive retain all three; edit retains source/materialization and
increments version; exact alias retains source/version/raw but creates a new
materialization; near/derived create parent-bound sources/materializations;
restore retains the deleted source/version/raw and creates a new
materialization.  The near PNG changes exactly one decoded RGB channel by one,
and the derived scan PDF embeds the parent's exact decoded RGB bytes without a
text layer.  Restore fixes a path/checkpoint locator in the source scope and
never uses a multi-file commit restore.

Structural sources add three source IDs/person and finish at four additional
live files/person.  Therefore full final active files are 195,080/replay and
585,240 across three replays, while the W0 physical-format percentages remain
reported against their original 195,000-file denominator.  These additions
are structural deltas, not a revised W0 format distribution.

Full contract-contributor checkpoints are:

| wave | current C | history-only H | planned delta |
| --- | ---: | ---: | --- |
| W0 | 120,000 | 0 | baseline |
| W1 | 120,000 | 24,000 | edit P+X+Y |
| W2 | 120,000 | 24,000 | same-scope rename; q=0 cross-scope sentinels |
| W3 | 120,000 | 48,000 | edit X+Y+N |
| W4 | 120,000 | 60,000 | delete X; same-scope/variant/quota X' replacements |
| W5 final | 120,000 | 60,000 | correct N; P path purge; P' replacements |

W5 first creates and normalizes every distinct P' while old P remains, together
with N corrections and quota-zero restores, in the wave's one ordinary index.
This explicit transient checkpoint has C=124,800 and H=64,800 and is included
in capacity planning.  Then, in canonical P-source order, replay removes one
old P working path and immediately runs `purge <old-path>` before touching the
next.  Every P path has exactly its W0 and W1 raw versions, so each path purge
deletes `2*q` historical version-chunks and its forced commit reports one file
deletion.  Across the person this purges 9,600 version-chunks: 4,800 from the
previously historical W0 versions and 4,800 from the retired current W1
versions.  P' supplies 4,800 current chunks.  Final C/H is therefore
120,000/60,000, and one following index per purge scope must be a strict noop.
`--raw-hash` is not equivalent because it selects only one raw version.

The obsolete exclusive raw buckets and their one-percent purge count are not
authorization to replay.  Feasibility probing found a P/X/Y/N exact subset for
all 60 persona-profile combinations; the implemented canonical allocator now
binds source ID, quota, gate role, variant, scope, cohort, and one-for-one
replacement, rejects any non-canonical W0 expansion, regenerates the canonical
result for validation, and gives every positive cohort full twenty-scope
coverage.  The structural allocator additionally binds the exact sentinels
above and canonically rebuilds them for all 60 persona/profile combinations.
The root-independent planned event manifest joins both lanes, renders complete
before/after hashes, coalesces wave/scope boundaries, and freezes W5 ordering.
The suite manifest hash-binds exactly twenty individually validated persona
manifests and replaces their independent execution chains with one root-wide
chain: all W1--W4 regular events precede all ordinary indexes in each wave;
W5 is all regular events, all ordinary indexes, persona/source-sorted purge
event/commit pairs, then all post-purge noops.  An executor must hold one
exclusive replay-root lock across that complete chain.
W1-W5 mutation nevertheless remains fail-closed until W0 history-ready
evidence and replay lock/preflight/journal/resume exist.

## 8. Three fresh replays

After event manifests are frozen, the entire W0-W5 sequence is generated into
three fresh roots.  Kio stores are never copied.  Each replay has twenty
independent device registries, for sixty registries total.

Immutable source/spec/event manifests are byte-identical across replays.
Root-specific prepare/attestation receipts are not byte-identical; their
canonical projections compare event/state roots, logical paths, raw hashes,
normalized scope-key history shape, commit type/message/statistics, and
current/history/deleted/purged counts.  They exclude absolute roots,
root-derived scope IDs, commit hashes, process IDs, durations, mtimes, and real
timestamps.  Receipts pin repository HEAD, Kio binary hash/version, renderer
and fixture schema versions, chunking-config hash, and tool-profile hash.
Re-running a completed root must be a strict no-op; interruption and resume
must converge without applying an event twice.

## 9. Evaluation order and gates

Generation may run fail-fast structural guards, but formal evaluation begins
only after all requested replay roots exist:

1. source/tree/format and capacity attestation;
2. isolated registry and HEAD/current-chunk attestation;
3. W0-W5 history, delete, restore, and purge attestation;
4. fifteen distinct M3-1, fifteen M3-2, and fifteen M3-3 oracle queries per
   person (900 unique queries), executed on a designated attested replay;
5. repeated warm/cold timing samples on that replay: per-person M3-1 p95 below
   5 seconds and M3-2/M3-3 p95 below 7 seconds — never a pooled average;
6. full-PC robustness report for additional ambient/noise directories, clearly
   outside the formal 20-scope performance guarantee.  The eight common-PC
   secondary scopes are inside the formal twenty and inside every per-person
   Recall and latency gate;
7. history-workload report covering event/commit count, W5 wall-clock, database
   and object-store growth at the 124,800/64,800 transient peak, per-path purge
   and resume throughput, and post-purge noop cost.  Byte/inode capacity alone
   is insufficient for the 2,775 forced purge commits per full replay.

Generated large corpora stay outside Git.  Git contains specifications,
deterministic renderers, event manifests/generators, small goldens, tests, and
reports only.

The other two fresh replays prove semantic reproducibility; they do not triple
the formal query count unless a run explicitly requests a variance study.
Q_hard baseline comparison, D1 byte-volume/TTFV/cost measurement, and real OCR
quality remain separate gates.  All persona runs isolate HOME and XDG state,
use offline execution, scrub ambient credentials/test seams, and attest zero
network-adapter completion and zero external cost.

## 10. Implementation status

Implemented now: canonical 20-person plans, deterministic format-by-scope and
source quota expansion, 25 safe render variants, W0 physical/logical/search
ledgers, root/suite/persona manifests, and allocated-block cardinality
projection.  The machine-readable spec also contains twenty distinct persona
fidelity profiles plus a common small/medium/large/tail size-complexity
hypothesis contract.  A bounded one-person plan API and a full planned-count
and resource-limit oracle complement the P/X/Y/N allocator, structural
allocator, event manifest, tiny-tested root-wide suite schedule, bounded
per-person event artifacts plus an O(20) schedule/locator/MMR composer,
tiny-only W0 publisher, prepare-envelope verifier, and read-only replay-root
lease, plus a canonical root/person/device/scope prepare-receipt composer.

The history allocator proves exact person-global planned sums in tiny/pilot/full
and full twenty-scope coverage for every positive cohort.  The prepare-receipt
composer regenerates the canonical all-person plan SHA one bounded persona at
a time, binds an exact ordered 20×20 projection to the root binding and declared
binary/environment/init/index receipt hashes, rejects root `/`, overlong paths,
duplicate environment/init/index receipt hashes, coherent plan-digest
substitution, and fixes every
semantic/history/execution/mutation claim to false.  It does not parse or
type-check the referenced artifact bodies.  The tiny filesystem
gate creates two fresh 4,000-source roots, proves immutable-byte equality and
disjoint inodes, preserves all metadata on a ready no-op, and rejects raw
tampering.  The lease identity-binds the root, owner marker, and W0 root binding,
rejects reentry/contention, repeats its checks before release, creates no lock
artifact, and remains POSIX-only.  A scoped API duplicates the already-held root
FD without reopening its path and detects persistent close/rebind/inheritable
tampering, including a fresh reopen of the same inode, without closing a reused
foreign FD.  The open-description probe is covered on Darwin and Linux.  It closes the root check/open
seam only for cooperating readers; same-UID ABA, transient rebinding, leaked
duplicates, immutable snapshots, and process isolation remain unresolved.  It
neither attests Kio nor authorizes mutation.

The full oracle processes one canonical persona at a time and derives, without
building full event manifests, exactly 43,596 events, 5,175 boundaries, and
48,771 schedule items/replay; the three-replay totals are 130,788 / 15,525 /
146,313.  Frozen caps include 8 MiB/persona plan, 16,000 sources, 20 scopes,
384 MiB worker RSS, 128 MiB composer RSS, 512 MiB process-tree RSS, one worker,
512 rows/shard, and 32 MiB/shard.  Worker/suite receipts are nevertheless
caller-declared projections with `formal_capacity_gate_satisfied=false` until
artifact readback and supervisor `wait4` evidence exist.

The streaming suite layer holds at most one complete persona event manifest at
a time, publishes bounded event/boundary/schedule-projection JSONL shards, and
composes the global schedule, external row locators, and their MMR from twenty
compact summaries.  It does not retain twenty full manifest objects.  Its tiny
projection is byte-semantically identical to the legacy builder: 1,076 events,
908 boundaries, 1,984 schedule items, and the same schedule and suite-manifest
SHA-256 values.  This is planning evidence only.  The artifacts inherit the
lower-level `source_directory_inode_not_bound_by_rename` blocker and remain
`formal_publication_attested=false`; full artifact readback, supervised RSS,
and `wait4` receipts have not been demonstrated.

The capacity layer derives exact file/chunk/event cardinalities but remains
blocked until canonical pilot measurement and destination-root availability
receipts are read back.  It binds filesystem allocation unit, caps, reserves,
and root identity without granting physical-write authority or Kio attestation.
Bounded streaming storage can no-replace publish and read back canonical JSONL,
but portable rename cannot atomically require that the already-verified source
directory inode remains the rename source.  Its receipts therefore retain
`formal_publication_attested=false` and blocker
`source_directory_inode_not_bound_by_rename`.

The Kio boundary implements strict result validators, isolated-environment
recipes, read-only binary snapshots, and unbound command-receipt types.  After
the scope-path-to-`Popen(cwd=...)` same-user TOCTOU finding,
`HANDLE_RELATIVE_EXECUTION_AVAILABLE`, `PERSONA_FILESYSTEM_MUTATION_AVAILABLE`,
and `TRUSTED_BINARY_EXECUTION_AVAILABLE` all remain false.  No init/index/version
subprocess or persona mutation is executable through this API.

The partial semantic attestor binds profile, canonical persona/scope identity,
contract-quota arithmetic, file bytes/content roots, and typed runtime checker
observations.  It does not itself validate SQLite/CAS semantics, HEAD/commit
relations, binary/config, root binding, or prepare intent.  Even an exact
20-person, 400-scope, 20-device projection always returns
`history_ready_attested=false`.  Before retaining child names or Merkle
children, every walked directory is hard-capped at 16,384 direct entries.  Its
experimental handle callback now has a lease-derived root-FD entry point, but is
explicitly non-authoritative.  Its typed receipt fixes
`formal_transport_attested=false` and cannot be serialized into the
provenance-free legacy nine-field envelope callback.  A complete checker additionally needs a native
FD-bound read-only SQLite/WAL snapshot backend: Python's standard `sqlite3`
path API cannot use a held directory FD as cross-platform authority for the
scope database and per-person registry without reopening paths or potentially
touching sidecars.  Until that backend also proves writer quiescence/same-epoch
snapshot semantics, actual chunks and history readiness remain unattested.

The fidelity and size profiles remain metadata-only initial hypotheses:
`implemented_by_renderer=false`.  Current renderer bytes, extension/domain-
binary variants, OS behavior, and searchability claims are unchanged.

Not implemented or not approved: formal publication plus supervised
RSS/artifact-readback/`wait4` evidence for the full suite stream, W0 init/index
prepare executor and complete Kio semantic history-ready
receipt, W1-W5 lease integration/safe mutation/journal/executor,
attestation/query generation, rendered rich size/domain-binary distributions,
pilot/full physical publication and measured byte cap, Windows physical
publication, and any actual 120,000-Kio-chunk/person result.  The existing path
boundary retains a same-user TOCTOU residual until handle-relative traversal is
implemented.  `HISTORY_ASSIGNMENT_EXECUTABLE` remains false.
See `tasks/persona-pc-eval-proposal.md` for the readable matrix and rollout order.
