#!/bin/zsh
# Replay the public v0.1.0-rc.1 binary for the independent Phase 4 M1/M8
# checkpoints.  This runner deliberately does not download, build, or select a
# product binary: it accepts only the output of phase4-bind-rc-release.sh.

set -eu
setopt noclobber pipefail

readonly EXPECTED_BINARY_BYTES=20603712
readonly EXPECTED_BINARY_SHA256='4bdc913150ecf839f05bac1237360ea2bc1cd48757009e077ead3689c806d02c'
readonly EXPECTED_ARCHIVE_BYTES=8083094
readonly EXPECTED_ARCHIVE_SHA256='590c41518b83eac8b3ba5dba4006ca5afdffd014ebc521817e804f3e77ddfd8c'
readonly EXPECTED_SIDECAR_BYTES=509
readonly EXPECTED_SIDECAR_SHA256='0ea4bbf4e26ac587653c59408dda65a704c6d075582a0f0eef2730eae20ec45b'
readonly EXPECTED_ORIGIN_MAIN='34d4107aece6aca0350295d68645d511b7388766'
readonly EXPECTED_TAG_OBJECT='8895d0e8eece48b3a99e4d67f2c8d3098edee531'
readonly EXPECTED_CANDIDATE_COMMIT='b95efd86d1ee738378edb7171509ae7ca81e8661'
readonly EXPECTED_CANDIDATE_TREE='a4183c874799ab55d2471b726f9b5dc4dd3eb8d8'
readonly EXPECTED_LOCK_SHA256='74059079ef8e69ce3e35c31214c0587616bd4eb6c3199553d5339389fc9ece21'
readonly EXPECTED_MANUAL_CONFIG_SHA256='455e7192e094bc14fdf58beb8b358d49bc2095ec57f03a5fb6ac46d8afcc7650'
readonly MANUAL_CONFIG=$'[gc]\nmode = "manual_only"\n\n[gc.auto_retention]\nkeep_last_hours = 0\nkeep_hourly_days = 0\nkeep_daily_weeks = 0\nkeep_weekly_months = 0\n'

usage() {
  print -u2 -- "usage: $0 --run-root ABSOLUTE_PATH"
  exit 64
}

sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
file_bytes() { stat -f '%z' "$1"; }
utc_now() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

