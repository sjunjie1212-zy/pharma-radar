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
    def _run(self, collected, existing):
        appended = []

        def fake_append(chosen, month=None):
            appended.extend(chosen)
            return len(chosen)

        with mock.patch("sys.argv", ["run.py"]), \
             mock.patch.object(run, "collect", return_value=collected), \
             mock.patch.object(run, "filter_relevant", side_effect=lambda x: x), \
             mock.patch.object(run, "load_raw", return_value=existing), \
             mock.patch.object(run, "append_raw", side_effect=fake_append), \
             mock.patch.object(run, "build", return_value={"days": []}), \
             mock.patch.object(run, "update_catalysts", return_value={}), \
             mock.patch.object(run, "resolve_anchor", return_value=ANCHOR):
            self.assertEqual(run.main(), 0)
        return appended

    def test_already_stored_items_do_not_consume_quota(self):
        stored = [_item("old", "昨日旧条目")]
        # 旧条目排到当天最晚，否则 limit=20 会先把它挤出去，测不到 known-id 过滤。
        stored[0]["published_at"] = "2026-11-03T18:00:00+08:00"
        fresh = [_item("new", "今天的新条目")]
        # 六个维度轮转，避免 per_dim=5 把条数卡在 5；26 条足够填满 limit=20。
        # 填充标题要彼此不相似，否则会被同事件聚类折叠，同样填不满配额。
        fresh.extend(_item(f"filler{n}", f"{COMPANIES[n]}：第{n}条简讯", DIMS[n % 6])
                     for n in range(25))
        appended = self._run(fresh + stored, stored)
        ids = [i["id"] for i in appended]
        self.assertIn("new", ids)
        self.assertNotIn("old", ids)
        self.assertEqual(len(ids), 20)

    def test_collapsed_duplicate_not_appended_twice(self):
        a = _item("a", "特宝生物10mg获批，长效生长激素的规格竞争")
        b = _item("b", "特宝生物长效生长激素10mg规格获批")
        appended = self._run([a, b], [])
        self.assertEqual([i["id"] for i in appended], ["a"])


if __name__ == "__main__":
    unittest.main()
