import os
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from sources import media_cn

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestParseBioon(unittest.TestCase):
    def test_titles_urls_dates(self):
        items = media_cn.parse_bioon(_fixture("bioon_list.html"))
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first["source"], "bioon")
        self.assertEqual(first["date"], "2026-11-02")
        self.assertEqual(first["published_at"], "2026-11-02T00:00:00+08:00")
        self.assertEqual(first["url"], "http://news.bioon.com/article/a8da9616261f.html")
        self.assertIn("复旦大学", first["title"])
        self.assertEqual(items[1]["date"], "2026-11-03")
        self.assertEqual(first["lang"], "zh")

    def test_navigation_links_skipped(self):
        items = media_cn.parse_bioon(_fixture("bioon_list.html"))
        self.assertNotIn("CAR-T/TCR-T细胞治疗", [i["title"] for i in items])


class TestParseYaozh(unittest.TestCase):
    def test_entity_unescaped_and_duplicates_collapsed(self):
        items = media_cn.parse_yaozh(_fixture("yaozh_home.html"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["source"], "yaozh")
        self.assertEqual(items[0]["url"], "https://news.yaozh.com/archive/49307.html")
        self.assertTrue(any("&" in i["title"] for i in items))
        self.assertTrue(all("&amp;" not in i["title"] for i in items))

    def test_date_captured(self):
        items = media_cn.parse_yaozh(_fixture("yaozh_home.html"))
        self.assertEqual({i["date"] for i in items}, {"2026-11-03"})


class TestParseDrugtimes(unittest.TestCase):
    def test_date_from_url_path(self):
        items = media_cn.parse_drugtimes(_fixture("drugtimes_home.html"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["date"], "2026-11-03")
        self.assertEqual(items[1]["date"], "2026-11-02")
        self.assertEqual(items[0]["source"], "drugtimes")
        self.assertTrue(items[0]["url"].startswith("https://www.drugtimes.cn/2026/11/03/"))

    def test_category_links_skipped(self):
        items = media_cn.parse_drugtimes(_fixture("drugtimes_home.html"))
        self.assertNotIn("药物资讯", [i["title"] for i in items])


class TestProxies(unittest.TestCase):
    def test_default_proxy(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(media_cn.proxies(),
                             {"http": "http://127.0.0.1:7890",
                              "https": "http://127.0.0.1:7890"})

    def test_env_override(self):
        with mock.patch.dict(os.environ, {"PHARMA_RADAR_PROXY": "http://127.0.0.1:1080"}, clear=True):
            self.assertEqual(media_cn.proxies()["https"], "http://127.0.0.1:1080")

    def test_empty_disables_proxy(self):
        with mock.patch.dict(os.environ, {"PHARMA_RADAR_PROXY": "  "}, clear=True):
            self.assertIsNone(media_cn.proxies())


class TestFetchAll(unittest.TestCase):
    def test_filters_old_items_and_isolates_failure(self):
        html = {
            "https://news.bioon.com/1.html": _fixture("bioon_list.html"),
            "https://news.bioon.com/2.html": _fixture("bioon_list.html"),
            "https://news.yaozh.com/": _fixture("yaozh_home.html"),
        }

        def fake_get(url, **kwargs):
            if url not in html:
                raise RuntimeError("boom")
            resp = mock.Mock()
            resp.text = html[url]
            resp.raise_for_status = mock.Mock()
            return resp

        with mock.patch.object(media_cn.requests, "get", side_effect=fake_get):
            items = media_cn.fetch_all(days=2, today=date(2026, 11, 3))

        self.assertTrue(items)
        self.assertTrue(all(i["date"] >= "2026-11-02" for i in items))
        self.assertNotIn("drugtimes", {i["source"] for i in items})

    def test_ids_unique(self):
        with mock.patch.object(media_cn, "_get", return_value=_fixture("yaozh_home.html")):
            items = media_cn.fetch_all(days=2, today=date(2026, 11, 3))
        ids = [i["id"] for i in items]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
