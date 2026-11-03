"""落盘与构建：jsonl 是唯一事实来源，items.json 是派生产物。"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")


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


def build(items: list[dict], out_path: str = "data/items.json") -> dict:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_date[item.get("date") or ""].append(item)

    days = []
    for date in sorted(by_date, reverse=True):
        rows = sorted(
            by_date[date],
            key=lambda i: (i.get("m", 0), i.get("source_weight", 0.0), i.get("published_at", "")),
            reverse=True,
        )
        days.append({"date": date, "must": [r["id"] for r in rows if _is_must(r)], "items": rows})

    payload = {
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "days": days,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    return payload
