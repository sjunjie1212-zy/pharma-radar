"""去重与同事件聚类。

URL 去重在前；同事件判定用两个信号取大：标题序列相似度（近重复）与
中文二元组 Jaccard（换词改写）。聚类只打标签，折叠由 collapse_clusters
在选稿前完成——原始条目流仍是 append-only。
"""
from __future__ import annotations

from difflib import SequenceMatcher

from sources.base import normalize_title


def _key(item: dict) -> str:
    return normalize_title(item.get("title_zh") or item.get("title") or "")


def _bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)}


def similarity(a: str, b: str) -> float:
    a, b = normalize_title(a), normalize_title(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    ba, bb = _bigrams(a), _bigrams(b)
    jac = len(ba & bb) / len(ba | bb) if ba and bb else 0.0
    return max(seq, jac)


def dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
    return out


def _same_event(a: str, b: str, threshold: float, jaccard_threshold: float) -> bool:
    if not a or not b:
        return False
    if SequenceMatcher(None, a, b).ratio() >= threshold:
        return True
    ba, bb = _bigrams(a), _bigrams(b)
    if not ba or not bb:
        return False
    return len(ba & bb) / len(ba | bb) >= jaccard_threshold


def assign_clusters(items: list[dict], threshold: float = 0.85,
                    jaccard_threshold: float = 0.5) -> list[dict]:
    reps: list[tuple[str, str]] = []  # (归一化标题, cluster_id)
    for item in items:
        key = _key(item)
        matched = ""
        for rep_key, rep_id in reps:
            if _same_event(key, rep_key, threshold, jaccard_threshold):
                matched = rep_id
                break
        if matched:
            item["cluster_id"] = matched
        else:
            item["cluster_id"] = item["id"]
            reps.append((key, item["id"]))
    return items


def _rank(item: dict):
    return (item.get("m", 0), item.get("source_weight", 0.0),
            item.get("published_at", ""))


def collapse_clusters(items: list[dict]) -> list[dict]:
    """同一 cluster 只留排名最高的一条；没有 cluster_id 的条目不折叠。"""
    best: dict[str, dict] = {}
    for item in items:
        cid = item.get("cluster_id") or ""
        if not cid:
            continue
        current = best.get(cid)
        if current is None or _rank(item) > _rank(current):
            best[cid] = item
    out: list[dict] = []
    for item in items:
        cid = item.get("cluster_id") or ""
        if not cid or best[cid] is item:
            out.append(item)
    return out
