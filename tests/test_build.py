import json
import pathlib
import tempfile
import unittest

from pipeline.build import append_raw, build, load_raw


def _item(i, date="2026-11-03", m=4, dim="D3"):
    return {
        "id": i, "date": date, "published_at": f"{date}T10:00:00", "source": "s",
        "source_weight": 1.0, "lang": "en", "title": f"title {i}", "title_zh": "",
        "url": f"https://e.com/{i}", "company": [], "drug": [], "target": [], "ta": [],
        "event_type": "regulatory", "dimension": dim, "m": m, "why": "", "cluster_id": i,
    }


class TestAppendRaw(unittest.TestCase):
    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(append_raw([_item("a")], "2026-11", raw_dir=tmp), 1)
            self.assertEqual(append_raw([_item("a")], "2026-11", raw_dir=tmp), 0)
            self.assertEqual(len(load_raw(raw_dir=tmp)), 1)


class TestBuild(unittest.TestCase):
    def test_groups_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            data = build([_item("a"), _item("b", date="2026-11-02")], out_path=str(out))
            self.assertEqual(len(data["days"]), 2)
            self.assertTrue(out.exists())
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["days"][0]["date"], "2026-11-03")

    def test_must_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            data = build([_item("a", m=5), _item("b", m=2), _item("c", m=4, dim="D5")], out_path=str(out))
            self.assertEqual(data["days"][0]["must"], ["a"])

    def test_days_sorted_desc(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            data = build([_item("a", date="2026-11-01"), _item("b", date="2026-11-03")], out_path=str(out))
            self.assertEqual([d["date"] for d in data["days"]], ["2026-11-03", "2026-11-01"])

    def test_js_artifact_matches_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            payload = build([_item("a", m=5), _item("b", date="2026-11-02")], out_path=str(out))
            js_path = pathlib.Path(tmp) / "items.js"
            self.assertTrue(js_path.exists(), "items.js")
            js = js_path.read_text(encoding="utf-8")
            prefix = "window.__ITEMS__ = "
            self.assertTrue(js.startswith(prefix))
            self.assertTrue(js.rstrip().endswith(";"))
            parsed = json.loads(js[len(prefix): js.rstrip().rfind(";")])
            self.assertEqual(parsed, payload)
            self.assertEqual(parsed, json.loads(out.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
