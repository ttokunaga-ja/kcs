```sh
#!/usr/bin/env bash
# 銀行明細CSVをOrionの入金消込待ち一覧へ渡す前の簡易検査。
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 SOURCE_CSV OUTPUT_CSV" >&2
  exit 64
fi

source_file=$1
output_file=$2
required_header='取引日,摘要,お預入れ金額,お引出し金額,残高'

header=$(head -n 1 "$source_file" | tr -d '\r')
if [[ "$header" != "$required_header" ]]; then
  echo "unexpected bank CSV header" >&2
  exit 65
fi

# ヘッダを保ったまま空行と広告行を除外し、取込用ディレクトリへ保存する。
awk -F',' 'NR == 1 || ($1 ~ /^[0-9][0-9][0-9][0-9]\/[0-9][0-9]\/[0-9][0-9]$/ && $2 !~ /キャンペーン/) { print }' \
  "$source_file" > "$output_file"

row_count=$(($(wc -l < "$output_file") - 1))
echo "validated bank rows=${row_count} output=${output_file}"
```
