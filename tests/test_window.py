import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pipeline.window import in_window, parse_timestamp, stamp_issue_date

CST = ZoneInfo("Asia/Shanghai")


def item(published_at, date=""):
    return {"published_at": published_at, "date": date, "title": "x"}


class TestParseTimestamp(unittest.TestCase):
    def test_rfc2822(self):
        ts = parse_timestamp("Tue, 03 Nov 2026 10:00:00 +0800")
        self.assertEqual(ts.astimezone(CST).strftime("%Y-%m-%d %H:%M"), "2026-11-03 10:00")

    def test_iso_with_offset(self):
        ts = parse_timestamp("2026-11-03T10:00:00+08:00")
        self.assertEqual(ts.strftime("%Y-%m-%d %H:%M"), "2026-11-03 10:00")

    def test_naive_iso_is_cst(self):
        ts = parse_timestamp("2026-11-03T00:00:00")
        self.assertEqual(ts.utcoffset(), timedelta(hours=8))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_timestamp("not a date"))


class TestInWindow(unittest.TestCase):
    now = datetime(2026, 11, 3, 19, 0, tzinfo=CST)

    def test_overnight_item_included(self):
        # 前一日 23:00 发布，属于本期
        self.assertTrue(in_window(item("Mon, 02 Nov 2026 23:00:00 +0800"), self.now))

    def test_yesterday_afternoon_excluded(self):
        self.assertFalse(in_window(item("Mon, 02 Nov 2026 15:00:00 +0800"), self.now))

    def test_today_before_run_included(self):
        self.assertTrue(in_window(item("Tue, 03 Nov 2026 18:59:00 +0800"), self.now))

    def test_exactly_24h_old_excluded(self):
        self.assertFalse(in_window(item("Mon, 02 Nov 2026 19:00:00 +0800"), self.now))

    def test_date_only_falls_back_to_today(self):
        self.assertTrue(in_window(item("2026-11-03T00:00:00+08:00", "2026-11-03"), self.now))

    def test_empty_timestamp_uses_date(self):
        self.assertTrue(in_window(item("", "2026-11-03"), self.now))
        self.assertFalse(in_window(item("", "2026-11-02"), self.now))


class TestStampIssueDate(unittest.TestCase):
    def test_overnight_gets_run_date(self):
        now = datetime(2026, 11, 3, 19, 0, tzinfo=CST)
        stamped = stamp_issue_date(item("Mon, 02 Nov 2026 23:00:00 +0800", "2026-11-02"), now)
        self.assertEqual(stamped["date"], "2026-11-03")
        self.assertEqual(stamped["published_at"], "Mon, 02 Nov 2026 23:00:00 +0800")

    def test_same_day_unchanged(self):
        now = datetime(2026, 11, 3, 19, 0, tzinfo=CST)
        stamped = stamp_issue_date(item("Tue, 03 Nov 2026 10:00:00 +0800", "2026-11-03"), now)
        self.assertEqual(stamped["date"], "2026-11-03")

    def test_returns_copy(self):
        original = item("Tue, 03 Nov 2026 10:00:00 +0800", "2026-11-02")
        now = datetime(2026, 11, 3, 19, 0, tzinfo=CST)
        stamped = stamp_issue_date(original, now)
        self.assertIsNot(stamped, original)
        self.assertEqual(original["date"], "2026-11-02")


class TestDateFallbackAtDifferentRunTimes(unittest.TestCase):
    """无时间戳时按「date == 运行日（北京时间）」判断，与运行时刻无关。"""

    def test_pre_noon_run_today_date_included(self):
        now = datetime(2026, 11, 3, 10, 0, tzinfo=CST)
        self.assertTrue(in_window(item("", "2026-11-03"), now))

    def test_pre_noon_run_yesterday_date_excluded(self):
        now = datetime(2026, 11, 3, 10, 0, tzinfo=CST)
        self.assertFalse(in_window(item("", "2026-11-02"), now))

    def test_early_morning_run_today_date_included(self):
        now = datetime(2026, 11, 3, 1, 0, tzinfo=CST)
        self.assertTrue(in_window(item("", "2026-11-03"), now))

    def test_early_morning_run_yesterday_date_excluded(self):
        now = datetime(2026, 11, 3, 1, 0, tzinfo=CST)
        self.assertFalse(in_window(item("", "2026-11-02"), now))

    def test_unparseable_timestamp_uses_date(self):
        now = datetime(2026, 11, 3, 10, 0, tzinfo=CST)
        self.assertTrue(in_window(item("garbage", "2026-11-03"), now))
        self.assertFalse(in_window(item("garbage", "2026-11-02"), now))


class TestUtcOffsets(unittest.TestCase):
    """UTC 时间先换算到北京时间再比较。"""

    now = datetime(2026, 11, 3, 19, 0, tzinfo=CST)

    def test_rfc2822_utc_converted_to_cst(self):
        # 10:00 UTC = 18:00 CST，在本期窗口内
        self.assertTrue(in_window(item("Tue, 03 Nov 2026 10:00:00 +0000"), self.now))
        # 16:00 UTC = 次日 00:00 CST，晚于运行时刻；若按 UTC 字面比较会误判为入选
        self.assertFalse(in_window(item("Tue, 03 Nov 2026 16:00:00 +0000"), self.now))

    def test_iso_z_converted_to_cst(self):
        self.assertTrue(in_window(item("2026-11-03T10:00:00Z"), self.now))
        self.assertFalse(in_window(item("2026-11-03T16:00:00Z"), self.now))

    def test_local_date_differs_from_utc_date(self):
        ts = parse_timestamp("2026-11-03T16:00:00Z")
        self.assertEqual(ts.astimezone(CST).strftime("%Y-%m-%d %H:%M"), "2026-11-04 00:00")


if __name__ == "__main__":
    unittest.main()
