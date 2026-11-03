import pathlib
import unittest

from sources.reg_cn import parse_listing

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "nmpa_sample.html"


class TestParseListing(unittest.TestCase):
    def setUp(self):
        self.items = parse_listing(FIXTURE.read_text(encoding="utf-8"), "nmpa")

    def test_two_items(self):
        self.assertEqual(len(self.items), 2)

    def test_relative_url_absolutized(self):
        self.assertTrue(self.items[0]["url"].startswith("https://www.nmpa.gov.cn/"))

    def test_date_parsed(self):
        self.assertEqual(self.items[0]["date"], "2026-11-03")

    def test_lang_is_zh(self):
        self.assertEqual(self.items[0]["lang"], "zh")


if __name__ == "__main__":
    unittest.main()
