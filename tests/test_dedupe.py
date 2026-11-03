import unittest

from pipeline.dedupe import assign_clusters, dedupe


def _item(i, title, url):
    return {"id": i, "title": title, "url": url, "title_zh": "", "cluster_id": ""}


class TestDedupe(unittest.TestCase):
    def test_same_id_kept_once(self):
        items = [_item("a", "t", "u"), _item("a", "t", "u")]
        self.assertEqual(len(dedupe(items)), 1)

    def test_order_preserved(self):
        items = [_item("a", "t1", "u1"), _item("b", "t2", "u2")]
        self.assertEqual([x["id"] for x in dedupe(items)], ["a", "b"])


class TestClusters(unittest.TestCase):
    def test_near_duplicate_titles_share_cluster(self):
        items = [
            _item("a", "FDA approves drug B for rare disease", "u1"),
            _item("b", "FDA approves Drug B for rare disease!", "u2"),
        ]
        out = assign_clusters(items)
        self.assertEqual(out[0]["cluster_id"], out[1]["cluster_id"])

    def test_distinct_titles_do_not_share(self):
        items = [
            _item("a", "FDA approves drug B", "u1"),
            _item("b", "Company C raises $200m in Series B", "u2"),
        ]
        out = assign_clusters(items)
        self.assertNotEqual(out[0]["cluster_id"], out[1]["cluster_id"])

    def test_uses_title_zh_when_present(self):
        items = [
            {"id": "a", "title": "x", "title_zh": "恒瑞与 BMS 达成 152 亿美元合作", "url": "u1", "cluster_id": ""},
            {"id": "b", "title": "y", "title_zh": "恒瑞与BMS达成152亿美元合作", "url": "u2", "cluster_id": ""},
        ]
        out = assign_clusters(items)
        self.assertEqual(out[0]["cluster_id"], out[1]["cluster_id"])


if __name__ == "__main__":
    unittest.main()
