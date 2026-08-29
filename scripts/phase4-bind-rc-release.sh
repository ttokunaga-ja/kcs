#!/bin/zsh
# Bind one freshly downloaded public v0.1.0-rc.1 macOS arm64 archive before
# any Phase 4 product replay. This script intentionally never executes bin/kio.

set -eu
setopt noclobber pipefail

readonly EXPECTED_MAIN='34d4107aece6aca0350295d68645d511b7388766'
readonly TAG='v0.1.0-rc.1'
readonly EXPECTED_TAG_OBJECT='8895d0e8eece48b3a99e4d67f2c8d3098edee531'
readonly EXPECTED_CANDIDATE='b95efd86d1ee738378edb7171509ae7ca81e8661'
readonly EXPECTED_TREE='a4183c874799ab55d2471b726f9b5dc4dd3eb8d8'
readonly EXPECTED_LOCK_SHA256='74059079ef8e69ce3e35c31214c0587616bd4eb6c3199553d5339389fc9ece21'
readonly ARCHIVE_NAME='kio-0.1.0-rc.1-aarch64-apple-darwin.tar.gz'
readonly SIDECAR_NAME='kio-0.1.0-rc.1-aarch64-apple-darwin.checksums.json'
readonly EXPECTED_ARCHIVE_BYTES='8083094'
readonly EXPECTED_ARCHIVE_SHA256='590c41518b83eac8b3ba5dba4006ca5afdffd014ebc521817e804f3e77ddfd8c'
readonly EXPECTED_SIDECAR_BYTES='509'
readonly EXPECTED_SIDECAR_SHA256='0ea4bbf4e26ac587653c59408dda65a704c6d075582a0f0eef2730eae20ec45b'
readonly EXPECTED_BINARY_BYTES='20603712'
readonly EXPECTED_BINARY_SHA256='4bdc913150ecf839f05bac1237360ea2bc1cd48757009e077ead3689c806d02c'
readonly RELEASE_BASE='https://github.com/ttokunaga-ja/kio/releases/download/v0.1.0-rc.1'
readonly RELEASE_API='https://api.github.com/repos/ttokunaga-ja/kio/releases/tags/v0.1.0-rc.1'

usage() {
  print -u2 -- "usage: $0 [--source-repo ABSOLUTE_PATH] [--parent ABSOLUTE_EXISTING_DIRECTORY]"
  exit 64
}

sha256() {
  shasum -a 256 "$1" | awk '{print $1}'
}

file_bytes() {
  stat -f '%z' "$1"
}

utc_now() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

