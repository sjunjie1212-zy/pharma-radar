import unittest
from datetime import date

from sources.trials import parse_study

STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT05677451",
                                 "briefTitle": "A Study of LOU064 in Chronic Spontaneous Urticaria"},
        "statusModule": {"overallStatus": "RECRUITING",
                         "startDateStruct": {"date": "2026-01-20"},
                         "studyFirstPostDateStruct": {"date": "2026-11-02"},
                         "primaryCompletionDateStruct": {"date": "2026-12-15"}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Novartis Pharmaceuticals"}},
        "conditionsModule": {"conditions": ["Chronic Spontaneous Urticaria"]},
        "designModule": {"phases": ["PHASE3"]},
        "armsInterventionsModule": {"interventions": [
            {"name": "Placebo"}, {"name": "LOU064 (blinded)"}]},
    }
}


class TestParseStudy(unittest.TestCase):
    def test_fields_extracted(self):
        s = parse_study(STUDY)
        self.assertEqual(s["nct"], "NCT05677451")
        self.assertEqual(s["sponsor"], "Novartis Pharmaceuticals")
        self.assertEqual(s["drug"], "LOU064 (blinded)")
        self.assertEqual(s["first_post"], "2026-11-02")
        self.assertEqual(s["completion"], "2026-12-15")
        self.assertEqual(s["conditions"], ["Chronic Spontaneous Urticaria"])

    def test_missing_nct_returns_none(self):
        self.assertIsNone(parse_study({"protocolSection": {}}))

    def test_missing_intervention_is_empty_string(self):
        s = parse_study({"protocolSection": {
            "identificationModule": {"nctId": "NCT1", "briefTitle": "t"}}})
        self.assertEqual(s["drug"], "")


class TestFetchItems(unittest.TestCase):
    def test_fetch_items_filters_old_and_sets_source(self):
        from unittest import mock
        from sources import trials

        rows = [dict(STUDY)]
        with mock.patch.object(trials, "_fetch", return_value=[trials.parse_study(r) for r in rows]):
            items = trials.fetch_items(today=date(2026, 11, 3))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "trials")
        self.assertEqual(items[0]["event_type"], "clinical")
        self.assertEqual(items[0]["published_at"], "2026-11-02")
        self.assertEqual(items[0]["url"], "https://clinicaltrials.gov/study/NCT05677451")

    def test_fetch_items_drops_studies_older_than_lookback(self):
        from unittest import mock
        from sources import trials
        old = {"protocolSection": {
            "identificationModule": {"nctId": "NCT2", "briefTitle": "old"},
            "statusModule": {"studyFirstPostDateStruct": {"date": "2026-10-01"}}}}
        with mock.patch.object(trials, "_fetch", return_value=[trials.parse_study(old)]):
            self.assertEqual(trials.fetch_items(today=date(2026, 11, 3)), [])

    def test_fetch_catalysts_only_day_precision(self):
        from unittest import mock
        from sources import trials
        month_only = {"protocolSection": {
            "identificationModule": {"nctId": "NCT3", "briefTitle": "m"},
            "statusModule": {"primaryCompletionDateStruct": {"date": "2029-01"}}}}
        rows = [trials.parse_study(STUDY), trials.parse_study(month_only)]
        with mock.patch.object(trials, "_fetch", return_value=rows):
            out = trials.fetch_catalysts(today=date(2026, 11, 3))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["date"], "2026-12-15")
        self.assertEqual(out[0]["kind"], "读出")
        self.assertEqual(out[0]["entity"], "Novartis Pharmaceuticals")
        self.assertIn("NCT05677451", out[0]["note"])


if __name__ == "__main__":
    unittest.main()
