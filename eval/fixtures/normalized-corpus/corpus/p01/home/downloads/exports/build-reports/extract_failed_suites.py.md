```py
"""CI の XML 要約から失敗したスイート名だけを取り出す。"""

from __future__ import annotations

from xml.etree import ElementTree as ET


def failed_suites(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    names: list[str] = []
    for suite in root.findall(".//testsuite"):
        if int(suite.attrib.get("failures", "0")) + int(suite.attrib.get("errors", "0")):
            names.append(suite.attrib.get("name", "unnamed-suite"))
    return sorted(set(names))


def release_summary(suites: list[str]) -> str:
    return "all focused checks passed" if not suites else f"follow up: {', '.join(suites)}"
```
