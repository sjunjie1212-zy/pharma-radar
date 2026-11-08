import pathlib
import unittest
from unittest import mock

from sources.reg_cn import fetch_all, parse_listing

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "nmpa_sample.html"
LISTING_URL = "https://www.nmpa.gov.cn/yaopin/ypggtg/index.html"
PAD = "公告内容" * 80  # 320 chars of date-free padding, separates anchors by >200 chars


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


class TestParseListingEdges(unittest.TestCase):
    def test_same_directory_url_resolves_against_listing_page(self):
        html = (
            '<li><a href="t20261103_1.html">国家药监局关于某事项的公告</a>'
            "<span>2026-11-03</span></li>"
        )
        resp = mock.Mock()
        resp.text = html
        resp.apparent_encoding = None
        resp.raise_for_status.return_value = None
        with mock.patch("sources.reg_cn.requests.get", return_value=resp):
            items = fetch_all()
        self.assertEqual(len(items), 2)
        self.assertEqual(
            items[0]["url"],
            "https://www.nmpa.gov.cn/yaopin/ypggtg/t20261103_1.html",
        )
        self.assertEqual(
            items[1]["url"],
            "https://www.nmpa.gov.cn/yaowen/ypjgyw/t20261103_1.html",
        )

    def test_anchor_without_date_is_dropped(self):
        html = (
            '<li><a href="/yaopin/a1.html">有日期的公告标题</a><span>2026-11-03</span></li>'
            f"<p>{PAD}</p>"
            '<li><a href="/yaopin/a2.html">没有日期的公告标题</a></li>'
            f"<p>{PAD}</p>"
        )
        items = parse_listing(html, "nmpa", base=LISTING_URL)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "有日期的公告标题")

    def test_impossible_calendar_date_is_dropped(self):
        html = (
            '<li><a href="/yaopin/bad.html">日期非法的公告标题</a><span>2026-13-40</span></li>'
            f"<p>{PAD}</p>"
        )
        self.assertEqual(parse_listing(html, "nmpa", base=LISTING_URL), [])

    def test_published_at_has_shanghai_offset(self):
        items = parse_listing(FIXTURE.read_text(encoding="utf-8"), "nmpa")
        self.assertEqual(items[0]["published_at"], "2026-11-03T00:00:00+08:00")

    def test_title_html_entities_unescaped(self):
        html = (
            '<li><a href="/yaopin/c1.html">药品&amp;器械监管公告</a>'
            "<span>2026-11-03</span></li>"
        )
        items = parse_listing(html, "nmpa", base=LISTING_URL)
        self.assertEqual(items[0]["title"], "药品&器械监管公告")


if __name__ == "__main__":
    unittest.main()