SOURCE_REPO="${0:A:h:h}"
PARENT_ROOT='/private/tmp'
while (( $# > 0 )); do
  case "$1" in
    --source-repo)
      (( $# >= 2 )) || usage
      SOURCE_REPO="$2"
      shift 2
      ;;
    --parent)
      (( $# >= 2 )) || usage
      PARENT_ROOT="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done

[[ "$SOURCE_REPO" = /* && "$PARENT_ROOT" = /* ]] || usage
[[ -d "$SOURCE_REPO" && -d "$PARENT_ROOT" ]] || {
  print -u2 -- 'source repository and parent must be existing directories'
  exit 64
}
SOURCE_REPO="$(cd "$SOURCE_REPO" && pwd -P)"
PARENT_ROOT="$(cd "$PARENT_ROOT" && pwd -P)"
[[ -f "$SOURCE_REPO/.git" ]] || {
  print -u2 -- 'source repository must be an independent linked worktree'
  exit 64
}
git -C "$SOURCE_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  print -u2 -- "not a Git worktree: $SOURCE_REPO"
  exit 64
}
[[ -z "$(git -C "$SOURCE_REPO" status --porcelain=v1)" ]] || {
  print -u2 -- 'source worktree must be clean'
  exit 64
}

RUN_ROOT="$(mktemp -d "${PARENT_ROOT}/kio-phase4-rc1.XXXXXXXX")"
RUN_ID="$(basename "$RUN_ROOT")"
EVIDENCE_ROOT="${RUN_ROOT}/phase4-manual-evidence/${RUN_ID}"
mkdir -p "$EVIDENCE_ROOT/binding/release-verify" "$RUN_ROOT/download" "$RUN_ROOT/extracted"

fatal() {
  local reason="$1"
  local code="${2:-1}"
  if [[ ! -e "$EVIDENCE_ROOT/binding/failure.json" ]]; then
    jq -n \
      --arg schema 'kio.phase4.binding-failure.v1' \
      --arg run_id "$RUN_ID" \
      --arg observed_at "$(utc_now)" \
      --arg reason "$reason" \
      --argjson exit_code "$code" \
      '{schema:$schema,run_id:$run_id,observed_at:$observed_at,status:"failed",reason:$reason,exit_code:$exit_code}' \
      > "$EVIDENCE_ROOT/binding/failure.json"
  fi
  print -u2 -- "phase4 binding failed: ${reason}"
  print -u2 -- "evidence: ${EVIDENCE_ROOT}"
  exit "$code"
}

unexpected_failure() {
  local code="$1"
  trap - ZERR
  fatal 'unexpected_runner_error' "$code"
}
trap 'unexpected_failure $?' ZERR

jq -n \
  --arg schema 'kio.phase4.manual-run.v1' \
  --arg run_id "$RUN_ID" \
  --arg started_at "$(utc_now)" \
  --arg source_repo "$SOURCE_REPO" \
  --arg run_root "$RUN_ROOT" \
  --arg evidence_root "$EVIDENCE_ROOT" \
  --arg host_os "$(uname -s)" \
  --arg host_arch "$(uname -m)" \
  --arg host_version "$(sw_vers -productVersion)" \
  --arg expected_main "$EXPECTED_MAIN" \
  --arg expected_tag_object "$EXPECTED_TAG_OBJECT" \
  --arg expected_candidate "$EXPECTED_CANDIDATE" \
  --arg expected_tree "$EXPECTED_TREE" \
  --arg expected_lock_sha256 "$EXPECTED_LOCK_SHA256" \
  --arg archive_name "$ARCHIVE_NAME" \
  --argjson archive_bytes "$EXPECTED_ARCHIVE_BYTES" \
  --arg expected_archive_sha256 "$EXPECTED_ARCHIVE_SHA256" \
  --arg sidecar_name "$SIDECAR_NAME" \
  --argjson sidecar_bytes "$EXPECTED_SIDECAR_BYTES" \
  --arg expected_sidecar_sha256 "$EXPECTED_SIDECAR_SHA256" \
  --argjson binary_bytes "$EXPECTED_BINARY_BYTES" \
  --arg expected_binary_sha256 "$EXPECTED_BINARY_SHA256" \
  '{schema:$schema,schema_version:1,run_id:$run_id,started_at:$started_at,status:"running",host:{os:$host_os,arch:$host_arch,version:$host_version,distribution_platform:"aarch64-apple-darwin"},paths:{source_repo:$source_repo,run_root:$run_root,evidence_root:$evidence_root},expected_binding:{origin_main:$expected_main,tag_name:"v0.1.0-rc.1",tag_object:$expected_tag_object,candidate_commit:$expected_candidate,candidate_tree:$expected_tree,cargo_lock_sha256:$expected_lock_sha256,archive:{name:$archive_name,bytes:$archive_bytes,sha256:$expected_archive_sha256},sidecar:{name:$sidecar_name,bytes:$sidecar_bytes,sha256:$expected_sidecar_sha256},binary:{path:"bin/kio",bytes:$binary_bytes,sha256:$expected_binary_sha256}}}' \
  > "$EVIDENCE_ROOT/run.json" || fatal 'could_not_create_run_record'

[[ "$(uname -s)" == 'Darwin' && "$(uname -m)" == 'arm64' ]] || fatal 'host_platform_mismatch'

ORIGIN_URL="$(git -C "$SOURCE_REPO" remote get-url origin 2>/dev/null)" || fatal 'origin_remote_missing'
[[ "$ORIGIN_URL" == 'https://github.com/ttokunaga-ja/kio.git' ]] || fatal 'origin_url_mismatch'
REFS_STDOUT="$EVIDENCE_ROOT/binding/refs-ls-remote.stdout"
REFS_STDERR="$EVIDENCE_ROOT/binding/refs-ls-remote.stderr"
if git ls-remote "$ORIGIN_URL" "refs/heads/main" "refs/tags/${TAG}" "refs/tags/${TAG}^{}" > "$REFS_STDOUT" 2> "$REFS_STDERR"; then
  REFS_EXIT=0
else
  REFS_EXIT=$?
fi
REFS="$(<"$REFS_STDOUT")"
LIVE_MAIN="$(print -r -- "$REFS" | awk '$2 == "refs/heads/main" { print $1 }')"
LIVE_TAG="$(print -r -- "$REFS" | awk '$2 == "refs/tags/v0.1.0-rc.1" { print $1 }')"
LIVE_PEELED="$(print -r -- "$REFS" | awk '$2 == "refs/tags/v0.1.0-rc.1^{}" { print $1 }')"
REFS_MATCH=false
if (( REFS_EXIT == 0 )) && [[ "$LIVE_MAIN" == "$EXPECTED_MAIN" && "$LIVE_TAG" == "$EXPECTED_TAG_OBJECT" && "$LIVE_PEELED" == "$EXPECTED_CANDIDATE" ]]; then
  REFS_MATCH=true
fi
jq -n \
  --arg schema 'kio.phase4.live-refs-attempt.v1' \
  --arg observed_at "$(utc_now)" \
  --arg origin "$ORIGIN_URL" \
  --arg main "$LIVE_MAIN" \
  --arg expected_main "$EXPECTED_MAIN" \
  --arg tag "$LIVE_TAG" \
  --arg expected_tag "$EXPECTED_TAG_OBJECT" \
  --arg peeled "$LIVE_PEELED" \
  --arg expected_peeled "$EXPECTED_CANDIDATE" \
  --arg stdout_sha256 "$(sha256 "$REFS_STDOUT")" \
  --arg stderr_sha256 "$(sha256 "$REFS_STDERR")" \
  --argjson exit_code "$REFS_EXIT" \
  --argjson matches "$REFS_MATCH" \
  '{schema:$schema,observed_at:$observed_at,origin:$origin,exit_code:$exit_code,matches:$matches,observed:{origin_main:$main,tag_object:$tag,peeled_candidate:$peeled},expected:{origin_main:$expected_main,tag_object:$expected_tag,peeled_candidate:$expected_peeled},stdout_sha256:$stdout_sha256,stderr_sha256:$stderr_sha256}' \
  > "$EVIDENCE_ROOT/binding/refs-attempt.json" || fatal 'could_not_create_refs_attempt_receipt'
(( REFS_EXIT == 0 )) || fatal 'live_ref_query_failed' "$REFS_EXIT"
[[ "$LIVE_MAIN" == "$EXPECTED_MAIN" && "$LIVE_TAG" == "$EXPECTED_TAG_OBJECT" && "$LIVE_PEELED" == "$EXPECTED_CANDIDATE" ]] || fatal 'live_ref_binding_mismatch'
jq -n \
  --arg schema 'kio.phase4.live-refs.v1' \
  --arg observed_at "$(utc_now)" \
  --arg origin "$ORIGIN_URL" \
  --arg main "$LIVE_MAIN" \
  --arg tag "$LIVE_TAG" \
  --arg peeled "$LIVE_PEELED" \
  --arg refs_attempt_sha256 "$(sha256 "$EVIDENCE_ROOT/binding/refs-attempt.json")" \
  '{schema:$schema,observed_at:$observed_at,status:"passed",origin:$origin,refs:{origin_main:$main,tag_object:$tag,peeled_candidate:$peeled},refs_attempt_sha256:$refs_attempt_sha256}' \
  > "$EVIDENCE_ROOT/binding/refs.json" || fatal 'could_not_create_refs_receipt'

ARCHIVE_PATH="$RUN_ROOT/download/$ARCHIVE_NAME"
SIDECAR_PATH="$RUN_ROOT/download/$SIDECAR_NAME"
RELEASE_API_PATH="$EVIDENCE_ROOT/binding/release-api.json"
[[ ! -e "$ARCHIVE_PATH" && ! -e "$SIDECAR_PATH" ]] || fatal 'download_path_collision'
if ! curl --fail --location --proto '=https' --tlsv1.2 \
  --header 'Accept: application/vnd.github+json' \
  --output "$RELEASE_API_PATH" "$RELEASE_API"; then
  fatal 'release_api_query_failed'
fi
jq -e \
  --arg archive "$ARCHIVE_NAME" \
  --arg sidecar "$SIDECAR_NAME" \
  --argjson archive_bytes "$EXPECTED_ARCHIVE_BYTES" \
  --argjson sidecar_bytes "$EXPECTED_SIDECAR_BYTES" \
  '.tag_name == "v0.1.0-rc.1" and .draft == false and .prerelease == true and
   (.assets | length == 6) and
   ([.assets[] | select(.name == $archive and .size == $archive_bytes)] | length == 1) and
   ([.assets[] | select(.name == $sidecar and .size == $sidecar_bytes)] | length == 1)' \
  "$RELEASE_API_PATH" >/dev/null || fatal 'live_release_metadata_mismatch'
if ! curl --fail --location --proto '=https' --tlsv1.2 --output "$ARCHIVE_PATH" "$RELEASE_BASE/$ARCHIVE_NAME"; then
  fatal 'archive_download_failed'
fi
if ! curl --fail --location --proto '=https' --tlsv1.2 --output "$SIDECAR_PATH" "$RELEASE_BASE/$SIDECAR_NAME"; then
  fatal 'sidecar_download_failed'
fi

ARCHIVE_BYTES="$(file_bytes "$ARCHIVE_PATH")"
ARCHIVE_SHA256="$(sha256 "$ARCHIVE_PATH")"
SIDECAR_BYTES="$(file_bytes "$SIDECAR_PATH")"
SIDECAR_SHA256="$(sha256 "$SIDECAR_PATH")"
[[ "$ARCHIVE_BYTES" == "$EXPECTED_ARCHIVE_BYTES" && "$ARCHIVE_SHA256" == "$EXPECTED_ARCHIVE_SHA256" ]] || fatal 'archive_size_or_digest_mismatch'
[[ "$SIDECAR_BYTES" == "$EXPECTED_SIDECAR_BYTES" && "$SIDECAR_SHA256" == "$EXPECTED_SIDECAR_SHA256" ]] || fatal 'sidecar_size_or_digest_mismatch'
jq -e \
  --arg archive "$ARCHIVE_NAME" \
  --arg archive_sha256 "$EXPECTED_ARCHIVE_SHA256" \
  --arg binary_sha256 "$EXPECTED_BINARY_SHA256" \
  'type == "object" and (keys == ["archive","archive_sha256","binary_sha256","checksums_sha256","provenance_sha256","sbom_sha256","schema"]) and .schema == "kio-rc-checksums-v1" and .archive == $archive and .archive_sha256 == $archive_sha256 and .binary_sha256 == $binary_sha256 and ([.checksums_sha256,.provenance_sha256,.sbom_sha256] | all(test("^[0-9a-f]{64}$")))' \
  "$SIDECAR_PATH" >/dev/null || fatal 'sidecar_schema_or_binding_mismatch'
cp "$SIDECAR_PATH" "$EVIDENCE_ROOT/binding/sidecar.json" || fatal 'could_not_copy_sidecar_receipt'
print -r -- "$ARCHIVE_SHA256  $ARCHIVE_NAME" > "$EVIDENCE_ROOT/binding/archive.sha256" || fatal 'could_not_write_archive_digest'
print -r -- "$SIDECAR_SHA256  $SIDECAR_NAME" > "$EVIDENCE_ROOT/binding/sidecar.sha256" || fatal 'could_not_write_sidecar_digest'
jq -n \
  --arg schema 'kio.phase4.release-download.v1' \
  --arg observed_at "$(utc_now)" \
  --arg archive_url "$RELEASE_BASE/$ARCHIVE_NAME" \
  --arg sidecar_url "$RELEASE_BASE/$SIDECAR_NAME" \
  --arg archive_path "$ARCHIVE_PATH" \
  --arg sidecar_path "$SIDECAR_PATH" \
  --arg archive_sha256 "$ARCHIVE_SHA256" \
  --arg sidecar_sha256 "$SIDECAR_SHA256" \
  --argjson archive_bytes "$ARCHIVE_BYTES" \
  --argjson sidecar_bytes "$SIDECAR_BYTES" \
  '{schema:$schema,observed_at:$observed_at,status:"bound",archive:{url:$archive_url,path:$archive_path,bytes:$archive_bytes,sha256:$archive_sha256},sidecar:{url:$sidecar_url,path:$sidecar_path,bytes:$sidecar_bytes,sha256:$sidecar_sha256}}' \
  > "$EVIDENCE_ROOT/binding/release-download.json" || fatal 'could_not_create_download_receipt'

CANDIDATE_REPO="$RUN_ROOT/candidate-source"
if ! git clone --no-hardlinks --no-checkout "$SOURCE_REPO" "$CANDIDATE_REPO" >/dev/null 2>&1; then
  fatal 'candidate_clone_failed'
fi
if ! git -C "$CANDIDATE_REPO" checkout --detach "$EXPECTED_CANDIDATE" >/dev/null 2>&1; then
  fatal 'candidate_checkout_failed'
fi
[[ "$(git -C "$CANDIDATE_REPO" rev-parse HEAD)" == "$EXPECTED_CANDIDATE" ]] || fatal 'candidate_head_mismatch'
[[ "$(git -C "$CANDIDATE_REPO" rev-parse 'HEAD^{tree}')" == "$EXPECTED_TREE" ]] || fatal 'candidate_tree_mismatch'
[[ -z "$(git -C "$CANDIDATE_REPO" status --porcelain)" ]] || fatal 'candidate_checkout_dirty'
[[ "$(git -C "$CANDIDATE_REPO" cat-file -t "$EXPECTED_TAG_OBJECT")" == 'tag' ]] || fatal 'candidate_tag_type_mismatch'
[[ "$(git -C "$CANDIDATE_REPO" rev-parse "${EXPECTED_TAG_OBJECT}^{}")" == "$EXPECTED_CANDIDATE" ]] || fatal 'candidate_tag_peel_mismatch'
[[ "$(sha256 "$CANDIDATE_REPO/Cargo.lock")" == "$EXPECTED_LOCK_SHA256" ]] || fatal 'candidate_lock_digest_mismatch'

VERIFY_DIR="$EVIDENCE_ROOT/binding/release-verify"
VERIFY_STDOUT="$VERIFY_DIR/stdout.bin"
VERIFY_STDERR="$VERIFY_DIR/stderr.bin"
VERIFY_TARGET_DIR="$RUN_ROOT/verifier-target"
AMBIENT_CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}"
AMBIENT_RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"
AMBIENT_CARGO_HOME="$(cd "$AMBIENT_CARGO_HOME" && pwd -P)" || fatal 'cargo_home_unavailable'
AMBIENT_RUSTUP_HOME="$(cd "$AMBIENT_RUSTUP_HOME" && pwd -P)" || fatal 'rustup_home_unavailable'
TOOLCHAIN_ROOT="$AMBIENT_RUSTUP_HOME/toolchains/1.98.0-aarch64-apple-darwin"
[[ -x "$TOOLCHAIN_ROOT/bin/cargo" && -x "$TOOLCHAIN_ROOT/bin/rustc" ]] || fatal 'rust_1_98_not_preinstalled'
CARGO_PROXY="$AMBIENT_CARGO_HOME/bin/cargo"
RUSTC_PROXY="$AMBIENT_CARGO_HOME/bin/rustc"
[[ -x "$AMBIENT_CARGO_HOME/bin/rustup" && -L "$CARGO_PROXY" && -L "$RUSTC_PROXY" ]] || fatal 'rustup_proxy_layout_mismatch'
[[ "$(readlink "$CARGO_PROXY")" == 'rustup' && "$(readlink "$RUSTC_PROXY")" == 'rustup' ]] || fatal 'rustup_proxy_target_mismatch'
VERIFY_HOME="$RUN_ROOT/verifier-home"
VERIFY_TMPDIR="$RUN_ROOT/verifier-tmp"
VERIFY_CARGO_HOME="$RUN_ROOT/verifier-cargo-home"
VERIFY_PATH_DIR="$RUN_ROOT/verifier-path"
mkdir -p "$VERIFY_HOME/xdg-config" "$VERIFY_HOME/xdg-cache" "$VERIFY_HOME/xdg-data" "$VERIFY_TMPDIR" "$VERIFY_CARGO_HOME" "$VERIFY_PATH_DIR"
ln -s "$CARGO_PROXY" "$VERIFY_PATH_DIR/cargo"
ln -s "$RUSTC_PROXY" "$VERIFY_PATH_DIR/rustc"
if [[ -d "$AMBIENT_CARGO_HOME/registry" ]]; then
  ln -s "$AMBIENT_CARGO_HOME/registry" "$VERIFY_CARGO_HOME/registry"
fi
if [[ -d "$AMBIENT_CARGO_HOME/git" ]]; then
  ln -s "$AMBIENT_CARGO_HOME/git" "$VERIFY_CARGO_HOME/git"
fi
VERIFY_PATH="$VERIFY_PATH_DIR:/usr/bin:/bin:/usr/sbin:/sbin"
VERIFY_ENV=(
  "HOME=$VERIFY_HOME"
  "XDG_CONFIG_HOME=$VERIFY_HOME/xdg-config"
  "XDG_CACHE_HOME=$VERIFY_HOME/xdg-cache"
  "XDG_DATA_HOME=$VERIFY_HOME/xdg-data"
  "TMPDIR=$VERIFY_TMPDIR"
  "PATH=$VERIFY_PATH"
  "CARGO_HOME=$VERIFY_CARGO_HOME"
  "RUSTUP_HOME=$AMBIENT_RUSTUP_HOME"
  'RUSTUP_AUTO_INSTALL=0'
  'RUSTUP_NO_UPDATE_CHECK=1'
  "CARGO_NET_OFFLINE=true"
  "CARGO_TARGET_DIR=$VERIFY_TARGET_DIR"
  'GIT_CONFIG_NOSYSTEM=1'
  'GIT_CONFIG_GLOBAL=/dev/null'
  'RUST_BACKTRACE=0'
  'LC_ALL=C'
  'LANG=C'
  'TZ=UTC'
)
RUST_VERSION="$(/usr/bin/env -i "${VERIFY_ENV[@]}" "$RUSTC_PROXY" +1.98.0 --version 2>&1)" || fatal 'rust_1_98_unavailable'
[[ "$RUST_VERSION" == 'rustc 1.98.0 '* ]] || fatal 'rust_version_mismatch'
VERIFY_ARGV=("$CARGO_PROXY" +1.98.0 run --locked --offline -p kio-eval -- release verify --archive "$ARCHIVE_PATH" --checksums "$SIDECAR_PATH" --expected-archive-sha256 "$EXPECTED_ARCHIVE_SHA256" --source-repo "$CANDIDATE_REPO" --expected-commit "$EXPECTED_CANDIDATE" --expected-lock-sha256 "$EXPECTED_LOCK_SHA256")
{
  print -r -- "cwd=$CANDIDATE_REPO"
  print -r -- 'environment=/usr/bin/env -i'
  for entry in "${VERIFY_ENV[@]}"; do
    printf '  %q\n' "$entry"
  done
  print -r -- "env:KIO_FIXED_NOW=unset"
  print -r -- 'env:KIO_TEST_*=unset'
  print -r -- 'env:secret/proxy/wrapper variables=unset'
  print -r -- 'argv:'
  for arg in "${VERIFY_ARGV[@]}"; do
    printf '  %q\n' "$arg"
  done
} > "$VERIFY_DIR/command.txt" || fatal 'could_not_create_verifier_command_record'

if (cd "$CANDIDATE_REPO" && /usr/bin/env -i "${VERIFY_ENV[@]}" "${VERIFY_ARGV[@]}") > "$VERIFY_STDOUT" 2> "$VERIFY_STDERR"; then
  VERIFY_EXIT=0
else
  VERIFY_EXIT=$?
fi
if (( VERIFY_EXIT != 0 )); then
  print -r -- "$(sha256 "$VERIFY_STDOUT")  stdout.bin" > "$VERIFY_DIR/stdout.sha256"
  print -r -- "$(sha256 "$VERIFY_STDERR")  stderr.bin" > "$VERIFY_DIR/stderr.sha256"
  jq -n --arg schema 'kio.phase4.release-verify.v1' --arg rust_version "$RUST_VERSION" --argjson exit_code "$VERIFY_EXIT" --arg stdout_sha256 "$(sha256 "$VERIFY_STDOUT")" --arg stderr_sha256 "$(sha256 "$VERIFY_STDERR")" '{schema:$schema,status:"failed",rust_version:$rust_version,exit_code:$exit_code,stdout_sha256:$stdout_sha256,stderr_sha256:$stderr_sha256}' > "$VERIFY_DIR/receipt.json"
  fatal 'canonical_release_verify_failed' "$VERIFY_EXIT"
fi
VERIFY_STDOUT_SHA256="$(sha256 "$VERIFY_STDOUT")"
VERIFY_STDERR_SHA256="$(sha256 "$VERIFY_STDERR")"
print -r -- "$VERIFY_STDOUT_SHA256  stdout.bin" > "$VERIFY_DIR/stdout.sha256"
print -r -- "$VERIFY_STDERR_SHA256  stderr.bin" > "$VERIFY_DIR/stderr.sha256"
jq -e \
  --arg archive_sha256 "$EXPECTED_ARCHIVE_SHA256" \
  --arg candidate "$EXPECTED_CANDIDATE" \
  --arg tree "$EXPECTED_TREE" \
  --arg lock_sha256 "$EXPECTED_LOCK_SHA256" \
  'type == "object" and
   (keys == ["archive_sha256","binding","root","support"]) and
   .root == "kio-0.1.0-rc.1-aarch64-apple-darwin" and
   .archive_sha256 == $archive_sha256 and
   .binding.commit == $candidate and .binding.tree == $tree and
   .binding.cargo_lock_sha256 == $lock_sha256 and
   .binding.target == "aarch64-apple-darwin" and
   .binding.version == "0.1.0-rc.1" and .support != null' \
  "$VERIFY_STDOUT" >/dev/null || fatal 'canonical_release_verify_receipt_invalid'
jq -n \
  --arg schema 'kio.phase4.release-verify.v1' \
  --arg verified_at "$(utc_now)" \
  --arg rust_version "$RUST_VERSION" \
  --arg cwd "$CANDIDATE_REPO" \
  --arg command_sha256 "$(sha256 "$VERIFY_DIR/command.txt")" \
  --arg archive_path "$ARCHIVE_PATH" \
  --arg archive_sha256 "$EXPECTED_ARCHIVE_SHA256" \
  --arg sidecar_path "$SIDECAR_PATH" \
  --arg sidecar_sha256 "$EXPECTED_SIDECAR_SHA256" \
  --arg candidate_repo "$CANDIDATE_REPO" \
  --arg candidate_commit "$EXPECTED_CANDIDATE" \
  --arg candidate_tree "$EXPECTED_TREE" \
  --arg lock_sha256 "$EXPECTED_LOCK_SHA256" \
  --arg stdout_sha256 "$VERIFY_STDOUT_SHA256" \
  --arg stderr_sha256 "$VERIFY_STDERR_SHA256" \
  --argjson stdout_bytes "$(file_bytes "$VERIFY_STDOUT")" \
  --argjson stderr_bytes "$(file_bytes "$VERIFY_STDERR")" \
  --slurpfile verifier_summary "$VERIFY_STDOUT" \
  '{schema:$schema,verified_at:$verified_at,status:"passed",rust_version:$rust_version,cwd:$cwd,exit_code:0,command_sha256:$command_sha256,inputs:{archive:{path:$archive_path,sha256:$archive_sha256},sidecar:{path:$sidecar_path,sha256:$sidecar_sha256},source_repo:$candidate_repo,expected_commit:$candidate_commit,expected_tree:$candidate_tree,expected_lock_sha256:$lock_sha256},outputs:{stdout:{bytes:$stdout_bytes,sha256:$stdout_sha256},stderr:{bytes:$stderr_bytes,sha256:$stderr_sha256}},verifier_summary:$verifier_summary[0],successful_checks:["archive_layout","archive_digest","sidecar_binding","source_binding","provenance","sbom","dependency_inventory","dependency_audit","internal_checksums","binary_binding"],assertions:{canonical_release_verify_exit_zero:true,archive_digest_matches:true,candidate_commit_matches:true,candidate_tree_matches:true,lock_digest_matches:true,target_matches:true,version_matches:true}}' \
  > "$VERIFY_DIR/receipt.json" || fatal 'could_not_create_verifier_receipt'

EXTRACTED_ROOT="$RUN_ROOT/extracted/kio-0.1.0-rc.1-aarch64-apple-darwin"
if ! tar -xzf "$ARCHIVE_PATH" -C "$RUN_ROOT/extracted"; then
  fatal 'archive_extraction_failed'
fi
BINARY_PATH="$EXTRACTED_ROOT/bin/kio"
[[ -f "$BINARY_PATH" && ! -L "$BINARY_PATH" ]] || fatal 'extracted_binary_missing_or_not_regular'
BINARY_BYTES="$(file_bytes "$BINARY_PATH")"
BINARY_SHA256="$(sha256 "$BINARY_PATH")"
[[ "$BINARY_BYTES" == "$EXPECTED_BINARY_BYTES" && "$BINARY_SHA256" == "$EXPECTED_BINARY_SHA256" ]] || fatal 'extracted_binary_size_or_digest_mismatch'
print -r -- "$BINARY_SHA256  bin/kio" > "$EVIDENCE_ROOT/binding/binary.sha256" || fatal 'could_not_write_binary_digest'
jq -n \
  --arg schema 'kio.phase4.binding-completion.v1' \
  --arg completed_at "$(utc_now)" \
  --arg archive_sha256 "$ARCHIVE_SHA256" \
  --arg sidecar_sha256 "$SIDECAR_SHA256" \
  --arg binary_sha256 "$BINARY_SHA256" \
  --arg extracted_binary "$BINARY_PATH" \
  --arg run_record_sha256 "$(sha256 "$EVIDENCE_ROOT/run.json")" \
  --arg refs_sha256 "$(sha256 "$EVIDENCE_ROOT/binding/refs.json")" \
  --arg release_api_sha256 "$(sha256 "$RELEASE_API_PATH")" \
  --arg release_download_sha256 "$(sha256 "$EVIDENCE_ROOT/binding/release-download.json")" \
  --arg sidecar_receipt_sha256 "$(sha256 "$EVIDENCE_ROOT/binding/sidecar.json")" \
  --arg verifier_command_sha256 "$(sha256 "$VERIFY_DIR/command.txt")" \
  --arg verifier_receipt_sha256 "$(sha256 "$VERIFY_DIR/receipt.json")" \
  --argjson archive_bytes "$ARCHIVE_BYTES" \
  --argjson sidecar_bytes "$SIDECAR_BYTES" \
  --argjson binary_bytes "$BINARY_BYTES" \
  '{schema:$schema,completed_at:$completed_at,status:"passed",product_binary_executed:false,archive:{bytes:$archive_bytes,sha256:$archive_sha256},sidecar:{bytes:$sidecar_bytes,sha256:$sidecar_sha256},binary:{path:$extracted_binary,bytes:$binary_bytes,sha256:$binary_sha256},evidence_sha256:{run_record:$run_record_sha256,refs:$refs_sha256,release_api:$release_api_sha256,release_download:$release_download_sha256,sidecar_receipt:$sidecar_receipt_sha256,verifier_command:$verifier_command_sha256,verifier_receipt:$verifier_receipt_sha256}}' \
  > "$EVIDENCE_ROOT/binding/completion.json" || fatal 'could_not_create_binding_completion'

print -- "phase4 binding passed"
print -- "run root: $RUN_ROOT"
print -- "evidence: $EVIDENCE_ROOT"
