import unittest
from sources.base import canonical_url, item_id, make_item, parse_date


class TestCanonicalUrl(unittest.TestCase):
    def test_strips_tracking_and_fragment(self):
        a = canonical_url("https://Example.com/drug/a/?utm_source=x&id=7#top")
        b = canonical_url("https://example.com/drug/a?id=7")
        self.assertEqual(a, b)

    def test_trailing_slash_ignored(self):
        self.assertEqual(canonical_url("https://a.com/x/"), canonical_url("https://a.com/x"))


class TestItemId(unittest.TestCase):
    def test_same_url_same_id(self):
        self.assertEqual(item_id("https://a.com/x?utm_medium=1"), item_id("https://a.com/x"))

    def test_id_is_16_hex(self):
        i = item_id("https://a.com/x")
        self.assertEqual(len(i), 16)
        int(i, 16)


class TestMakeItem(unittest.TestCase):
    def test_defaults_present(self):
        it = make_item(title="t", url="https://a.com/x", source="s", published_at="2026-11-03T10:00:00")
        for k in ("id", "date", "published_at", "source", "source_weight", "lang",
                  "title", "title_zh", "url", "company", "drug", "target", "ta",
                  "event_type", "dimension", "m", "why", "cluster_id"):
            self.assertIn(k, it)
        self.assertEqual(it["dimension"], "D6")
        self.assertEqual(it["m"], 1)
        self.assertEqual(it["company"], [])
        self.assertEqual(it["date"], "2026-11-03")

    def test_id_derived_from_url(self):
        it = make_item(title="t", url="https://a.com/x", source="s", published_at="2026-11-03T10:00:00")
        self.assertEqual(it["id"], item_id("https://a.com/x"))


class TestParseDate(unittest.TestCase):
    def test_rfc822(self):
        self.assertEqual(parse_date("Tue, 03 Nov 2026 10:20:00 +0000"), "2026-11-03")

    def test_iso(self):
        self.assertEqual(parse_date("2026-11-03T10:20:00Z"), "2026-11-03")

    def test_rfc822_positive_offset_keeps_local_day(self):
        self.assertEqual(parse_date("Tue, 03 Nov 2026 07:00:00 +0800"), "2026-11-03")

    def test_iso_negative_offset_crosses_to_next_day(self):
        self.assertEqual(parse_date("2026-11-03T20:00:00-08:00"), "2026-11-04")

    def test_garbage_returns_empty(self):
        self.assertEqual(parse_date("not a date"), "")


if __name__ == "__main__":
    unittest.main()
