"""药脉每日流水线。用法：python3 run.py [--date 2026-11-03]"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline.build import append_raw, build, load_raw
from pipeline.dedupe import assign_clusters, dedupe
from pipeline.gate import filter_relevant
from pipeline.scoring import enrich
from pipeline.select import select
from pipeline.window import in_window, stamp_issue_date
from sources import reg_cn
from sources.rss_en import fetch_all

CST = ZoneInfo("Asia/Shanghai")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("run")


def collect() -> list[dict]:
    items: list[dict] = []
    for fn in (fetch_all, reg_cn.fetch_all):
        try:
            items.extend(fn())
        except Exception as exc:  # 单源失败不影响整体
            log.error("%s failed: %s", fn.__module__, exc)
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(CST).strftime("%Y-%m-%d"))
    args = parser.parse_args()

    now = datetime.now(CST)
    today = args.date

    collected = [enrich(i) for i in collect()]
    gated = filter_relevant(collected)
    log.info("gate: kept %d of %d", len(gated), len(collected))

    # 本期 = 运行时刻向前 24 小时。19:00 运行即「前一日 19:00 → 当日 19:00」。
    windowed = [stamp_issue_date(i, now) for i in gated if in_window(i, now)]
    log.info("window: kept %d of %d (issue=%s)", len(windowed), len(gated),
             now.astimezone(CST).strftime("%Y-%m-%d"))

    fresh = assign_clusters(dedupe(windowed))
    chosen = select(fresh)

    added = append_raw(chosen, month=today[:7])
    payload = build(load_raw())
    log.info("date=%s collected=%d selected=%d added=%d days=%d",
             today, len(collected), len(chosen), added, len(payload["days"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
