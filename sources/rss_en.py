# sources/rss_en.py
"""英文医药新闻源：解析 RSS 2.0 与 Atom，统一产出 Item。"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

from sources.base import canonical_url, item_id, make_item

log = logging.getLogger(__name__)

FEEDS = [
    {"source": "endpoints", "url": "https://endpoints.news/feed/", "weight": 1.3},
    {"source": "fierce-biotech", "url": "https://www.fiercebiotech.com/rss/xml", "weight": 1.1},
    {"source": "fierce-pharma", "url": "https://www.fiercepharma.com/rss/xml", "weight": 1.1},
    {"source": "stat", "url": "https://www.statnews.com/feed/", "weight": 1.2},
    {"source": "biopharmadive", "url": "https://www.biopharmadive.com/feeds/news/", "weight": 1.0},
    {"source": "nature-biotech", "url": "https://www.nature.com/nbt.rss", "weight": 1.3},
]

ATOM = "{http://www.w3.org/2005/Atom}"


def _text(node, tag: str) -> str:
    child = node.find(tag)
    return (child.text or "").strip() if child is not None else ""


def parse_feed(xml_bytes: bytes, source: str, weight: float = 1.0) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    entries: list[dict] = []
    for node in root.iter("item"):
        url = canonical_url(_text(node, "link"))
        if not url:
            continue
        entries.append(
            make_item(
                title=_text(node, "title"),
                url=url,
                source=source,
                published_at=_text(node, "pubDate"),
                source_weight=weight,
                lang="en",
            )
        )

    for node in root.iter(f"{ATOM}entry"):
        link = node.find(f"{ATOM}link")
        url = canonical_url((link.get("href") or "").strip() if link is not None else "")
        if not url:
            continue
        entries.append(
            make_item(
                title=_text(node, f"{ATOM}title"),
                url=url,
                source=source,
                published_at=_text(node, f"{ATOM}updated") or _text(node, f"{ATOM}published"),
                source_weight=weight,
                lang="en",
            )
        )

    return [e for e in entries if e["title"]]


def fetch_all(timeout: int = 20) -> list[dict]:
    out: list[dict] = []
    for feed in FEEDS:
        try:
            resp = requests.get(feed["url"], timeout=timeout, headers={"User-Agent": "pharma-radar/0.1"})
            resp.raise_for_status()
            items = parse_feed(resp.content, feed["source"], feed["weight"])
            log.info("feed %s: %d items", feed["source"], len(items))
            out.extend(items)
        except Exception as exc:  # 单源失败不影响整体
            log.warning("feed %s failed: %s", feed["source"], exc)
    return out
