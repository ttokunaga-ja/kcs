#!/bin/sh
set -eu

EXPECTED_REVISION=0e19f3c6489da458e93a982a333c308d92d0a0ae
MAX_BOUNDED_BYTES=1048576
OBJECT_BYTES=${OBJECT_BYTES:-65536}

if [ "$#" -ne 1 ]; then
    echo "usage: $0 PATH_TO_KCS_SOURCE" >&2
    exit 2
fi

case "$OBJECT_BYTES" in
    ''|*[!0-9]*)
        echo "OBJECT_BYTES must be an integer between 1 and $MAX_BOUNDED_BYTES" >&2
        exit 2
        ;;
esac

if [ "$OBJECT_BYTES" -lt 1 ] || [ "$OBJECT_BYTES" -gt "$MAX_BOUNDED_BYTES" ]; then
    echo "OBJECT_BYTES must be between 1 and $MAX_BOUNDED_BYTES" >&2
    exit 2
fi

source_path=$(CDPATH= cd "$1" && pwd -P)
actual_revision=$(git -C "$source_path" rev-parse HEAD)
if [ "$actual_revision" != "$EXPECTED_REVISION" ]; then
    echo "refusing non-target revision: $actual_revision" >&2
    echo "expected: $EXPECTED_REVISION" >&2
    exit 2
fi

if [ -n "$(git -C "$source_path" status --porcelain --untracked-files=no)" ]; then
    echo "refusing a modified source checkout" >&2
    exit 2
fi

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/kcs-cas-read-poc.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM
umask 077

mkdir -p "$work_dir/src" "$work_dir/scope"
cp "$script_dir/main.rs" "$work_dir/src/main.rs"
ln -s "$source_path" "$work_dir/kcs-source"

cat >"$work_dir/Cargo.toml" <<'EOF'
[package]
name = "kcs-cas-read-before-verification-poc"
version = "0.1.0"
edition = "2021"

[dependencies]
kcs-core = { path = "kcs-source/crates/kcs-core" }
serde_json = "1"
EOF

export CARGO_NET_OFFLINE=true
export CARGO_TARGET_DIR="$work_dir/target"
cargo run \
    --offline \
    --quiet \
    --manifest-path "$work_dir/Cargo.toml" \
    -- "$work_dir/scope" "$OBJECT_BYTES"
