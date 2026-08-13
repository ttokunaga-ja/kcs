#!/bin/zsh
# Auditable, one-shot builder for the sealed macOS baseline comparator runtime.
# It never invokes sudo: an administrator must explicitly run this file with sudo.
set -euo pipefail
cd /
readonly MANAGED_ROOT=/Library/KioComparatorRuntime RUNTIME_ROOT=/Library/KioComparatorRuntime/v1
readonly IMAGE=/Library/KioComparatorRuntime/v1.dmg MANIFEST=/Library/KioComparatorRuntime/v1.manifest.json
readonly BUILD_ROOT=/private/tmp/kio-comparator-runtime-v1-build VOLUME_NAME=KioComparatorRuntime-v1
readonly ADMIN_SCRIPT_PREFIX=/private/tmp/kio-comparator-runtime-v1-admin.
die() { print -u2 -- "error: $*"; exit 1; }
require_safe_xattrs() {
  local target_path=$1 names
  names=$(/usr/bin/xattr "$target_path") || die "cannot enumerate extended attributes: $target_path"
  [[ -z $names || $names == com.apple.provenance ]] || die "unexpected extended attributes: $target_path: ${names//$'\n'/,}"
}
require_safe_image_xattrs() {
  local target_path=$1 names
  names=$(/usr/bin/xattr "$target_path") || die "cannot enumerate disk image extended attributes: $target_path"
  case $names in
    ''|com.apple.FinderInfo|com.apple.provenance|$'com.apple.FinderInfo\ncom.apple.provenance'|$'com.apple.provenance\ncom.apple.FinderInfo') ;;
    *) die "unexpected disk image extended attributes: $target_path: ${names//$'\n'/,}" ;;
  esac
}
normalize_attached_image_xattrs() {
  local target_path=$1 names name
  names=$(/usr/bin/xattr "$target_path") || die "cannot enumerate attached disk image extended attributes: $target_path"
  for name in ${(f)names}; do
    case $name in
      com.apple.FinderInfo|com.apple.provenance|com.apple.diskimages.recentcksum) ;;
      *) die "unexpected attached disk image extended attribute: $target_path: $name" ;;
    esac
  done
  if print -r -- "$names" | /usr/bin/grep -Fxq com.apple.diskimages.recentcksum; then
    /usr/bin/xattr -d com.apple.diskimages.recentcksum "$target_path" || die "cannot remove disk image checksum cache: $target_path"
  fi
  require_safe_image_xattrs "$target_path"
}
mode=${1:-build}
[[ $mode == build || $mode == verify ]] || die "usage: $0 [build|verify]"
if [[ $mode == verify ]]; then
  [[ ${EUID} -ne 0 ]] || die "verify must be run by an ordinary user, never root"
  [[ $(/usr/bin/uname -s) == Darwin ]] || die "macOS only"
  [[ -d $RUNTIME_ROOT && ! -L $RUNTIME_ROOT ]] || die "runtime is not built and mounted: $RUNTIME_ROOT"
  /usr/bin/env -i HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    /usr/bin/python3 -I -E -s - "$RUNTIME_ROOT" <<'PY'
import ctypes
import os
import stat
import sys

runtime = sys.argv[1]
required = [
    "bin/rga",
    "bin/rga-preproc",
    "bin/pandoc",
    "bin/pdftotext",
    "bin/rg",
    "config/rga-config.json",
]


def fail(message):
    raise SystemExit("verify preflight failed: " + message)


if os.path.realpath(runtime) != runtime:
    fail("runtime path is not canonical")
root = os.lstat(runtime)
if not stat.S_ISDIR(root.st_mode) or root.st_uid != 0 or root.st_gid != 0 or root.st_mode & 0o022:
    fail("runtime root ownership, type, or mode is unsafe")


class Fsid(ctypes.Structure):
    _fields_ = [("val", ctypes.c_int32 * 2)]


class Statfs(ctypes.Structure):
    _fields_ = [
        ("f_bsize", ctypes.c_uint32),
        ("f_iosize", ctypes.c_int32),
        ("f_blocks", ctypes.c_uint64),
        ("f_bfree", ctypes.c_uint64),
        ("f_bavail", ctypes.c_uint64),
        ("f_files", ctypes.c_uint64),
        ("f_ffree", ctypes.c_uint64),
        ("f_fsid", Fsid),
        ("f_owner", ctypes.c_uint32),
        ("f_type", ctypes.c_uint32),
        ("f_flags", ctypes.c_uint32),
        ("f_fssubtype", ctypes.c_uint32),
        ("f_fstypename", ctypes.c_char * 16),
        ("f_mntonname", ctypes.c_char * 1024),
        ("f_mntfromname", ctypes.c_char * 1024),
    ]


libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
XATTR_NOFOLLOW = 0x0001
libc.listxattr.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
libc.listxattr.restype = ctypes.c_ssize_t


def safe_xattrs(path):
    encoded_path = os.fsencode(path)
    size = libc.listxattr(encoded_path, None, 0, XATTR_NOFOLLOW)
    if size < 0:
        fail("cannot enumerate xattrs: " + path + ": " + os.strerror(ctypes.get_errno()))
    if size > 4096:
        fail("xattr name list exceeds cap: " + path)
    if size == 0:
        return
    buffer = ctypes.create_string_buffer(size)
    actual = libc.listxattr(encoded_path, buffer, size, XATTR_NOFOLLOW)
    if actual != size:
        fail("xattr names changed during inspection: " + path)
    fields = bytes(buffer.raw[:actual]).split(b"\0")
    if not fields or fields[-1] != b"" or fields[:-1] != [b"com.apple.provenance"]:
        fail("unexpected extended attributes: " + path)


def mount_info(path=None, fd=None):
    value = Statfs()
    result = libc.fstatfs(fd, ctypes.byref(value)) if fd is not None else libc.statfs(path.encode(), ctypes.byref(value))
    if result:
        fail("statfs is unavailable: " + os.strerror(ctypes.get_errno()))
    return (
        tuple(value.f_fsid.val),
        value.f_mntonname.split(b"\0", 1)[0].decode(),
        value.f_mntfromname.split(b"\0", 1)[0].decode(),
        value.f_type,
        value.f_flags,
    )


public = mount_info(path=runtime)
descriptor = os.open(runtime, os.O_RDONLY | os.O_DIRECTORY)
try:
    retained = mount_info(fd=descriptor)
finally:
    os.close(descriptor)
if public != retained:
    fail("public and retained mount identities differ")
if not public[4] & 1:
    fail("runtime mount is writable; MNT_RDONLY is not set")
