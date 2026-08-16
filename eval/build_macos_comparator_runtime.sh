#!/bin/zsh
# One-shot administrator boundary for the sealed comparator runtime.
# Rust owns every content/security decision; this script only makes and mounts
# the image, then invokes the two Rust construction phases.
set -euo pipefail

readonly KIO_EVAL=/usr/local/bin/kio-eval
readonly MANAGED_ROOT=/Library/KioComparatorRuntime
readonly RUNTIME_ROOT=/Library/KioComparatorRuntime/v1
readonly IMAGE=/Library/KioComparatorRuntime/v1.dmg
readonly MANIFEST=/Library/KioComparatorRuntime/v1.manifest.json
readonly BUILD_ROOT=/private/tmp/kio-comparator-runtime-v1-build
readonly VOLUME_NAME=KioComparatorRuntime-v1

die() { print -u2 -- "error: $*"; exit 1; }
[[ ${EUID} -eq 0 ]] || die "administrator execution required; run explicitly with sudo"
[[ $(/usr/bin/uname -s) == Darwin ]] || die "macOS only"
[[ -x $KIO_EVAL && ! -L $KIO_EVAL ]] || die "missing root-installed kio-eval at $KIO_EVAL"
kio_eval_stat=$(/usr/bin/stat -f '%u:%p' "$KIO_EVAL")
[[ $kio_eval_stat == 0:* ]] || die "kio-eval must be root-owned"
[[ $(( 8#${kio_eval_stat##*:} & 8#022 )) -eq 0 ]] || die "kio-eval must not be group/other writable"
for target in "$MANAGED_ROOT" "$RUNTIME_ROOT" "$IMAGE" "$MANIFEST" "$BUILD_ROOT"; do
  [[ ! -e $target && ! -L $target ]] || die "create-only target already exists: $target"
done

made_root=0 made_mount=0 made_build=0 made_image=0 mounted=0
rollback() {
  local status=$?
  if (( status )); then
    (( mounted )) && /usr/bin/hdiutil detach "$RUNTIME_ROOT" >/dev/null 2>&1 || true
    (( made_image )) && /bin/rm -f "$IMAGE"
    (( made_build )) && /bin/rm -rf "$BUILD_ROOT"
    (( made_mount )) && /bin/rmdir "$RUNTIME_ROOT" 2>/dev/null || true
    (( made_root )) && /bin/rmdir "$MANAGED_ROOT" 2>/dev/null || true
  fi
  exit $status
}
trap rollback EXIT

/bin/mkdir -m 0755 "$MANAGED_ROOT"; made_root=1
/bin/mkdir -m 0755 "$RUNTIME_ROOT"; made_mount=1
made_build=1
"$KIO_EVAL" benchmark comparator-runtime prepare --build-root "$BUILD_ROOT"
/usr/bin/hdiutil create -srcfolder "$BUILD_ROOT/payload" -format UDRO -fs "Case-sensitive APFS" -volname "$VOLUME_NAME" -srcowners on -noanyowners "$IMAGE"; made_image=1
/bin/chmod 0444 "$IMAGE"
/usr/bin/hdiutil attach -readonly -owners on -nobrowse -noautoopen -mountpoint "$RUNTIME_ROOT" "$IMAGE" >/dev/null; mounted=1
"$KIO_EVAL" benchmark comparator-runtime finalize --runtime-root "$RUNTIME_ROOT" --preimage "$BUILD_ROOT/manifest-preimage.json" --image "$IMAGE" --out "$MANIFEST"
/bin/chmod 0444 "$MANIFEST"
/bin/rm -rf "$BUILD_ROOT"
trap - EXIT
print -- "sealed comparator runtime ready: $RUNTIME_ROOT"
print -- "image: $IMAGE"
print -- "manifest: $MANIFEST"
