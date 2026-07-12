# Store-local consent records can be forged or replayed across adopted scopes

## Executive Summary

KCS stores persistent network and secret-release consent inside the same
folder-local `.kcs` tree that it supports copying and adopting as scope state.
At revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`, the consent readers do not
authenticate who created a record or bind it to the canonical root on the
current device. They only compare fields that a contributor can choose together
inside the supplied store. A lower-trust archive or shared-state contributor can
therefore preseed a syntactically valid `scope.json`, `approvals.jsonl`, and
`secrets-approved.jsonl`; a whole-store copy also preserves the self-consistent
identifiers that the readers accept.

Once a victim adopts that store and later invokes an online-capable indexing,
resume, retry, or search workflow, the forged network record can stand in for a
fresh operator opt-in. A forged `send_secrets` record can independently lift the
hold on secret-classified chunks. The eventual adapter call uses the victim's
configured provider and credentials, so this primitive does not itself select an
attacker endpoint. Adoption, a configured online adapter, a later operator
command, and the absence of offline mode or revocation are all required. Those
constraints make the final rating **Medium (P2)** despite the potential
confidentiality impact.

I reviewed the exact revision above, ran the included offline state-regression
PoC, and reran the focused foreign-scope negative-control test with temporary
XDG directories. Both completed successfully. I did not configure credentials,
contact a provider, or perform an end-to-end outbound send. No fixed revision or
release was available during this review, and I did not establish the first
version in which the behavior appeared.

## Background

KCS treats each folder's `.kcs` directory as the authoritative state for that
scope. Among other data, the directory carries a `scope.json` identity,
adapter-specific persistent network approvals, and a second audit stream for
explicit permission to send secret-classified content. The documented network
invariant is strong: file content must not go to an online API until the user has
explicitly opted in, with persistent permission scoped to a particular scope and
adapter.

That design has two legitimate requirements that become dangerous when they are
combined. First, `.kcs` is portable enough to be copied for backup or recovery.
Second, KCS consumes records inside `.kcs` as authorization, not merely as an
audit history. A data store can safely be portable; an authorization grant cannot
be portable across trust boundaries unless its provenance is authenticated or
the recipient explicitly reauthorizes it.

Repository opening illustrates the distinction. In
`crates/kcs-core/src/scope.rs`, `Repository::open()` canonicalizes the selected
working root, but then derives `.kcs` from that root and accepts any target that
resolves as a directory:

```rust
pub fn open(path: impl AsRef<Path>) -> Result<Self> {
    let root = path.as_ref().canonicalize().kcs_io(path.as_ref())?;
    let kcs_dir = root.join(".kcs");
    if !kcs_dir.is_dir() {
        return Err(KcsError::invalid_usage("not a kcs scope"));
    }

    let repo = Self {
        root,
        kcs_dir: kcs_dir.clone(),
        store: ObjectStore::new(kcs_dir),
    };
    repo.validate()?;
    // ...
    Ok(repo)
}
```

The decisive lines are 188-200. We carry `kcs_dir` from there into all later
consent reads. `validate_scope()` at lines 889-909 validates the JSON schema,
requires a nonempty ULID-shaped `scope_id`, and checks the format version. It
does not compare the optional `scope_path` with `repo.root()`, nor does it
authenticate the store's origin. The schema itself requires only `scope_id`.

Network and secret consent are separate. `approvals.jsonl` records a persistent
online opt-in for one adapter `tool_id`; `secrets-approved.jsonl` records the
additional `send_secrets` decision that releases secret-classified content. This
separation is sound in principle, but both records currently live in the same
attacker-copyable authority domain.

## Vulnerability Details

### The store supplies both sides of the identity comparison

When KCS legitimately creates a network approval, the writer in
`crates/kcs-cli/src/main.rs:10718-10779` includes useful provenance-looking
fields:

```rust
let base = json!({
    "scope_id": preview.scope_id,
    "root_path": repo.root(),
    "approved_at": now_utc_seconds(),
    "actor": std::env::var("USER").unwrap_or_else(|_| "unknown".to_owned()),
    "approval_method": approval_method,
    // ...
    "network_opt_in": network_opt_in,
    "execution_mode": "online_api",
});
```

Those fields could help explain how a grant was created, but they do not protect
it. The reader at `main.rs:6362-6378` ignores `root_path`, `actor`,
`approved_at`, `approval_method`, and any device identity:

```rust
fn approval_row_present_in_kcs_dir(kcs_dir: &Path, tool_id: Option<&str>) -> Result<bool> {
    let expected_scope_id = scope_id(kcs_dir)?;
    let path = kcs_dir.join("approvals.jsonl");
    let Ok(text) = fs::read_to_string(&path) else {
        return Ok(false);
    };
    Ok(text
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .any(|value| {
            value.get("scope_id").and_then(Value::as_str) == Some(expected_scope_id.as_str())
                && tool_id
                    .map(|tool_id| value.get("tool_id").and_then(Value::as_str) == Some(tool_id))
                    .unwrap_or(true)
                && value.get("execution_mode").and_then(Value::as_str) == Some("online_api")
                && value.get("network_opt_in").and_then(Value::as_bool) == Some(true)
        }))
}
```

The apparent scope check is self-referential. We read `expected_scope_id` from
the supplied `.kcs/scope.json` and compare it with a row from the supplied
`.kcs/approvals.jsonl`. A contributor who controls the whole store can choose the
same valid ULID in both files. The `tool_id`, execution mode, and boolean checks
restrict what a row authorizes, but the contributor can also set those fields.

### The accepted row bypasses fresh approval

The generic approval check delegates directly to that reader:

```rust
fn approval_exists(repo: &Repository) -> Result<bool> {
    approval_row_present_for_scope(repo, None)
}
```

At `main.rs:586-610`, `run_index()` calls `approval_exists()`. If it returns
true, the branch that would otherwise require `--preview`, `--approve`, or
`--yes` is skipped. The same underlying predicate reaches the online policy at
`main.rs:10422-10445`; absent `--offline` or revocation, a matching row is
sufficient for the configured markdown adapter. Embedding uses the adapter-
specific form through `embedding_online_allowed()` at lines 6393-6422.

We can now follow the accepted authorization into a concrete send path. During
embedding, KCS constructs `EmbeddingItem` values from local chunk text and
passes them to the active adapter in `main.rs:7727-7743`:

```rust
let items = to_send
    .iter()
    .map(|(chunk, _)| EmbeddingItem {
        id: chunk.chunk_id.clone(),
        text: Some(chunk.text.clone()),
        path: None,
        mime: None,
    })
    .collect::<Vec<_>>();
