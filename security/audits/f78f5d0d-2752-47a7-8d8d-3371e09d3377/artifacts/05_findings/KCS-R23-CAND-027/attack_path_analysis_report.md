# Attack-path analysis: Scan-time replacement can authorize an outside-scope file under a benign name

- Candidate: `KCS-R23-CAND-027`
- Ledger row: `KCS-R23-CAND-027`
- Instance key: `KCS-R23-CAND-027`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.91) in the code interleaving; medium in practical race reliability**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoint | `crates/kcs-cli/src/main.rs` | `558-580` | Non-preview index asks the scanner to compute raw hashes for selected-root candidates. |
| root_control | `crates/kcs-pipeline/src/scan.rs` | `97-149` | The scanner checks file type and classifies a benign name before a later following read computes the accepted raw hash. |
| hash_acceptance | `crates/kcs-cli/src/main.rs` | `9072-9118` | Secret policy uses the benign name; a reread equal to the already-substituted scan hash is accepted and only a mutable path is passed onward. |
| prepare_reopen | `crates/kcs-pipeline/src/prepare.rs` | `72-103` | Preparation independently reopens input_path rather than consuming the previously verified buffer. |
| online_sink | `crates/kcs-adapter/src/mistral_ocr.rs` | `112-138` | The OCR client reopens the path, base64-encodes those bytes, and sends them to the configured endpoint. |
| secret_control | `crates/kcs-cli/src/main.rs` | `7317-7329` | Embedding secret holds classify stored benign raw_path rather than the physical outside target. |

## Scope and actor

### Context

This is a local TOCTOU confused-deputy path across the selected-scope boundary. The actor is an explicitly in-scope lower-trust content contributor, not a same-user principal with unrestricted access to all private KCS state.

### In scope

yes; mutable direct-child paths, stable-byte use, scope containment, and local contributors are explicit I1/I2/I3 surfaces

### Exposure and identity

not public; local shared-filesystem race reached through operator indexing, with optional approved outbound OCR as the final sink

the attacker has only directory-entry replacement authority; KCS follows the path using the victim OS identity and victim read permissions

### Boundary crossed

yes; a lower-trust scope writer can cause victim-readable out-of-scope bytes to be adopted under an in-scope benign identity and potentially cross the adapter boundary

### Authorization scope

internal-only; lower-trust writer of an operator-selected local scope, with operator-approved adapter controls for network egress

## Preconditions and attacker control

### Assumptions

- The attacker has concurrent rename authority in a selected shared or supplied root but lacks direct read authority to the outside target.
- The attacker knows a victim-readable target path and wins the check/read replacement window.
- The victim invokes index; OCR egress additionally requires eligible media, adapter configuration, network approval, budget, and task execution.

### Preconditions

plausible but constrained: shared-root rename rights, a known readable outside target, a successful timing race, and victim indexing; maximum network impact needs additional ordinary online controls

### Attacker control

plausible; the attacker controls the directory-entry replacement and symlink target but not the outside file's bytes or victim permissions

### Vector

none

## Attack path

- A lower-trust writer places a benignly named regular direct child in a shared or supplied scope the victim will index.
- After KCS observes the regular-file type and classifies the benign name, the writer atomically replaces the entry with a symlink to a known victim-readable file outside the selected scope.
- The scanner follows the replacement for its raw hash; later hash equality accepts the same outside target while secret and media policy remain bound to the benign name.
- Preparation and normalization reopen the path, and an eligible OCR workflow can ultimately read and send the outside file under the victim identity.

## Impact and reach

- Category: filesystem TOCTOU / symlink substitution and scope escape (CWE-367, CWE-59)
- Impact: **high**
- Likelihood: **medium**

### Impact surface

scope confidentiality, raw archive and normalized content identity, and optional outbound OCR data

### Target reach

one victim-readable outside file per successful replacement and the selected scope's derived/archive state

### Secret references

- The outside target may contain victim-readable secrets, but no specific secret file was demonstrated.
- A configured OCR credential is attached only if the separately authorized online path executes.

## Controls and counterevidence

### Existing controls

- initial file-type and stable-symlink filtering
- later content-hash comparison
- input size and media eligibility
- network approval, credential, budget, and task controls

### Mitigations

- A symlink already present at the initial type check is skipped.
- A later reread whose bytes differ from the scan hash is rejected.
- Size/media controls, online opt-in, configured adapter, budget, and task eligibility constrain OCR egress.
- KCS has no listener and the operator must index the affected scope.

### Counterevidence

- The race was not reproduced and practical reliability is unmeasured.
- Stable symlinks are skipped and changed post-scan bytes fail the later hash comparison.
- OCR egress requires multiple additional operator-controlled eligibility conditions.
- Candidate 028 separately covers substitution after the final send-time hash; this decision relies only on the earlier scan-time mismatch.

### Blind spots or proof gap

- No deterministic race harness or loopback send capture was retained.
- Exploit reliability, attacker knowledge of a valuable target path, and accessibility of locally archived output remain deployment-dependent.

## Final decision

A shared-scope writer is a realistic lower-trust actor and needs no administrator or unrestricted private-state access, so hard suppression does not apply. The potential outside-scope disclosure is high impact, while the unmeasured race and required victim workflow constrain likelihood to medium; the matrix yields medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
