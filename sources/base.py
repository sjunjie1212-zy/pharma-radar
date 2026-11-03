"""Item 数据结构与 URL 规范化。所有源适配器都产出这里的 Item 字典。"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DIMENSIONS = ("D1", "D2", "D3", "D4", "D5", "D6")
EVENT_TYPES = ("deal", "clinical", "regulatory", "payment", "commercial", "science", "policy")

_TRACKING_EXACT = {"spm", "from", "ref", "source_id", "share", "trk"}
_TRAILING_PUNCT = re.compile(r"[\s。！？!?,，.；;：:]+$")


def canonical_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_EXACT
    ]
    return urlunsplit((scheme, netloc, path, urlencode(kept), ""))


def item_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def normalize_title(title: str) -> str:
    return re.sub(r"[\W_]+", "", (title or "").lower())


def parse_date(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, IndexError):
        pass
    try:
        cleaned = text.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def make_item(
    *,
    title: str,
    url: str,
    source: str,
    published_at: str,
    source_weight: float = 1.0,
    lang: str = "zh",
    title_zh: str = "",
    date: str = "",
    company: list[str] | None = None,
    drug: list[str] | None = None,
    target: list[str] | None = None,
    ta: list[str] | None = None,
) -> dict:
    published_at = (published_at or "").strip()
    return {
        "id": item_id(url),
        "date": date or parse_date(published_at),
        "published_at": published_at,
        "source": source,
        "source_weight": float(source_weight),
        "lang": lang,
        "title": _TRAILING_PUNCT.sub("", title or "").strip(),
        "title_zh": title_zh,
        "url": url,
        "company": list(company or []),
        "drug": list(drug or []),
        "target": list(target or []),
        "ta": list(ta or []),
        "event_type": "science",
        "dimension": "D6",
        "m": 1,
        "why": "",
        "cluster_id": "",
    }