let vectors = run_embedding_adapter(execution, items, EmbeddingInputType::MarkdownChunk)?;
```

This is the security-relevant outcome of the network record: local document
text is placed into the adapter request without a fresh approval on the current
device or root.

### Secret-release consent is independently forgeable

KCS applies a second gate before secret-classified chunks become sendable. The
reader at `main.rs:10543-10555` is even narrower:

```rust
fn secrets_send_approved(repo: &Repository) -> bool {
    let Ok(expected_scope_id) = scope_id(repo.kcs_dir()) else {
        return false;
    };
    let Ok(text) = fs::read_to_string(repo.kcs_dir().join(SECRETS_APPROVAL_FILE)) else {
        return false;
    };
    text.lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .any(|value| {
            value.get("scope_id").and_then(Value::as_str) == Some(expected_scope_id.as_str())
                && value.get("approval_method").and_then(Value::as_str) == Some("send_secrets")
        })
}
```

Again, `scope_id` comes from the same supplied authority domain. The reader does
not validate `actor`, timestamp, canonical root, adapter, or device provenance.
At `main.rs:7317-7334`, `run_embedding_enrichment()` partitions secret chunks
into `held` and `sendable` according to this result. Once the forged row returns
true, those chunks can enter the same adapter path if network consent and the
other execution preconditions are also satisfied.

The violated invariant is therefore not merely that an audit field can be
edited. KCS derives active authorization from unsigned, portable content whose
identity fields are all controlled by the same lower-trust contributor.

## Exploitability Analysis

The strongest realistic route is a preseeded store supplied with an archive,
shared project folder, restore image, or similar lower-trust state. The
contributor creates a valid ULID, places it in `scope.json`, and adds matching
online-approval rows for likely KCS adapter identifiers. If secret-bearing
content is a goal, the contributor also adds a matching `send_secrets` row. The
victim later opens the folder with KCS and invokes an eligible online workflow.
KCS interprets the contributor's rows as the victim's prior consent and uses the
victim's configured adapter and credential.

A whole-store replay is a second route. Copying only an approval row into a
different existing scope fails because the IDs differ, but copying `scope.json`
and the approval rows together preserves the equality. This matters for backup
and restore workflows: portability is useful for data recovery, yet it should
not silently carry network or secret-release authority to a new canonical root
or device.

Several constraints keep exploitation from being automatic:

- The victim must adopt or open the supplied store and later invoke an online-
  capable command. Merely placing an archive on disk does not transmit data.
- A matching online adapter and usable provider credential must be configured.
- The forged network row remains scoped to the named `tool_id`; a row for one
  adapter does not authorize another.
- `--offline` and scope-local network revocation override stored consent.
- The destination remains the victim's configured provider. This finding does
  not prove that the store contributor controls or can observe that provider
  account.

Those controls are meaningful but do not authenticate the decision. In
particular, the foreign-row negative control demonstrates only that a mismatched
identifier is rejected. It does not protect a store in which the contributor
selects both identifiers. Similarly, changing the descriptive `actor` or
`root_path` field is neither necessary nor useful to the exploit because the
reader never consults them.

The secret-release primitive has the highest confidentiality consequence, but
it still composes with the separate network gate. A forged `send_secrets` row
alone does not cause a send. The contributor needs the network predicate to be
satisfied as well, and the later workflow must discover a classified chunk.
Conversely, a network row alone can expose ordinary document content but leaves
secret-classified chunks held. These compositional constraints, plus the lack of
attacker-selected destination in this candidate, support Medium severity rather
than a higher rating.

## Proof of Concept

The bundled `poc/consent_state_regression.py` is an offline, source-faithful
model of the two reader predicates. It creates three synthetic stores in an
automatically removed temporary directory:

1. a foreign row placed into a different scope;
2. a whole `.kcs` copy moved to a new root; and
3. a fully preseeded store whose scope identity and consent rows were chosen
   together.

It then compares those results with a fixed-state oracle whose grants live in a
protected device-local set keyed by canonical root, scope identity, adapter, and
operation. The script uses only the Python standard library. It does not invoke
KCS, load credentials, create sockets, or contact a service.

Run it from the report directory:

```sh
cd poc
python3 consent_state_regression.py
```

Expected output is:

```text
[+] foreign-row negative control: network=False secrets=False
[!] copied whole-store replay: network=True secrets=True
[!] preseeded same-store forgery: network=True secrets=True
[+] fixed provenance oracle: origin=True copied=False forged=False
[+] no KCS binary, adapter, service, socket, or credential was used
```

I ran that command with bytecode generation disabled and observed the output
above with exit status zero. I also reran the source tree's focused test
`r6_foreign_approval_rows_do_not_grant_online_embedding` under temporary
`XDG_DATA_HOME`, `XDG_CONFIG_HOME`, and `XDG_CACHE_HOME`; it passed with one test
run and 203 filtered out. That test is a useful negative control but deliberately
does not cover a self-consistent whole-store copy. I did not execute an actual
provider send, so this PoC proves the authorization-state flaw and the affected
predicates rather than external service behavior.

The PoC cleans up its temporary state automatically and does not alter the
working repository.

## Remediation

The invariant to restore is: **portable scope content must not be sufficient to
create network or secret-release authority on a device or canonical root that
did not grant it**. Keep `.kcs` approval rows as audit history if desired, but do
not treat them as authorization by themselves.

A robust design should store active grants in a device-protected location,
keyed at least by the canonical root, `scope_id`, adapter `tool_id`, operation
(`network` versus `send_secrets`), and an explicit grant version. The record
should be created only by the current approval flow. Moving or importing a scope
to a different canonical root should require fresh consent; a dedicated trusted-
move workflow may deliberately rebind ordinary network permission, but secret-
release permission should default to cleared.

The following Rust sketch shows the minimal shape of the reader change. It is a
design example rather than a patch tested against the current tree:

```rust
fn trusted_consent_present(
    repo: &Repository,
    tool_id: &str,
    operation: ConsentOperation,
) -> Result<bool> {
    let key = ConsentKey {
        canonical_root: repo.root().canonicalize().kcs_io(repo.root())?,
        scope_id: scope_id(repo.kcs_dir())?,
        tool_id: tool_id.to_owned(),
        operation,
    };
    device_consent_store()?.contains(&key)
}

