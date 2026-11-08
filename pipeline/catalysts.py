"""催化剂日历：未来事件的独立存储（data/catalysts.json）。

与条目流分开：条目是一次性新闻，催化剂是可被改期、到期后应消失的未来事件，
所以每次运行按 id 合并后重写，而不是只追加。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")
KINDS = ("读出", "审批决定", "会议", "政策窗口")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


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
    # 先卡死 YYYY-MM-DD 形状：3.11+ 的 fromisoformat 还接受 "20261103"、
    # "2026-W45-1" 等写法，若放进来 prune 的字符串比较就会失真。
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return False
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


def _atomic_write(path: str, text: str) -> None:
    """同目录临时文件 + os.replace，避免写到一半留下损坏文件。"""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-catalysts-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write(records: list[dict], out_path: str = "data/catalysts.json") -> dict:
    payload = {
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "catalysts": sorted(records, key=_sort_key),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    _atomic_write(out_path, text)
    js_path = os.path.splitext(out_path)[0] + ".js"
    _atomic_write(js_path, "window.__CATALYSTS__ = " + text + ";\n")
    return payload


def load(path: str = "data/catalysts.json") -> list[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        # 文件缺失、截断或编码损坏都不该让下一次运行崩掉。
        return []
    if not isinstance(data, dict):
        return []
    rows = data.get("catalysts")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and "id" in row]
