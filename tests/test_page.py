# tests/test_page.py
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestPageFiles(unittest.TestCase):
    def test_files_exist(self):
        for name in ("index.html", "app.js", "style.css"):
            self.assertTrue((ROOT / name).exists(), name)

    def test_html_references_assets_locally(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("./app.js", html)
        self.assertIn("./style.css", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://cdn", html)

    def test_js_reads_items_json(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("./data/items.json", js)

    def test_dimension_colors_defined(self):
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        for dim in ("d1", "d2", "d3", "d4", "d5", "d6"):
            self.assertIn(f".dim-{dim}", css)

    def test_sample_items_json_matches_schema(self):
        import json
        data = json.loads((ROOT / "tests" / "fixtures" / "items_sample.json").read_text(encoding="utf-8"))
        day = data["days"][0]
        self.assertIn("date", day)
        self.assertIn("must", day)
        self.assertIn("items", day)
        self.assertTrue(all("dimension" in i and "m" in i for i in day["items"]))


class TestPageBehaviour(unittest.TestCase):
    def test_js_exposes_render_day(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertRegex(js, r"window\.renderDay\s*=\s*renderDay")

    def test_js_has_readable_load_failure_path(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("无法显示今日简报", js)
        self.assertIn("JSON 解析失败", js)
        self.assertIn("catch", js)

    def test_html_has_prev_next_day_controls(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        for marker in ('id="prev-day"', 'id="next-day"', 'id="current-date"'):
            self.assertIn(marker, html)

    def test_js_shows_empty_must_line(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("今日无必看", js)


if __name__ == "__main__":
    unittest.main()
