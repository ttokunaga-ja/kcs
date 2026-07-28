```py
"""Small helper retained from an early data-room export."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

MAIN_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def extract_comments(workbook: Path) -> list[dict[str, str]]:
    """Return visible legacy-comment text without modifying the workbook."""
    comments: list[dict[str, str]] = []
    with ZipFile(workbook) as archive:
        for name in archive.namelist():
            if not name.startswith("xl/comments") or not name.endswith(".xml"):
                continue
            root = ET.fromstring(archive.read(name))
            for comment in root.findall(".//a:comment", MAIN_NS):
                fragments = [node.text or "" for node in comment.findall(".//a:t", MAIN_NS)]
                comments.append({"cell": comment.get("ref", ""), "text": "".join(fragments).strip()})
    return comments


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args()
    for entry in extract_comments(args.workbook):
        print(f"{entry['cell']}: {entry['text']}")
```
