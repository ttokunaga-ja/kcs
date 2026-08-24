# Manual full and cold Rust gates

This is the single entry point for high-cost or external Kio validation that
does not belong in every push/pull-request run. The commands below are explicit
Rust entry points, not ignored tests or compatibility wrappers. They do not
authorize a scheduled workflow, a paid request, a GPU allocation, fixture
discovery, deployment, or publication.

The ordinary five-job responsibility and timeouts remain in
[the CI workflow](../.github/workflows/ci.yml):

| Job | Signal | Timeout |
| --- | --- | ---: |
| `rust` | format, clippy, complete workspace/all-target tests | 35 min |
| `persona-w0-integration` | create-only Tiny persona W0 lifecycle and leases | 15 min |
| `synthetic-history-eval` | release/all-features synthetic, scale, replay, cross-scope, rerank, M3-1/2/3 | 10 min |
| `macos-security-r23` | native macOS workspace/all-target behavior | 35 min |
| `windows-security-r23` | native Windows workspace/all-target behavior | 90 min |

Do not shorten these bounds or merge jobs until several matching successful
GitHub runs exist. Do not generate measurement samples with empty commits,
reruns, dispatches, or repeated pushes.

## 1. Explicit Full persona contract

The Full-only signal is the checked-in Rust example. It constructs the Full
source projection, suite schedule, and render artifact once, then asserts the
pinned plan/render/schedule digests, 195,000 sources, 2,400,000 planned chunks,
and canonical byte limits.

```sh
cargo +1.98.0 run --release --locked --offline \
  -p kio-eval --example persona_full_contract
```

Any panic, nonzero exit, digest/count mismatch, or byte-limit failure rejects
the run. This command is compiled by `--all-targets`; it is intentionally not
hidden behind `#[ignore]` and is not automatically executed by push/PR CI.

## 2. Complete cold build and environment variance

Use fresh target directories rather than deleting a shared `target/`. The
first directory proves a complete offline cold workspace test and release
all-features build. Both directories independently compile and execute the
Full persona command. Separate processes receive independent Rust runtime hash
seeds; Kio has no `PYTHONHASHSEED` compatibility switch.

```sh
KIO_COLD_A=$(mktemp -d "${TMPDIR:-/tmp}/kio-cold-a.XXXXXX")
KIO_COLD_B=$(mktemp -d "${TMPDIR:-/tmp}/kio-cold-b.XXXXXX")
mkdir -p "$KIO_COLD_A/tmp" "$KIO_COLD_B/tmp"

CARGO_TARGET_DIR="$KIO_COLD_A/target" TMPDIR="$KIO_COLD_A/tmp" \
  LC_ALL=C LANG=C TZ=UTC \
  cargo +1.98.0 test --workspace --all-targets --locked --offline
CARGO_TARGET_DIR="$KIO_COLD_A/target" TMPDIR="$KIO_COLD_A/tmp" \
  LC_ALL=C LANG=C TZ=UTC \
  cargo +1.98.0 build --release --all-features --locked --offline
CARGO_TARGET_DIR="$KIO_COLD_A/target" TMPDIR="$KIO_COLD_A/tmp" \
  LC_ALL=C LANG=C TZ=UTC \
  cargo +1.98.0 run --release --locked --offline \
  -p kio-eval --example persona_full_contract > "$KIO_COLD_A/persona.json"

CARGO_TARGET_DIR="$KIO_COLD_B/target" TMPDIR="$KIO_COLD_B/tmp" \
  LC_ALL=C LANG=C TZ=Asia/Tokyo \
  cargo +1.98.0 run --release --locked --offline \
  -p kio-eval --example persona_full_contract > "$KIO_COLD_B/persona.json"

cmp "$KIO_COLD_A/persona.json" "$KIO_COLD_B/persona.json"
jq -e '.sources == 195000 and .chunks == 2400000' \
  "$KIO_COLD_A/persona.json" "$KIO_COLD_B/persona.json"
```

The gate fails on any Cargo/test/build failure, different summary bytes, or a
failed pinned count/digest assertion. `--offline` makes a missing local Cargo
cache an explicit environment blocker; it must not silently enable network.
The fresh directories are retained as evidence unless the operator separately
chooses to remove those exact paths.

## 3. Full scale acceptance

The Full scale fixture is 20 scopes, 4,000 files, and 120,000 expected current
chunks. Only Full with exactly five warmups and 100 samples is formal-eligible.
The first command builds the shared release binaries used by this section and
sections 4-5. Run that command first when starting directly at U7 or OCR.

