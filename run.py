"""药脉每日流水线。用法：python3 run.py [--date 2026-11-03]"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline.build import append_raw, build, load_raw
from pipeline.dedupe import assign_clusters, dedupe
from pipeline.scoring import enrich
from pipeline.select import select
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

    today = args.date
    fresh = [i for i in collect() if i.get("date") == today]
    fresh = [enrich(i) for i in fresh]
    fresh = assign_clusters(dedupe(fresh))
    chosen = select(fresh)

    added = append_raw(chosen, month=today[:7])
    payload = build(load_raw())
    log.info("date=%s fetched=%d selected=%d added=%d days=%d",
             today, len(fresh), len(chosen), added, len(payload["days"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
