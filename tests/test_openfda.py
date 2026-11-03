import unittest
from datetime import date
from unittest import mock

from sources import openfda
from sources.openfda import parse_results

NDA = {
    "application_number": "NDA221183",
    "sponsor_name": "COSETTE",
    "products": [{"brand_name": "EVOXAC",
                  "active_ingredients": [{"name": "CEVIMELINE HYDROCHLORIDE"}]}],
    "submissions": [
        {"submission_type": "ORIG", "submission_status": "AP",
         "submission_status_date": "20261102"},
        {"submission_type": "SUPPL", "submission_status": "AP",
         "submission_status_date": "20261103"},
    ],
}
ANDA = dict(NDA, application_number="ANDA220010")


class TestParseResults(unittest.TestCase):
    def test_nda_becomes_item(self):
        out = parse_results([NDA])
        self.assertEqual(len(out), 1)
        item = out[0]
        self.assertEqual(item["source"], "openfda")
        self.assertEqual(item["event_type"], "regulatory")
        self.assertEqual(item["published_at"], "2026-11-02")
        self.assertEqual(item["company"], ["COSETTE"])
        self.assertIn("EVOXAC", item["title"])
        self.assertIn("ApplNo=221183", item["url"])

    def test_anda_generic_skipped(self):
        self.assertEqual(parse_results([ANDA]), [])

    def test_submission_without_approval_skipped(self):
        pending = dict(NDA, submissions=[{"submission_type": "ORIG",
                                          "submission_status": "TA",
                                          "submission_status_date": "20261102"}])
        self.assertEqual(parse_results([pending]), [])

    def test_latest_orig_approval_wins(self):
        two = dict(NDA, submissions=NDA["submissions"] + [
            {"submission_type": "ORIG", "submission_status": "AP",
             "submission_status_date": "20261103"}])
        self.assertEqual(parse_results([two])[0]["published_at"], "2026-11-03")


class TestFetchAll(unittest.TestCase):
    def test_404_is_empty_not_error(self):
        resp = mock.Mock(status_code=404)
        with mock.patch.object(openfda.requests, "get", return_value=resp):
            self.assertEqual(openfda.fetch_all(), [])

    def test_results_parsed(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"results": [NDA]}
        with mock.patch.object(openfda.requests, "get", return_value=resp):
            out = openfda.fetch_all(today=date(2026, 11, 3))
        self.assertEqual([i["source"] for i in out], ["openfda"])

    def test_old_orig_approval_dropped(self):
        # openFDA 的区间命中可能来自别的 submission，原始批准日期可能很旧。
        old = dict(NDA, submissions=[{"submission_type": "ORIG",
                                      "submission_status": "AP",
                                      "submission_status_date": "20200101"}])
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"results": [old]}
        with mock.patch.object(openfda.requests, "get", return_value=resp):
            self.assertEqual(openfda.fetch_all(today=date(2026, 11, 3)), [])


if __name__ == "__main__":
    unittest.main()
