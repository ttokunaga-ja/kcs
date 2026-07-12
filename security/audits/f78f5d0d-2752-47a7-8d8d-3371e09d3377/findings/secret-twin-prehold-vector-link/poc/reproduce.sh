#!/usr/bin/env bash
set -euo pipefail

# This regression probe uses only synthetic files, an in-process deterministic
# embedding seam, and disposable HOME/XDG/scope directories. It never contacts
# a network service and removes the temporary tree on exit.

if [[ -n "${KCS_BIN:-}" ]]; then
    KCS_CMD=$(command -v -- "$KCS_BIN" 2>/dev/null || true)
else
    KCS_CMD=$(command -v -- kcs 2>/dev/null || true)
fi

if [[ -z "$KCS_CMD" ]]; then
    echo "error: set KCS_BIN to a kcs binary built from the revision under test" >&2
    exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "error: jq is required to inspect the temporary JSON artifacts" >&2
    exit 2
fi

ROOT=$(mktemp -d "${TMPDIR:-/tmp}/kcs-secret-twin-regression.XXXXXX")
trap 'rm -rf "$ROOT"' EXIT

SCOPE="$ROOT/scope"
HOME_DIR="$ROOT/home"
XDG_CONFIG="$ROOT/xdg/config"
XDG_DATA="$ROOT/xdg/data"
XDG_CACHE="$ROOT/xdg/cache"
mkdir -p "$SCOPE" "$HOME_DIR" "$XDG_CONFIG" "$XDG_DATA" "$XDG_CACHE"

run_kcs() {
    env -i \
        PATH="$PATH" \
        HOME="$HOME_DIR" \
        XDG_CONFIG_HOME="$XDG_CONFIG" \
        XDG_DATA_HOME="$XDG_DATA" \
        XDG_CACHE_HOME="$XDG_CACHE" \
        KCS_TEST_GEMINI_EMBED=mock \
        "$KCS_CMD" "$@"
}

cat >"$SCOPE/public.md" <<'EOF'
# Public document

This public-only introduction gives the document a distinct raw identity.

## Shared paragraph

The shared synthetic paragraph says cobalt orchid glacier 7719.
EOF

(
    cd "$SCOPE"
    run_kcs init --json >"$ROOT/init.json"
    run_kcs index --approve --online --json >"$ROOT/public-index.json"
)

cat >"$SCOPE/credentials_backup.md" <<'EOF'
# Candidate-secret document

This synthetic introduction gives the document a second raw identity.

## Shared paragraph

The shared synthetic paragraph says cobalt orchid glacier 7719.
EOF

(
    cd "$SCOPE"
    run_kcs index --approve --online --json >"$ROOT/secret-index.json"
    run_kcs search "cobalt orchid glacier 7719" --scope . --vector --json \
        >"$ROOT/search.json"
)

PUBLIC_SHARED_ID=$(jq -r \
    'select(.raw_path == "public.md" and (.text | contains("cobalt orchid glacier 7719"))) | .chunk_id' \
    "$SCOPE/.kcs/index/chunks.jsonl")
SECRET_SHARED_ID=$(jq -r \
    'select(.raw_path == "credentials_backup.md" and (.text | contains("cobalt orchid glacier 7719"))) | .chunk_id' \
    "$SCOPE/.kcs/index/chunks.jsonl")
PUBLIC_TEXT_HASH=$(jq -r \
    'select(.raw_path == "public.md" and (.text | contains("cobalt orchid glacier 7719"))) | .text_hash' \
    "$SCOPE/.kcs/index/chunks.jsonl")
SECRET_TEXT_HASH=$(jq -r \
    'select(.raw_path == "credentials_backup.md" and (.text | contains("cobalt orchid glacier 7719"))) | .text_hash' \
    "$SCOPE/.kcs/index/chunks.jsonl")

if [[ -z "$PUBLIC_SHARED_ID" || -z "$SECRET_SHARED_ID" ]]; then
    echo "error: fixture did not produce both shared chunks" >&2
    exit 1
fi

TEXT_TWIN=false
if [[ "$PUBLIC_TEXT_HASH" == "$SECRET_TEXT_HASH" && "$PUBLIC_SHARED_ID" != "$SECRET_SHARED_ID" ]]; then
    TEXT_TWIN=true
fi

SECRET_SHARED_HOLDS=$(jq -s --arg output_ref "embedding:$SECRET_SHARED_ID" \
    '[.[]
      | select(.type == "embedding"
          and .output_ref == $output_ref
          and .status == "paused"
          and .fallback_reason == "secrets_tier_b_hold")]
     | length' \
    "$SCOPE/.kcs/tasks.jsonl")
SECRET_TOTAL_HOLDS=$(jq -s \
    '[.[]
      | select(.type == "embedding"
          and .input_path == "credentials_backup.md"
          and .status == "paused"
          and .fallback_reason == "secrets_tier_b_hold")]
     | length' \
    "$SCOPE/.kcs/tasks.jsonl")
SECRET_SHARED_IN_VECTOR_RESULTS=$(jq -r --arg id "$SECRET_SHARED_ID" \
    'any(.results[]?; .chunk_hash == $id and .title == "credentials_backup.md")' \
    "$ROOT/search.json")

echo "temporary_scope=true"
echo "network_adapter=deterministic_in_process_mock"
echo "distinct_chunk_ids_share_text_hash=$TEXT_TWIN"
echo "secret_unique_chunk_hold_count=$SECRET_TOTAL_HOLDS"
echo "secret_shared_chunk_hold_count=$SECRET_SHARED_HOLDS"
echo "secret_shared_chunk_in_vector_results=$SECRET_SHARED_IN_VECTOR_RESULTS"

# Vulnerable behavior is an internally inconsistent policy state: classification
# created a hold for the unique secret chunk, but the shared secret chunk was
# linked by reuse and omitted from both the hold set and pending enrichment.
if [[ "$TEXT_TWIN" != true || "$SECRET_TOTAL_HOLDS" -lt 1 ]]; then
    echo "error: fixture/control preconditions were not established" >&2
    exit 1
fi

if [[ "$SECRET_SHARED_HOLDS" -eq 0 && "$SECRET_SHARED_IN_VECTOR_RESULTS" == true ]]; then
    echo "result=VULNERABLE_POLICY_STATE_OBSERVED"
    exit 0
fi

if [[ "$SECRET_SHARED_HOLDS" -ge 1 && "$SECRET_SHARED_IN_VECTOR_RESULTS" == false ]]; then
    echo "result=FIXED_POLICY_STATE_OBSERVED"
    exit 0
fi

echo "result=INDETERMINATE_POLICY_STATE"
exit 1