RUN_ROOT=''
while (( $# > 0 )); do
  case "$1" in
    --run-root) (( $# >= 2 )) || usage; RUN_ROOT="$2"; shift 2 ;;
    *) usage ;;
  esac
done
[[ -n "$RUN_ROOT" && "$RUN_ROOT" = /* && -d "$RUN_ROOT" ]] || usage
RUN_ROOT="$(cd "$RUN_ROOT" && pwd -P)"
RUN_ID="$(basename "$RUN_ROOT")"
EVIDENCE_ROOT="$RUN_ROOT/phase4-manual-evidence/$RUN_ID"
BINDING="$EVIDENCE_ROOT/binding"
FIXTURE="$EVIDENCE_ROOT/fixture"
STAGES="$EVIDENCE_ROOT/stages"

[[ -f "$EVIDENCE_ROOT/run.json" && -f "$BINDING/completion.json" && -f "$BINDING/binary.sha256" ]] || {
  print -u2 -- 'binding completion is missing'
  exit 65
}
jq -e \
  --arg archive_sha "$EXPECTED_ARCHIVE_SHA256" --argjson archive_bytes "$EXPECTED_ARCHIVE_BYTES" \
  --arg sidecar_sha "$EXPECTED_SIDECAR_SHA256" --argjson sidecar_bytes "$EXPECTED_SIDECAR_BYTES" \
  --arg binary_sha "$EXPECTED_BINARY_SHA256" --argjson binary_bytes "$EXPECTED_BINARY_BYTES" \
  '.schema == "kio.phase4.binding-completion.v1" and .status == "passed" and .product_binary_executed == false and
   .archive == {bytes:$archive_bytes,sha256:$archive_sha} and
   .sidecar == {bytes:$sidecar_bytes,sha256:$sidecar_sha} and
   .binary.bytes == $binary_bytes and .binary.sha256 == $binary_sha and
   (.binary.path | type == "string" and length > 1)' \
  "$BINDING/completion.json" >/dev/null || {
  print -u2 -- 'binding completion does not authorize product replay'
  exit 65
}
jq -e \
  --arg run_id "$RUN_ID" --arg origin "$EXPECTED_ORIGIN_MAIN" \
  --arg tag_object "$EXPECTED_TAG_OBJECT" --arg commit "$EXPECTED_CANDIDATE_COMMIT" \
  --arg tree "$EXPECTED_CANDIDATE_TREE" --arg lock "$EXPECTED_LOCK_SHA256" \
  --arg archive_sha "$EXPECTED_ARCHIVE_SHA256" --argjson archive_bytes "$EXPECTED_ARCHIVE_BYTES" \
  --arg sidecar_sha "$EXPECTED_SIDECAR_SHA256" --argjson sidecar_bytes "$EXPECTED_SIDECAR_BYTES" \
  --arg binary_sha "$EXPECTED_BINARY_SHA256" --argjson binary_bytes "$EXPECTED_BINARY_BYTES" '
    .schema == "kio.phase4.manual-run.v1" and .schema_version == 1 and
    .run_id == $run_id and .status == "running" and
    .expected_binding.origin_main == $origin and
    .expected_binding.tag_name == "v0.1.0-rc.1" and
    .expected_binding.tag_object == $tag_object and
    .expected_binding.candidate_commit == $commit and
    .expected_binding.candidate_tree == $tree and
    .expected_binding.cargo_lock_sha256 == $lock and
    .expected_binding.archive == {name:"kio-0.1.0-rc.1-aarch64-apple-darwin.tar.gz",bytes:$archive_bytes,sha256:$archive_sha} and
    .expected_binding.sidecar == {name:"kio-0.1.0-rc.1-aarch64-apple-darwin.checksums.json",bytes:$sidecar_bytes,sha256:$sidecar_sha} and
    .expected_binding.binary == {path:"bin/kio",bytes:$binary_bytes,sha256:$binary_sha}' \
  "$EVIDENCE_ROOT/run.json" >/dev/null || {
  print -u2 -- 'run record does not match the fixed binding'
  exit 65
}
PRODUCT_BINARY="$(jq -r '.binary.path' "$BINDING/completion.json")"
EXPECTED_PRODUCT_BINARY="$RUN_ROOT/extracted/kio-0.1.0-rc.1-aarch64-apple-darwin/bin/kio"
PRODUCT_BINARY_PHYSICAL="$(cd "$(dirname "$PRODUCT_BINARY")" 2>/dev/null && pwd -P)/$(basename "$PRODUCT_BINARY")" || {
  print -u2 -- 'bound binary path cannot be resolved physically'
  exit 65
}
[[ "$PRODUCT_BINARY" == "$EXPECTED_PRODUCT_BINARY" && "$PRODUCT_BINARY_PHYSICAL" == "$EXPECTED_PRODUCT_BINARY" && \
  -f "$PRODUCT_BINARY" && ! -L "$PRODUCT_BINARY" && -x "$PRODUCT_BINARY" && "$(stat -f '%l' "$PRODUCT_BINARY")" == 1 ]] || {
  print -u2 -- 'bound binary is not a regular file inside this run root'
  exit 65
}
[[ "$(file_bytes "$PRODUCT_BINARY")" == "$EXPECTED_BINARY_BYTES" && "$(sha256 "$PRODUCT_BINARY")" == "$EXPECTED_BINARY_SHA256" ]] || {
  print -u2 -- 'bound binary bytes or digest mismatch'
  exit 65
}
[[ "$(awk 'NR == 1 {print $1 "  " $2} NR > 1 {exit 1}' "$BINDING/binary.sha256")" == "$EXPECTED_BINARY_SHA256  bin/kio" ]] || {
  print -u2 -- 'binding binary digest sidecar mismatch'
  exit 65
}

for collision_target in "$FIXTURE" "$STAGES/M1" "$STAGES/M8"; do
  [[ ! -e "$collision_target" ]] || { print -u2 -- "evidence collision: $collision_target"; exit 65; }
done
mkdir -p "$FIXTURE" "$STAGES/M1" "$STAGES/M8"

fatal_stage() {
  local stage="$1" reason="$2" code="${3:-1}" dir="$STAGES/$1"
  local existing_terminal=''
  if [[ -f "$dir/result.json" ]]; then
    existing_terminal="$(jq -r '.terminal_status // "unreadable"' "$dir/result.json" 2>/dev/null || print -r -- 'unreadable')"
  fi
  if [[ ! -e "$dir/result.json" ]]; then
    jq -n --arg stage "$stage" --arg reason "$reason" --arg at "$(utc_now)" \
      --argjson exit_code "$code" \
      '{schema:"kio.phase4.stage-result.v1",stage:$stage,terminal_status:"failed",reason:$reason,ended_at:$at,exit_code:$exit_code}' > "$dir/result.json"
    existing_terminal='failed'
  elif [[ "$existing_terminal" != failed ]]; then
    if [[ ! -e "$dir/failure-receipt.json" ]]; then
      jq -n --arg stage "$stage" --arg reason "$reason" --arg at "$(utc_now)" \
        --arg observed_result_terminal_status "$existing_terminal" \
        --arg result_sha256 "$(sha256 "$dir/result.json")" --argjson exit_code "$code" \
        '{schema:"kio.phase4.stage-finalization-failure.v1",stage:$stage,status:"failed",reason:$reason,failed_at:$at,exit_code:$exit_code,observed_result_terminal_status:$observed_result_terminal_status,result_sha256:$result_sha256,completion_written:false}' > "$dir/failure-receipt.json"
    fi
    print -u2 -- "$stage failed after terminal result creation: $reason"
    exit "$code"
  fi
  if [[ ! -e "$dir/completion.json" ]]; then
    jq -n --arg stage "$stage" --arg reason "$reason" --arg at "$(utc_now)" \
      --arg result_sha256 "$(sha256 "$dir/result.json")" \
      '{schema:"kio.phase4.stage-completion.v1",stage:$stage,status:"failed",result_terminal_status:"failed",reason:$reason,completed_at:$at,artifact_sha256:{result:$result_sha256}}' > "$dir/completion.json"
  fi
  print -u2 -- "$stage failed: $reason"
  exit "$code"
}

ACTIVE_STAGE=''
unexpected_failure() {
  local code="$1"
  trap - ZERR
  if [[ -n "$ACTIVE_STAGE" && -d "$STAGES/$ACTIVE_STAGE" ]]; then
    fatal_stage "$ACTIVE_STAGE" 'unexpected_runner_error' "$code"
  fi
  print -u2 -- 'M1/M8 runner failed before a stage started'
  exit "$code"
}
trap 'unexpected_failure $?' ZERR

# A manifest is deterministic, covers directories and every regular file, and
# rejects symlinks, special files, and unsafe hardlinks rather than hiding them.
manifest() {
  local root="$1" output="$2" entry relative nlink
  [[ ! -e "$output" ]] || return 1
  [[ -d "$root" && ! -L "$root" ]] || return 1
  {
    print -r -- '{"schema":"kio.phase4.fixture-manifest.v1","entries":['
    local first=true
    while IFS= read -r -d '' entry; do
      if [[ "$first" == true ]]; then first=false; else print -n -- ','; fi
      relative="${entry#"$root"/}"
      if [[ -L "$entry" ]]; then
        return 1
      elif [[ -d "$entry" ]]; then
        jq -cn --arg path "$relative" --arg mode "$(stat -f '%Lp' "$entry")" \
          '{path:$path,kind:"directory",mode:$mode}'
      elif [[ -f "$entry" ]]; then
        nlink="$(stat -f '%l' "$entry")"
        [[ "$nlink" == 1 ]] || return 1
        jq -cn --arg path "$relative" --arg mode "$(stat -f '%Lp' "$entry")" \
          --arg sha "$(sha256 "$entry")" --argjson bytes "$(file_bytes "$entry")" \
          --argjson nlink "$nlink" \
          '{path:$path,kind:"regular",mode:$mode,bytes:$bytes,nlink:$nlink,sha256:$sha}'
      else
        return 1
      fi
    done < <(find "$root" -mindepth 1 -print0 | LC_ALL=C sort -z)
    print -r -- ']}'
  } > "$output"
}

manifest_diff() {
  local before="$1" after="$2" output="$3"
  [[ -f "$before" && -f "$after" && ! -e "$output" ]] || return 1
  jq -n --slurpfile before "$before" --slurpfile after "$after" '
    def path_map($manifest): reduce $manifest.entries[] as $entry ({}; .[$entry.path] = $entry);
    path_map($before[0]) as $left |
    path_map($after[0]) as $right |
    (($left | keys) + ($right | keys) | unique) as $paths |
    {schema:"kio.phase4.manifest-diff.v1",entries:[
      $paths[] as $path |
      select($left[$path] != $right[$path]) |
      {path:$path,before:($left[$path] // null),after:($right[$path] // null)}
    ]}' > "$output"
}

write_text_once() {
  local target_file="$1" text="$2"
  [[ ! -e "$target_file" ]] || return 1
  print -rn -- "$text" > "$target_file"
}

replace_fixture_text() {
  local target_file="$1" text="$2" temporary="${1}.phase4-replacement"
  [[ -f "$target_file" && ! -L "$target_file" && "$(stat -f '%l' "$target_file")" == 1 && ! -e "$temporary" ]] || return 1
  print -rn -- "$text" > "$temporary" || return 1
  /bin/mv -f "$temporary" "$target_file"
}

record_harness_text() {
  # record_harness_text STAGE LABEL PATH create|replace CONTRACT_REASON TEXT
  local stage="$1" label="$2" target_file="$3" operation="$4" reason="$5" text="$6"
  local dir="$STAGES/$stage/harness-$label" before="$STAGES/$stage/harness-$label/fixture-manifest.before.json"
  local after="$STAGES/$stage/harness-$label/fixture-manifest.after.json" diff="$STAGES/$stage/harness-$label/manifest-diff.json"
  local relative="${target_file#"$FIXTURE"/}"
  [[ "$target_file" == "$FIXTURE"/* && "$relative" != "$target_file" && ! -e "$dir" ]] || return 1
  mkdir -p "$dir"
  manifest "$FIXTURE" "$before" || return 70
  case "$operation" in
    create) write_text_once "$target_file" "$text" || return 1 ;;
    replace) replace_fixture_text "$target_file" "$text" || return 1 ;;
    *) return 1 ;;
  esac
  manifest "$FIXTURE" "$after" || return 70
  manifest_diff "$before" "$after" "$diff" || return 70
  jq -e --arg path "$relative" '.entries | length == 1 and .[0].path == $path' "$diff" >/dev/null || return 71
  jq -n --arg label "$label" --arg operation "$operation" --arg reason "$reason" \
    --arg path "$relative" --arg content_sha256 "$(sha256 "$target_file")" \
    --arg before_sha256 "$(sha256 "$before")" --arg after_sha256 "$(sha256 "$after")" \
    --slurpfile diff "$diff" \
    '{schema:"kio.phase4.harness-transition.v1",label:$label,operation:$operation,contract_reason:$reason,path:$path,content_sha256:$content_sha256,before_manifest_sha256:$before_sha256,after_manifest_sha256:$after_sha256,entries:[$diff[0].entries[] | . + {contract_reason:$reason}]}' > "$dir/receipt.json"
  jq -n --arg source "harness-$label" --arg reason "$reason" \
    --arg before "$(sha256 "$before")" --arg after "$(sha256 "$after")" \
    --slurpfile diff "$diff" \
    '{schema:"kio.phase4.observation-log-manifest.v1",source:$source,contract_reason:$reason,before_digest:$before,after_digest:$after,entries:[$diff[0].entries[] | . + {contract_reason:$reason}]}' > "$dir/observation-log-manifest.json"
}

make_scope() {
  local name="$1" scope private
  scope="$FIXTURE/$name"
  private="$FIXTURE/private-$name"
  [[ ! -e "$scope" && ! -e "$private" ]] || return 1
  mkdir -p "$scope" "$private/home" "$private/xdg-config" "$private/xdg-cache" "$private/xdg-data" "$private/tmp"
  jq -n --arg scope "$scope" --arg private "$private" \
    --arg home "$private/home" --arg config "$private/xdg-config" \
    --arg cache "$private/xdg-cache" --arg data "$private/xdg-data" --arg tmp "$private/tmp" \
    '{scope:$scope,private_root:$private,HOME:$home,XDG_CONFIG_HOME:$config,XDG_CACHE_HOME:$cache,XDG_DATA_HOME:$data,TMPDIR:$tmp}'
}

for scope_name in m1-m2 m8 m6-m7 m3 m4-m5; do
  make_scope "$scope_name" > "$FIXTURE/isolation-$scope_name.json" || {
    print -u2 -- "could not create isolated scope: $scope_name"; exit 65
  }
done
jq -s '{schema:"kio.phase4.isolation.v1",subscopes:.}' "$FIXTURE"/isolation-*.json > "$FIXTURE/isolation.json"
INITIAL_MANIFEST_TMP="$EVIDENCE_ROOT/.fixture-manifest.before.json"
manifest "$FIXTURE" "$INITIAL_MANIFEST_TMP" || {
  print -u2 -- 'could not record the initial complete fixture manifest'; exit 70
}
/bin/mv "$INITIAL_MANIFEST_TMP" "$FIXTURE/manifest.before.json"
print -r -- "$(sha256 "$FIXTURE/manifest.before.json")  manifest.before.json" > "$FIXTURE/digest.before.sha256"

record_command() {
  # record_command STAGE LABEL SCOPE PRIVATE none|kio_writer argv...
  local stage="$1" label="$2" scope="$3" private="$4" mutation_policy="$5"; shift 5
  local dir before after observation diff stdout stderr start end exit_code scope_prefix device_prefix mutation_valid=true
  dir="$STAGES/$stage/$label"
  before="$dir/fixture-manifest.before.json"
  after="$dir/fixture-manifest.after.json"
  observation="$dir/observation-log-manifest.json"
  diff="$dir/manifest-diff.json"
  stdout="$dir/stdout.bin"
  stderr="$dir/stderr.bin"
  [[ ! -e "$dir" ]] || return 1
  mkdir -p "$dir"
  manifest "$FIXTURE" "$before.fixture.json" || return 70
  manifest "$scope" "$before.scope.json" || return 70
  manifest "$private" "$before.private.json" || return 70
  jq -n --arg fixture "$(sha256 "$before.fixture.json")" \
    --arg scope "$(sha256 "$before.scope.json")" --arg private "$(sha256 "$before.private.json")" \
    '{fixture_manifest_sha256:$fixture,scope_manifest_sha256:$scope,private_manifest_sha256:$private}' > "$before"
  start="$(utc_now)"
  {
    print -r -- "cwd=$scope"
    print -r -- 'environment=/usr/bin/env -i'
    print -r -- "  HOME=$private/home"
    print -r -- "  XDG_CONFIG_HOME=$private/xdg-config"
    print -r -- "  XDG_CACHE_HOME=$private/xdg-cache"
    print -r -- "  XDG_DATA_HOME=$private/xdg-data"
    print -r -- "  TMPDIR=$private/tmp"
    print -r -- '  PATH=/usr/bin:/bin:/usr/sbin:/sbin'
    print -r -- '  LC_ALL=C; LANG=C; TZ=UTC'
    print -r -- '  KIO_FIXED_NOW=unset; KIO_TEST_*=unset; proxy/secret variables=unset'
    print -r -- "mutation_policy=$mutation_policy"
    print -r -- 'argv:'; printf '  %q\n' "$@"
  } > "$dir/command.txt"
  jq -cn --args '$ARGS.positional' -- "$@" > "$dir/argv.json"
  jq -n --arg cwd "$scope" --arg home "$private/home" \
    --arg xdg_config "$private/xdg-config" --arg xdg_cache "$private/xdg-cache" \
    --arg xdg_data "$private/xdg-data" --arg tmpdir "$private/tmp" --arg mutation_policy "$mutation_policy" \
    --slurpfile argv "$dir/argv.json" \
    '{cwd:$cwd,mutation_policy:$mutation_policy,environment:{clear_environment:true,HOME:$home,XDG_CONFIG_HOME:$xdg_config,XDG_CACHE_HOME:$xdg_cache,XDG_DATA_HOME:$xdg_data,TMPDIR:$tmpdir,PATH:"/usr/bin:/bin:/usr/sbin:/sbin",LC_ALL:"C",LANG:"C",TZ:"UTC",KIO_FIXED_NOW:"unset",test_fault_proxy_and_secret_variables:"unset_by_env_i"},argv:$argv[0]}' > "$dir/invocation-input.json"
  if (cd "$scope" && /usr/bin/env -i HOME="$private/home" XDG_CONFIG_HOME="$private/xdg-config" XDG_CACHE_HOME="$private/xdg-cache" XDG_DATA_HOME="$private/xdg-data" TMPDIR="$private/tmp" PATH='/usr/bin:/bin:/usr/sbin:/sbin' LC_ALL=C LANG=C TZ=UTC "$@") > "$stdout" 2> "$stderr"; then
    exit_code=0
  else
    exit_code=$?
  fi
  end="$(utc_now)"
  manifest "$FIXTURE" "$after.fixture.json" || return 70
  manifest "$scope" "$after.scope.json" || return 70
  manifest "$private" "$after.private.json" || return 70
  jq -n --arg fixture "$(sha256 "$after.fixture.json")" \
    --arg scope "$(sha256 "$after.scope.json")" --arg private "$(sha256 "$after.private.json")" \
    '{fixture_manifest_sha256:$fixture,scope_manifest_sha256:$scope,private_manifest_sha256:$private}' > "$after"
  manifest_diff "$before.fixture.json" "$after.fixture.json" "$diff" || return 70
  scope_prefix="${scope#"$FIXTURE"/}/.kio"
  device_prefix="${private#"$FIXTURE"/}/xdg-data/kio"
  case "$mutation_policy" in
    none)
      jq -e '.entries | length == 0' "$diff" >/dev/null || mutation_valid=false
      ;;
    kio_writer)
      jq -e --arg scope_prefix "$scope_prefix" --arg device_prefix "$device_prefix" '
        (.entries | length > 0) and
        (.entries | all(
          (.path == $scope_prefix or (.path | startswith($scope_prefix + "/"))) or
          (.path == $device_prefix or (.path | startswith($device_prefix + "/")))
        ))' "$diff" >/dev/null || mutation_valid=false
      ;;
    *) mutation_valid=false ;;
  esac
  jq -n --arg label "$label" --arg mutation_policy "$mutation_policy" \
    --arg scope_prefix "$scope_prefix" --arg device_prefix "$device_prefix" \
    --arg contract_reason "$(if [[ "$mutation_policy" == kio_writer ]]; then print -r -- 'public Kio writer may change only its scope .kio and isolated device-data kio roots'; else print -r -- 'read-only command permits no fixture or private-root change'; fi)" \
    --arg before "$(sha256 "$before")" --arg after "$(sha256 "$after")" \
    --slurpfile diff "$diff" \
    --argjson mutation_policy_valid "$mutation_valid" \
    '{schema:"kio.phase4.observation-log-manifest.v1",source:$label,mutation_policy:$mutation_policy,mutation_policy_valid:$mutation_policy_valid,contract_reason:$contract_reason,allowed_path_prefixes:(if $mutation_policy == "none" then [] else [$scope_prefix,$device_prefix] end),before_digest:$before,after_digest:$after,entries:[$diff[0].entries[] | . + {contract_reason:$contract_reason}]}' > "$observation"
  print -r -- "$(sha256 "$stdout")  stdout.bin" > "$dir/stdout.sha256"
  print -r -- "$(sha256 "$stderr")  stderr.bin" > "$dir/stderr.sha256"
  jq -n --arg start "$start" --arg end "$end" --argjson exit_code "$exit_code" --argjson mutation_policy_valid "$mutation_valid" \
    --arg stdout_sha256 "$(sha256 "$stdout")" --arg stderr_sha256 "$(sha256 "$stderr")" \
    --arg before_sha256 "$(sha256 "$before")" --arg after_sha256 "$(sha256 "$after")" \
    '{started_at:$start,ended_at:$end,exit_code:$exit_code,mutation_policy_valid:$mutation_policy_valid,stdout_sha256:$stdout_sha256,stderr_sha256:$stderr_sha256,before_manifest_sha256:$before_sha256,after_manifest_sha256:$after_sha256}' > "$dir/receipt.json"
  jq -n --slurpfile input "$dir/invocation-input.json" --slurpfile receipt "$dir/receipt.json" \
    '$input[0] + {receipt:$receipt[0]}' > "$dir/invocation.json"
  [[ "$mutation_valid" == true ]] || return 71
  return "$exit_code"
}

stage_command_manifest() {
  local stage="$1" output="$2"; shift 2
  local dir label first=true
  [[ ! -e "$output" ]] || return 1
  {
    print -r -- '{"schema":"kio.phase4.command-manifest.v1","commands":['
    for label in "$@"; do
      dir="$STAGES/$stage/$label"
      [[ -d "$dir" && -f "$dir/command.txt" && -f "$dir/receipt.json" && -f "$dir/invocation.json" ]] || return 1
      if [[ "$first" == true ]]; then first=false; else print -n -- ','; fi
      jq -cn --arg label "$label" \
        --arg command_sha256 "$(sha256 "$dir/command.txt")" \
        --arg receipt_sha256 "$(sha256 "$dir/receipt.json")" \
        --arg invocation_sha256 "$(sha256 "$dir/invocation.json")" \
        --arg stdout_sha256 "$(sha256 "$dir/stdout.bin")" --arg stderr_sha256 "$(sha256 "$dir/stderr.bin")" \
        --arg before_manifest_sha256 "$(sha256 "$dir/fixture-manifest.before.json")" \
        --arg after_manifest_sha256 "$(sha256 "$dir/fixture-manifest.after.json")" \
        --arg observation_log_manifest_sha256 "$(sha256 "$dir/observation-log-manifest.json")" \
        --rawfile command "$dir/command.txt" --slurpfile receipt "$dir/receipt.json" \
        --slurpfile invocation "$dir/invocation.json" \
        '{label:$label,invocation:$invocation[0],invocation_sha256:$invocation_sha256,command:$command,command_sha256:$command_sha256,receipt:$receipt[0],receipt_sha256:$receipt_sha256,stdout_sha256:$stdout_sha256,stderr_sha256:$stderr_sha256,fixture_manifest_before_sha256:$before_manifest_sha256,fixture_manifest_after_sha256:$after_manifest_sha256,observation_log_manifest_sha256:$observation_log_manifest_sha256}'
    done
    print -r -- ']}'
  } > "$output"
}

stage_manifest_summary() {
  local stage="$1" before_source="$2" after_source="$3" transition_reason="$4" dir="$STAGES/$1" source_label
  shift 4
  local -a observation_files=()
  [[ ! -e "$dir/fixture-manifest.before.json" && ! -e "$dir/fixture-manifest.after.json" && \
    ! -e "$dir/digest.before.sha256" && ! -e "$dir/digest.after.sha256" && \
    ! -e "$dir/observation-log-manifest.json" ]] || return 1
  cp "$before_source" "$dir/fixture-manifest.before.json"
  cp "$after_source" "$dir/fixture-manifest.after.json"
  print -r -- "$(sha256 "$dir/fixture-manifest.before.json")  fixture-manifest.before.json" > "$dir/digest.before.sha256"
  print -r -- "$(sha256 "$dir/fixture-manifest.after.json")  fixture-manifest.after.json" > "$dir/digest.after.sha256"
  for source_label in "$@"; do
    [[ -f "$dir/$source_label/observation-log-manifest.json" ]] || return 1
    observation_files+=("$dir/$source_label/observation-log-manifest.json")
  done
  (( ${#observation_files[@]} > 0 )) || return 1
  jq -s --arg before "$(sha256 "$dir/fixture-manifest.before.json")" \
    --arg after "$(sha256 "$dir/fixture-manifest.after.json")" \
    --arg reason "$transition_reason" \
    '{schema:"kio.phase4.stage-observation-log-manifest.v1",contract_reason:$reason,before_digest:$before,after_digest:$after,transitions:.,entries:[.[] as $observation | $observation.entries[] | . + {source:$observation.source}]}' \
    "${observation_files[@]}" > "$dir/observation-log-manifest.json"
}

stage_primary_invocation() {
  local stage="$1" label="$2" dir="$STAGES/$1" source="$STAGES/$1/$2"
  [[ -f "$source/command.txt" && -f "$source/stdout.bin" && -f "$source/stderr.bin" && \
    ! -e "$dir/command.txt" && ! -e "$dir/stdout.bin" && ! -e "$dir/stderr.bin" && \
    ! -e "$dir/stdout.sha256" && ! -e "$dir/stderr.sha256" ]] || return 1
  cp "$source/command.txt" "$dir/command.txt"
  cp "$source/stdout.bin" "$dir/stdout.bin"
  cp "$source/stderr.bin" "$dir/stderr.bin"
  print -r -- "$(sha256 "$dir/stdout.bin")  stdout.bin" > "$dir/stdout.sha256"
  print -r -- "$(sha256 "$dir/stderr.bin")  stderr.bin" > "$dir/stderr.sha256"
}

json_commit() { jq -er '.. | objects | .commit_hash? // empty | strings | select(test("^sha256:[0-9a-f]{64}$"))' "$1" | head -1; }
json_tree() { jq -er '.. | objects | .tree_hash? // empty | strings | select(test("^sha256:[0-9a-f]{64}$"))' "$1" | head -1; }

stage_start() {
  local stage="$1" predecessor="$2" mutation="$3"
  ACTIVE_STAGE="$stage"
  jq -n --arg stage "$stage" --arg predecessor "$predecessor" --arg mutation "$mutation" --arg at "$(utc_now)" \
    '{schema:"kio.phase4.stage-start.v1",stage:$stage,predecessors:(if $predecessor == "" then [] else [$predecessor] end),mutation_class:$mutation,status:"running",started_at:$at}' > "$STAGES/$stage/stage.json"
}

complete_stage() {
  local stage="$1" terminal_state="$2" reason="$3" assertion_file="$4"
  local dir="$STAGES/$stage" manifest_tmp="$EVIDENCE_ROOT/.${stage}-evidence-manifest.json"
  local completion_tmp="$EVIDENCE_ROOT/.${stage}-completion.json" result_terminal required
  for required in stage.json command.txt command-manifest.json stdout.bin stdout.sha256 stderr.bin stderr.sha256 fixture-manifest.before.json fixture-manifest.after.json digest.before.sha256 digest.after.sha256 observation-log-manifest.json result.json assertions.json; do
    [[ -f "$dir/$required" && ! -L "$dir/$required" ]] || return 1
  done
  result_terminal="$(jq -er '.terminal_status' "$dir/result.json")" || return 1
  [[ "$result_terminal" == "$terminal_state" ]] || return 1
  if [[ "$terminal_state" == passed ]]; then
    jq -e '[.. | booleans] | all' "$assertion_file" >/dev/null || return 1
  fi
  [[ ! -e "$manifest_tmp" && ! -e "$completion_tmp" && ! -e "$dir/evidence-manifest.json" && ! -e "$dir/completion.json" ]] || return 1
  manifest "$dir" "$manifest_tmp" || return 1
  /bin/mv "$manifest_tmp" "$dir/evidence-manifest.json"
  jq -n --arg stage "$stage" --arg status "$terminal_state" --arg result_terminal "$result_terminal" \
    --arg reason "$reason" --arg at "$(utc_now)" \
    --arg stage_sha256 "$(sha256 "$dir/stage.json")" --arg result_sha256 "$(sha256 "$dir/result.json")" \
    --arg assertions_sha256 "$(sha256 "$assertion_file")" \
    --arg command_sha256 "$(sha256 "$dir/command.txt")" --arg command_manifest_sha256 "$(sha256 "$dir/command-manifest.json")" \
    --arg stdout_sha256 "$(sha256 "$dir/stdout.bin")" --arg stderr_sha256 "$(sha256 "$dir/stderr.bin")" \
    --arg fixture_before_sha256 "$(sha256 "$dir/fixture-manifest.before.json")" \
    --arg fixture_after_sha256 "$(sha256 "$dir/fixture-manifest.after.json")" \
    --arg digest_before_sha256 "$(sha256 "$dir/digest.before.sha256")" \
    --arg digest_after_sha256 "$(sha256 "$dir/digest.after.sha256")" \
    --arg observation_sha256 "$(sha256 "$dir/observation-log-manifest.json")" \
    --arg evidence_manifest_sha256 "$(sha256 "$dir/evidence-manifest.json")" \
    --slurpfile assertions "$assertion_file" --slurpfile commands "$dir/command-manifest.json" \
    '{schema:"kio.phase4.stage-completion.v1",stage:$stage,status:$status,result_terminal_status:$result_terminal,reason:$reason,completed_at:$at,assertions:$assertions[0],artifact_sha256:{stage:$stage_sha256,result:$result_sha256,assertions:$assertions_sha256,command:$command_sha256,command_manifest:$command_manifest_sha256,stdout:$stdout_sha256,stderr:$stderr_sha256,fixture_manifest_before:$fixture_before_sha256,fixture_manifest_after:$fixture_after_sha256,digest_before:$digest_before_sha256,digest_after:$digest_after_sha256,observation_log_manifest:$observation_sha256,evidence_manifest:$evidence_manifest_sha256},command_artifacts:($commands[0].commands | map({label,invocation_sha256,command_sha256,receipt_sha256,stdout_sha256,stderr_sha256,fixture_manifest_before_sha256,fixture_manifest_after_sha256,observation_log_manifest_sha256}))}' > "$completion_tmp"
  /bin/mv "$completion_tmp" "$dir/completion.json"
  ACTIVE_STAGE=''
}

run_m1() {
  local stage=M1 scope private doc
  scope="$FIXTURE/m1-m2"
  private="$FIXTURE/private-m1-m2"
  doc="$scope/document.md"
  local old=$'## Retention fixture\nold byte sequence\n' current=$'## Retention fixture\ncurrent byte sequence\n'
  local old_commit old_tree current_commit current_tree plan1="$STAGES/$stage/gc-1/stdout.bin" plan2="$STAGES/$stage/gc-2/stdout.bin"
  stage_start "$stage" '' 'fixture writes through index; dry-run thereafter'
  record_command "$stage" init "$scope" "$private" kio_writer "$PRODUCT_BINARY" init --json || fatal_stage "$stage" 'init_failed_or_unlisted_mutation'
  record_harness_text "$stage" config "$scope/.kio/config.toml" replace 'install exact manual-only all-zero retention config' "$MANUAL_CONFIG" || fatal_stage "$stage" 'config_replace_failed_or_unlisted_mutation'
  [[ "$(sha256 "$scope/.kio/config.toml")" == "$EXPECTED_MANUAL_CONFIG_SHA256" ]] || fatal_stage "$stage" 'config_exact_bytes_mismatch'
  print -r -- "$(sha256 "$scope/.kio/config.toml")  .kio/config.toml" > "$STAGES/$stage/config.sha256"
  record_harness_text "$stage" document-old "$doc" create 'old fixture document bytes' "$old" || fatal_stage "$stage" 'old_document_collision_or_unlisted_mutation'
  print -r -- "$(sha256 "$doc")  document.md" > "$STAGES/$stage/document.old.sha256"
  record_command "$stage" index-old "$scope" "$private" kio_writer "$PRODUCT_BINARY" index --offline --approve --json || fatal_stage "$stage" 'old_index_failed_or_unlisted_mutation'
  old_commit="$(json_commit "$STAGES/$stage/index-old/stdout.bin")" || fatal_stage "$stage" 'old_index_commit_missing'
  old_tree="$(json_tree "$STAGES/$stage/index-old/stdout.bin")" || fatal_stage "$stage" 'old_index_tree_missing'
  record_harness_text "$stage" document-current "$doc" replace 'current fixture document bytes with a distinct tree' "$current" || fatal_stage "$stage" 'current_document_replace_failed_or_unlisted_mutation'
  print -r -- "$(sha256 "$doc")  document.md" > "$STAGES/$stage/document.current.sha256"
  record_command "$stage" index-current "$scope" "$private" kio_writer "$PRODUCT_BINARY" index --offline --approve --json || fatal_stage "$stage" 'current_index_failed_or_unlisted_mutation'
  current_commit="$(json_commit "$STAGES/$stage/index-current/stdout.bin")" || fatal_stage "$stage" 'current_index_commit_missing'
  current_tree="$(json_tree "$STAGES/$stage/index-current/stdout.bin")" || fatal_stage "$stage" 'current_index_tree_missing'
  [[ "$old_commit" != "$current_commit" && "$old_tree" != "$current_tree" ]] || fatal_stage "$stage" 'index_transition_not_distinct'
  record_command "$stage" gc-1 "$scope" "$private" none "$PRODUCT_BINARY" gc --dry-run --json || fatal_stage "$stage" 'dry_run_1_failed_or_mutated'
  record_command "$stage" gc-2 "$scope" "$private" none "$PRODUCT_BINARY" gc --dry-run --json || fatal_stage "$stage" 'dry_run_2_failed_or_mutated'
  jq -e --arg oc "$old_commit" --arg ot "$old_tree" --arg cc "$current_commit" --arg scope "$scope" '
    (keys == ["as_of","baseline_receipts_digest","candidate_count","candidate_tree_count","candidates","estimated_bytes","exclusions","limits","object_kinds_planned","plan_digest","policy","scope_path","stability_check_stats","stable_truth_digest","stats","status","truth_digest"]) and
    .status == "dry_run" and (.as_of | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")) and .scope_path == $scope and .candidate_count == 1 and .candidate_tree_count == 1 and .object_kinds_planned == ["tree"] and
    (.limits | keys == ["max_commits","max_depth","max_dir_entries","max_graph_steps","max_name_bytes","max_receipts","max_refs","max_tree_entries","max_verified_bytes"]) and
    (.stats | keys == ["commits","dir_entries","graph_steps","receipts","refs","tree_entries","trees_verified","verified_bytes"]) and .stats == .stability_check_stats and
    (.policy | keys == ["keep_daily_weeks","keep_hourly_days","keep_last_hours","keep_repaired_per_branch","keep_weekly_months"]) and
    .policy.keep_last_hours == 0 and .policy.keep_hourly_days == 0 and .policy.keep_daily_weeks == 0 and .policy.keep_weekly_months == 0 and .policy.keep_repaired_per_branch == 5 and
    (.exclusions | all(keys == ["count","reason"] and (.count | type == "number" and . >= 0) and (.reason | type == "string"))) and
    (.candidates | length == 1) and (.candidates[0] | keys == ["commit_hash","commit_type","created_at","policy","size_bytes","tree_hash"] and .commit_hash == $oc and .commit_hash != $cc and .tree_hash == $ot and .commit_type == "auto" and .policy == "auto_retention" and (.created_at | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?Z$")) and (.size_bytes | type == "number" and . > 0)) and
    .estimated_bytes == .candidates[0].size_bytes and
    ([.truth_digest,.stable_truth_digest,.baseline_receipts_digest,.plan_digest] | all(type == "string" and test("^sha256:[0-9a-f]{64}$"))) and
    ([.exclusions[]? | select(.reason == "ref_tip" and .count >= 1)] | length == 1)' "$plan1" >/dev/null || fatal_stage "$stage" 'dry_run_1_predicate_failed'
  jq -e --argfile first "$plan1" '
    (.as_of | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")) and
    (del(.as_of) == ($first | del(.as_of))) and
    ([.truth_digest,.stable_truth_digest,.baseline_receipts_digest,.plan_digest] | all(type == "string" and test("^sha256:[0-9a-f]{64}$")))' "$plan2" >/dev/null || fatal_stage "$stage" 'dry_run_stability_failed'
  [[ "$(sha256 "$STAGES/$stage/gc-1/fixture-manifest.before.json")" == "$(sha256 "$STAGES/$stage/gc-1/fixture-manifest.after.json")" && "$(sha256 "$STAGES/$stage/gc-2/fixture-manifest.before.json")" == "$(sha256 "$STAGES/$stage/gc-2/fixture-manifest.after.json")" ]] || fatal_stage "$stage" 'dry_run_mutated_protected_manifest'
  [[ "$(sha256 "$STAGES/$stage/gc-1/fixture-manifest.after.json")" == "$(sha256 "$STAGES/$stage/gc-2/fixture-manifest.before.json")" ]] || fatal_stage "$stage" 'dry_run_cross_invocation_state_changed'
  manifest "$scope" "$STAGES/$stage/frozen-scope-manifest.json"
  manifest "$private" "$STAGES/$stage/frozen-private-manifest.json"
  jq -n --arg scope_sha256 "$(sha256 "$STAGES/$stage/frozen-scope-manifest.json")" \
    --arg private_sha256 "$(sha256 "$STAGES/$stage/frozen-private-manifest.json")" \
    '{schema:"kio.phase4.frozen-fixture.v1",scope_manifest_sha256:$scope_sha256,private_manifest_sha256:$private_sha256}' > "$STAGES/$stage/frozen-fixture-manifest.json"
  print -r -- "$(sha256 "$STAGES/$stage/frozen-fixture-manifest.json")  frozen-fixture-manifest.json" > "$STAGES/$stage/frozen-fixture.sha256"
  jq -n --arg old_commit "$old_commit" --arg old_tree "$old_tree" --arg current_commit "$current_commit" --arg current_tree "$current_tree" \
    --arg binary_sha256 "$EXPECTED_BINARY_SHA256" \
    --arg config_sha256 "$(sha256 "$scope/.kio/config.toml")" \
    --arg old_document_sha256 "$(awk '{print $1}' "$STAGES/$stage/document.old.sha256")" \
    --arg current_document_sha256 "$(awk '{print $1}' "$STAGES/$stage/document.current.sha256")" \
    --arg plan_1_sha256 "$(sha256 "$plan1")" --arg plan_2_sha256 "$(sha256 "$plan2")" \
    --arg frozen_fixture_sha256 "$(sha256 "$STAGES/$stage/frozen-fixture-manifest.json")" \
    --slurpfile run "$EVIDENCE_ROOT/run.json" \
    '{fixed_binding:$run[0].expected_binding,downloaded_binary_sha256:$binary_sha256,config_sha256:$config_sha256,documents:{old_sha256:$old_document_sha256,current_sha256:$current_document_sha256},old:{commit:$old_commit,tree:$old_tree},current:{commit:$current_commit,tree:$current_tree},plans:{first_sha256:$plan_1_sha256,second_sha256:$plan_2_sha256},predicates:{real_candidate:true,tip_excluded:true,tree_only:true,internal_stability:true,semantic_repeat_stability:true,dry_run_1_no_write:true,dry_run_2_no_write:true,dry_run_cross_invocation_state_unchanged:true},frozen_fixture_sha256:$frozen_fixture_sha256}' > "$STAGES/$stage/assertions.json"
  stage_command_manifest "$stage" "$STAGES/$stage/command-manifest.json" init index-old index-current gc-1 gc-2 || fatal_stage "$stage" 'command_manifest_failed'
  stage_primary_invocation "$stage" gc-2 || fatal_stage "$stage" 'primary_invocation_receipt_failed'
  stage_manifest_summary "$stage" "$STAGES/$stage/init/fixture-manifest.before.json" "$STAGES/$stage/gc-2/fixture-manifest.after.json" 'public init and two index transitions; two final dry-runs read-only' init harness-config harness-document-old index-old harness-document-current index-current gc-1 gc-2 || fatal_stage "$stage" 'stage_manifest_summary_failed'
  jq -n --arg stage "$stage" --arg before "$(sha256 "$STAGES/$stage/init/fixture-manifest.before.json")" --arg after "$(sha256 "$STAGES/$stage/gc-2/fixture-manifest.after.json")" \
    --slurpfile assertions "$STAGES/$stage/assertions.json" --slurpfile commands "$STAGES/$stage/command-manifest.json" \
    --slurpfile observations "$STAGES/$stage/observation-log-manifest.json" \
    '{schema:"kio.phase4.stage-result.v1",stage:$stage,terminal_status:"passed",primary_invocation:"gc-2",stop_rule:"continue_to_M8",fixture_manifest_before_sha256:$before,fixture_manifest_after_sha256:$after,commands:$commands[0].commands,observations:$observations[0],predicates:$assertions[0]}' > "$STAGES/$stage/result.json"
  complete_stage "$stage" passed 'retention_dry_run_verified' "$STAGES/$stage/assertions.json"
}

run_m8() {
  local stage=M8 scope private doc
  scope="$FIXTURE/m8"
  private="$FIXTURE/private-m8"
  doc="$scope/document.md"
  local old=$'## Unreachable inventory fixture\nold byte sequence\n' current=$'## Unreachable inventory fixture\ncurrent byte sequence\n'
  local old_commit old_tree current_commit current_tree
  local retention_plan="$STAGES/$stage/retention-plan/stdout.bin"
  local inventory1="$STAGES/$stage/inventory-1/stdout.bin" inventory2="$STAGES/$stage/inventory-2/stdout.bin"
  stage_start "$stage" M1 'fixture writes through index; diagnostic dry-run thereafter'
  record_command "$stage" init "$scope" "$private" kio_writer "$PRODUCT_BINARY" init --json || fatal_stage "$stage" 'init_failed_or_unlisted_mutation'
  record_harness_text "$stage" config "$scope/.kio/config.toml" replace 'install exact manual-only all-zero retention config' "$MANUAL_CONFIG" || fatal_stage "$stage" 'config_replace_failed_or_unlisted_mutation'
  [[ "$(sha256 "$scope/.kio/config.toml")" == "$EXPECTED_MANUAL_CONFIG_SHA256" ]] || fatal_stage "$stage" 'config_exact_bytes_mismatch'
  print -r -- "$(sha256 "$scope/.kio/config.toml")  .kio/config.toml" > "$STAGES/$stage/config.sha256"
  record_harness_text "$stage" document-old "$doc" create 'old fixture document bytes' "$old" || fatal_stage "$stage" 'old_document_collision_or_unlisted_mutation'
  print -r -- "$(sha256 "$doc")  document.md" > "$STAGES/$stage/document.old.sha256"
  record_command "$stage" index-old "$scope" "$private" kio_writer "$PRODUCT_BINARY" index --offline --approve --json || fatal_stage "$stage" 'old_index_failed_or_unlisted_mutation'
  old_commit="$(json_commit "$STAGES/$stage/index-old/stdout.bin")" || fatal_stage "$stage" 'old_index_commit_missing'
  old_tree="$(json_tree "$STAGES/$stage/index-old/stdout.bin")" || fatal_stage "$stage" 'old_index_tree_missing'
  record_harness_text "$stage" document-current "$doc" replace 'current fixture document bytes with a distinct tree' "$current" || fatal_stage "$stage" 'current_document_replace_failed_or_unlisted_mutation'
  print -r -- "$(sha256 "$doc")  document.md" > "$STAGES/$stage/document.current.sha256"
  record_command "$stage" index-current "$scope" "$private" kio_writer "$PRODUCT_BINARY" index --offline --approve --json || fatal_stage "$stage" 'current_index_failed_or_unlisted_mutation'
  current_commit="$(json_commit "$STAGES/$stage/index-current/stdout.bin")" || fatal_stage "$stage" 'current_index_commit_missing'
  current_tree="$(json_tree "$STAGES/$stage/index-current/stdout.bin")" || fatal_stage "$stage" 'current_index_tree_missing'
  [[ "$old_commit" != "$current_commit" && "$old_tree" != "$current_tree" ]] || fatal_stage "$stage" 'index_transition_not_distinct'
  record_command "$stage" retention-plan "$scope" "$private" none "$PRODUCT_BINARY" gc --dry-run --json || fatal_stage "$stage" 'retention_plan_failed_or_mutated'
  jq -e --arg oc "$old_commit" --arg ot "$old_tree" --arg cc "$current_commit" --arg scope "$scope" '
    (keys == ["as_of","baseline_receipts_digest","candidate_count","candidate_tree_count","candidates","estimated_bytes","exclusions","limits","object_kinds_planned","plan_digest","policy","scope_path","stability_check_stats","stable_truth_digest","stats","status","truth_digest"]) and
    .status == "dry_run" and (.as_of | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")) and .scope_path == $scope and .candidate_count == 1 and .candidate_tree_count == 1 and .object_kinds_planned == ["tree"] and
    (.limits | keys == ["max_commits","max_depth","max_dir_entries","max_graph_steps","max_name_bytes","max_receipts","max_refs","max_tree_entries","max_verified_bytes"]) and
    (.stats | keys == ["commits","dir_entries","graph_steps","receipts","refs","tree_entries","trees_verified","verified_bytes"]) and .stats == .stability_check_stats and
    (.policy | keys == ["keep_daily_weeks","keep_hourly_days","keep_last_hours","keep_repaired_per_branch","keep_weekly_months"]) and
    .policy.keep_last_hours == 0 and .policy.keep_hourly_days == 0 and .policy.keep_daily_weeks == 0 and .policy.keep_weekly_months == 0 and .policy.keep_repaired_per_branch == 5 and
    (.exclusions | all(keys == ["count","reason"] and (.count | type == "number" and . >= 0) and (.reason | type == "string"))) and
    (.candidates | length == 1) and (.candidates[0] | keys == ["commit_hash","commit_type","created_at","policy","size_bytes","tree_hash"] and .commit_hash == $oc and .commit_hash != $cc and .tree_hash == $ot and .commit_type == "auto" and .policy == "auto_retention" and (.created_at | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?Z$")) and (.size_bytes | type == "number" and . > 0)) and
    .estimated_bytes == .candidates[0].size_bytes and
    ([.truth_digest,.stable_truth_digest,.baseline_receipts_digest,.plan_digest] | all(type == "string" and test("^sha256:[0-9a-f]{64}$"))) and
    ([.exclusions[]? | select(.reason == "ref_tip" and .count >= 1)] | length == 1)' "$retention_plan" >/dev/null || fatal_stage "$stage" 'retention_plan_predicate_failed'
  [[ "$(sha256 "$STAGES/$stage/retention-plan/fixture-manifest.before.json")" == "$(sha256 "$STAGES/$stage/retention-plan/fixture-manifest.after.json")" ]] || fatal_stage "$stage" 'retention_plan_mutated_protected_manifest'
  record_command "$stage" inventory-1 "$scope" "$private" none "$PRODUCT_BINARY" gc --dry-run --prune-unreachable --json || fatal_stage "$stage" 'inventory_1_failed_or_mutated'
  record_command "$stage" inventory-2 "$scope" "$private" none "$PRODUCT_BINARY" gc --dry-run --prune-unreachable --json || fatal_stage "$stage" 'inventory_2_failed_or_mutated'
  jq -e --arg old_tree "$old_tree" '
    . as $report |
    (keys == ["diagnostic_only","limits","mutation_authority","objects","operation","read_only","schema_version","shallow_boundaries","stats","status","summary"]) and
    .schema_version == 1 and .operation == "unreachable_object_inventory" and .status == "dry_run" and .read_only == true and .diagnostic_only == true and .mutation_authority == false and
    (.summary | keys == ["candidate_bytes","candidate_count","inventory_only_bytes","inventory_only_count","object_count","physical_bytes","protected_bytes","protected_count"] and
      .candidate_count == 0 and .candidate_bytes == 0 and
      .object_count == ($report.objects | length) and
      .physical_bytes == ([$report.objects[].physical_bytes] | add // 0) and
      .protected_count == ([$report.objects[] | select(.classification == "protected")] | length) and
      .protected_bytes == ([$report.objects[] | select(.classification == "protected") | .physical_bytes] | add // 0) and
      .inventory_only_count == ([$report.objects[] | select(.classification == "inventory_only")] | length) and
      .inventory_only_bytes == ([$report.objects[] | select(.classification == "inventory_only") | .physical_bytes] | add // 0) and
      .object_count == (.candidate_count + .protected_count + .inventory_only_count) and
      .physical_bytes == (.candidate_bytes + .protected_bytes + .inventory_only_bytes)) and
    (.objects | all(keys == ["classification","hash","kind","physical_bytes","reason"] and
      (.kind == "raw" or .kind == "commit" or .kind == "tree" or .kind == "chunk" or
       .kind == "manifest" or .kind == "normalized_unit" or .kind == "embedding" or
       .kind == "toollock" or .kind == "prepared" or .kind == "image") and
      (.hash | test("^sha256:[0-9a-f]{64}$")) and
      (.physical_bytes | type == "number" and . >= 0) and
      (.classification == "candidate" or .classification == "protected" or .classification == "inventory_only") and
      (.reason | type == "string" and length > 0))) and
    (.objects == (.objects | sort_by(.kind, .hash))) and ([.objects[] | [.kind,.hash]] | unique | length == length) and
    (.limits | keys == ["max_depth","max_directory_entries","max_history_steps","max_manifest_units","max_name_bytes","max_objects","max_physical_bytes","max_receipts","max_refs","max_verified_bytes"] and all(type == "number" and . > 0)) and
    (.stats | keys == ["inventory_pass","stability_pass"] and .inventory_pass == .stability_pass and
      (.inventory_pass | keys == ["directory_entries","history_steps","manifest_units","objects","physical_bytes","receipts","refs","verified_bytes"])) and
    (.shallow_boundaries | type == "array" and all(keys == ["commit_hash","tree_hash"] and
      (.commit_hash | test("^sha256:[0-9a-f]{64}$")) and (.tree_hash | test("^sha256:[0-9a-f]{64}$")))) and
    ([.objects[] | select(.hash == $old_tree and .kind == "tree" and .classification == "protected" and .reason == "retention_gc_owned")] | length == 1)' "$inventory1" >/dev/null || fatal_stage "$stage" 'inventory_1_predicate_failed'
  cmp -s "$inventory1" "$inventory2" || fatal_stage "$stage" 'inventory_output_not_byte_identical'
  [[ "$(sha256 "$STAGES/$stage/inventory-1/fixture-manifest.before.json")" == "$(sha256 "$STAGES/$stage/inventory-1/fixture-manifest.after.json")" && "$(sha256 "$STAGES/$stage/inventory-2/fixture-manifest.before.json")" == "$(sha256 "$STAGES/$stage/inventory-2/fixture-manifest.after.json")" ]] || fatal_stage "$stage" 'inventory_mutated_protected_manifest'
  [[ "$(sha256 "$STAGES/$stage/retention-plan/fixture-manifest.after.json")" == "$(sha256 "$STAGES/$stage/inventory-1/fixture-manifest.before.json")" && "$(sha256 "$STAGES/$stage/inventory-1/fixture-manifest.after.json")" == "$(sha256 "$STAGES/$stage/inventory-2/fixture-manifest.before.json")" ]] || fatal_stage "$stage" 'inventory_cross_invocation_state_changed'
  jq -n --arg old_commit "$old_commit" --arg old_tree "$old_tree" \
    --arg current_commit "$current_commit" --arg current_tree "$current_tree" \
    --arg retention_plan_sha256 "$(sha256 "$retention_plan")" --arg output_sha256 "$(sha256 "$inventory1")" \
    --arg binary_sha256 "$EXPECTED_BINARY_SHA256" --arg config_sha256 "$(sha256 "$scope/.kio/config.toml")" \
    --arg old_document_sha256 "$(awk '{print $1}' "$STAGES/$stage/document.old.sha256")" \
    --arg current_document_sha256 "$(awk '{print $1}' "$STAGES/$stage/document.current.sha256")" \
    --slurpfile run "$EVIDENCE_ROOT/run.json" \
    '{fixed_binding:$run[0].expected_binding,downloaded_binary_sha256:$binary_sha256,config_sha256:$config_sha256,documents:{old_sha256:$old_document_sha256,current_sha256:$current_document_sha256},old:{commit:$old_commit,tree:$old_tree},current:{commit:$current_commit,tree:$current_tree},retention_plan:{sha256:$retention_plan_sha256,real_candidate:true,no_write:true},candidate_count:0,old_tree_classification:"protected",old_tree_reason:"retention_gc_owned",predicates:{exact_schema:true,exact_summary:true,independent_pass_stats_match:true,objects_sorted_unique:true,outputs_byte_identical:true,retention_plan_no_write:true,inventory_1_no_write:true,inventory_2_no_write:true,inventory_cross_invocation_state_unchanged:true,public_cli_real_unreachable_candidate_exercised:false},output_sha256:$output_sha256}' > "$STAGES/$stage/assertions.json"
  stage_command_manifest "$stage" "$STAGES/$stage/command-manifest.json" init index-old index-current retention-plan inventory-1 inventory-2 || fatal_stage "$stage" 'command_manifest_failed'
  stage_primary_invocation "$stage" inventory-2 || fatal_stage "$stage" 'primary_invocation_receipt_failed'
  stage_manifest_summary "$stage" "$STAGES/$stage/init/fixture-manifest.before.json" "$STAGES/$stage/inventory-2/fixture-manifest.after.json" 'public init and two index transitions; retention plan and two inventories read-only' init harness-config harness-document-old index-old harness-document-current index-current retention-plan inventory-1 inventory-2 || fatal_stage "$stage" 'stage_manifest_summary_failed'
  jq -n --arg stage "$stage" --arg before "$(sha256 "$STAGES/$stage/init/fixture-manifest.before.json")" --arg after "$(sha256 "$STAGES/$stage/inventory-2/fixture-manifest.after.json")" \
    --slurpfile assertions "$STAGES/$stage/assertions.json" --slurpfile commands "$STAGES/$stage/command-manifest.json" \
    --slurpfile observations "$STAGES/$stage/observation-log-manifest.json" \
    '{schema:"kio.phase4.stage-result.v1",stage:$stage,terminal_status:"blocked",reason:"public_cli_unreachable_candidate_unconstructable",primary_invocation:"inventory-2",stop_rule:"known_coverage_blocker_continue_independent_stages",fixture_manifest_before_sha256:$before,fixture_manifest_after_sha256:$after,commands:$commands[0].commands,observations:$observations[0],predicates:$assertions[0]}' > "$STAGES/$stage/result.json"
  complete_stage "$stage" blocked 'public_cli_unreachable_candidate_unconstructable' "$STAGES/$stage/assertions.json"
}

run_m1
run_m8
print -- "M1 passed; M8 blocked only at the public-CLI unreachable-candidate coverage boundary"
