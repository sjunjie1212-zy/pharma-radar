import pathlib
import unittest

from sources.rss_en import parse_feed

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "rss_sample.xml"


class TestParseFeed(unittest.TestCase):
    def setUp(self):
        self.items = parse_feed(FIXTURE.read_bytes(), "sample", 1.5)

    def test_parses_two_items(self):
        self.assertEqual(len(self.items), 2)

    def test_fields(self):
        first = self.items[0]
        self.assertEqual(first["title"], "Company A reports Phase 3 win in NSCLC")
        self.assertEqual(first["source"], "sample")
        self.assertEqual(first["source_weight"], 1.5)
        self.assertEqual(first["lang"], "en")
        self.assertEqual(first["date"], "2026-11-03")

    def test_tracking_params_removed(self):
        self.assertEqual(self.items[0]["url"], "https://example.com/a")

    def test_broken_xml_returns_empty(self):
        self.assertEqual(parse_feed(b"<not xml", "sample"), [])


if __name__ == "__main__":
    unittest.main()