if public[1] != runtime:
    fail("runtime is not the exact mount point")
safe_xattrs(runtime)
checked = set()
for relative in required:
    current = runtime
    components = relative.split("/")
    for index, component in enumerate(components):
        current = os.path.join(current, component)
        if current in checked:
            continue
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            fail("required runtime entry is missing: " + relative)
        final = index == len(components) - 1
        expected_type = stat.S_ISREG(metadata.st_mode) if final else stat.S_ISDIR(metadata.st_mode)
        if not expected_type or metadata.st_uid != 0 or metadata.st_gid != 0 or metadata.st_mode & 0o022:
            fail("required runtime path is not sealed: " + os.path.relpath(current, runtime))
        if mount_info(path=current) != public:
            fail("required runtime path is on a different mount: " + os.path.relpath(current, runtime))
        safe_xattrs(current)
        checked.add(current)
config = os.path.join(runtime, "config/rga-config.json")
with open(config, "rb") as handle:
    if handle.read() != b'{"custom_adapters":[]}':
        fail("rga config bytes differ from the sealed contract")
PY
  readonly VERIFY_ROOT=/private/tmp/kio-comparator-runtime-v1-verify
  [[ ! -e $VERIFY_ROOT && ! -L $VERIFY_ROOT ]] || die "refusing to reuse verifier directory: $VERIFY_ROOT"
  /bin/mkdir -m 0700 "$VERIFY_ROOT"
  trap '/bin/rm -rf "$VERIFY_ROOT"' EXIT
  /bin/mkdir -m 0700 "$VERIFY_ROOT/home" "$VERIFY_ROOT/config" "$VERIFY_ROOT/cache"
  readonly SMOKE_PDF="$VERIFY_ROOT/smoke.pdf" SMOKE_DOCX="$VERIFY_ROOT/smoke.docx" SMOKE_MD="$VERIFY_ROOT/smoke.md"
  /usr/bin/env -i HOME="$VERIFY_ROOT/home" PATH=/usr/bin:/bin /usr/bin/python3 -I -E -s - "$SMOKE_PDF" "$SMOKE_DOCX" "$SMOKE_MD" <<'PY'
from pathlib import Path
import sys
import zipfile

pdf, docx, markdown = map(Path, sys.argv[1:])
stream = b"BT /F1 12 Tf 72 720 Td (Kio comparator runtime smoke) Tj ET\n"
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
]
data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
offsets = [0]
for number, body in enumerate(objects, 1):
    offsets.append(len(data))
    data += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
xref = len(data)
data += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
for offset in offsets[1:]:
    data += f"{offset:010d} 00000 n \n".encode()
data += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
pdf.write_bytes(data)
markdown.write_text("# Kio comparator runtime smoke\n", encoding="utf-8")
with zipfile.ZipFile(docx, "w", compression=zipfile.ZIP_STORED) as archive:
    archive.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>""")
    archive.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>""")
    archive.writestr("word/document.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Kio comparator runtime smoke</w:t></w:r></w:p><w:sectPr/></w:body></w:document>""")
PY
  readonly CLEAN_HOME="HOME=$VERIFY_ROOT/home" CLEAN_CONFIG="XDG_CONFIG_HOME=$VERIFY_ROOT/config" CLEAN_CACHE="XDG_CACHE_HOME=$VERIFY_ROOT/cache"
  /usr/bin/env -i "$CLEAN_HOME" "$CLEAN_CONFIG" "$CLEAN_CACHE" PATH="$RUNTIME_ROOT/bin" LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    "$RUNTIME_ROOT/bin/rga-preproc" "$SMOKE_PDF" | /usr/bin/grep -Fq "Kio comparator runtime smoke"
  /usr/bin/env -i "$CLEAN_HOME" "$CLEAN_CONFIG" "$CLEAN_CACHE" PATH="$RUNTIME_ROOT/bin" LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    "$RUNTIME_ROOT/bin/rga" --rga-config-file="$RUNTIME_ROOT/config/rga-config.json" --rga-adapters=pandoc,poppler \
    --rga-cache-path="$VERIFY_ROOT/cache" -F \
    "Kio comparator runtime smoke" "$SMOKE_PDF" >/dev/null
  /usr/bin/env -i "$CLEAN_HOME" "$CLEAN_CONFIG" "$CLEAN_CACHE" PATH="$RUNTIME_ROOT/bin" LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    "$RUNTIME_ROOT/bin/rga" --rga-config-file="$RUNTIME_ROOT/config/rga-config.json" --rga-adapters=pandoc,poppler \
    --rga-cache-path="$VERIFY_ROOT/cache" -F \
    "Kio comparator runtime smoke" "$SMOKE_DOCX" >/dev/null
  /usr/bin/env -i "$CLEAN_HOME" "$CLEAN_CONFIG" "$CLEAN_CACHE" PATH="$RUNTIME_ROOT/bin" LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    "$RUNTIME_ROOT/bin/pandoc" -f docx -t plain "$SMOKE_DOCX" | /usr/bin/grep -Fq "Kio comparator runtime smoke"
  /usr/bin/env -i "$CLEAN_HOME" "$CLEAN_CONFIG" "$CLEAN_CACHE" PATH="$RUNTIME_ROOT/bin" LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    "$RUNTIME_ROOT/bin/pdftotext" "$SMOKE_PDF" - | /usr/bin/grep -Fq "Kio comparator runtime smoke"
  /usr/bin/env -i "$CLEAN_HOME" "$CLEAN_CONFIG" "$CLEAN_CACHE" PATH="$RUNTIME_ROOT/bin" LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    "$RUNTIME_ROOT/bin/rg" -Fq -- "Kio comparator runtime smoke" "$SMOKE_MD"
  print -- "ordinary-user smoke verification passed: $RUNTIME_ROOT"
  exit 0
