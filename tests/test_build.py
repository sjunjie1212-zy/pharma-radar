import json
import pathlib
import tempfile
import unittest

from pipeline.build import append_raw, build, load_raw


def _item(i, date="2026-11-03", m=4, dim="D3", published_at=None, source="biopharmadive"):
    return {
        "id": i, "date": date, "published_at": published_at or f"{date}T10:00:00", "source": source,
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

    def test_render_enforces_daily_and_per_dimension_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            items = [_item(f"{dim}-{n}", dim=dim) for dim in ("D2", "D3", "D4", "D5")
                     for n in range(6)]
            items.append(_item("D1-only", dim="D1"))
            self.assertEqual(len(items), 25)
            data = build(items, out_path=str(out))
            rows = data["days"][0]["items"]
            self.assertLessEqual(len(rows), 20)
            for dim in {r["dimension"] for r in rows}:
                self.assertLessEqual(sum(1 for r in rows if r["dimension"] == dim), 5)

    def test_build_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            items = [_item(f"{dim}-{n}", dim=dim) for dim in ("D2", "D3", "D4", "D5")
                     for n in range(6)]
            first = build(items, out_path=str(out))
            second = build(items, out_path=str(out))
            self.assertEqual(first["days"], second["days"])

    def test_day_without_required_dimensions_builds_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            items = [_item(f"d6-{n}", dim="D6") for n in range(25)]
            data = build(items, out_path=str(out))
            self.assertEqual(len(data["days"]), 1)
            rows = data["days"][0]["items"]
            self.assertLessEqual(len(rows), 20)
            ids = [r["id"] for r in rows]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertTrue(all(r["dimension"] == "D6" for r in rows))

    def test_must_is_capped_at_five_in_rank_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            dims = ("D1", "D2", "D3", "D4", "D5", "D1", "D3")
            items = [
                _item(f"m{n}", m=5, dim=dims[n - 1],
                      published_at=f"2026-11-03T{n:02d}:00:00")
                for n in range(1, 8)
            ]
            data = build(items, out_path=str(out))
            day = data["days"][0]
            self.assertEqual(len(day["must"]), 5)
            self.assertEqual(day["must"], ["m7", "m6", "m5", "m4", "m3"])
            item_ids = {r["id"] for r in day["items"]}
            self.assertTrue(set(day["must"]) <= item_ids)

    def test_build_reapplies_gate(self):
        # raw 是累积的：曾经通过较松门（或门之前）的条目不能在每次 build 时重现。
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            failing = _item("bad", source="stat")
            failing["title"] = "Opinion: how meditation helped me"
            passing = _item("good", source="stat")
            passing["title"] = "FDA approves new drug for NSCLC"
            data = build([failing, passing], out_path=str(out))
            ids = [r["id"] for d in data["days"] for r in d["items"]]
            self.assertNotIn("bad", ids)
            self.assertIn("good", ids)

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
