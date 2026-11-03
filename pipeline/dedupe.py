"""去重与同事件聚类。聚类只做粗分：URL 去重 + 标题相似度。"""
from __future__ import annotations

from difflib import SequenceMatcher

from sources.base import normalize_title


def _key(item: dict) -> str:
    return normalize_title(item.get("title_zh") or item.get("title") or "")


def dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
    return out


def assign_clusters(items: list[dict], threshold: float = 0.85) -> list[dict]:
    reps: list[tuple[str, str]] = []  # (归一化标题, cluster_id)
    for item in items:
        key = _key(item)
        matched = ""
        for rep_key, rep_id in reps:
            if key and rep_key and SequenceMatcher(None, key, rep_key).ratio() >= threshold:
                matched = rep_id
                break
        if matched:
            item["cluster_id"] = matched
        else:
            item["cluster_id"] = item["id"]
            reps.append((key, item["id"]))
    return items
