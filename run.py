"""药脉每日流水线。用法：python3 run.py [--date 2026-11-03]"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline import catalysts
from pipeline.build import append_raw, build, load_raw
from pipeline.dedupe import assign_clusters, collapse_clusters, dedupe
from pipeline.gate import filter_relevant
from pipeline.scoring import enrich
from pipeline.select import select
from pipeline.window import in_window, resolve_anchor, stamp_issue_date
from sources import media_cn, openfda, pubmed, reg_cn, trials
from sources.rss_en import fetch_all as fetch_rss

CST = ZoneInfo("Asia/Shanghai")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("run")


def collect() -> list[dict]:
    items: list[dict] = []
    for fn in (fetch_rss, reg_cn.fetch_all, trials.fetch_all,
               openfda.fetch_all, pubmed.fetch_all, media_cn.fetch_all):
        try:
            items.extend(fn())
        except Exception as exc:  # 单源失败不影响整体
            log.error("%s failed: %s", fn.__module__, exc)
    return items


def update_catalysts(anchor: datetime, timeout: int = 30,
                     path: str = "data/catalysts.json") -> dict:
    """读旧文件 → 抓新催化剂 → 合并 → 丢弃过去 → 写回。

    抓取失败时保留旧数据并照常裁剪：过期事件仍然要消失。
    """
    today = anchor.astimezone(CST).date()
    existing = catalysts.load(path)
    try:
        fresh = trials.fetch_catalysts(today=today, timeout=timeout)
    except Exception as exc:
        log.error("catalysts: clinicaltrials failed: %s", exc)
        fresh = []
    merged = catalysts.prune(catalysts.merge(existing, fresh), today.isoformat())
    log.info("catalysts: existing=%d fresh=%d kept=%d",
             len(existing), len(fresh), len(merged))
    return catalysts.write(merged, out_path=path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None,
                        help="期号日期 YYYY-MM-DD，锚定该日 19:00；默认运行时刻")
    args = parser.parse_args()

    try:
        anchor = resolve_anchor(args.date)
    except ValueError as exc:
        parser.error(str(exc))

    today = anchor.astimezone(CST).strftime("%Y-%m-%d")

    collected = [enrich(i) for i in collect()]
    gated = filter_relevant(collected)
    log.info("gate: kept %d of %d", len(gated), len(collected))

    # 本期 = 锚点向前 24 小时。锚点为 19:00 即「前一日 19:00 → 当日 19:00」。
    windowed = [stamp_issue_date(i, anchor) for i in gated if in_window(i, anchor)]
    log.info("window: kept %d of %d (issue=%s)", len(windowed), len(gated), today)

    fresh = collapse_clusters(assign_clusters(dedupe(windowed)))
    known = {i["id"] for i in load_raw()}
    pending = [i for i in fresh if i["id"] not in known]
    chosen = select(pending)
    log.info("pending: %d of %d after known-id filter", len(pending), len(fresh))

    added = append_raw(chosen, month=today[:7])
    payload = build(load_raw())
    log.info("date=%s collected=%d selected=%d added=%d days=%d",
             today, len(collected), len(chosen), added, len(payload["days"]))

    try:
        update_catalysts(anchor)
    except Exception as exc:  # 催化剂更新失败不影响已生成的日报
        log.error("catalysts update failed: %s", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
