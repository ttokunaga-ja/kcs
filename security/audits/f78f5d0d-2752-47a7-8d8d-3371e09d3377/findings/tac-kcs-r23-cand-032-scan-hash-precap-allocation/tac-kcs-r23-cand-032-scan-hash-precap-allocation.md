# Scan Hashing Allocates the Full File Before the Input-Size Gate

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
contains a local availability flaw in the normal, non-preview `kcs index`
path. The scanner records each direct child file's metadata length, but when
raw hashes are enabled it immediately calls `std::fs::read()` on the whole
file before the configured `adapter.policy.max_input_bytes` gate is consulted.
An included oversized or sparse regular file can therefore force `O(n)` heap
allocation, file I/O, and hashing work while the index command holds the store
lock. The later cap still protects adapter normalization and network
submission, but it is too late to protect the scan-time allocation.

I reviewed the affected revision and the saved validation and attack-path
analysis directly. I did not run a high-memory or host-exhaustion experiment;
the included PoC is a safe local source-order probe with a bounded 1 MiB read
demonstration. The validated severity is Medium/P2 because the issue is
recoverable and scope-local, but it can reliably deny indexing for the selected
scope and stress the invoking user's host resources.

## Background

KCS indexes a selected repository root by first building a scan preview, then
passing accepted candidates into the indexing pipeline. That preview stage is
where KCS decides which direct children are regular files, whether they are
ignored or secret-excluded, and, during normal indexing, what raw hash belongs
to each candidate. Preview mode is the important negative control: it disables
raw hashes and returns before the heavy pipeline.

The normal entry point asks for raw hashes before it checks whether the command
is only a preview:

```rust
// crates/kcs-cli/src/main.rs:575-584
let preview = build_scan_preview(ScanPreviewRequest {
    scope_path: repo.root().display().to_string(),
    include_raw_hashes: !args.preview,
    require_network_approval: !args.offline,
})
.map_err(pipeline_to_kcs)?;

if args.preview {
    return Ok(index_preview_json(repo.root(), &preview));
}
```

We should read that as the point where ordinary `kcs index` commits to
scan-time content hashing. The command has already opened the repository,
taken the store lock, and is about to inspect direct children in the selected
scope. A lower-trust contributor who can place files in that scope does not
need network access, credentials, or a race; file size is enough to influence
the resource cost of this stage.

The intended size policy is documented in code as the effective
`adapter.policy.max_input_bytes` value. By default, KCS uses 100 MiB:

```rust
// crates/kcs-cli/src/main.rs:4425-4433
/// Documented default for `adapter.policy.max_input_bytes` (07 §7): 100 MB.
const DEFAULT_MAX_INPUT_BYTES: u64 = 104_857_600;

/// R12-2: effective `adapter.policy.max_input_bytes` -- scope config wins over user
/// config, default 100 MB (07 §7). Enforced as an input gate in `run_index_pipeline`.
fn effective_max_input_bytes(repo: &Repository) -> u64 {
    read_max_input_bytes_config(&repo.kcs_dir().join("config.toml"))
        .or_else(|| read_max_input_bytes_config(&user_config_toml_path()))
        .unwrap_or(DEFAULT_MAX_INPUT_BYTES)
}
```

That policy is real, but it is an adapter input gate. The vulnerability is the
temporal gap before KCS reaches it.

## Vulnerability Details

The vulnerable control flow is compact. The scanner enumerates direct
children, rejects non-regular entries, derives the relative path, and reads
the metadata length at line 122. At that exact point, KCS already knows the
logical size that should drive any pre-allocation decision:

```rust
// crates/kcs-pipeline/src/scan.rs:97-122
for entry in std::fs::read_dir(scope_path).pipeline_io(scope_path)? {
    let entry = entry.pipeline_io(scope_path)?;
    let name = match entry.file_name().into_string() {
        Ok(name) => name,
        Err(_) => continue,
    };
    if name == ".kcs" || name == ".kcsignore" {
        continue;
    }
    let path = entry.path();
    if is_xdg_state_inside_scope(scope_path, &path) {
        continue;
    }
    let file_type = entry.file_type().pipeline_io(&path)?;
    if !file_type.is_file() {
        continue;
    }
    let relative = path
        .strip_prefix(scope_path)
        .unwrap_or(&path)
        .to_string_lossy()
        .replace('\\', "/");
    if relative == ".kcsignore" {
        continue;
    }
    let size_bytes = entry.metadata().pipeline_io(&path)?.len();
```

We then carry `size_bytes` forward as metadata, but the raw-hash branch does
not consult it. If the file is included and raw hashes are enabled, KCS reads
the entire pathname into a `Vec<u8>` and hashes that buffer:

```rust
// crates/kcs-pipeline/src/scan.rs:123-149
let secret = classify_secret(&relative);
let ignored = ignored_by_rules(
    &relative,
    file_type.is_dir(),
    ignore_rules,
    case_insensitive,
) || secret == Some(SecretTier::TierA)
    && !explicitly_unignored(
        &relative,
        file_type.is_dir(),
        ignore_rules,
        case_insensitive,
    );
let quarantine_reason = match secret {
    Some(SecretTier::TierA) if ignored => Some("secrets_tier_a_excluded".to_owned()),
    Some(SecretTier::TierA) => Some("secrets_tier_a_online_hold".to_owned()),
    Some(SecretTier::TierB) => Some("secrets_tier_b_warning".to_owned()),
    _ => None,
};
let raw_hash = if include_raw_hashes && !ignored {
    Some(hash_bytes(&std::fs::read(&path).pipeline_io(&path)?))
} else {
    None
};
```

This is the violated invariant: a known file length and configured input
budget exist, but the scanner allocates and reads the complete file before
any budget decision is made. `std::fs::read()` returns an owned byte vector,
so the peak heap growth is proportional to the file length; hashing then adds
proportional CPU and I/O work. A sparse file makes the logical size cheap for
the contributor to place while still making the vulnerable read materialize
the full logical contents as observed by the filesystem.

The configured cap appears only after `build_scan_preview()` has returned and
`run_index_pipeline()` starts iterating over the preview candidates:

```rust
// crates/kcs-cli/src/main.rs:9047-9070
// R12-2: the documented `adapter.policy.max_input_bytes` input gate (07 §7.1.2 --
// "KCS 側の入力制御" is an MVP contract). Scope config wins over user config,
// default 100 MB. A file larger than the cap is never handed to the Markdownize
// adapter (below); it stays archived but unenriched, and the count is disclosed.
let max_input_bytes = effective_max_input_bytes(repo);
// R12-1: the documented `[markdownize.incremental]` overrides (were hardcoded).
let incremental_config = effective_incremental_config(repo)?;

for candidate in preview
    .candidates
    .iter()
    .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
{
    if candidate.size_bytes > max_input_bytes {
        result.skipped_oversized_files += 1;
        append_event_log(
            "KCS-I-INDEX-INPUT-OVERSIZED-001",
            "input file exceeds adapter.policy.max_input_bytes; skipped adapter processing",
            json!({
                "size_bytes": candidate.size_bytes,
                "max_input_bytes": max_input_bytes,
            }),
        )?;
        continue;
    }
```

By the time we reach this branch, the scan-time raw hash has already paid the
whole-file cost. The existing cap test confirms this late behavior rather
than disproving the issue:

```rust
// crates/kcs-cli/tests/step3_p0_contract.rs:4212-4231
// max_input_bytes is a real input gate: a file larger than the cap is skipped for
// adapter processing (never normalized) but the index still succeeds.
#[test]
fn r12_2_max_input_bytes_gates_oversized_input() {
    let dir = tempfile::tempdir().unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Cap at 50 bytes; write a markdown file well over that.
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[adapter.policy]\nmax_input_bytes = 50\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("big.md"),
        "# Big\n\n## Section\nthis body is definitely longer than fifty bytes in total.\n",
    )
    .unwrap();
    let index = json_success(&dir, &["index", "--approve"]);
    assert_eq!(index["skipped_oversized_files"], 1);
    assert_eq!(index["normalized_files"], 0);
}
```

That regression is useful because it proves the adapter skip, but it uses a
small file and does not assert that the scanner avoids pre-cap allocation.
No saved evidence showed a large-file or sparse-file regression that would
catch the raw-hash read itself.

## Exploitability Analysis

The strongest route is an ordinary availability attack against an
operator-selected scope. We start with a contributor who can add a readable,
included, regular direct-child file. The file must not be ignored, must not be
the internal `.kcs` state, must not be a symlink or directory at enumeration
time, and the operator must run normal indexing rather than `--preview`.

From there the attacker-controlled value is the file's logical size `n`. The
scanner records that length, but because no pre-read guard consumes it, the
next decisive operation is still the whole-file `std::fs::read()`. We can push
the primitive in two practical directions:

1. A physically large file consumes disk, read bandwidth, heap, and hash CPU
   in direct proportion to its size. This is noisy but deterministic.
2. A sparse file can advertise a much larger logical size while consuming
   little initial storage. Filesystem behavior varies, but KCS still asks
   `std::fs::read()` to produce a byte vector for the logical contents.

The store lock matters because the index command holds it end-to-end. While
the process is reading, hashing, swapping, or failing allocation, the selected
scope's index operation is unavailable. If the process aborts or is killed by
the OS, the operator can remove the offending file and retry, so this is not a
persistent compromise. It is nevertheless a concrete denial of indexing and a
host resource pressure primitive.

