# Byte-Oriented `?` Globs Bypass Unicode Filenames

## Executive Summary

KCS evaluates `.kcsignore` and configured ignore globs on normalized Unicode
strings, but the final wildcard matcher converts both the pattern and pathname
to UTF-8 bytes. The `?` metacharacter therefore consumes one byte rather than
one Unicode scalar value. A rule such as `?.txt` excludes `a.txt`, but it does
not exclude one-character Unicode names such as `é.txt`, decomposed `é.txt`, or
`😀.txt`.

I reviewed vulnerable revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
directly, reproduced the matcher behavior with the offline PoC in this report,
and did not perform any live adapter or network transmission test. The exact
released version range is not established here; the validated basis is the
source revision above.

The practical impact is an exclusion-policy bypass. If an operator relies on a
one-character `?` rule as a scope boundary, a lower-trust contributor who can
choose filenames inside that scope can cause a Unicode-named file to be treated
as non-ignored. From there, KCS reads and prepares the bytes for local archive
and indexing, and recognized files can become eligible for already-approved
online OCR or embedding flows. Independent controls such as literal ignore
rules, `*` rules, secret-name classification, offline mode, adapter approval,
and operator invocation still matter, so I rate the final issue Medium/P2.

## Background

KCS builds a scan preview before indexing. The preview combines ignore rules
from scope configuration and `.kcsignore`, then walks direct children of the
selected scope. The threat model that matters here is not a remote unauthenticated
attacker. It is a local, lower-trust contributor in a shared folder, synced
workspace, unpacked archive, or generated content tree. That contributor controls
the pathname and file bytes, while the operator controls the KCS invocation,
archive, and any online adapter approval.

The `.kcsignore` loader accepts each non-comment line as a rule and preserves
the pattern text for later matching:

```rust
// crates/kcs-pipeline/src/scan.rs
pub fn load_kcsignore(scope_path: &Path) -> Result<Vec<IgnoreRule>> {
    let path = scope_path.join(".kcsignore");
    if !path.is_file() {
        return Ok(Vec::new());
    }
    let content = std::fs::read_to_string(&path).pipeline_io(&path)?;
    Ok(content
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                return None;
            }
            let (negated, pattern) = trimmed
                .strip_prefix('!')
                .map(|pattern| (true, pattern))
                .unwrap_or((false, trimmed));
            Some(IgnoreRule {
                pattern: pattern.to_owned(),
                negated,
            })
        })
        .collect())
}
```

The preview then applies those rules before deciding whether to hash and later
process a candidate. When we follow `relative` into `ignored_by_rules`, the
ignore decision becomes the gate that determines whether the candidate remains
active:

```rust
// crates/kcs-pipeline/src/scan.rs
let relative = path
    .strip_prefix(scope_path)
    .unwrap_or(&path)
    .to_string_lossy()
    .replace('\\', "/");
if relative == ".kcsignore" {
    continue;
}
let size_bytes = entry.metadata().pipeline_io(&path)?.len();
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
```

That means the `?` semantics are not cosmetic. If a file should have been
ignored but the matcher returns false, we carry it into the same candidate stream
as intentionally in-scope content.

## Vulnerability Details

The bug sits at the transition from Unicode-aware normalization to byte-oriented
matching. The surrounding code explicitly acknowledges Unicode canonical forms:
both `path` and `pattern` are projected to NFC, and optionally lowercased with
Unicode-aware `to_lowercase()`. Up to this point, we are still dealing with Rust
`String` values whose scalar boundaries are known:

```rust
// crates/kcs-pipeline/src/scan.rs
fn matches_ignore_pattern(path: &str, is_dir: bool, pattern: &str, case_insensitive: bool) -> bool {
    let mut path = path.nfc().collect::<String>();
    let mut pattern = pattern.nfc().collect::<String>();
    if case_insensitive {
        path = path.to_lowercase();
        pattern = pattern.to_lowercase();
    }
    let directory_only = pattern.ends_with('/');
    if directory_only && !is_dir {
        return false;
    }
    let rooted = pattern.starts_with('/');
    let pattern = pattern.trim_start_matches('/').trim_end_matches('/');
    let normalized_path = path.trim_start_matches('/').replace('\\', "/");
    if !rooted && !pattern.contains('/') {
        return wildcard_match(
            pattern,
            normalized_path
                .rsplit('/')
                .next()
                .unwrap_or(&normalized_path),
        );
    }
    wildcard_match(pattern, &normalized_path)
}

fn wildcard_match(pattern: &str, value: &str) -> bool {
    wildcard_match_bytes(pattern.as_bytes(), value.as_bytes())
}
```

The next function discards that scalar structure. The important branch is
`b'?'`: it checks that the value is non-empty and not a slash, then recurses with
`&value[1..]`. That slice advances by one byte:

```rust
// crates/kcs-pipeline/src/scan.rs
fn wildcard_match_bytes(pattern: &[u8], value: &[u8]) -> bool {
    if pattern.is_empty() {
        return value.is_empty();
    }
    if pattern.starts_with(b"**/") {
        return wildcard_match_bytes(&pattern[3..], value)
            || value
                .iter()
                .position(|byte| *byte == b'/')
                .map(|slash| wildcard_match_bytes(pattern, &value[slash + 1..]))
                .unwrap_or(false);
    }
    if pattern == b"**" {
        return true;
    }
    match pattern[0] {
        b'*' => {
            wildcard_match_bytes(&pattern[1..], value)
                || !value.is_empty()
                    && value[0] != b'/'
                    && wildcard_match_bytes(pattern, &value[1..])
        }
        b'?' => {
            !value.is_empty()
                && value[0] != b'/'
                && wildcard_match_bytes(&pattern[1..], &value[1..])
        }
        byte => {
            !value.is_empty()
                && byte == value[0]
                && wildcard_match_bytes(&pattern[1..], &value[1..])
        }
    }
}
```

Now we can carry a concrete filename through the matcher. The operator writes
`?.txt`, intending one filename character followed by `.txt`. For `a.txt`, the
bytes are:

```text
61 2e 74 78 74
```

The `?` consumes `61`, and the next pattern byte `2e` matches the next value
byte `2e`. The rule matches, so the ASCII control is ignored.

For precomposed `é.txt`, after NFC the path is still one Unicode scalar followed
by `.txt`, but its UTF-8 bytes are:

```text
c3 a9 2e 74 78 74
```

The `?` consumes only `c3`. The next pattern byte is `2e` for `.`, but the next
value byte is the continuation byte `a9`. That literal comparison fails, so the
rule does not match. Decomposed `é.txt` reaches the same bad state because NFC
collapses it to precomposed `é` before the byte matcher runs. Non-BMP scalars
such as `😀` fail for the same reason, with four bytes left behind after the
single-byte `?` step.

The bad decision is then consumed by indexing. The index pipeline filters only
non-ignored, non-directory candidates, reads their bytes, prepares units, and
writes prepared objects:

```rust
// crates/kcs-cli/src/main.rs
for candidate in preview
    .candidates
    .iter()
    .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
{
    if candidate.size_bytes > max_input_bytes {
        result.skipped_oversized_files += 1;
        continue;
    }
    let secrets_hold = !secrets_approved && classify_secret(&candidate.input_path).is_some();
    let path = repo.root().join(&candidate.input_path);
    let bytes = fs::read(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    let current_hash = hash_bytes(&bytes);
    if let Some(scan_hash) = &candidate.raw_hash {
        if scan_hash != &current_hash {
            result.failed_files += 1;
            continue;
        }
    }
    let raw_hash = current_hash;
    let prepare = prepare_units(PrepareStageRequest {
        raw_hash: raw_hash.clone(),
        media_type: candidate.media_type.clone(),
        input_path: path.display().to_string(),
        tool_profile_hash: prepare_profile_hash.clone(),
    })
    .map_err(pipeline_to_kcs)?;

    write_prepared_objects(
        repo,
        &prepare.prepared_units,
        &prepare.prepared_object_hashes,
        &bytes,
        &candidate.media_type,
    )?;
```

