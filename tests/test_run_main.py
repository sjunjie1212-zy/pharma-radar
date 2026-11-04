import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import run

CST = ZoneInfo("Asia/Shanghai")
ANCHOR = datetime(2026, 11, 3, 19, 0, tzinfo=CST)
DIMS = ("D1", "D2", "D3", "D4", "D5", "D6")
COMPANIES = (
    "恒瑞医药", "百济神州", "信达生物", "君实生物", "复星医药",
    "石药集团", "中国生物", "绿叶制药", "先声药业", "翰森制药",
    "康方生物", "再鼎医药", "和黄医药", "贝达药业", "荣昌生物",
    "康希诺", "智飞生物", "沃森生物", "长春高新", "通化东宝",
    "华东医药", "京新药业", "科伦药业", "丽珠集团", "双鹭药业",
)


def _item(i, title, dimension="D3"):
    return {
        "id": i, "date": "2026-11-03", "published_at": "2026-11-03T10:00:00+08:00",
        "source": "bioon", "source_weight": 1.3, "lang": "zh", "title": title,
        "title_zh": "", "url": "u" + i, "company": [], "drug": [], "target": [],
        "ta": [], "event_type": "regulatory", "dimension": dimension, "m": 3,
        "why": "", "cluster_id": "",
    }


class TestMainOrdering(unittest.TestCase):
    def _run(self, collected, existing, on_summarize=None, on_save=None):
        """跑一遍 main()，返回落档结果、事件顺序与提炼入参。"""
        appended = []
        events = []
        summarize_items = []
        saved = {}

        def fake_summarize(items, cache, **kwargs):
            events.append("summarize")
            summarize_items.append(list(items))
            if on_summarize is not None:
                on_summarize(items, cache)
            return cache

        def fake_save(cache, path=None):
            events.append("save")
            saved["cache"] = cache
            if on_save is not None:
                on_save(cache, path)

        def fake_append(chosen, month=None):
            events.append("append")
            appended.extend(chosen)
            return len(chosen)

        with mock.patch("sys.argv", ["run.py"]), \
             mock.patch.object(run, "collect", return_value=collected), \
             mock.patch.object(run, "filter_relevant", side_effect=lambda x: x), \
             mock.patch.object(run, "load_raw", return_value=existing), \
             mock.patch.object(run, "append_raw", side_effect=fake_append), \
             mock.patch.object(run, "build", return_value={"days": []}), \
             mock.patch.object(run, "update_catalysts", return_value={}), \
             mock.patch.object(run.summarize, "load_cache", return_value={}), \
             mock.patch.object(run.summarize, "summarize", side_effect=fake_summarize), \
             mock.patch.object(run.summarize, "save_cache", side_effect=fake_save), \
             mock.patch.object(run, "resolve_anchor", return_value=ANCHOR):
            self.assertEqual(run.main(), 0)
        return {"appended": appended, "events": events,
                "summarize_items": summarize_items, "cache": saved.get("cache")}

    def test_already_stored_items_do_not_consume_quota(self):
        stored = [_item("old", "昨日旧条目")]
        # 旧条目排到当天最晚，否则 limit=20 会先把它挤出去，测不到 known-id 过滤。
        stored[0]["published_at"] = "2026-11-03T18:00:00+08:00"
        fresh = [_item("new", "今天的新条目")]
        # 六个维度轮转，避免 per_dim=5 把条数卡在 5；26 条足够填满 limit=20。
        # 填充标题要彼此不相似，否则会被同事件聚类折叠，同样填不满配额。
        fresh.extend(_item(f"filler{n}", f"{COMPANIES[n]}：第{n}条简讯", DIMS[n % 6])
                     for n in range(25))
        appended = self._run(fresh + stored, stored)["appended"]
        ids = [i["id"] for i in appended]
        self.assertIn("new", ids)
        self.assertNotIn("old", ids)
        self.assertEqual(len(ids), 20)

    def test_collapsed_duplicate_not_appended_twice(self):
        a = _item("a", "特宝生物10mg获批，长效生长激素的规格竞争")
        b = _item("b", "特宝生物长效生长激素10mg规格获批")
        appended = self._run([a, b], [])["appended"]
        self.assertEqual([i["id"] for i in appended], ["a"])

    def test_summarize_receives_history_and_chosen(self):
        stored = [_item("old", "昨日旧条目")]
        fresh = [_item("new", "今天的新条目")]
        result = self._run(fresh, stored)
        self.assertEqual(len(result["summarize_items"]), 1)
        ids = [i["id"] for i in result["summarize_items"][0]]
        self.assertIn("old", ids)
        self.assertIn("new", ids)

    def test_summarize_runs_before_append_raw(self):
        result = self._run([_item("new", "今天的新条目")], [])
        self.assertIn("summarize", result["events"])
        self.assertLess(result["events"].index("summarize"),
                        result["events"].index("append"))
        self.assertLess(result["events"].index("save"),
                        result["events"].index("append"))

    def test_summarize_failure_still_appends_and_returns_zero(self):
        def boom(items, cache):
            raise RuntimeError("claude exploded")

        result = self._run([_item("new", "今天的新条目")], [], on_summarize=boom)
        self.assertIn("new", [i["id"] for i in result["appended"]])
        self.assertIn("append", result["events"])

    def test_save_cache_failure_still_appends_and_returns_zero(self):
        def boom(cache, path):
            raise OSError("disk full")

        result = self._run([_item("new", "今天的新条目")], [], on_save=boom)
        self.assertIn("new", [i["id"] for i in result["appended"]])
        self.assertIn("append", result["events"])

    def test_empty_run_passes_empty_list_to_summarize(self):
        # 没有新条目也没有历史缺口时仍以空列表调用；是否真提炼由
        # summarize 内部 early-return 决定，接线层不做第二次判断。
        result = self._run([], [])
        self.assertEqual(result["appended"], [])
        self.assertEqual(result["summarize_items"], [[]])


if __name__ == "__main__":
    unittest.main()
