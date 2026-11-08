import unittest

from pipeline.dedupe import assign_clusters, collapse_clusters, dedupe, similarity


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


class TestSimilarity(unittest.TestCase):
    def test_identical_is_one(self):
        self.assertEqual(similarity("特宝生物10mg获批", "特宝生物10mg获批"), 1.0)

    def test_empty_is_zero(self):
        self.assertEqual(similarity("", "任何标题"), 0.0)

    def test_paraphrase_scores_high(self):
        a = "特宝生物10mg获批，长效生长激素的规格竞争"
        b = "特宝生物长效生长激素10mg规格获批"
        # 实测：SequenceMatcher 0.615，二元组 Jaccard 0.542。
        self.assertGreaterEqual(similarity(a, b), 0.5)

    def test_unrelated_scores_low(self):
        a = "特宝生物10mg获批，长效生长激素的规格竞争"
        b = "三季报扣除股份支付利润转正，君实的牌面藏不住了"
        # 实测：SequenceMatcher 0.047，二元组 Jaccard 0.0。
        self.assertLess(similarity(a, b), 0.5)


class TestCrossSourceClusters(unittest.TestCase):
    def test_different_wording_same_event_share_cluster(self):
        items = [
            _item("a", "特宝生物10mg获批，长效生长激素的规格竞争", "u1"),
            _item("b", "特宝生物长效生长激素10mg规格获批", "u2"),
        ]
        out = assign_clusters(items)
        self.assertEqual(out[0]["cluster_id"], out[1]["cluster_id"])


class TestCollapse(unittest.TestCase):
    def _item(self, i, title, m, weight=1.0):
        return {"id": i, "title": title, "url": "u" + i, "title_zh": "",
                "cluster_id": "", "m": m, "source_weight": weight,
                "published_at": "2026-11-03T08:00:00+08:00"}

    def test_same_cluster_keeps_highest_m(self):
        items = [self._item("a", "特宝生物10mg获批，长效生长激素的规格竞争", 2),
                 self._item("b", "特宝生物长效生长激素10mg规格获批", 4)]
        items = assign_clusters(items)
        self.assertEqual(items[0]["cluster_id"], items[1]["cluster_id"])
        out = collapse_clusters(items)
        self.assertEqual([i["id"] for i in out], ["b"])

    def test_tie_breaks_on_source_weight(self):
        items = [self._item("a", "特宝生物10mg获批，长效生长激素的规格竞争", 3, 1.0),
                 self._item("b", "特宝生物长效生长激素10mg规格获批", 3, 1.4)]
        items = assign_clusters(items)
        out = collapse_clusters(items)
        self.assertEqual([i["id"] for i in out], ["b"])

    def test_distinct_events_all_kept(self):
        items = [self._item("a", "FDA 批准新药甲", 4),
                 self._item("b", "某公司完成 B 轮融资", 2)]
        items = assign_clusters(items)
        out = collapse_clusters(items)
        self.assertEqual([i["id"] for i in out], ["a", "b"])

    def test_preserves_input_order(self):
        items = [self._item("a", "事件甲", 4), self._item("b", "无关事件乙", 1)]
        items = assign_clusters(items)
        self.assertEqual([i["id"] for i in collapse_clusters(items)], ["a", "b"])

    def test_items_without_cluster_id_survive(self):
        items = [self._item("a", "事件甲", 4), self._item("b", "事件甲", 2)]
        out = collapse_clusters(items)
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