fi
[[ ${EUID} -eq 0 ]] || die "administrator execution required; run this script explicitly with sudo (the script never invokes sudo)"
[[ $(/usr/bin/uname -s) == Darwin ]] || die "macOS only"
readonly ADMIN_SCRIPT=${0:A}
readonly ADMIN_SCRIPT_DIR=${ADMIN_SCRIPT:h}
[[ ${${ADMIN_SCRIPT}:t} == build-script && $ADMIN_SCRIPT_DIR == ${ADMIN_SCRIPT_PREFIX}* ]] || die "root build must execute a root-private administrator-reviewed script copy"
[[ "$0" == "$ADMIN_SCRIPT" && ${ADMIN_SCRIPT_DIR:A} == "$ADMIN_SCRIPT_DIR" && ! -L $ADMIN_SCRIPT && ! -L $ADMIN_SCRIPT_DIR ]] || die "administrator script path must be canonical and symlink-free"
for p in "$ADMIN_SCRIPT_DIR" "$ADMIN_SCRIPT"; do
  script_stat=$(/usr/bin/stat -f '%u:%g:%p' "$p")
  [[ $script_stat == 0:0:* ]] || die "administrator script path must be root:wheel: $p"
  [[ $(( 8#${script_stat##*:} & 8#022 )) -eq 0 ]] || die "administrator script path is group/other writable: $p"
  require_safe_xattrs "$p"
  [[ $(/bin/ls -lde "$p" | /usr/bin/wc -l | /usr/bin/tr -d ' ') -eq 1 ]] || die "administrator script path has an ACL: $p"
done
admin_dir_mode=$(/usr/bin/stat -f '%p' "$ADMIN_SCRIPT_DIR")
[[ $(( 8#$admin_dir_mode & 8#077 )) -eq 0 ]] || die "administrator script directory must be mode 0700"
for p in "$MANAGED_ROOT" "$RUNTIME_ROOT" "$IMAGE" "$MANIFEST" "$BUILD_ROOT"; do
 if [[ -e $p || -L $p ]]; then
  print -u2 -- "existing target (no writes): $p"
  /usr/bin/stat -f 'realpath=%N uid=%u gid=%g mode=%Sp' "$p" 2>&1 || true
  print -u2 -r -- "canonical=${p:A}"
  exit 1
 fi
done
created=0 created_mountpoint=0 created_build=0 created_image=0 created_manifest=0 mounted=0
rollback() { local rollback_rc=$?; if (( rollback_rc )); then
  print -u2 -- "build failed; rolling back only fixed paths created by this invocation"
  (( mounted )) && /usr/bin/hdiutil detach "$RUNTIME_ROOT" >/dev/null 2>&1 || true
  (( created_image )) && [[ -e $IMAGE && ! -L $IMAGE ]] && /bin/rm -f "$IMAGE"
  (( created_manifest )) && [[ -e $MANIFEST && ! -L $MANIFEST ]] && /bin/rm -f "$MANIFEST"
  (( created_mountpoint )) && [[ -d $RUNTIME_ROOT && ! -L $RUNTIME_ROOT ]] && /bin/rmdir "$RUNTIME_ROOT" 2>/dev/null || true
  (( created_build )) && [[ -d $BUILD_ROOT && ! -L $BUILD_ROOT ]] && /bin/rm -rf "$BUILD_ROOT"
  (( created )) && /bin/rmdir "$MANAGED_ROOT" 2>/dev/null || true
 fi; exit $rollback_rc; }
trap rollback EXIT
/bin/mkdir -m 0755 "$MANAGED_ROOT"; created=1; /usr/sbin/chown root:wheel "$MANAGED_ROOT"
/bin/mkdir -m 0755 "$RUNTIME_ROOT"; created_mountpoint=1; /usr/sbin/chown root:wheel "$RUNTIME_ROOT"
/bin/mkdir -m 0700 "$BUILD_ROOT"; created_build=1; /usr/sbin/chown root:wheel "$BUILD_ROOT"
for p in "$MANAGED_ROOT" "$RUNTIME_ROOT" "$BUILD_ROOT"; do
  /bin/chmod -N "$p"
  require_safe_xattrs "$p"
done
[[ $(/usr/bin/stat -f '%u:%g:%p' "$MANAGED_ROOT") == 0:0:* ]] || die "managed root ownership is unsafe"
managed_mode=$(/usr/bin/stat -f '%p' "$MANAGED_ROOT")
[[ $(( 8#$managed_mode & 8#022 )) -eq 0 ]] || die "managed root is group/other writable"
require_safe_xattrs "$MANAGED_ROOT"
[[ $(/bin/ls -lde "$MANAGED_ROOT" | /usr/bin/wc -l | /usr/bin/tr -d ' ') -eq 1 ]] || die "managed root has an ACL"

# The embedded resolver reads only the hard-coded Homebrew inputs.  It rejects
# unresolved paths, non-system escapes, and basename collisions before copying.
/usr/bin/env -i HOME=/var/root PATH=/usr/bin:/bin:/usr/sbin:/sbin /usr/bin/python3 -I -E -s - "$BUILD_ROOT" <<'PY'
import ctypes,hashlib,json,os,re,shutil,subprocess,sys
B=os.path.abspath(sys.argv[1]); P=B+"/payload"; BIN=P+"/bin"; LIB=P+"/lib"; CFG=P+"/config"
for d in (BIN,LIB,CFG): os.makedirs(d,mode=0o755)
S={"rga":"/opt/homebrew/Cellar/ripgrep-all/0.10.10/bin/rga","rga-preproc":"/opt/homebrew/Cellar/ripgrep-all/0.10.10/bin/rga-preproc","pandoc":"/opt/homebrew/Cellar/pandoc/3.10.1/bin/pandoc","pdftotext":"/opt/homebrew/Cellar/poppler/26.02.0_1/bin/pdftotext","rg":"/opt/homebrew/Cellar/ripgrep/15.1.0/bin/rg"}
SYS=("/usr/lib/","/System/Library/")
PINS={
"/opt/homebrew/Cellar/fontconfig/2.17.1/lib/libfontconfig.1.dylib":"0a960b13c03e85926cc2fecdd73ea89b352f3a90ce4792b2c2612f224fe7ed48","/opt/homebrew/Cellar/freetype/2.14.1_2/lib/libfreetype.6.dylib":"9de156e3493b53e42060e91d15627926b1b55e7b854bf1800fecee8ede469d0d","/opt/homebrew/Cellar/gettext/1.0/lib/libintl.8.dylib":"0c6d618e75fea85cc3d631e164a71766fba9341d19ce1f723300c52e63037c51","/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib":"14123464af436d67ef69114810aa9e1e74de50e4097166fe8c110397b3ba6961","/opt/homebrew/Cellar/gpgme/2.0.1/lib/libgpgme.45.dylib":"69c0e16bee0d16d0ccb68cad0143fef4dbcb47395921d03f89ed611636d07544","/opt/homebrew/Cellar/gpgmepp/2.0.0/lib/libgpgmepp.7.0.0.dylib":"403f6cd87b492dbdfcea5665b3136734449b596d6b3b045a3cc4cc62388aade3","/opt/homebrew/Cellar/jpeg-turbo/3.1.3/lib/libjpeg.8.3.2.dylib":"b61e868fffc3c13501417e78d70fafadb4daccad593590f9e96e59f4cefdd20b","/opt/homebrew/Cellar/libassuan/3.0.2/lib/libassuan.9.dylib":"1c45b3dd61f6f07249149723358e4d8448af5ced1a6b279a99ddbd7a906d1ff6","/opt/homebrew/Cellar/libgpg-error/1.59/lib/libgpg-error.0.dylib":"a6dded3a14c1adc1465b65b517640bab484012ae37071d87c20fdf87c2262495","/opt/homebrew/Cellar/libpng/1.6.55/lib/libpng16.16.dylib":"a665b05d0a9fc37b96e6f6651cf1ba182db93bcf7992e73f5e8d5cdbb4700ee6","/opt/homebrew/Cellar/libtiff/4.7.1_1/lib/libtiff.6.dylib":"f65bfa09fe4b3710e308d53707d081644eede6e57f06df6c376ad7f5bc6ffcb2","/opt/homebrew/Cellar/little-cms2/2.18/lib/liblcms2.2.dylib":"2b01b3d4983f379da0c7a433b926144340a5210390019f9aaf15c3b3ede6abfa","/opt/homebrew/Cellar/nspr/4.38.2/lib/libnspr4.dylib":"7f85b5d639f28836895dd93717685cf891def04f1f91d41b6a6f9543297ade6f","/opt/homebrew/Cellar/nspr/4.38.2/lib/libplc4.dylib":"8945b7af3ae90a3fa1d49482be01ff78f0a1380ca4bb685b59454abb4aae4fe8","/opt/homebrew/Cellar/nspr/4.38.2/lib/libplds4.dylib":"24627ef67deda78448f7cab363f554b857fae595f3d0cdba86ec97f1bfff1418","/opt/homebrew/Cellar/nss/3.121/lib/libnss3.dylib":"2bd3c828466d9b6aeb985b62d45e6a77c0dfd4e9177bb72530e80dfcc19f4794","/opt/homebrew/Cellar/nss/3.121/lib/libnssutil3.dylib":"7891381b35027b011965293667987ddeef5a2e58cfbab9a589bf09c1a28422cd","/opt/homebrew/Cellar/nss/3.121/lib/libsmime3.dylib":"ea59d0432a835d3c8a9e8e31b4b3584e26336d2b104c0b7464a3f37caaa21091","/opt/homebrew/Cellar/nss/3.121/lib/libssl3.dylib":"090acb80d058254c9f9e44c5836334a401d86744991804c3bdf441a9cf4cffb7","/opt/homebrew/Cellar/openjpeg/2.5.4/lib/libopenjp2.2.5.4.dylib":"3b46324a48881d5ef030a096a5c242d0641299f85576895611ff0deb1505cbca","/opt/homebrew/Cellar/pandoc/3.10.1/bin/pandoc":"61574e53a089110eae07817b91510ff150e826807ac020aa744e0ade23025e0d","/opt/homebrew/Cellar/pcre2/10.47_1/lib/libpcre2-8.0.dylib":"fc0491cc252c2938b6c37d1b6b4d7bfedffb9edb2519c47cef577637eddb73d5","/opt/homebrew/Cellar/poppler/26.02.0_1/bin/pdftotext":"e75be019b2ab471970560493262458a3b4be1b9f9584d004bb8a624d5487c9b6","/opt/homebrew/Cellar/poppler/26.02.0_1/lib/libpoppler.157.0.0.dylib":"688a66fbad757086fc64ae2262585953d13a2868f49a7cfadf7f5857297ba371","/opt/homebrew/Cellar/ripgrep/15.1.0/bin/rg":"2fb61b6e5b3e2d89b115fe6c18fd8805670fdf4bdfde85954d40855a76830e5f","/opt/homebrew/Cellar/ripgrep-all/0.10.10/bin/rga":"279d3f49b1ebf9db88d6f2ab58906bf43182be51df63a3555ade27ba611a9a5c","/opt/homebrew/Cellar/ripgrep-all/0.10.10/bin/rga-preproc":"4f583ec9b9edbe5956ad82fd40d3df6876e2d1b084935a44e87a1cc999964196","/opt/homebrew/Cellar/xz/5.8.3/lib/liblzma.5.dylib":"3d5bfa2f097c31463642b1daab5e662b44368bb4da368f85e412e7f9adcbaa10","/opt/homebrew/Cellar/zstd/1.5.7_1/lib/libzstd.1.5.7.dylib":"e2847c4613b386683c234913ae3b7b04299254096caf7616e3b3cd9bb97a39ab"}
PIN_SIZES={
"/opt/homebrew/Cellar/fontconfig/2.17.1/lib/libfontconfig.1.dylib":304544,"/opt/homebrew/Cellar/freetype/2.14.1_2/lib/libfreetype.6.dylib":638192,"/opt/homebrew/Cellar/gettext/1.0/lib/libintl.8.dylib":228800,"/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib":452352,"/opt/homebrew/Cellar/gpgme/2.0.1/lib/libgpgme.45.dylib":345392,"/opt/homebrew/Cellar/gpgmepp/2.0.0/lib/libgpgmepp.7.0.0.dylib":414640,"/opt/homebrew/Cellar/jpeg-turbo/3.1.3/lib/libjpeg.8.3.2.dylib":486672,"/opt/homebrew/Cellar/libassuan/3.0.2/lib/libassuan.9.dylib":116320,"/opt/homebrew/Cellar/libgpg-error/1.59/lib/libgpg-error.0.dylib":198720,"/opt/homebrew/Cellar/libpng/1.6.55/lib/libpng16.16.dylib":208272,"/opt/homebrew/Cellar/libtiff/4.7.1_1/lib/libtiff.6.dylib":539248,"/opt/homebrew/Cellar/little-cms2/2.18/lib/liblcms2.2.dylib":372080,"/opt/homebrew/Cellar/nspr/4.38.2/lib/libnspr4.dylib":238752,"/opt/homebrew/Cellar/nspr/4.38.2/lib/libplc4.dylib":70768,"/opt/homebrew/Cellar/nspr/4.38.2/lib/libplds4.dylib":69632,"/opt/homebrew/Cellar/nss/3.121/lib/libnss3.dylib":1174848,"/opt/homebrew/Cellar/nss/3.121/lib/libnssutil3.dylib":222048,"/opt/homebrew/Cellar/nss/3.121/lib/libsmime3.dylib":218912,"/opt/homebrew/Cellar/nss/3.121/lib/libssl3.dylib":383520,"/opt/homebrew/Cellar/openjpeg/2.5.4/lib/libopenjp2.2.5.4.dylib":324160,"/opt/homebrew/Cellar/pandoc/3.10.1/bin/pandoc":277080112,"/opt/homebrew/Cellar/pcre2/10.47_1/lib/libpcre2-8.0.dylib":588224,"/opt/homebrew/Cellar/poppler/26.02.0_1/bin/pdftotext":82456,"/opt/homebrew/Cellar/poppler/26.02.0_1/lib/libpoppler.157.0.0.dylib":3419584,"/opt/homebrew/Cellar/ripgrep-all/0.10.10/bin/rga":7700968,"/opt/homebrew/Cellar/ripgrep-all/0.10.10/bin/rga-preproc":9177616,"/opt/homebrew/Cellar/ripgrep/15.1.0/bin/rg":6154240,"/opt/homebrew/Cellar/xz/5.8.3/lib/liblzma.5.dylib":184512,"/opt/homebrew/Cellar/zstd/1.5.7_1/lib/libzstd.1.5.7.dylib":649648}
if set(PINS)!=set(PIN_SIZES) or sum(PIN_SIZES.values())!=312045232:
 raise RuntimeError("reviewed pin size manifest is inconsistent")
def digest(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1048576),b""): h.update(b)
 return h.hexdigest()
XATTR_NOFOLLOW=0x0001
libc=ctypes.CDLL("/usr/lib/libSystem.B.dylib",use_errno=True)
libc.listxattr.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
libc.listxattr.restype=ctypes.c_ssize_t
def safe_xattrs(path):
 raw=os.fsencode(path); size=libc.listxattr(raw,None,0,XATTR_NOFOLLOW)
 if size<0: raise RuntimeError("cannot enumerate xattrs: %s: %s"%(path,os.strerror(ctypes.get_errno())))
 if size>4096: raise RuntimeError("xattr name list exceeds cap: "+path)
 if size==0: return []
 buf=ctypes.create_string_buffer(size)
 got=libc.listxattr(raw,buf,size,XATTR_NOFOLLOW)
 if got!=size: raise RuntimeError("xattr names changed during inspection: "+path)
 encoded=bytes(buf.raw[:got]); parts=encoded.split(b"\0")
 if not parts or parts[-1]!=b"": raise RuntimeError("malformed xattr name list: "+path)
 names=parts[:-1]
 if names not in ([b"com.apple.provenance"],): raise RuntimeError("unexpected xattrs: %s: %r"%(path,names))
 return [name.decode("ascii") for name in names]
# Never inspect a Homebrew Mach-O image.  First copy the *reviewed pin set*
# through no-follow descriptors and verify it while streaming.  Everything
# below, including otool, only receives these root-owned staged regular files.
SRC=B+"/reviewed-sources"; os.makedirs(SRC,mode=0o700)
def pinned_copy(src,want,want_size):
 if os.path.realpath(src)!=src: raise RuntimeError("pinned source is not canonical: "+src)
 fd=os.open(src,os.O_RDONLY|os.O_NOFOLLOW); before=os.fstat(fd)
 if not stat.S_ISREG(before.st_mode) or before.st_size!=want_size:
  os.close(fd); raise RuntimeError("pinned input size/type differs from reviewed manifest: "+src)
 dst=os.path.join(SRC,hashlib.sha256(src.encode()).hexdigest())
 outfd=os.open(dst,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); h=hashlib.sha256(); total=0
 try:
  while True:
   b=os.read(fd,1048576)
   if not b: break
   h.update(b); total+=len(b); os.write(outfd,b)
 finally: os.close(outfd)
 after=os.fstat(fd); os.close(fd); named=os.lstat(src)
 if (before.st_dev,before.st_ino,before.st_size)!=(after.st_dev,after.st_ino,after.st_size) or (before.st_dev,before.st_ino)!=(named.st_dev,named.st_ino) or total!=before.st_size or h.hexdigest()!=want: raise RuntimeError("pinned source changed or digest mismatched: "+src)
 return dst
import stat
STAGED={src:pinned_copy(src,want,PIN_SIZES[src]) for src,want in PINS.items()}
STAGED_PINS={STAGED[src]:want for src,want in PINS.items()}
ORIGINAL={v:k for k,v in STAGED.items()}
S={n:STAGED[p] for n,p in S.items()}
def out(*a): return subprocess.check_output(a,text=True,stderr=subprocess.STDOUT)
def real(p):
 p=os.path.realpath(p)
 if not os.path.isabs(p) or not os.path.exists(p): raise RuntimeError("unresolved: "+p)
 return p
def system(p):
 if not os.path.isabs(p) or os.path.normpath(p)!=p: return False
 return p=="/usr/lib/dyld" or p.startswith(SYS)
LOAD_CMDS={"LC_LOAD_DYLIB","LC_LOAD_WEAK_DYLIB","LC_REEXPORT_DYLIB","LC_LOAD_UPWARD_DYLIB","LC_LAZY_LOAD_DYLIB"}
def unsafe_commands(p,seed):
 ls=out("/usr/bin/otool","-arch","arm64","-l",p).splitlines()
 if any(x.strip()=="cmd LC_DYLD_ENVIRONMENT" for x in ls): raise RuntimeError("LC_DYLD_ENVIRONMENT prohibited: "+p)
 loaders=[]
 for i,x in enumerate(ls):
  if x.strip()=="cmd LC_LOAD_DYLINKER":
   for y in ls[i+1:i+6]:
    m=re.match(r"\s*name (.+) \(offset ",y)
    if m: loaders.append(m.group(1)); break
 if (seed and loaders != ["/usr/lib/dyld"]) or (not seed and loaders): raise RuntimeError("invalid LC_LOAD_DYLINKER policy: "+p)
def loads(p):
 # `otool -L` also displays LC_ID_DYLIB.  Parse only LC_LOAD_* commands so a
 # dylib's install-name is never mistaken for a dependency.
 ls=out("/usr/bin/otool","-arch","arm64","-l",p).splitlines(); ans=[]
 for i,x in enumerate(ls):
  command=x.strip()
  if command.startswith("cmd ") and command[4:] in LOAD_CMDS:
   for y in ls[i+1:i+6]:
    m=re.match(r"\s*name (.+) \(offset ",y)
    if m: ans.append(m.group(1)); break
 return ans
def install_id(p):
 ls=out("/usr/bin/otool","-arch","arm64","-l",p).splitlines(); ids=[]
 for i,x in enumerate(ls):
  if x.strip()=="cmd LC_ID_DYLIB":
   for y in ls[i+1:i+6]:
    m=re.match(r"\s*name (.+) \(offset ",y)
    if m: ids.append(m.group(1)); break
 if len(ids)>1: raise RuntimeError("multiple LC_ID_DYLIB commands: "+p)
 return ids[0] if ids else None
def raw_rpaths(p):
 ls=out("/usr/bin/otool","-arch","arm64","-l",p).splitlines(); r=[]
 for i,x in enumerate(ls):
  if x.strip()=="cmd LC_RPATH":
   for y in ls[i+1:i+6]:
    m=re.match(r"\s*path (.+) \(offset ",y)
    if m: r.append(m.group(1)); break
 return r
ALIASES={}
for staged in STAGED_PINS:
 aliases={os.path.basename(ORIGINAL[staged])}
 identity=install_id(staged)
 if identity: aliases.add(os.path.basename(identity))
 for alias in aliases:
  prior=ALIASES.setdefault(alias,staged)
  if prior!=staged: raise RuntimeError("ambiguous reviewed dependency alias: "+alias)
def resolve_source(raw,p,exe):
 if system(raw): return raw
 # Source load names are untrusted metadata: match them only against aliases
 # authenticated by the reviewed copy's own LC_ID_DYLIB, never follow a
 # Homebrew rpath or filesystem symlink.
 base=os.path.basename(raw)
 if base in ALIASES: return ALIASES[base]
 raise RuntimeError("load command is absent from the reviewed pin aliases: %s in %s"%(raw,p))
for p in S.values():
 if real(p)!=p or not os.path.isfile(p): raise RuntimeError("noncanonical/missing fixed source: "+p)
for p in S.values(): unsafe_commands(p,True)
C={}; q=[(p,p) for p in S.values()]
while q:
 p,e=q.pop(); p,e=real(p),real(e)
 if p in C: continue
 unsafe_commands(p,p in S.values())
 C[p]=e
 for raw in loads(p):
  d=resolve_source(raw,p,e)
  if not system(d): q.append((d,e))
if set(C)!=set(STAGED_PINS): raise RuntimeError("discovered closure differs from reviewed pins: missing=%r extra=%r" % (sorted(set(STAGED_PINS)-set(C)),sorted(set(C)-set(STAGED_PINS))))
for p in C:
 if digest(p)!=STAGED_PINS[p]: raise RuntimeError("staged source digest does not match reviewed pin: "+p)
names={real(p):n for n,p in S.items()}; D={}; used={}
for p in sorted(C):
 d=os.path.join(BIN,names[p]) if p in names else os.path.join(LIB,os.path.basename(p))
 if d in used and used[d]!=p: raise RuntimeError("basename collision: %s / %s"%(used[d],p))
 used[d]=p; D[p]=d; shutil.copy2(p,d,follow_symlinks=False)
 if digest(d)!=STAGED_PINS[p]: raise RuntimeError("copied pre-rewrite digest mismatch: "+p)
for p in sorted(C):
 d=D[p]; e=C[p]
 for raw in loads(p):
  x=resolve_source(raw,p,e)
  if not system(x): subprocess.check_call(["/usr/bin/install_name_tool","-change",raw,"@rpath/"+os.path.basename(D[x]),d])
 # Delete source rpaths after their load commands are flattened, then give each
 # copied image exactly one sealed rpath.  This avoids retained Homebrew opt/
 # indirection while retaining standard Mach-O rpath semantics.
 for rp in raw_rpaths(p):
  subprocess.check_call(["/usr/bin/install_name_tool","-delete_rpath",rp,d])
 if p in names: subprocess.check_call(["/usr/bin/install_name_tool","-add_rpath","@loader_path/../lib",d])
 else:
  subprocess.check_call(["/usr/bin/install_name_tool","-id","@rpath/"+os.path.basename(d),d])
  subprocess.check_call(["/usr/bin/install_name_tool","-add_rpath","@loader_path",d])
 subprocess.check_call(["/usr/bin/codesign","--force","--sign","-","--timestamp=none",d],stdout=subprocess.DEVNULL)
 subprocess.check_call(["/usr/bin/codesign","--verify","--strict",d],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
# Re-walk the payload after the source rpaths have been deleted.  At this
# boundary every non-system load must be the exact `@rpath/<basename>` form
# produced above and resolve to one payload image, never back to the reviewed
# source copies.
def resolve_payload(raw):
 if system(raw): return raw
 if not raw.startswith("@rpath/"): raise RuntimeError("unsealed payload load command: "+raw)
 name=raw[7:]
 if not name or "/" in name or name in (".",".."): raise RuntimeError("invalid payload dependency basename: "+raw)
 candidates=[x for x in D.values() if os.path.basename(x)==name]
 if len(candidates)!=1: raise RuntimeError("payload dependency is unresolved or ambiguous: "+raw)
 return candidates[0]
seen=set(); q=[(BIN+"/"+n,BIN+"/"+n) for n in S]
while q:
 p,e=q.pop(); p,e=real(p),real(e)
 if p in seen: continue
 if not p.startswith(P+os.sep): raise RuntimeError("closure escaped payload: "+p)
 seen.add(p)
 for raw in loads(p):
  x=resolve_payload(raw)
  if not system(x):
   if not x.startswith(P+os.sep): raise RuntimeError("external dependency after sealing: "+x)
   q.append((x,e))
if seen != set(D.values()): raise RuntimeError("sealed payload closure differs from reviewed pins")
open(CFG+"/rga-config.json","wb").write(b'{"custom_adapters":[]}')
subprocess.check_call(["/bin/chmod","-RN",P])
payload_xattrs=[]
for root,dirs,files in os.walk(P):
 dirs.sort(); files.sort()
 for name in ["."]+files:
  path=root if name=="." else os.path.join(root,name)
  names=safe_xattrs(path)
  if names: payload_xattrs.append({"path":os.path.relpath(path,P),"names":names})
for root,dirs,files in os.walk(P):
 os.chmod(root,0o555)
 for n in dirs: os.chmod(os.path.join(root,n),0o555)
 for n in files: os.chmod(os.path.join(root,n),0o555 if root==BIN else 0o444)
json.dump({"schema_version":1,"runtime_root":"/Library/KioComparatorRuntime/v1","xattr_policy":"only-com.apple.provenance","payload_allowed_xattrs":payload_xattrs,"sources_before":[{"path":ORIGINAL[p],"sha256":STAGED_PINS[p],"bytes":PIN_SIZES[ORIGINAL[p]]} for p in sorted(C)],"payload_files":[{"path":os.path.relpath(os.path.join(r,n),P),"sha256":digest(os.path.join(r,n))} for r,_,fs in os.walk(P) for n in sorted(fs)],"closure_images":sorted(os.path.relpath(x,P) for x in seen)},open(B+"/manifest-preimage.json","w"),sort_keys=True,separators=(",",":"))
PY
created_image=1
/usr/bin/hdiutil create -srcfolder "$BUILD_ROOT/payload" -format UDRO -fs "Case-sensitive APFS" -volname "$VOLUME_NAME" -srcowners on -noanyowners "$IMAGE"
/usr/sbin/chown root:wheel "$IMAGE"; /bin/chmod 0444 "$IMAGE"
/bin/chmod -N "$IMAGE"; require_safe_image_xattrs "$IMAGE"
/usr/bin/hdiutil attach -readonly -owners on -nobrowse -noautoopen -mountpoint "$RUNTIME_ROOT" "$IMAGE" >/dev/null; mounted=1
normalize_attached_image_xattrs "$IMAGE"

created_manifest=1
/usr/bin/env -i HOME=/var/root PATH=/usr/bin:/bin:/usr/sbin:/sbin /usr/bin/python3 -I -E -s - "$RUNTIME_ROOT" "$BUILD_ROOT/manifest-preimage.json" "$MANIFEST" "$IMAGE" <<'PY'
import ctypes,hashlib,json,os,stat,subprocess,sys
R,pre,M,I=map(os.path.abspath,sys.argv[1:])
def bad(x): raise SystemExit("verification failed: "+x)
def dg(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1048576),b""):h.update(b)
 return h.hexdigest()
def pinned_source_digest(p,expected,expected_size):
 if os.path.realpath(p)!=p: bad("Homebrew input is no longer canonical: "+p)
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW); before=os.fstat(fd)
 if not stat.S_ISREG(before.st_mode) or before.st_size!=expected_size:
  os.close(fd); bad("Homebrew input is not a bounded regular file: "+p)
 h=hashlib.sha256(); total=0
 try:
  while True:
   chunk=os.read(fd,1048576)
   if not chunk: break
   h.update(chunk); total+=len(chunk)
  after=os.fstat(fd)
 finally: os.close(fd)
 named=os.lstat(p)
 if (before.st_dev,before.st_ino,before.st_size)!=(after.st_dev,after.st_ino,after.st_size) or (before.st_dev,before.st_ino)!=(named.st_dev,named.st_ino) or total!=before.st_size or h.hexdigest()!=expected:
  bad("Homebrew input changed during build: "+p)
 return h.hexdigest()
class Fsid(ctypes.Structure): _fields_=[("val",ctypes.c_int32*2)]
class Statfs(ctypes.Structure): _fields_=[("f_bsize",ctypes.c_uint32),("f_iosize",ctypes.c_int32),("f_blocks",ctypes.c_uint64),("f_bfree",ctypes.c_uint64),("f_bavail",ctypes.c_uint64),("f_files",ctypes.c_uint64),("f_ffree",ctypes.c_uint64),("f_fsid",Fsid),("f_owner",ctypes.c_uint32),("f_type",ctypes.c_uint32),("f_flags",ctypes.c_uint32),("f_fssubtype",ctypes.c_uint32),("f_fstypename",ctypes.c_char*16),("f_mntonname",ctypes.c_char*1024),("f_mntfromname",ctypes.c_char*1024)]
libc=ctypes.CDLL("/usr/lib/libSystem.B.dylib",use_errno=True)
XATTR_NOFOLLOW=0x0001
libc.listxattr.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
libc.listxattr.restype=ctypes.c_ssize_t
def safe_xattrs(path):
 raw=os.fsencode(path); size=libc.listxattr(raw,None,0,XATTR_NOFOLLOW)
 if size<0: bad("cannot enumerate xattrs: %s: %s"%(path,os.strerror(ctypes.get_errno())))
 if size>4096: bad("xattr name list exceeds cap: "+path)
 if size==0: return []
 buf=ctypes.create_string_buffer(size)
 got=libc.listxattr(raw,buf,size,XATTR_NOFOLLOW)
 if got!=size: bad("xattr names changed during inspection: "+path)
 encoded=bytes(buf.raw[:got]); parts=encoded.split(b"\0")
 if not parts or parts[-1]!=b"": bad("malformed xattr name list: "+path)
 names=parts[:-1]
 if names not in ([b"com.apple.provenance"],): bad("unexpected xattrs: %s: %r"%(path,names))
 return [name.decode("ascii") for name in names]
def safe_image_xattrs(path):
 raw=os.fsencode(path); size=libc.listxattr(raw,None,0,XATTR_NOFOLLOW)
 if size<0: bad("cannot enumerate disk image xattrs: %s: %s"%(path,os.strerror(ctypes.get_errno())))
 if size>4096: bad("disk image xattr name list exceeds cap: "+path)
 if size==0: return []
 buf=ctypes.create_string_buffer(size)
 got=libc.listxattr(raw,buf,size,XATTR_NOFOLLOW)
 if got!=size: bad("disk image xattr names changed during inspection: "+path)
 encoded=bytes(buf.raw[:got]); parts=encoded.split(b"\0")
 if not parts or parts[-1]!=b"": bad("malformed disk image xattr name list: "+path)
 names=parts[:-1]
 allowed={b"com.apple.FinderInfo",b"com.apple.provenance"}
 if len(names)!=len(set(names)) or not set(names).issubset(allowed): bad("unexpected disk image xattrs: %s: %r"%(path,names))
 return [name.decode("ascii") for name in names]
def fsinfo(path=None,fd=None):
 s=Statfs(); rc=libc.fstatfs(fd,ctypes.byref(s)) if fd is not None else libc.statfs(path.encode(),ctypes.byref(s))
 if rc: bad("statfs unavailable: "+os.strerror(ctypes.get_errno()))
 return (tuple(s.f_fsid.val),s.f_mntonname.split(b"\0",1)[0].decode(),s.f_mntfromname.split(b"\0",1)[0].decode(),s.f_type,s.f_flags)
if os.path.realpath(R)!=R: bad("noncanonical mountpoint")
s=os.stat(R)
if s.st_uid!=0 or s.st_gid!=0 or s.st_mode&0o022: bad("unsafe runtime root ownership/mode")
public=fsinfo(R); fd=os.open(R,os.O_RDONLY|os.O_DIRECTORY)
try: retained=fsinfo(fd=fd)
finally: os.close(fd)
if public != retained: bad("public/retained mount identity differs")
if not (public[4] & 1): bad("MNT_RDONLY is not set")
if public[1] != R: bad("mountpoint identity differs from runtime root")
if "\n " in subprocess.check_output(["/bin/ls","-lde",R],text=True): bad("ACL on runtime root")
runtime_xattrs=[]
root_xattrs=safe_xattrs(R)
if root_xattrs: runtime_xattrs.append({"path":".","names":root_xattrs})
for root,ds,fs in os.walk(R,followlinks=False):
 ds.sort(); fs.sort()
 if os.path.islink(root): bad("directory symlink")
 for n in ds+fs:
  p=os.path.join(root,n); q=os.lstat(p)
  if os.path.islink(p): bad("symlink: "+p)
  if q.st_uid!=0 or q.st_gid!=0 or q.st_mode&0o022: bad("unsafe ownership/mode: "+p)
  if "\n " in subprocess.check_output(["/bin/ls","-lde",p],text=True): bad("ACL: "+p)
  names=safe_xattrs(p)
  if names: runtime_xattrs.append({"path":os.path.relpath(p,R),"names":names})
if open(R+"/config/rga-config.json","rb").read()!=b'{"custom_adapters":[]}': bad("wrong config bytes")
d=json.load(open(pre));
for x in d["payload_files"]:
 if dg(os.path.join(R,x["path"]))!=x["sha256"]: bad("payload digest: "+x["path"])
d["sources_after"]=[{"path":x["path"],"sha256":pinned_source_digest(x["path"],x["sha256"],x["bytes"]),"bytes":x["bytes"]} for x in d["sources_before"]]
if d["sources_after"]!=d["sources_before"]: bad("Homebrew input changed during build")
# A sealed payload has only @loader_path and sealed-system absolute loads.  Walk
# every recorded image after mounting so a packaging/relink error cannot be
# hidden by the pre-image digest check.
system=("/usr/lib/","/System/Library/")
def system_load(path):
 return os.path.isabs(path) and os.path.normpath(path)==path and (path=="/usr/lib/dyld" or path.startswith(system))
for rel in d["closure_images"]:
 p=os.path.join(R,rel)
 lines=subprocess.check_output(["/usr/bin/otool","-arch","arm64","-l",p],text=True).splitlines(); raw_loads=[]; raw_rpaths=[]; loaders=[]
 for i,line in enumerate(lines):
  command=line.strip()
  if command=="cmd LC_DYLD_ENVIRONMENT": bad("LC_DYLD_ENVIRONMENT in sealed image: "+p)
  if command=="cmd LC_LOAD_DYLINKER":
   for x in lines[i+1:i+6]:
    if x.strip().startswith("name "): loaders.append(x.strip()[5:].split(" (offset ",1)[0]); break
  if command.startswith("cmd ") and command[4:] in {"LC_LOAD_DYLIB","LC_LOAD_WEAK_DYLIB","LC_REEXPORT_DYLIB","LC_LOAD_UPWARD_DYLIB","LC_LAZY_LOAD_DYLIB"}:
   for x in lines[i+1:i+6]:
    if x.strip().startswith("name "): raw_loads.append(x.strip()[5:].split(" (offset ",1)[0]); break
  if line.strip()=="cmd LC_RPATH":
   for x in lines[i+1:i+6]:
    if x.strip().startswith("path "): raw_rpaths.append(x.strip()[5:].split(" (offset ",1)[0]); break
 want=["@loader_path/../lib"] if rel.startswith("bin/") else ["@loader_path"]
 if (rel.startswith("bin/") and loaders != ["/usr/lib/dyld"]) or (not rel.startswith("bin/") and loaders): bad("unexpected dynamic linker in %s: %r"%(p,loaders))
 if raw_rpaths!=want: bad("unexpected rpaths in %s: %r"%(p,raw_rpaths))
 for raw in raw_loads:
  if raw.startswith("@rpath/"):
   base=os.path.dirname(p) if want[0]=="@loader_path" else os.path.normpath(os.path.join(os.path.dirname(p),"../lib"))
   target=os.path.realpath(os.path.join(base,raw[7:]))
   if not target.startswith(R+"/lib/") or not os.path.isfile(target): bad("rpath escape/unresolved: "+raw)
  elif system_load(raw): pass
  else: bad("external or unsealed dependency %s in %s"%(raw,p))
d.update(image_sha256=dg(I),image_xattr_policy="subset:com.apple.FinderInfo,com.apple.provenance",image_attach_cache_policy="delete:com.apple.diskimages.recentcksum",image_allowed_xattrs=safe_image_xattrs(I),runtime_read_only=True,runtime_allowed_xattrs=runtime_xattrs)
with open(M,"w") as f: json.dump(d,f,sort_keys=True,separators=(",",":")); f.write("\n")
os.chown(M,0,0); os.chmod(M,0o444)
subprocess.check_call(["/bin/chmod","-N",M])
PY
# The image and manifest live on the writable parent volume, so verify their
# own replacement boundary after every root write. The mounted payload is
# independently checked above through statfs/fstatfs and its complete tree.
for p in "$MANAGED_ROOT" "$IMAGE" "$MANIFEST"; do
  [[ ! -L $p ]] || die "sealed runtime artifact is a symlink: $p"
  artifact_stat=$(/usr/bin/stat -f '%u:%g:%p' "$p")
  [[ $artifact_stat == 0:0:* ]] || die "sealed runtime artifact is not root:wheel: $p"
  [[ $(( 8#${artifact_stat##*:} & 8#022 )) -eq 0 ]] || die "sealed runtime artifact is group/other writable: $p"
  if [[ $p == $IMAGE ]]; then
    require_safe_image_xattrs "$p"
  else
    require_safe_xattrs "$p"
  fi
  [[ $(/bin/ls -lde "$p" | /usr/bin/wc -l | /usr/bin/tr -d ' ') -eq 1 ]] || die "sealed runtime artifact has an ACL: $p"
done
# Never execute Homebrew-derived runtime images while privileged.  An ordinary
# user may run the explicit `verify` mode after this command returns.
/bin/rm -rf "$BUILD_ROOT"; trap - EXIT
print -- "sealed comparator runtime ready: $RUNTIME_ROOT"
print -- "image: $IMAGE"; print -- "manifest: $MANIFEST"
print -- "ordinary-user smoke: run the reviewed checkout script with the verify argument"
print -- "manual rollback if this version is retired:"
print -- "  /usr/bin/hdiutil detach $RUNTIME_ROOT"
print -- "  /bin/rm $IMAGE $MANIFEST"
print -- "  /bin/rmdir $RUNTIME_ROOT $MANAGED_ROOT"