```sh
KIO_FULL_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/kio-scale-full.XXXXXX")

cargo +1.98.0 build --release --all-features --locked --offline \
  -p kio-cli -p kio-eval --bins
target/release/kio-eval scale generate \
  --out "$KIO_FULL_ROOT/corpus" --profile full
target/release/kio-eval scale prepare \
  --corpus "$KIO_FULL_ROOT/corpus" --bin target/release/kio
target/release/kio-eval scale attest \
  --corpus "$KIO_FULL_ROOT/corpus" \
  --out "$KIO_FULL_ROOT/attestation.json"
target/release/kio-eval scale benchmark \
  --corpus "$KIO_FULL_ROOT/corpus" --bin target/release/kio \
  --warmups 5 --samples 100 \
  --out "$KIO_FULL_ROOT/benchmark.json"
jq -e '
  .measurement_class == "full_100k_acceptance" and
  .acceptance_eligible == true and
  .passed_p95_thresholds == true and
  .current_chunks >= 100001 and
  .warmups == 5 and .samples == 100
' "$KIO_FULL_ROOT/benchmark.json"
```

The Rust command publishes its create-only report even when an eligible run
misses a threshold, then exits nonzero. M3-1 requires both measured p95 signals
below 5 seconds; M3-2 and M3-3 each require both below 7 seconds. Tiny remains a
contract smoke and cannot satisfy this gate. See [the evaluator contract](../eval/README.md).

## 4. U7 GPU/model gate

This lane requires an explicitly started serving runtime, a reviewed local
reference-model directory, a Python environment containing the reference ML
runtime, and GPU capacity. Rust owns HTTP, comparison, verdict, and create-only
reporting; Python owns only local reference inference.

```sh
target/release/kio-eval u7 \
  --base-url http://127.0.0.1:8000 \
  --model Qwen/Qwen3-VL-Embedding-2B \
  --reference-python /absolute/path/to/reference-venv/bin/python3 \
  --reference-adapter /absolute/path/to/kio/eval/u7/reference_adapter.py \
  --reference-model /absolute/path/to/pinned-local-model \
  --text "same-space text control" \
  --image /absolute/path/to/control-image.png \
  --out /absolute/new/u7-report.json
jq -e '.verdict.adoptable == true and .verdict.reason == "both-agree"' \
  /absolute/new/u7-report.json
```

`image-diverged`, `harness-suspect`, `image-not-measured`, malformed vectors,
or a nonzero command rejects/blocks adoption. This command must not download a
model implicitly. Full operating details remain in [the U7 manual](../eval/u7/README.md).

## 5. OCR fixture and paid provider gates

Fixture rendering is the sole Python-native OCR boundary and receives no
credentials. Inputs and outputs are explicit absolute paths and create-only.

```sh
target/release/kio-eval ocr render \
  --python /absolute/path/to/renderer-venv/bin/python3 \
  --adapter /absolute/path/to/kio/experiments/ocr-verification/fixtures/render_native.py \
  --request-id fixture-001 \
  --image /absolute/path/to/page-001.png \
  --out /absolute/new/fixture.pdf
```

The paid provider lane is a separate explicit operation. It requires network,
a valid `MISTRAL_API_KEY`, and cost approval immediately before execution.
Normal local gates and CI must not run it.

```sh
MISTRAL_API_KEY=... target/release/kio-eval ocr provider \
  --document /absolute/path/to/fixture.pdf \
  --model mistral-ocr-4-1 \
  --request-id paid-001 \
  --out /absolute/new/ocr-response.json
target/release/kio-eval ocr evaluate \
  --ground-truth /absolute/path/to/ground-truth.json \
  --response /absolute/new/ocr-response.json \
  --out /absolute/new/ocr-report.json
jq -e '.verdict == "passed"' /absolute/new/ocr-report.json
```

The provider is one fixed direct-HTTP POST with no retry, redirect, or proxy
inheritance. Timeout, status/header/schema errors, document replacement,
create-only collision, or a rejected evaluation is a failure. See
[the OCR boundary manual](../experiments/ocr-verification/README.md).

## Deliberate exclusions

- No nightly/weekly Actions schedule is enabled by this runbook.
- No paid API, GPU/model runtime, or external fixture is implied by a normal
  local or push/PR gate.
- No physical prune, non-tree CAS reclamation, CoW GC, M9, deployment, or
  publication command is included.
- Operational snapshot, batch evidence, retarget, dry-run GC, purge, fsck, and
  recovery commands remain in [the operations manual](../docs/10-operations.md);
  this file does not create a second entry point for them.
