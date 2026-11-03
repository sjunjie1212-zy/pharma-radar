"""日报窗口：前一日 19:00 至当日 19:00。

窗口以「当期锚点」为终点、向前 24 小时。定时运行时锚点就是运行时刻；传入
``--date`` 时锚点固定为该日 19:00（见 ``resolve_anchor``），因此窗口是严格的
[date-1 19:00, date 19:00)，与运行时刻无关。
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def resolve_anchor(date_arg: str | None) -> datetime:
    """把 ``--date`` 参数解析成当期锚点。

    无参数时返回当前北京时间；有参数时返回该日 19:00 北京时间。格式非法抛
    ValueError，避免把 "x" 之类的值当成月份写进 data/raw/。
    """
    if date_arg is None:
        return datetime.now(CST)
    try:
        day = date.fromisoformat(date_arg)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"--date 需要 YYYY-MM-DD 格式，收到 {date_arg!r}") from exc
    return datetime.combine(day, time(19, 0), tzinfo=CST)


def parse_timestamp(text: str) -> datetime | None:
    """把 RFC 2822 或 ISO 8601 时间串解析成带时区的 datetime；失败返回 None。"""
    if not text:
        return None
    try:
        ts = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        ts = None
    if ts is None:
        try:
            ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=CST)
    return ts


def in_window(item: dict, now: datetime) -> bool:
    ts = parse_timestamp(item.get("published_at", ""))
    if ts is None:
        # 时间戳缺失或解析失败时，退回到「date == 本期日期（北京时间）」。
        # 平时本期日期就是运行日；`--date` 补跑时是补跑的那一期，与运行时刻无关。
        return item.get("date", "") == now.astimezone(CST).strftime("%Y-%m-%d")
    if _DATE_ONLY.match((item.get("published_at") or "").strip()):
        # 结构化源（临床试验、openFDA、PubMed）只给日期。窗口跨两个日历日，
        # 落在其中任何一天都无法排除，两天都收。
        anchor_day = now.astimezone(CST).date()
        day = ts.astimezone(CST).date()
        return day in (anchor_day, anchor_day - timedelta(days=1))
    start = now - timedelta(hours=24)
    # 左边界取开区间：恰好 24 小时前发布的条目属于上一期（见 test_exactly_24h_old_excluded）。
    return start < ts < now


def stamp_issue_date(item: dict, now: datetime) -> dict:
    """把条目的 date 改写为本期日期，published_at 保持不变；返回新 dict。"""
    stamped = dict(item)
    stamped["date"] = now.astimezone(CST).strftime("%Y-%m-%d")
    return stamped
