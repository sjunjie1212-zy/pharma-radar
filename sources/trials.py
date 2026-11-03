"""ClinicalTrials.gov API v2：新登记的 III 期研究，以及近期主要完成日期（催化剂）。"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from pipeline.catalysts import make_catalyst
from sources.base import make_item

log = logging.getLogger(__name__)

API = "https://clinicaltrials.gov/api/v2/studies"
BASE_URL = "https://clinicaltrials.gov/study/"
FIELDS = ",".join((
    "NCTId", "BriefTitle", "OverallStatus", "Phase", "LeadSponsorName",
    "StartDate", "PrimaryCompletionDate", "StudyFirstPostDate",
    "Condition", "InterventionName",
))
STATUSES = "RECRUITING|ACTIVE_NOT_RECRUITING"
ITEM_DAYS = 7
CATALYST_DAYS = 90


def _struct(node: dict, key: str) -> str:
    value = (node or {}).get(key)
    return (value or {}).get("date", "") if isinstance(value, dict) else ""


def parse_study(study: dict) -> dict | None:
    protocol = (study or {}).get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    nct = (ident.get("nctId") or "").strip()
    if not nct:
        return None
    status = protocol.get("statusModule") or {}
    sponsor = ((protocol.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {})
    conditions = (protocol.get("conditionsModule") or {}).get("conditions") or []
    drug = ""
    for intervention in (protocol.get("armsInterventionsModule") or {}).get("interventions") or []:
        name = (intervention.get("name") or "").strip()
        if name and name.lower() != "placebo":
            drug = name
            break
    return {
        "nct": nct,
        "title": (ident.get("briefTitle") or "").strip(),
        "sponsor": (sponsor.get("name") or "").strip(),
        "conditions": [c for c in conditions if c],
        "first_post": _struct(status, "studyFirstPostDateStruct"),
        "completion": _struct(status, "primaryCompletionDateStruct"),
        "drug": drug,
    }


def _fetch(params: dict, timeout: int = 30) -> list[dict]:
    resp = requests.get(API, params=params, timeout=timeout,
                        headers={"User-Agent": "pharma-radar/0.1"})
    resp.raise_for_status()
    studies = resp.json().get("studies") or []
    return [s for s in (parse_study(x) for x in studies) if s]


def _base_params() -> dict:
    return {
        "query.term": "AREA[Phase]PHASE3",
        "filter.overallStatus": STATUSES,
        "fields": FIELDS,
        "pageSize": 100,
    }


def fetch_items(days: int = ITEM_DAYS, today: date | None = None,
                timeout: int = 30) -> list[dict]:
    """近 days 天首次登记的 III 期研究。API 只做倒序取前 100 条，日期在本地筛。"""
    today = today or date.today()
    params = dict(_base_params(), sort="StudyFirstPostDate:desc")
    floor = (today - timedelta(days=days)).isoformat()
    out: list[dict] = []
    for study in _fetch(params, timeout):
        if not study["title"] or not study["first_post"] or study["first_post"] < floor:
            continue
        out.append(make_item(
            title=study["title"],
            url=BASE_URL + study["nct"],
            source="trials",
            published_at=study["first_post"],
            source_weight=1.1,
            lang="en",
            company=[study["sponsor"]] if study["sponsor"] else [],
            drug=[study["drug"]] if study["drug"] else [],
            ta=study["conditions"][:3],
            event_type="clinical",
        ))
    return out


def fetch_catalysts(today: date | None = None, days: int = CATALYST_DAYS,
                    timeout: int = 30) -> list[dict]:
    """主要完成日期在未来 days 天内的 III 期研究。"""
    today = today or date.today()
    end = today + timedelta(days=days)
    params = dict(
        _base_params(),
        sort="PrimaryCompletionDate:asc",
        **{"filter.advanced":
           f"AREA[PrimaryCompletionDate]RANGE[{today.isoformat()},{end.isoformat()}]"},
    )
    out: list[dict] = []
    for study in _fetch(params, timeout):
        completion = study["completion"]
        if len(completion) != 10:  # 月精度（2029-01）无法排期
            continue
        condition = "、".join(study["conditions"][:2])
        note = f"{condition}（{study['nct']}）" if condition else study["nct"]
        out.append(make_catalyst(
            date=completion,
            kind="读出",
            entity=study["sponsor"],
            drug=study["drug"],
            note=note,
            source="clinicaltrials.gov",
        ))
    return out


def fetch_all(timeout: int = 30) -> list[dict]:
    return fetch_items(timeout=timeout)
