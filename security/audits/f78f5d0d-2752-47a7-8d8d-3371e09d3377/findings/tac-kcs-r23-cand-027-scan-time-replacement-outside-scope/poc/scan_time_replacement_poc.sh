#!/bin/sh
set -eu

hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

secret_hold_for_name() {
    name=$(basename "$1" | tr '[:upper:]' '[:lower:]')
    case "$name" in
        .env|.env.*|*.pem|*.key|*.p12|*.pfx|id_rsa*|id_ecdsa*|id_ed25519*|.netrc|.npmrc|.pypirc|*credentials*|*secret*|*token*|*apikey*|*password*)
            printf 'yes'
            ;;
        *)
            printf 'no'
            ;;
    esac
}

tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/kcs-scan-replacement.XXXXXX")
trap 'rm -rf "$tmpdir"' EXIT INT TERM

scope="$tmpdir/scope"
outside_dir="$tmpdir/outside"
mkdir -p "$scope" "$outside_dir"

outside="$outside_dir/victim-readable-outside.pdf"
benign="$scope/quarterly-summary.pdf"
relative="quarterly-summary.pdf"

cat >"$outside" <<'EOF'
%PDF-1.4
1 0 obj
SYNTHETIC_OUTSIDE_SECRET_TOKEN=not-a-real-secret
endobj
EOF

cat >"$benign" <<'EOF'
%PDF-1.4
1 0 obj
benign quarterly summary placeholder
endobj
EOF

printf '[+] setup complete with a synthetic selected scope and synthetic outside target\n'

if [ -L "$benign" ] || [ ! -f "$benign" ]; then
    printf '[!] expected the initial child to be a regular file\n' >&2
    exit 1
fi

secret_hold=$(secret_hold_for_name "$relative")
media_type="application/pdf"
printf '[+] phase 1: observed %s as a regular direct child\n' "$relative"
printf '[+] phase 1: benign identity secret_hold=%s media_type=%s\n' "$secret_hold" "$media_type"

ln -s "$outside" "$scope/.replacement-link"
mv -f "$scope/.replacement-link" "$benign"
printf '[+] phase 2: replaced the direct child with a symlink to the outside target\n'

scan_hash=$(hash_file "$benign")
printf '[+] phase 3: scan raw_hash=sha256:%s\n' "$scan_hash"

index_hash=$(hash_file "$benign")
if [ "$scan_hash" != "$index_hash" ]; then
    printf '[!] unexpected mismatch: scan=%s index=%s\n' "$scan_hash" "$index_hash" >&2
    exit 1
fi
printf '[+] phase 4: later index hash matched the scan hash\n'

if grep -q 'SYNTHETIC_OUTSIDE_SECRET_TOKEN' "$benign"; then
    printf '[+] result: accepted identity=%s content_source=outside target\n' "$relative"
    printf '[+] result: synthetic outside marker reached through the benign path\n'
else
    printf '[!] outside marker was not reachable through the benign path\n' >&2
    exit 1
fi
