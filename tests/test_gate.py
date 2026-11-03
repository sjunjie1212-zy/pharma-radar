import unittest

from pipeline.gate import filter_relevant, is_relevant


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


if __name__ == "__main__":
    unittest.main()
