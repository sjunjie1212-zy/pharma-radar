"""药脉每日流水线。用法：python3 run.py [--date 2026-11-03]"""
from __future__ import annotations

import argparse
import logging
from zoneinfo import ZoneInfo

from pipeline.build import append_raw, build, load_raw
from pipeline.dedupe import assign_clusters, dedupe
from pipeline.gate import filter_relevant
from pipeline.scoring import enrich
from pipeline.select import select
from pipeline.window import in_window, resolve_anchor, stamp_issue_date
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

    fresh = assign_clusters(dedupe(windowed))
    chosen = select(fresh)

    added = append_raw(chosen, month=today[:7])
    payload = build(load_raw())
    log.info("date=%s collected=%d selected=%d added=%d days=%d",
             today, len(collected), len(chosen), added, len(payload["days"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
