```py
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SPEAKER_PREFIX = re.compile(r"^\s*(?:\[([^\]]+)\]|([^:：]+)[:：])\s*")
BLANK_LINES = re.compile(r"\n{3,}")


def clean_line(line: str) -> str:
    """転記時に混ざる余分な空白と引用記号だけを整える。"""
    line = line.replace("\r\n", "\n").replace("\r", "\n")
    line = line.replace("\u3000", " ").rstrip()
    return re.sub(r"^[>＞]\s?", "", line)


def normalize_transcript(raw: str) -> str:
    """会話の順序を変えずに、読み返し用の本文を作る。"""
    rows: list[str] = []
    for original in raw.splitlines():
        line = clean_line(original)
        if not line:
            rows.append("")
            continue

        match = SPEAKER_PREFIX.match(line)
        if match:
            speaker = (match.group(1) or match.group(2) or "").strip()
            body = line[match.end() :].strip()
            rows.append(f"[{speaker}] {body}")
        else:
            rows.append(line)

    text = "\n".join(rows).strip()
    return BLANK_LINES.sub("\n\n", text) + ("\n" if text else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="会話転記をレビュー用に整形する")
    parser.add_argument("input", type=Path, help="受け取った転記ファイル")
    parser.add_argument("output", type=Path, help="整形後の保存先")
    args = parser.parse_args()

    raw = args.input.read_text(encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(normalize_transcript(raw), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
