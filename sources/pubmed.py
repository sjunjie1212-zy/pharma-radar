"""PubMed E-utilities：近两日入库的指南与共识，进 D1 疾病格局。"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from sources.base import make_item

log = logging.getLogger(__name__)

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TERM = '(guideline[pt] OR "practice guideline"[pt])'
LOOKBACK_DAYS = 2


def _date_arg(day: date) -> str:
    return day.strftime("%Y/%m/%d")


def _item_date(sortpubdate: str, fallback: str) -> str:
    """sortpubdate 形如 2026/11/02 00:00；取到日。拿不到就用兜底日期。"""
    text = (sortpubdate or "").strip()
    if len(text) >= 10 and text[4] == "/" and text[7] == "/":
        return text[:10].replace("/", "-")
    return fallback if len(fallback) == 10 else ""


def parse_summaries(result: dict, fallback_date: str = "") -> list[dict]:
    out: list[dict] = []
    for pmid in result.get("uids") or []:
        record = result.get(pmid) or {}
        title = (record.get("title") or "").strip()
        if not title:
            continue
        day = _item_date(record.get("sortpubdate", ""), fallback_date)
        if not day:
            continue
        out.append(make_item(
            title=title,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            source="pubmed",
            published_at=day,
            source_weight=1.0,
            lang="en",
            event_type="science",
            dimension="D1",
        ))
    return out


def fetch_all(days: int = LOOKBACK_DAYS, today: date | None = None,
              timeout: int = 30) -> list[dict]:
    today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start = today - timedelta(days=days)
    search = requests.get(
        f"{BASE}/esearch.fcgi",
        params={
            "db": "pubmed",
            "retmode": "json",
            "retmax": 100,
            "sort": "pub date",
            "term": f"{TERM} AND ({_date_arg(start)}:{_date_arg(today)}[edat])",
        },
        timeout=timeout,
        headers={"User-Agent": "pharma-radar/0.1"},
    )
    search.raise_for_status()
    esearch = search.json().get("esearchresult")
    if not isinstance(esearch, dict):
        log.warning("pubmed: esearch returned no esearchresult")
        return []
    error = esearch.get("ERROR") or esearch.get("error")
    if error:
        # NCBI 限流与非法 term 都以 HTTP 200 + esearchresult.error 返回；记日志以免
        # 与「当天确实没有新指南」混为一谈。
        log.warning("pubmed: esearch rejected the query: %s", error)
        return []
    ids = esearch.get("idlist") or []
    if not ids:
        return []
    summary = requests.get(
        f"{BASE}/esummary.fcgi",
        params={"db": "pubmed", "retmode": "json", "id": ",".join(ids)},
        timeout=timeout,
        headers={"User-Agent": "pharma-radar/0.1"},
    )
    summary.raise_for_status()
    return parse_summaries(summary.json().get("result") or {},
                           fallback_date=today.isoformat())
