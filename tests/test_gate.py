import unittest

from pipeline.gate import GATED_SOURCES, filter_relevant, is_relevant, should_gate


def item(title, title_zh=""):
    return {"title": title, "title_zh": title_zh}


class TestIsRelevant(unittest.TestCase):
    def test_pharma_trial_kept(self):
        self.assertTrue(is_relevant(item("Phase 3 trial meets primary endpoint in NSCLC")))

    def test_regulator_kept(self):
        self.assertTrue(is_relevant(item("FDA approves first gene therapy for hemophilia")))

    def test_chinese_drug_news_kept(self):
        self.assertTrue(is_relevant(item("国家药监局发布某创新药指导原则")))

    def test_reimbursement_kept(self):
        self.assertTrue(is_relevant(item("2026 年国家医保药品目录调整结果公布")))

    def test_politics_dropped(self):
        self.assertFalse(is_relevant(item("Opinion: What the 2024 electoral map reveals about America")))

    def test_lifestyle_dropped(self):
        self.assertFalse(is_relevant(item("Opinion: How meditation helped me become a better doctor")))

    def test_disease_name_alone_not_enough(self):
        self.assertFalse(is_relevant(item("Washington state resident dies from bird flu")))

    def test_ascii_word_boundary(self):
        # "pharmacy" starts with "pharma" but must not match on a word boundary.
        self.assertFalse(is_relevant(item("The pharmacy counter is open late tonight")))

    def test_title_zh_counts(self):
        self.assertTrue(is_relevant(item("Some English headline", title_zh="国产 PD-1 获批新适应症")))

    def test_filter_keeps_order(self):
        items = [item("electoral map"), item("FDA approves drug"), item("FDA rejects drug")]
        kept = filter_relevant(items)
        self.assertEqual([i["title"] for i in kept], ["FDA approves drug", "FDA rejects drug"])


class TestSourcePolicy(unittest.TestCase):
    def test_dedicated_pharma_source_not_gated(self):
        self.assertFalse(should_gate({"source": "biopharmadive"}))

    def test_broad_source_gated(self):
        self.assertTrue(should_gate({"source": "stat"}))

    def test_nmpa_news_gated(self):
        # 断言在名单里，而不只是 should_gate 返回 True：未知源默认也返回 True，
        # 只测返回值的话，把 nmpa-news 从名单里移出去这个测试仍然通过。
        self.assertIn("nmpa-news", GATED_SOURCES)
        self.assertTrue(should_gate({"source": "nmpa-news"}))

    def test_nature_biotech_gated(self):
        self.assertIn("nature-biotech", GATED_SOURCES)
        self.assertTrue(should_gate({"source": "nature-biotech"}))

    def test_unknown_source_gated(self):
        self.assertTrue(should_gate({"source": "somewhere-new"}))

    def test_ungated_source_keeps_unmatched_title(self):
        items = [{"source": "biopharmadive", "title": "This week in charts"}]
        self.assertEqual(len(filter_relevant(items)), 1)

    def test_gated_source_still_drops(self):
        items = [{"source": "stat", "title": "Opinion: how meditation helped me"}]
        self.assertEqual(filter_relevant(items), [])


class TestInflections(unittest.TestCase):
    def test_immunotherapy(self):
        self.assertTrue(is_relevant({"title": "Immunotherapy shows promise in melanoma"}))

    def test_antibodies(self):
        self.assertTrue(is_relevant({"title": "New monoclonal antibodies advance"}))

    def test_acquires_inflection(self):
        # 只有 "acquire" 的屈折后缀能命中这里，无其它词干/术语可借。
        self.assertTrue(is_relevant({"title": "Company acquires rival"}))

    def test_aromatherapy_still_rejected(self):
        self.assertFalse(is_relevant({"title": "Aromatherapy oils for sale"}))

    def test_deal_terms(self):
        self.assertTrue(is_relevant({"title": "Pfizer acquires Seagen in $43 billion deal"}))
        self.assertTrue(is_relevant({"title": "Company files for Chapter 11"}))

    def test_karyopharm_bankruptcy_term(self):
        self.assertTrue(is_relevant({"title": "Karyopharm, deep in debt, to sell itself in bankruptcy"}))

    def test_chemotherapy(self):
        self.assertTrue(is_relevant({"title": "Chemotherapy shows promise"}))

    def test_pd1_token(self):
        self.assertTrue(is_relevant({"title": "PD-1 inhibitor shows new data"}))


class TestPrecisionTerms(unittest.TestCase):
    def test_generic_topics_stay_relevant_via_pharma_words(self):
        self.assertTrue(is_relevant({"title": "Medicare drug pricing"}))
        self.assertTrue(is_relevant({"title": "Insurers' coverage of gene therapy"}))
        self.assertTrue(is_relevant({"title": "Biotech IPO market cools"}))

    def test_generic_news_terms_alone_not_relevant(self):
        self.assertFalse(is_relevant({"title": "Opinion: What the election coverage got wrong"}))
        self.assertFalse(is_relevant({"title": "Tesla valuation hits record"}))


if __name__ == "__main__":
    unittest.main()
