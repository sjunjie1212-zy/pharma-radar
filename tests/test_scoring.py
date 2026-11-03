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

    def test_license_is_policy_not_deal(self):
        self.assertEqual(classify_event("药品生产许可新规"), "policy")

    def test_profiling_does_not_match_filing(self):
        self.assertEqual(classify_event("Genomic profiling reveals resistance"), "science")

    def test_cooperative_termination_is_not_clinical(self):
        self.assertNotEqual(classify_event("公司宣布合作终止"), "clinical")

    def test_recombinant_protein_is_not_commercial(self):
        self.assertNotEqual(classify_event("重组蛋白疫苗机制研究"), "commercial")

    def test_trial_termination_is_clinical(self):
        self.assertEqual(classify_event("公司决定终止 III 期试验"), "clinical")

    def test_dealer_is_not_deal(self):
        self.assertNotEqual(classify_event("dealer network expansion"), "deal")

    def test_word_bounded_deal_matches(self):
        self.assertEqual(classify_event("Company announces $2bn deal"), "deal")

    def test_deal_plural_matches(self):
        self.assertEqual(classify_event("Pfizer signs two deals in oncology"), "deal")


class TestDimension(unittest.TestCase):
    def test_guideline_goes_D1(self):
        self.assertEqual(assign_dimension("regulatory", "CSCO 指南更新：一线治疗顺序调整"), "D1")

    def test_regulatory_goes_D3(self):
        self.assertEqual(assign_dimension("regulatory", "FDA approves drug X"), "D3")

    def test_payment_goes_D4(self):
        self.assertEqual(assign_dimension("payment", "集采中选结果公布"), "D4")

    def test_deal_goes_D5(self):
        self.assertEqual(assign_dimension("deal", "Company sells asset for $1bn"), "D5")

    def test_policy_goes_D6(self):
        self.assertEqual(assign_dimension("policy", "医药代表备案新规"), "D6")

    def test_non_guideline_treatment_landscape_is_not_D1(self):
        self.assertEqual(assign_dimension("regulatory", "治疗格局变化"), "D3")

    def test_unmatched_science_goes_D6(self):
        self.assertEqual(assign_dimension("science", "Researchers describe a pathway"), "D6")

    def test_explicit_science_signal_goes_D1(self):
        self.assertEqual(
            assign_dimension("science", "New mechanism linking inflammation to fibrosis"), "D1"
        )

    def test_explicit_disease_landscape_signal_goes_D1(self):
        self.assertEqual(assign_dimension("science", "Epidemiology of unmet need in NSCLC"), "D1")


class TestScoreM(unittest.TestCase):
    def test_class_level_readout_is_5(self):
        self.assertEqual(score_m("clinical", "First-in-class readout reshapes the field"), 5)

    def test_approval_is_4(self):
        self.assertEqual(score_m("regulatory", "FDA approves drug B"), 4)

    def test_phase3_start_is_3(self):
        self.assertEqual(score_m("clinical", "Phase 3 trial initiated in China"), 3)

    def test_unknown_is_2(self):
        self.assertEqual(score_m("science", "Researchers describe a pathway"), 2)

    def test_acceptance_is_3(self):
        self.assertEqual(score_m("regulatory", "NMPA 受理新药上市申请"), 3)

    def test_topline_readout_is_4(self):
        self.assertEqual(score_m("clinical", "Phase 3 topline readout"), 4)

    def test_enrollment_is_not_4(self):
        self.assertNotEqual(score_m("clinical", "纳入 120 例患者"), 4)


class TestEnrich(unittest.TestCase):
    def test_enrich_sets_fields(self):
        item = {"title": "FDA approves drug B", "event_type": "science", "dimension": "D6", "m": 1}
        out = enrich(item)
        self.assertIs(out, item)
        self.assertEqual(out["event_type"], "regulatory")
        self.assertEqual(out["dimension"], "D3")
        self.assertEqual(out["m"], 4)

    def test_enrich_unmatched_title_lands_D6(self):
        item = {"title": "Researchers describe a pathway"}
        out = enrich(item)
        self.assertEqual(out["event_type"], "science")
        self.assertEqual(out["dimension"], "D6")


class TestEventKeywordsAdded(unittest.TestCase):
    def test_fda_oks_is_regulatory(self):
        title = "STAT+: FDA OKs generic HIV prevention shot, widening access"
        self.assertEqual(classify_event(title), "regulatory")
        self.assertEqual(assign_dimension("regulatory", title), "D3")
        self.assertEqual(score_m("regulatory", title), 3)

    def test_bankruptcy_is_commercial(self):
        title = "Karyopharm, deep in debt, to sell itself in bankruptcy"
        self.assertEqual(classify_event(title), "commercial")
        self.assertEqual(assign_dimension("commercial", title), "D5")
        self.assertEqual(score_m("commercial", title), 3)

    def test_ipo_is_commercial(self):
        title = "Aspen raises a $141M IPO in pursuit of a cell therapy"
        self.assertEqual(classify_event(title), "commercial")
        self.assertEqual(score_m("commercial", title), 3)

    def test_key_trial_is_clinical(self):
        title = "Genmab soars to record highs after cancer drug succeeds in key trial"
        self.assertEqual(classify_event(title), "clinical")
        self.assertEqual(assign_dimension("clinical", title), "D2")

    def test_pbm_rule_is_policy(self):
        title = "Labor Department finalizes sweeping PBM disclosure rule"
        self.assertEqual(classify_event(title), "policy")

    def test_biosimilar_is_commercial(self):
        title = "Keytruda biosimilars are coming — but they face an uphill battle"
        self.assertEqual(classify_event(title), "commercial")

    def test_succeeds_in_alone_is_not_clinical(self):
        # "succeeds in" 太泛：专利纠纷、IPO 都可能这么写，不能进 clinical。
        title = "Amgen succeeds in patent dispute with Sanofi"
        self.assertNotEqual(classify_event(title), "clinical")

    def test_pbm_alone_is_policy(self):
        # 只靠 "pbm" 命中，不借助 "disclosure rule"，守住 pbm 不重复进 commercial。
        title = "PBM reform advances in Congress"
        self.assertEqual(classify_event(title), "policy")

    def test_pbm_not_duplicated_in_commercial(self):
        # 行为测试无法区分「只在 policy」与「两边都有」（policy 元组优先），
        # 这里直接守住表结构：pbm 不能重新出现在 commercial。
        from pipeline.scoring import _EVENT_KEYWORDS

        by_event = dict(_EVENT_KEYWORDS)
        self.assertIn("pbm", by_event["policy"])
        self.assertNotIn("pbm", by_event["commercial"])

    def test_fda_clearance_is_regulatory(self):
        title = "Gilead wins FDA clearance for once-daily pill"
        self.assertEqual(classify_event(title), "regulatory")

    def test_chapter_11_is_commercial(self):
        title = "Company files for Chapter 11 protection"
        self.assertEqual(classify_event(title), "commercial")
        self.assertEqual(score_m("commercial", title), 3)

    def test_cost_cut_is_commercial(self):
        title = "AstraZeneca unveils cost cuts"
        self.assertEqual(classify_event(title), "commercial")

    def test_clears_stays_out_of_regulatory(self):
        # "clears" 在英文里太泛（Boeing clears FAA hurdle、court clears executive），不收。
        for title in ("Boeing clears FAA hurdle for new jet",
                      "Court clears former pharma executive"):
            self.assertNotEqual(classify_event(title), "regulatory")


if __name__ == "__main__":
    unittest.main()
