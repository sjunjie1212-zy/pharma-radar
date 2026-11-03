"""NMPA / CDE 公告列表页解析。页面结构变化时只改这个文件。"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import requests

from sources.base import canonical_url, make_item

log = logging.getLogger(__name__)

BASE = "https://www.nmpa.gov.cn"
SOURCES = [
    {"source": "nmpa", "url": f"{BASE}/yaopin/ypggtg/index.html", "weight": 1.4},
    {"source": "nmpa-news", "url": f"{BASE}/yaowen/ypjgyw/index.html", "weight": 1.2},
]

_LINK = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,})</a>', re.S)
_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _nearest_date(html: str, start: int, end: int) -> str:
    """在链接前后各 200 字符内找最近的日期，找不到返回空串。"""
    match = _DATE.search(html[end : end + 200]) or _DATE.search(html[max(0, start - 200) : start])
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else ""


def parse_listing(html: str, source: str, weight: float = 1.2, base: str = BASE) -> list[dict]:
    items: list[dict] = []
    for match in _LINK.finditer(html):
        href, raw_title = match.group(1), match.group(2)
        title = re.sub(r"\s+", " ", raw_title).strip()
        if not title or href.startswith("javascript"):
            continue
        date = _nearest_date(html, match.start(), match.end())
        items.append(
            make_item(
                title=title,
                url=canonical_url(urljoin(base, href)),
                source=source,
                published_at=f"{date}T00:00:00" if date else "",
                date=date,
                source_weight=weight,
                lang="zh",
            )
        )
    return items


def fetch_all(timeout: int = 20) -> list[dict]:
    out: list[dict] = []
    for cfg in SOURCES:
        try:
            resp = requests.get(cfg["url"], timeout=timeout, headers={"User-Agent": "pharma-radar/0.1"})
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            items = parse_listing(resp.text, cfg["source"], cfg["weight"])
            log.info("source %s: %d items", cfg["source"], len(items))
            out.extend(items)
        except Exception as exc:
            log.warning("source %s failed: %s", cfg["source"], exc)
    return out
