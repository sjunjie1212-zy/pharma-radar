"""NMPA / CDE 公告列表页解析。页面结构变化时只改这个文件。"""
from __future__ import annotations

import logging
import re
from datetime import date
from html import unescape
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


def _valid_date(value: str) -> bool:
    """校验 YYYY-MM-DD 是真实存在的日历日，拒绝 2026-13-40 这类形状正确但非法的日期。"""
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _nearest_date(html: str, start: int, end: int) -> str:
    """在链接前后各 200 字符内找最近的合法日期，找不到返回空串。"""
    match = _DATE.search(html[end : end + 200]) or _DATE.search(html[max(0, start - 200) : start])
    if not match:
        return ""
    value = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return value if _valid_date(value) else ""


def parse_listing(html: str, source: str, weight: float = 1.2, base: str = BASE) -> list[dict]:
    items: list[dict] = []
    for match in _LINK.finditer(html):
        href, raw_title = match.group(1), match.group(2)
        title = unescape(re.sub(r"\s+", " ", raw_title).strip())
        if not title or href.startswith("javascript"):
            continue
        date = _nearest_date(html, match.start(), match.end())
        if not date:  # 导航/页脚链接没有日期，不进入 Item 流
            continue
        items.append(
            make_item(
                title=title,
                url=canonical_url(urljoin(base, href)),
                source=source,
                published_at=f"{date}T00:00:00+08:00",
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
            items = parse_listing(resp.text, cfg["source"], cfg["weight"], base=cfg["url"])
            log.info("source %s: %d items", cfg["source"], len(items))
            out.extend(items)
        except Exception as exc:
            log.warning("source %s failed: %s", cfg["source"], exc)
    return out
