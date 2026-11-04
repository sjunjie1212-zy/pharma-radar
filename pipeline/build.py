"""落盘与构建：jsonl 是唯一事实来源，items.json 是派生产物。"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline import summarize
from pipeline.gate import filter_relevant
from pipeline.select import select

CST = ZoneInfo("Asia/Shanghai")
log = logging.getLogger(__name__)


def append_raw(items: list[dict], month: str, raw_dir: str = "data/raw") -> int:
    os.makedirs(raw_dir, exist_ok=True)
    path = os.path.join(raw_dir, f"{month}.jsonl")
    seen: set[str] = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    seen.add(json.loads(line)["id"])

    new = [i for i in items if i["id"] not in seen]
    if new:
        with open(path, "a", encoding="utf-8") as fh:
            for item in new:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(new)


def load_raw(raw_dir: str = "data/raw") -> list[dict]:
    out: list[dict] = []
    if not os.path.isdir(raw_dir):
        return out
    for name in sorted(os.listdir(raw_dir)):
        if not name.endswith(".jsonl"):
            continue
        with open(os.path.join(raw_dir, name), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def _is_must(item: dict) -> bool:
    if item.get("m", 0) >= 5:
        return True
    return item.get("m", 0) >= 4 and item.get("dimension") in {"D1", "D3", "D4"}


def build(items: list[dict], out_path: str = "data/items.json",
          summaries_path: str = summarize.DEFAULT_PATH) -> dict:
    cache = summarize.load_cache(summaries_path)
    merged: list[dict] = []
    for item in items:
        entry = cache.get(item.get("id") or "")
        if entry and entry.get("title_zh"):
            merged.append({**item, "title_zh": entry["title_zh"]})
        else:
            merged.append(item)
    items = merged

    by_date: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_date[item.get("date") or ""].append(item)

    days = []
    for date in sorted(by_date, reverse=True):
        # 渲染时重跑一次主题门：raw 是累积的，早期较松的门或门出现之前的条目
        # 不能靠 build 再被发出来。
        day_rows = by_date[date]
        relevant = filter_relevant(day_rows)
        if len(relevant) != len(day_rows):
            log.info("gate: kept %d of %d (build, date=%s)",
                     len(relevant), len(day_rows), date)
        # 再截断一次：同日重跑会累积 raw，不能让配额在上游被绕过。
        rows = select(relevant)
        must = [r["id"] for r in rows if _is_must(r)][:5]
        days.append({"date": date, "must": must, "items": rows})

    payload = {
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "days": days,
    }
    json_text = json.dumps(payload, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(json_text)
    js_path = os.path.splitext(out_path)[0] + ".js"
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write("window.__ITEMS__ = " + json_text + ";\n")
    return payload
