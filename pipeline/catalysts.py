"""催化剂日历：未来事件的独立存储（data/catalysts.json）。

与条目流分开：条目是一次性新闻，催化剂是可被改期、到期后应消失的未来事件，
所以每次运行按 id 合并后重写，而不是只追加。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")
KINDS = ("读出", "审批决定", "会议", "政策窗口")


def _catalyst_id(*, source: str, kind: str, entity: str, drug: str, note: str) -> str:
    # 不含 date：申办方改期时用同一个 id 覆盖旧记录。
    raw = "|".join((source, kind, entity.lower(), drug.lower(), note))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def make_catalyst(*, date: str, kind: str, entity: str, drug: str = "",
                  note: str = "", source: str = "") -> dict:
    if kind not in KINDS:
        raise ValueError(f"未知催化剂类型 {kind!r}，允许：{KINDS}")
    return {
        "id": _catalyst_id(source=source, kind=kind, entity=entity, drug=drug, note=note),
        "date": date,
        "kind": kind,
        "entity": entity,
        "drug": drug,
        "note": note,
        "source": source,
    }


def merge(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """按 id 覆盖：同一事件以本次抓取为准。"""
    by_id = {c["id"]: c for c in existing}
    for c in incoming:
        by_id[c["id"]] = c
    return list(by_id.values())


def _valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return True


def prune(records: list[dict], today: str) -> list[dict]:
    """丢掉已经过去或日期非法的条目。"""
    return [c for c in records if _valid_date(c.get("date", "")) and c["date"] >= today]


def _sort_key(c: dict):
    return (c.get("date", ""), c.get("entity", ""), c.get("drug", ""))


def write(records: list[dict], out_path: str = "data/catalysts.json") -> dict:
    payload = {
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "catalysts": sorted(records, key=_sort_key),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    js_path = os.path.splitext(out_path)[0] + ".js"
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write("window.__CATALYSTS__ = " + text + ";\n")
    return payload


def load(path: str = "data/catalysts.json") -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return []
    rows = data.get("catalysts")
    return rows if isinstance(rows, list) else []
