#!/bin/sh
set -eu

# This is a bounded reachability probe, not a stress test. The fixture size is
# fixed in this file and cannot be increased through an argument or environment
# variable.
fixture_bytes=262144
configured_adapter_cap_bytes=4096

usage() {
    printf 'usage: %s [kcs-command]\n' "$0" >&2
}

if [ "$#" -gt 1 ]; then
    usage
    exit 2
fi

kcs_arg=${1:-${KCS_BIN:-kcs}}
case "$kcs_arg" in
    */*)
        if [ ! -x "$kcs_arg" ]; then
            printf 'error: KCS executable is not runnable: %s\n' "$kcs_arg" >&2
            exit 2
        fi
        kcs_dir=$(CDPATH= cd -- "$(dirname -- "$kcs_arg")" && pwd -P)
        kcs_bin=$kcs_dir/$(basename -- "$kcs_arg")
        ;;
    *)
        kcs_bin=$(command -v "$kcs_arg" 2>/dev/null || true)
        if [ -z "$kcs_bin" ]; then
            printf 'error: KCS executable was not found: %s\n' "$kcs_arg" >&2
            exit 2
        fi
        ;;
esac

work=$(mktemp -d "${TMPDIR:-.}/kcs-bounded-read.XXXXXX")
cleanup() {
    rm -rf -- "$work"
}
trap cleanup EXIT HUP INT TERM

scope=$work/scope
mkdir -p \
    "$scope" \
    "$work/home" \
    "$work/xdg-config" \
    "$work/xdg-data" \
    "$work/xdg-cache"

export HOME=$work/home
export XDG_CONFIG_HOME=$work/xdg-config
export XDG_DATA_HOME=$work/xdg-data
export XDG_CACHE_HOME=$work/xdg-cache

"$kcs_bin" init "$scope" --json >"$work/init.json"

# Keep the existing adapter-only control deliberately small. At the affected
# revision this setting does not protect core status or snapshot processing.
{
    printf '%s\n' 'kcs_format_version = "0.1.0"'
    printf '%s\n' '[adapter.policy]'
    printf 'max_input_bytes = %s\n' "$configured_adapter_cap_bytes"
} >"$scope/.kcs/config.toml"

# awk emits exactly 8,192 copies of a 32-byte ASCII block: 262,144 bytes total.
# There is no sparse file and no large allocation request in this probe.
LC_ALL=C awk 'BEGIN {
    for (i = 0; i < 8192; i++) {
        printf "0123456789abcdef0123456789abcdef"
    }
}' >"$scope/bounded.bin"

actual_fixture_bytes=$(wc -c <"$scope/bounded.bin" | tr -d '[:space:]')
if [ "$actual_fixture_bytes" -ne "$fixture_bytes" ]; then
    printf 'error: fixture size was %s bytes, expected %s\n' \
        "$actual_fixture_bytes" "$fixture_bytes" >&2
    exit 2
fi

if command -v sha256sum >/dev/null 2>&1; then
    digest=$(sha256sum "$scope/bounded.bin" | awk '{print $1}')
elif command -v shasum >/dev/null 2>&1; then
    digest=$(shasum -a 256 "$scope/bounded.bin" | awk '{print $1}')
else
    printf 'error: sha256sum or shasum is required\n' >&2
    exit 2
fi

set +e
(
    cd "$scope"
    "$kcs_bin" status --json
) >"$work/status.json" 2>"$work/status.err"
status_exit=$?

(
    cd "$scope"
    "$kcs_bin" snapshot -m 'bounded read regression' --json
) >"$work/snapshot.json" 2>"$work/snapshot.err"
snapshot_exit=$?
set -e

status_full_hash=false
if [ "$status_exit" -eq 0 ] && grep -q "sha256:$digest" "$work/status.json"; then
    status_full_hash=true
fi

first=$(printf '%s' "$digest" | cut -c1-2)
second=$(printf '%s' "$digest" | cut -c3-4)
raw_object=$scope/.kcs/objects/raw/$first/$second/sha256:$digest
snapshot_raw_object=false
snapshot_raw_object_bytes=0
if [ -f "$raw_object" ]; then
    snapshot_raw_object=true
    snapshot_raw_object_bytes=$(wc -c <"$raw_object" | tr -d '[:space:]')
fi

printf 'fixture_bytes=%s\n' "$fixture_bytes"
printf 'configured_adapter_cap_bytes=%s\n' "$configured_adapter_cap_bytes"
printf 'status_exit=%s\n' "$status_exit"
printf 'status_full_hash=%s\n' "$status_full_hash"
printf 'snapshot_exit=%s\n' "$snapshot_exit"
printf 'snapshot_raw_object=%s\n' "$snapshot_raw_object"
printf 'snapshot_raw_object_bytes=%s\n' "$snapshot_raw_object_bytes"

if [ "$status_full_hash" = true ] \
    && [ "$snapshot_exit" -eq 0 ] \
    && [ "$snapshot_raw_object" = true ] \
    && [ "$snapshot_raw_object_bytes" -eq "$fixture_bytes" ]; then
    printf '%s\n' 'result=WHOLE_FILE_STATUS_AND_SNAPSHOT_PATH_REACHED'
    exit 0
fi

if [ "$status_exit" -ne 0 ] && [ "$snapshot_exit" -ne 0 ]; then
    printf '%s\n' 'result=OVERSIZE_REJECTED_BY_BOTH_COMMANDS'
    exit 0
fi

printf '%s\n' 'result=INDETERMINATE_OR_PARTIALLY_FIXED'
exit 1
