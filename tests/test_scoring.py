import unittest

from pipeline.scoring import assign_dimension, classify_event, enrich, score_m


class TestClassifyEvent(unittest.TestCase):
    def test_deal(self):
        self.assertEqual(classify_event("AstraZeneca licenses ADC asset in $2bn deal"), "deal")

    def test_regulatory(self):
        self.assertEqual(classify_event("FDA approves new therapy for NSCLC"), "regulatory")

    def test_clinical(self):
        self.assertEqual(classify_event("Phase 3 trial meets primary endpoint"), "clinical")

    def test_payment(self):
        self.assertEqual(classify_event("医保谈判结果公布，创新药平均降价 60%"), "payment")

    def test_policy(self):
        self.assertEqual(classify_event("CDE 发布新的指导原则"), "policy")

    def test_fallback_science(self):
        self.assertEqual(classify_event("New mechanism linking inflammation to fibrosis"), "science")


class TestDimension(unittest.TestCase):
    def test_guideline_goes_D1(self):
        self.assertEqual(assign_dimension("science", "CSCO 指南更新：一线治疗顺序调整"), "D1")

    def test_regulatory_goes_D3(self):
        self.assertEqual(assign_dimension("regulatory", "FDA approves drug X"), "D3")

    def test_payment_goes_D4(self):
        self.assertEqual(assign_dimension("payment", "集采中选结果公布"), "D4")

    def test_deal_goes_D5(self):
        self.assertEqual(assign_dimension("deal", "Company sells asset for $1bn"), "D5")

    def test_policy_goes_D6(self):
        self.assertEqual(assign_dimension("policy", "医药代表备案新规"), "D6")


class TestScoreM(unittest.TestCase):
    def test_class_level_readout_is_5(self):
        self.assertEqual(score_m("clinical", "First-in-class readout reshapes the field"), 5)

    def test_approval_is_4(self):
        self.assertEqual(score_m("regulatory", "FDA approves drug B"), 4)

    def test_phase3_start_is_3(self):
        self.assertEqual(score_m("clinical", "Phase 3 trial initiated in China"), 3)

    def test_unknown_is_2(self):
        self.assertEqual(score_m("science", "Researchers describe a pathway"), 2)


class TestEnrich(unittest.TestCase):
    def test_enrich_sets_fields(self):
        item = {"title": "FDA approves drug B", "event_type": "science", "dimension": "D6", "m": 1}
        out = enrich(item)
        self.assertEqual(out["event_type"], "regulatory")
        self.assertEqual(out["dimension"], "D3")
        self.assertEqual(out["m"], 4)


if __name__ == "__main__":
    unittest.main()
