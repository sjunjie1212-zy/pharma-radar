"""配额选择：防单一话题霸榜。"""
from __future__ import annotations


def _rank_key(item: dict):
    return (item.get("m", 0), item.get("source_weight", 0.0), item.get("published_at", ""))


def select(items, limit: int = 20, per_dim: int = 5, required=("D1", "D2", "D3", "D4", "D5")):
    ranked = sorted(items, key=_rank_key, reverse=True)
    chosen: list[dict] = []
    counts: dict[str, int] = {}

    for item in ranked:
        if len(chosen) >= limit:
            break
        dim = item.get("dimension", "D6")
        if counts.get(dim, 0) >= per_dim:
            continue
        chosen.append(item)
        counts[dim] = counts.get(dim, 0) + 1

    for dim in required:
        if counts.get(dim, 0) > 0:
            continue
        candidate = next((i for i in ranked if i.get("dimension") == dim and i not in chosen), None)
        if candidate is None:
            continue
        if len(chosen) >= limit:
            evict = min(
                (c for c in chosen if counts.get(c["dimension"], 0) > 1),
                key=_rank_key,
                default=None,
            )
            if evict is None:
                continue
            chosen.remove(evict)
            counts[evict["dimension"]] -= 1
        chosen.append(candidate)
        counts[dim] = counts.get(dim, 0) + 1

    return sorted(chosen, key=_rank_key, reverse=True)