Several controls narrow the finding and keep the severity at Medium. Preview
mode sets `include_raw_hashes` to false and exits before the pipeline.
Ignored files, non-regular entries, `.kcs`, `.kcsignore`, XDG state inside the
scope, and default-excluded Tier-A secrets do not enter the vulnerable read.
The later `max_input_bytes` gate correctly prevents oversized adapter
normalization and network submission, so this does not become a confidentiality
or billing issue by itself. These controls are meaningful, but none of them
answers the specific allocation-order problem for an included regular file in
normal indexing.

I did not measure process termination thresholds because doing so would
require deliberately stressing the host. The source proof is sufficient for
the bug class: `metadata.len()` is available, `std::fs::read()` performs the
allocation, and the configured cap is downstream of that read. Runtime testing
would refine constants such as RSS growth and OS kill behavior, not the
existence of the pre-cap allocation.

## Proof of Concept

The PoC included with this report is intentionally defensive and local. It
does not run KCS, does not create a huge file, and does not use the network.
Instead, it verifies the vulnerable source ordering against the affected
revision when a checkout is supplied, then performs a bounded 1 MiB
`read_bytes()` demonstration to show the same class of whole-file allocation
on a safe synthetic file.

From the `poc` directory, run:

```sh
make check
```

To verify against a checkout of the affected revision, pass the checkout path:

```sh
python3 scan_hash_order_probe.py --repo <kcs-checkout> \
  --rev 0e19f3c6489da458e93a982a333c308d92d0a0ae
```

Representative output:

```text
[ok] normal index enables raw scan hashes before preview returns
[ok] scanner records metadata length before the raw-hash read
[ok] raw-hash branch performs a whole-file read before the adapter cap
[ok] downstream max_input_bytes gate is adapter-only and post-preview
[ok] bounded local read demo allocated 1048576 bytes for hashing
[safe] no KCS command executed; no network, credentials, or large files used
```

This is not an exhaustion exploit. It is a regression-friendly proof that the
available pre-read length and the later cap are ordered incorrectly. A full
resource test should be run only under an explicit memory limit or disposable
environment.

## Remediation

The invariant to restore is simple: KCS must make a bounded decision before
any whole-file allocation, and hashing should not require an owned buffer whose
size equals the candidate's logical length. There are two reasonable patch
shapes.

The smallest change is to enforce a scan-stage cap before the raw-hash read:

```rust
let size_bytes = entry.metadata().pipeline_io(&path)?.len();
let max_scan_bytes = request.max_scan_hash_bytes;

let raw_hash = if include_raw_hashes && !ignored {
    if size_bytes > max_scan_bytes {
        None
    } else {
        Some(hash_bytes(&std::fs::read(&path).pipeline_io(&path)?))
    }
} else {
    None
};
```

That protects memory, but it changes raw-hash availability for oversized
files. The stronger structural fix is to stream the hash and any local CAS
ingestion through a bounded reader:

```rust
let size_bytes = entry.metadata().pipeline_io(&path)?.len();
if size_bytes > max_scan_bytes {
    mark_oversized_for_adapter_skip(&relative, size_bytes);
    // Either omit raw_hash or compute it with an explicitly approved streaming path.
} else {
    let file = std::fs::File::open(&path).pipeline_io(&path)?;
    let raw_hash = Some(hash_reader(file).pipeline_io(&path)?);
}
```

If KCS wants to preserve archival behavior for large files, the streaming path
is the better long-term direction: it lets the scanner hash or ingest without
materializing the whole file. The same design should be applied to the later
accepted-file read at `crates/kcs-cli/src/main.rs:9077-9090` where practical,
so accepted inputs also avoid avoidable `Vec` growth.

Regression coverage should include:

- a normal non-preview index over a file larger than a tiny configured cap,
  asserting that the skip decision occurs before raw hashing allocates the
  full file;
- a sparse-file case under a process memory limit, proving the scanner does
  not allocate logical file size;
- a preview-mode negative control showing raw hashes remain disabled;
- ignored, symlink, directory, `.kcs`, `.kcsignore`, XDG state, and Tier-A
  secret exclusions to keep existing bypass controls intact;
- a streaming hash test that verifies hash equality for ordinary small files.

## Summary

This finding is a resource-consumption bug, not a remote compromise. The
validated path shows that ordinary non-preview indexing asks the scanner to
compute raw hashes, the scanner records file length but immediately performs a
whole-file read for included regular files, and the documented input-size cap
is only enforced after the preview has already been built. We demonstrated the
source order with a safe local probe and kept the operational impact bounded
to local availability.

Fixing the issue means moving the budget decision or the streaming primitive
to the first point where KCS already knows the file length. Variant review
should look for other `fs::read()` uses on attacker-supplied scope files,
especially where a metadata length or configured limit is already available
but not used before allocation.