fn approval_row_present(repo: &Repository, tool_id: &str) -> Result<bool> {
    trusted_consent_present(repo, tool_id, ConsentOperation::Network)
}

fn secrets_send_approved(repo: &Repository, tool_id: &str) -> Result<bool> {
    trusted_consent_present(repo, tool_id, ConsentOperation::SendSecrets)
}
```

If device-local storage cannot be introduced immediately, an intermediate
mitigation is to cryptographically authenticate consent records with a
device-held key and include the canonical root, scope ID, adapter, operation,
and version in the authenticated payload. A signature or MAC stored alongside
the portable row is useful only if the verification key is not itself supplied
by `.kcs`. Even with authentication, explicit import semantics remain valuable
because a legitimate signed grant may not be appropriate after a move.

Regression coverage should include all of the following:

- a row copied into a different scope remains rejected;
- a whole store copied to a different canonical root has no active grant;
- a self-consistent preseeded scope and row have no active grant;
- a grant created locally for the exact root, scope, adapter, and operation is
  accepted;
- network and `send_secrets` grants cannot substitute for one another;
- a grant for one adapter cannot authorize another;
- offline mode and revocation still override a valid local grant; and
- an explicit trusted-move workflow has a visible, auditable reauthorization
  step and defaults secret release to disabled.

As defense in depth, KCS should surface the grant's device and canonical-root
binding in status output and warn whenever copied scope state contains historical
approval rows that are not active locally. This preserves useful audit data
without silently converting it into permission.

## Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` accepts persistent network
and secret-release consent from unsigned records inside a portable `.kcs` store.
Because `scope.json` and the consent rows come from the same supplied state, the
scope-ID comparison establishes internal consistency, not provenance. We traced
that self-consistent state through prompt bypass, network policy, the secret hold,
and the embedding adapter call, then demonstrated the distinction between a
foreign-row negative control and whole-store replay with a harmless offline PoC.

The practical path requires adoption, a later online-capable command, a matching
adapter and credential, and no offline or revocation override, which supports the
final Medium/P2 rating. The durable fix is to separate portable audit data from
active authorization and bind grants to protected device-local state plus the
canonical root, scope, adapter, and operation. Future variant analysis should
review every other decision loaded from `.kcs` and ask whether it represents
portable data or non-portable authority.
