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

    def test_html_loads_generated_items_js_before_app_js(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        items_pos = html.find('<script src="./data/items.js"></script>')
        app_pos = html.find('<script src="./app.js"></script>')
        self.assertNotEqual(items_pos, -1)
        self.assertNotEqual(app_pos, -1)
        self.assertLess(items_pos, app_pos)

    def test_js_allows_only_http_links(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('url.protocol === "http:"', js)
        self.assertIn('url.protocol === "https:"', js)
        self.assertNotIn('item.url || "#"', js)

    def test_js_skips_non_object_items(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('typeof item === "object"', js)
        self.assertIn("!Array.isArray(item)", js)

    def test_js_has_filtered_must_copy(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("本维度今日无必看", js)

    def test_html_has_catalyst_view_switch(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="today"', html)
        self.assertIn('data-view="catalysts"', html)

    def test_html_loads_catalysts_js_before_app_js(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        cat_pos = html.find('<script src="./data/catalysts.js"></script>')
        app_pos = html.find('<script src="./app.js"></script>')
        self.assertNotEqual(cat_pos, -1)
        self.assertLess(cat_pos, app_pos)

    def test_js_exposes_render_catalysts(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertRegex(js, r"window\.renderCatalysts\s*=\s*renderCatalysts")
        self.assertIn("./data/catalysts.json", js)

    def test_js_shows_days_until(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("天后", js)
        self.assertIn("今天", js)

    def test_css_has_catalyst_styles(self):
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        for marker in (".view-tab", ".catalyst-row", ".kind-badge"):
            self.assertIn(marker, css)


if __name__ == "__main__":
    unittest.main()
