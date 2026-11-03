"""日报窗口：前一日 19:00 至当日 19:00。

等价于「以运行时刻为终点、向前 24 小时」。19:00 定时运行时与 spec 的 19:00 切点一致；
提前手动运行则窗口收紧，不会把更早的条目算进本期。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")


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


def _item_timestamp(item: dict, now: datetime) -> datetime | None:
    ts = parse_timestamp(item.get("published_at", ""))
    if ts is not None:
        return ts
    date_text = item.get("date", "")
    if not date_text:
        return None
    try:
        return datetime.fromisoformat(date_text).replace(hour=12, tzinfo=CST)
    except ValueError:
        return None


def in_window(item: dict, now: datetime) -> bool:
    ts = _item_timestamp(item, now)
    if ts is None:
        return False
    start = now - timedelta(hours=24)
    # 左边界取开区间：恰好 24 小时前发布的条目属于上一期（见 test_exactly_24h_old_excluded）。
    return start < ts < now


def stamp_issue_date(item: dict, now: datetime) -> dict:
    """把条目的 date 改写为本期日期，published_at 保持不变；返回新 dict。"""
    stamped = dict(item)
    stamped["date"] = now.astimezone(CST).strftime("%Y-%m-%d")
    return stamped
