"""openFDA Drugs@FDA：NDA/BLA 原始批准。仿制药（ANDA）与补充申请不入日报。"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from sources.base import make_item

log = logging.getLogger(__name__)

API = "https://api.fda.gov/drug/drugsfda.json"
LABEL_URL = ("https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm"
             "?event=overview.process&ApplNo=")
LOOKBACK_DAYS = 30


def _ymd(value: str) -> str:
    """YYYYMMDD -> YYYY-MM-DD；格式不符返回空串。"""
    text = (value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return ""
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def parse_results(results: list[dict]) -> list[dict]:
    out: list[dict] = []
    for record in results or []:
        number = (record.get("application_number") or "").upper()
        if not (number.startswith("NDA") or number.startswith("BLA")):
            continue
        approved = [
            sub for sub in record.get("submissions") or []
            if sub.get("submission_type") == "ORIG"
            and sub.get("submission_status") == "AP"
            and _ymd(sub.get("submission_status_date", ""))
        ]
        if not approved:
            continue
        latest = max(approved, key=lambda s: s["submission_status_date"])
        product = (record.get("products") or [{}])[0]
        brand = (product.get("brand_name") or "").strip()
        ingredients = [i.get("name", "").strip()
                       for i in product.get("active_ingredients") or []]
        ingredient = ingredients[0] if ingredients else ""
        label = brand or ingredient
        if not label:
            continue
        title = f"FDA approves {label}"
        if ingredient and ingredient.lower() != brand.lower():
            title += f" ({ingredient})"
        sponsor = (record.get("sponsor_name") or "").strip()
        out.append(make_item(
            title=title,
            url=LABEL_URL + number[3:],
            source="openfda",
            published_at=_ymd(latest["submission_status_date"]),
            source_weight=1.3,
            lang="en",
            company=[sponsor] if sponsor else [],
            drug=list(dict.fromkeys(d for d in (brand, ingredient) if d)),
            event_type="regulatory",
        ))
    return out


def fetch_all(days: int = LOOKBACK_DAYS, today: date | None = None,
              timeout: int = 30) -> list[dict]:
    today = today or date.today()
    start = (today - timedelta(days=days)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    params = {
        # openFDA 的 TO 是空格分隔的语法；requests 会把空格编码成 +。
        "search": (f"submissions.submission_status_date:[{start} TO {end}]"
                   " AND submissions.submission_type:ORIG"),
        "limit": 100,
    }
    resp = requests.get(API, params=params, timeout=timeout,
                        headers={"User-Agent": "pharma-radar/0.1"})
    if resp.status_code == 404:  # openFDA 用 404 表示「没有匹配」，不是故障
        log.info("openfda: no approvals in window")
        return []
    resp.raise_for_status()
    floor = (today - timedelta(days=days)).isoformat()
    # 区间命中可能来自同一申请下的其它 submission，原始批准日期要在本地再卡一次。
    return [i for i in parse_results(resp.json().get("results") or [])
            if i["published_at"] >= floor]
