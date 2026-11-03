"""中文医药媒体列表页解析。页面结构变化时只改这个文件。

代理：环境变量 PHARMA_RADAR_PROXY，缺省本机 7890；设为空串时不走代理
（GitHub Actions 用）。决定见 spec §7 的 2026-11-04 条。
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta
from html import unescape
from urllib.parse import urljoin

import requests

from sources.base import CST, canonical_url, make_item

log = logging.getLogger(__name__)

DEFAULT_PROXY = "http://127.0.0.1:7890"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

BIOON_PAGES = 2
BIOON_URL = "https://news.bioon.com/{page}.html"
YAOZH_URL = "https://news.yaozh.com/"
DRUGTIMES_URL = "https://www.drugtimes.cn/"

_BIOON_ITEM = re.compile(r'<div class="item">(.*?)(?=<div class="item">|\Z)', re.S)
_BIOON_LINK = re.compile(r'<h2>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_BIOON_DATE = re.compile(r'item-meta-item">\s*(\d{4}-\d{2}-\d{2})')

_YAOZH_LINK = re.compile(
    r'<a[^>]+href="(/archive/\d+\.html)"[^>]*>\s*<div[^>]*title="([^"]+)"[^>]*>'
    r'.*?class="fr">\s*(\d{4}-\d{2}-\d{2})',
    re.S,
)

_DRUGTIMES_LINK = re.compile(
    r'<a[^>]+href="(https://www\.drugtimes\.cn/(\d{4})/(\d{2})/(\d{2})/[^"]+)"[^>]*>(.*?)</a>',
    re.S,
)

_TAG = re.compile(r"<[^>]+>")


def proxies() -> dict[str, str] | None:
    value = os.environ.get("PHARMA_RADAR_PROXY", DEFAULT_PROXY).strip()
    return {"http": value, "https": value} if value else None


def _get(url: str, timeout: int) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": UA},
                        proxies=proxies())
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG.sub(" ", raw))).strip()


def _item(title: str, url: str, source: str, day: str, weight: float) -> dict:
    return make_item(
        title=title,
        url=canonical_url(url),
        source=source,
        published_at=f"{day}T00:00:00+08:00",
        date=day,
        source_weight=weight,
        lang="zh",
    )


def parse_bioon(html: str, base: str = "https://news.bioon.com/") -> list[dict]:
    items: list[dict] = []
    for block in _BIOON_ITEM.findall(html):
        link = _BIOON_LINK.search(block)
        day = _BIOON_DATE.search(block)
        if not link or not day:
            continue
        title = _clean(link.group(2))
        if len(title) < 6:
            continue
        items.append(_item(title, urljoin(base, link.group(1)), "bioon",
                           day.group(1), 1.3))
    return items


def parse_yaozh(html: str, base: str = "https://news.yaozh.com") -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for href, raw_title, day in _YAOZH_LINK.findall(html):
        url = base.rstrip("/") + href
        title = _clean(raw_title)
        if not title or url in seen:
            continue
        seen.add(url)
        items.append(_item(title, url, "yaozh", day, 1.2))
    return items


def parse_drugtimes(html: str, base: str = "https://www.drugtimes.cn") -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for href, year, month, day, raw_title in _DRUGTIMES_LINK.findall(html):
        title = _clean(raw_title)
        if len(title) < 6 or href in seen:
            continue
        seen.add(href)
        items.append(_item(title, href, "drugtimes",
                           f"{year}-{month}-{day}", 1.2))
    return items


def fetch_all(days: int = 2, today: date | None = None,
              timeout: int = 20) -> list[dict]:
    today = today or datetime.now(CST).date()
    floor = (today - timedelta(days=days - 1)).isoformat()
    plan = [
        ("bioon", [BIOON_URL.format(page=p) for p in range(1, BIOON_PAGES + 1)],
         parse_bioon),
        ("yaozh", [YAOZH_URL], parse_yaozh),
        ("drugtimes", [DRUGTIMES_URL], parse_drugtimes),
    ]
    out: list[dict] = []
    for name, urls, parser in plan:
        try:
            parsed: list[dict] = []
            for url in urls:
                parsed.extend(parser(_get(url, timeout), url))
            fresh = [i for i in parsed if i["date"] and i["date"] >= floor]
            log.info("source %s: %d parsed, %d fresh", name, len(parsed), len(fresh))
            out.extend(fresh)
        except Exception as exc:
            log.warning("source %s failed: %s", name, exc)
    return out