For recognized media with no local text extraction, the same accepted candidate
can be queued for online OCR when the existing network and secret gates allow it:

```rust
// crates/kcs-cli/src/main.rs
if candidate.media_type != "application/octet-stream" {
    enqueue_online_placeholder_task(
        repo,
        &task_store,
        candidate,
        &raw_hash,
        &scope_id,
        network_allowed,
        secrets_hold,
        args,
        &now,
        &mut result,
        &cost_ledger,
        &budget_caps,
        &month,
    )?;
}
```

Embedding has a similar eligibility shape after chunks exist: secret-looking
chunks are partitioned out unless separately approved, and the remaining
sendable chunks are enqueued when online execution is available. I did not need
to call an adapter to validate the vulnerable boundary; the source proof is that
the ignore bypass happens before the local archive and before the later
eligibility gates.

## Exploitability Analysis

The strongest realistic route is a scope-boundary bypass in a mixed-trust local
tree. We start with an operator who expects `.kcsignore` to keep a class of
single-character names out of KCS. This is plausible when the operator uses a
simple bounded rule for generated scratch files, incoming attachments, or a
single-character naming convention. A lower-trust contributor then supplies a
filename whose first visible character is a multibyte Unicode scalar.

The primitive is deterministic. There is no race, no allocator behavior, and no
filesystem timing dependency. Once the filename reaches `ignored_by_rules`, the
result depends only on the normalized pattern and normalized path. We can choose:

- `é.txt` for a one-scalar, two-byte precomposed name;
- `é.txt` for a decomposed spelling that becomes `é.txt` after NFC; or
- `😀.txt` for a non-BMP scalar that leaves three continuation bytes after the
  first-byte `?` step.

All three should satisfy a Unicode-scalar interpretation of `?.txt`. None is
matched by the byte-oriented implementation.

The most direct impact is local. The bypassed file can be hashed, archived,
prepared, normalized, and made visible in status or search surfaces as ordinary
in-scope content. That already crosses the operator's stated policy boundary:
the operator asked KCS not to ingest a class of files, and a lower-trust filename
choice silently defeats that request.

The network route is conditional but still security-relevant. If the operator
has enabled online processing, and if no independent secret or budget gate holds
the file, the wrongly accepted bytes can move into OCR or embedding work. This
does not create adapter credentials, bypass the `--online` approval model, or
force a live network call on its own. It changes which files are eligible under
an approval the operator already gave.

Several dead ends are useful for calibration:

- A literal rule such as `é.txt` still works, because every literal byte is
  compared against the same UTF-8 byte sequence.
- A broad `*` rule often hides the issue because `*` can consume an arbitrary
  number of non-slash bytes. That does not restore the intended bounded
  semantics of `?`.
- Tier A secret-name classification can independently exclude recognized secret
  filenames, and Tier B or lifted Tier A names can be held from online send.
  A neutral filename containing sensitive document content remains in scope for
  the bypass.
- The contributor commonly knows the file they supplied, so the most typical
  confidentiality harm is not "attacker learns their own file." The stronger
  harm is that the operator's archive and optional provider boundary process
  content the operator intended to exclude, especially in shared or generated
  trees where filename control and content sensitivity are separated.

Because the issue needs a `?` rule, a Unicode name, an operator scan, and
independent gates for remote impact, Medium/P2 is a more accurate final rating
than the raw high-impact sink might suggest.

## Proof of Concept

The bundled PoC is local and offline. It mirrors the vulnerable byte matcher and
compares it with a scalar-aware matcher for the same normalized inputs. It does
not use KCS credentials, external services, or real user files.

From the report directory:

```sh
cd poc
make test
```

Representative output:

```text
pattern: ?.txt
case=ascii        name='a.txt'    nfc_bytes=61 2e 74 78 74               vulnerable_ignored=yes fixed_ignored=yes
case=precomposed  name='é.txt'    nfc_bytes=c3 a9 2e 74 78 74            vulnerable_ignored=no  fixed_ignored=yes
case=decomposed   name='é.txt'   nfc_bytes=c3 a9 2e 74 78 74            vulnerable_ignored=no  fixed_ignored=yes
case=emoji        name='😀.txt'    nfc_bytes=f0 9f 98 80 2e 74 78 74      vulnerable_ignored=no  fixed_ignored=yes
[+] vulnerable matcher reproduces the Unicode '?' bypass
[+] scalar matcher excludes the same one-character Unicode filenames
```

