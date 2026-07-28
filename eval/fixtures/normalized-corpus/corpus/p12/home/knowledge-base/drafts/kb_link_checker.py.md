```py
#!/usr/bin/env python3
"""ナレッジベースの公開前リンクをまとめて確認する小さな補助ツール。"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LOG = logging.getLogger("kb_link_checker")


@dataclass(frozen=True)
class LinkCheck:
    url: str
    status: int | None
    detail: str

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 400


def load_urls(list_file: Path) -> list[str]:
    """空行とコメントを除き、確認対象の URL だけを返す。"""
    urls: list[str] = []
    for raw_line in list_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def check_link(url: str, timeout: float) -> LinkCheck:
    request = Request(
        url,
        headers={
            "User-Agent": "Harborline-KB-Link-Check/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return LinkCheck(url=url, status=response.status, detail="reachable")
    except HTTPError as error:
        return LinkCheck(url=url, status=error.code, detail=error.reason)
    except URLError as error:
        return LinkCheck(url=url, status=None, detail=str(error.reason))


def main() -> int:
    parser = argparse.ArgumentParser(description="ナレッジ記事の外部リンク確認")
    parser.add_argument("url_list", type=Path, help="1 行 1 URL のテキストファイル")
    parser.add_argument("--timeout", type=float, default=8.0, help="接続待ち秒数")
    parser.add_argument("--workers", type=int, default=4, help="同時確認数")
    args = parser.parse_args()

    urls = load_urls(args.url_list)
    if not urls:
        LOG.warning("確認対象がありません: %s", args.url_list)
        return 0

    failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(check_link, url, args.timeout) for url in urls]
        for future in as_completed(futures):
            result = future.result()
            mark = "OK" if result.ok else "NG"
            status = str(result.status) if result.status is not None else "-"
            print(f"{mark}\t{status}\t{result.url}\t{result.detail}")
            failed += int(not result.ok)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
```
