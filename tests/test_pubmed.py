import unittest
from unittest import mock

from sources import pubmed
from sources.pubmed import parse_summaries

SUMMARY = {
    "uids": ["42971815", "42970000"],
    "42971815": {"title": "Continuous glucose monitoring in diabetes: guidelines for primary care",
                 "sortpubdate": "2026/11/02 00:00"},
    "42970000": {"title": "Some accepted manuscript", "sortpubdate": ""},
}


class TestParseSummaries(unittest.TestCase):
    def test_item_fields(self):
        out = parse_summaries(SUMMARY, fallback_date="2026-11-02")
        self.assertEqual(len(out), 2)
        first = out[0]
        self.assertEqual(first["source"], "pubmed")
        self.assertEqual(first["event_type"], "science")
        self.assertEqual(first["dimension"], "D1")
        self.assertEqual(first["published_at"], "2026-11-02")
        self.assertEqual(first["url"], "https://pubmed.ncbi.nlm.nih.gov/42971815/")

    def test_missing_sortpubdate_uses_fallback(self):
        out = parse_summaries(SUMMARY, fallback_date="2026-11-03")
        self.assertEqual(out[1]["published_at"], "2026-11-03")

    def test_no_date_anywhere_skips(self):
        out = parse_summaries(SUMMARY, fallback_date="")
        self.assertEqual([i["title"] for i in out],
                         ["Continuous glucose monitoring in diabetes: guidelines for primary care"])

    def test_empty_title_skipped(self):
        result = {"uids": ["1"], "1": {"title": "  ", "sortpubdate": "2026/11/02 00:00"}}
        self.assertEqual(parse_summaries(result), [])


class TestFetchAll(unittest.TestCase):
    def test_no_ids_returns_empty_without_summary_call(self):
        search = mock.Mock(status_code=200)
        search.json.return_value = {"esearchresult": {"idlist": []}}
        with mock.patch.object(pubmed.requests, "get", return_value=search) as get:
            self.assertEqual(pubmed.fetch_all(), [])
        self.assertEqual(get.call_count, 1)

    def test_two_calls_esearch_then_esummary(self):
        search = mock.Mock(status_code=200)
        search.json.return_value = {"esearchresult": {"idlist": ["42971815"]}}
        summary = mock.Mock(status_code=200)
        summary.json.return_value = {"result": {
            "uids": ["42971815"],
            "42971815": {"title": "G", "sortpubdate": "2026/11/02 00:00"}}}
        with mock.patch.object(pubmed.requests, "get", side_effect=[search, summary]) as get:
            out = pubmed.fetch_all()
        self.assertEqual(len(out), 1)
        self.assertEqual(get.call_count, 2)
        self.assertIn("esummary.fcgi", get.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