The important row is `precomposed`: the filename is one Unicode scalar before
`.txt`, but the vulnerable matcher leaves a continuation byte for the following
literal `.` comparison. The `decomposed` row shows that the existing NFC step
does not save the matcher; it normalizes the string and then byte matching
breaks the scalar boundary anyway.

## Remediation

The invariant to restore is simple: after KCS normalizes the comparison
projection as Unicode text, a `?` wildcard must consume exactly one non-slash
Unicode scalar value, not one UTF-8 byte. The implementation should keep the
matcher in a character representation for `?` and literal comparisons, while
preserving the intended path-separator behavior for `/`, `*`, and `**`.

One minimal direction is to convert to `Vec<char>` at the matcher boundary:

```rust
fn wildcard_match(pattern: &str, value: &str) -> bool {
    let pattern = pattern.chars().collect::<Vec<_>>();
    let value = value.chars().collect::<Vec<_>>();
    wildcard_match_chars(&pattern, &value)
}

fn wildcard_match_chars(pattern: &[char], value: &[char]) -> bool {
    if pattern.is_empty() {
        return value.is_empty();
    }
    if pattern.starts_with(&['*', '*', '/']) {
        return wildcard_match_chars(&pattern[3..], value)
            || value
                .iter()
                .position(|ch| *ch == '/')
                .map(|slash| wildcard_match_chars(pattern, &value[slash + 1..]))
                .unwrap_or(false);
    }
    if pattern == ['*', '*'] {
        return true;
    }
    match pattern[0] {
        '*' => {
            wildcard_match_chars(&pattern[1..], value)
                || !value.is_empty()
                    && value[0] != '/'
                    && wildcard_match_chars(pattern, &value[1..])
        }
        '?' => {
            !value.is_empty()
                && value[0] != '/'
                && wildcard_match_chars(&pattern[1..], &value[1..])
        }
        ch => {
            !value.is_empty()
                && ch == value[0]
                && wildcard_match_chars(&pattern[1..], &value[1..])
        }
    }
}
```

That patch keeps the current scalar semantics simple. If KCS wants
user-perceived grapheme clusters instead, it should document that stronger
contract and use a grapheme-aware segmentation library consistently in both
pattern and value. Either way, the project should avoid returning to raw UTF-8
byte slices after Unicode normalization.

Regression tests should cover:

- `?.txt` excludes `a.txt`, `é.txt`, decomposed `é.txt`, and `😀.txt`;
- `?.txt` does not match `ab.txt`;
- `?.txt` does not cross `/`;
- case-insensitive matching still works after NFC;
- literal Unicode rules still match both NFC and NFD spellings;
- `*` and `**/` behavior remains compatible with existing tests.

It is also worth adding an integration test at the scan-preview level, not only
at the helper level. The vulnerable behavior matters because `ignored=false`
flows into archive and online eligibility; a regression test should assert that
a Unicode direct child excluded by `?.txt` is absent from the active ingestion
set.

## Summary

KCS starts with a Unicode-aware comparison pipeline, but then implements glob
matching over UTF-8 bytes. That single representation change makes `?` consume a
byte rather than the one filename character operators reasonably expect. We
demonstrated that `?.txt` excludes an ASCII control while allowing precomposed,
decomposed, and non-BMP one-character Unicode filenames through the same policy.

The result is a deterministic ignore-policy bypass before local archive and
optional online-processing eligibility. The fix is to keep wildcard matching on
Unicode scalar values, or to explicitly document and implement a grapheme-based
contract, and to lock the invariant with helper-level and scan-preview-level
regression tests. Future variant analysis should review any other path or
policy code that normalizes as Unicode and then drops back to byte-wise wildcard
or length semantics.
