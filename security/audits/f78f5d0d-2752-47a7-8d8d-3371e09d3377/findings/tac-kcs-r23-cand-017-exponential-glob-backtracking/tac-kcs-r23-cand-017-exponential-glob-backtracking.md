# Recursive .kcsignore star matching has exponential backtracking

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
contains an algorithmic complexity denial of service in the custom ignore
glob matcher used while building scan previews. A lower-trust contributor to a
local or shared scope can add a crafted `.kcsignore` rule and a matching
candidate filename. When the operator later runs a normal `kcs snapshot`,
`kcs index`, or `kcs index --preview` command, KCS evaluates the ignore rule
synchronously and can spend exponential CPU time before useful work completes.

I reviewed revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` directly,
checked the supplied bounded validation data, and built and ran the included
offline PoC. I did not run larger cases to exhaustion because the validated
pattern family grows exponentially and the safe reproduction already proves the
state explosion. No CVE, advisory, fix commit, or exact affected release range
was supplied, so the affected-version statement here is limited to the reviewed
revision.

The impact is scope-local availability loss rather than code execution or
cross-scope compromise. That still crosses a meaningful trust boundary: a
shared repository or archive contributor can make an operator's KCS scan
operation hang or burn CPU until the crafted rule is removed outside the normal
scan flow. The issue is best rated Medium.

## Background

KCS builds a scan preview before snapshotting or indexing a scope. The preview
loads ignore rules from both configuration and `.kcsignore`, then walks the
scope's direct child files and asks whether each candidate should be ignored.
The important security boundary is ordinary local scope adoption: the operator
runs KCS, but a different contributor may control files and metadata in the
scope being opened or indexed.

The preview entry point in `crates/kcs-pipeline/src/scan.rs` loads the
workspace-controlled ignore rules before candidate enumeration:

```rust
pub fn build_scan_preview(request: ScanPreviewRequest) -> Result<ScanPreview> {
    let scope_path = PathBuf::from(&request.scope_path);
    let case_insensitive = probe_case_insensitive(&scope_path);
    let mut ignore_rules = load_config_ignore(&scope_path)?;
    ignore_rules.extend(load_kcsignore(&scope_path)?);
    let mut candidates = Vec::new();
    collect_direct_candidates(
        &scope_path,
        &ignore_rules,
        request.include_raw_hashes,
        case_insensitive,
        &mut candidates,
    )?;
```

The CLI reaches this path in common commands. In `crates/kcs-cli/src/main.rs`,
`snapshot` builds the preview before creating the filtered snapshot:

```rust
let preview = build_scan_preview(ScanPreviewRequest {
    scope_path: repo.root().display().to_string(),
    include_raw_hashes: false,
    require_network_approval: false,
})
.map_err(pipeline_to_kcs)?;
```

`index` does the same before the preview response and before approval handling:

```rust
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

We therefore do not need a daemon, a network listener, private store access, or
online approval to reach the matcher. If the operator processes a supplied
scope, the preview path is already on the synchronous command path.

## Vulnerability Details

The attacker-controlled input starts in `.kcsignore`. `load_kcsignore()` trims
each non-empty, non-comment line and stores it as an `IgnoreRule`. There is no
line length limit, star-count limit, parse complexity check, or per-rule work
budget:

```rust
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

From there, every direct candidate is evaluated against the loaded rules. This
means one crafted direct-child filename is enough to drive the matcher:

```rust
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

`ignored_by_rules()` applies every rule and calls the custom glob matcher for
each one:

```rust
pub fn ignored_by_rules(
    path: &str,
    is_dir: bool,
    rules: &[IgnoreRule],
    case_insensitive: bool,
) -> bool {
    let mut ignored = false;
    for rule in rules {
        if matches_ignore_pattern(path, is_dir, &rule.pattern, case_insensitive) {
            ignored = !rule.negated;
        }
    }
    ignored
}
```

The normalization wrapper in `matches_ignore_pattern()` is not itself the bug;
it just preserves the attacker's pattern shape and selects whether to match the
full normalized path or the last path component:

```rust
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
```

The vulnerable transition is in `wildcard_match_bytes()`. When the pattern byte
is `*`, the matcher first tries to skip the star and then, if the value still
has a non-slash byte, tries to consume one byte of value while keeping the same
pattern. Those two recursive branches repeatedly revisit the same pattern/value
suffixes, but the function has no memo table and no work limit:

```rust
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

The adversarial family is compact: use the pattern `(*a)^n b`, written as
`*a*a*...*ab`, against a candidate filename `a^n`. We force a failing match by
ending the pattern with `b`. While failure is inevitable, the matcher must
explore many ways to assign the `a` bytes among the preceding stars before it
can prove that no trailing `b` exists. The validated recurrence for this exact
family is:

```text
C(n) = 2^(n+2) - 3
```

The bounded validation data measured 1,021 recursive calls at `n=8` and
1,048,573 calls at `n=18`; the included PoC reproduces those call counts. This
is not a large-input issue. At `n=18`, the pattern is only 37 bytes and the
filename is only 18 bytes. A common filesystem filename limit is already far
larger than the values needed to make the command unusable.

## Exploitability Analysis

The strongest practical route is a scope-level CPU wedge. We create a scope
with a crafted `.kcsignore` line and a direct child file whose name is the
failing value. When the operator runs `kcs index --preview`, `kcs index`, or
`kcs snapshot`, KCS reaches `build_scan_preview()`, loads the rule, evaluates
the candidate, and enters the recursive star branch before indexing or
snapshotting can make useful progress.

The attacker controls both values that matter:

- the ignore pattern through `.kcsignore`;
- the direct-child candidate name through a normal file in the supplied scope.

The primitive is deterministic excessive work in the victim CLI process. The
operator does not need to approve network use, and the candidate file does not
need meaningful contents. The crafted rule also persists in the local scope
until the operator edits or removes it outside the failing KCS command.

There are useful multipliers, but the single-rule case is already enough. Each
additional crafted rule multiplies candidate evaluation work because
`ignored_by_rules()` keeps iterating over all rules. More direct child files
can multiply the trigger as well. We do not need those multipliers for a clean
PoC because the `(*a)^n b` family gives exponential growth on one rule and one
filename.

The `**/` branch is less attractive in this specific scanner because
`collect_direct_candidates()` only scans direct child files. That limits how
many slash-separated path suffixes the attacker can place in the value for
preview matching. We should still fix `**/` under the same invariant because it
also recurses without memoization, but the shortest demonstrated exploit path
uses plain `*` and avoids directory-depth assumptions.

The issue is bounded to availability. I did not find a path from this primitive
to arbitrary file read, remote code execution, or privilege escalation. The
operator can recover by editing or deleting `.kcsignore` and rerunning KCS.
Those constraints keep severity at Medium, but they do not remove the trust
boundary: a lower-trust scope contributor can block ordinary operator commands
with tiny, valid metadata.

## Proof of Concept

The `poc/` directory contains a self-contained Rust probe that copies the small
recursive matcher shape and instruments call counts. It does not depend on the
target source tree, does not access a real KCS scope, and does not contact any
service. By default it stops at `n=18` and checks the exact recurrence, so it
is safe to run on a local workstation.

From this report directory:

```sh
cd poc
make
./kcs-glob-backtracking-probe
```

Representative output from the validated run:

```text
rustc -O probe.rs -o kcs-glob-backtracking-probe
[+] bounded offline probe for KCS recursive star matching
[+] pattern family: (*a)^n b against a^n
   n  pattern_bytes    value_bytes          calls    matched   elapsed_us
   8             17              8           1021      false            3
  10             21             10           4093      false           12
  12             25             12          16381      false           49
  14             29             14          65533      false          200
  16             33             16         262141      false          810
  18             37             18        1048573      false         3790
[+] linear control a*b vs aaaaaaaaab: matched=true, calls=20, elapsed_us=0
[+] recurrence validated through n=18; larger cases intentionally not executed
```

The elapsed times are host-dependent, but the call counts are the important
part of the demonstration. We see the failing cases double repeatedly while
the successful linear control completes with only 20 calls. Do not raise the
default bound on a shared machine; larger values intentionally exercise the
resource-exhaustion condition.

## Remediation

The invariant to restore is: ignore matching must be bounded by the number of
distinct `(pattern_index, value_index)` states, not by the number of recursive
paths through those states. KCS can satisfy that invariant by replacing the
hand-written backtracking matcher with a vetted linear or near-linear glob
implementation, or by memoizing the existing grammar and enforcing a clear work
budget.

A minimal local repair is to memoize `wildcard_match_bytes()` and fail closed
or surface a scan error when a rule exceeds a configured state budget. The
exact error policy should be chosen by product behavior, but the matcher should
not silently do unbounded work:

```rust
const MAX_GLOB_STATES: usize = 100_000;

fn wildcard_match_bytes(pattern: &[u8], value: &[u8]) -> bool {
    fn go(
        pattern: &[u8],
        value: &[u8],
        pi: usize,
        vi: usize,
        memo: &mut [Vec<Option<bool>>],
        states: &mut usize,
    ) -> bool {
        if let Some(result) = memo[pi][vi] {
            return result;
        }
        *states += 1;
        if *states > MAX_GLOB_STATES {
            return false;
        }

        let rest = &pattern[pi..];
        let result = if rest.is_empty() {
            vi == value.len()
        } else if rest.starts_with(b"**/") {
            go(pattern, value, pi + 3, vi, memo, states)
                || value[vi..]
                    .iter()
                    .position(|byte| *byte == b'/')
                    .map(|slash| go(pattern, value, pi, vi + slash + 1, memo, states))
                    .unwrap_or(false)
        } else if rest == b"**" {
            true
        } else {
            match rest[0] {
                b'*' => {
                    go(pattern, value, pi + 1, vi, memo, states)
                        || vi < value.len()
                            && value[vi] != b'/'
                            && go(pattern, value, pi, vi + 1, memo, states)
                }
                b'?' => {
                    vi < value.len()
                        && value[vi] != b'/'
                        && go(pattern, value, pi + 1, vi + 1, memo, states)
                }
                byte => {
                    vi < value.len()
                        && byte == value[vi]
                        && go(pattern, value, pi + 1, vi + 1, memo, states)
                }
            }
        };

        memo[pi][vi] = Some(result);
        result
    }

    let mut memo = vec![vec![None; value.len() + 1]; pattern.len() + 1];
    let mut states = 0;
    go(pattern, value, 0, 0, &mut memo, &mut states)
}
```

In production, I would prefer returning a structured error instead of treating
a budget hit as a non-match, because a non-match can surprise users who expect
their ignore rules to apply. A clean implementation should also collapse
adjacent `*` tokens before matching, cap `.kcsignore` line length and rule
count, and report the offending rule with enough context for the operator to
delete or rewrite it.

Regression tests should include:

- `(*a)^n b` against `a^n` for a bounded `n` and assert the matcher completes
  within a small state budget;
- the same adversarial rule through `ignored_by_rules()` to exercise the real
  wrapper;
- a `build_scan_preview()` fixture containing a crafted `.kcsignore` and direct
  child filename;
- normal successful globs, negated rules, rooted rules, `?`, `**`, and
  directory-only rules to preserve existing semantics.

## Summary

The vulnerability is present because KCS accepts scope-controlled ignore
patterns and evaluates them with a recursive glob matcher that branches on
`*` without remembering visited states. We can carry a short `.kcsignore`
pattern and a short direct-child filename from a supplied scope into
`wildcard_match_bytes()` through normal snapshot and index preview paths. Once
there, the failing `(*a)^n b` family forces `2^(n+2)-3` recursive calls before
the command can continue.

The demonstrated impact is deterministic local denial of service for the
selected scope. The most useful follow-up research is variant analysis around
other hand-written matchers and preview-time parsers that process
scope-controlled metadata before approval or before expensive-work limits are
active. For this specific bug, the durable fix is straightforward: use a
bounded, memoized, or vetted glob matcher and test the real preview path with
adversarial patterns.
