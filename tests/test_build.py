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
    def _sum_path(self, tmp):
        return str(pathlib.Path(tmp) / "summaries.json")

    def test_groups_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            data = build([_item("a"), _item("b", date="2026-11-02")], out_path=str(out),
                         summaries_path=self._sum_path(tmp))
            self.assertEqual(len(data["days"]), 2)
            self.assertTrue(out.exists())
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["days"][0]["date"], "2026-11-03")

    def test_must_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            data = build([_item("a", m=5), _item("b", m=2), _item("c", m=4, dim="D5")], out_path=str(out),
                         summaries_path=self._sum_path(tmp))
            self.assertEqual(data["days"][0]["must"], ["a"])

    def test_days_sorted_desc(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            data = build([_item("a", date="2026-11-01"), _item("b", date="2026-11-03")], out_path=str(out),
                         summaries_path=self._sum_path(tmp))
            self.assertEqual([d["date"] for d in data["days"]], ["2026-11-03", "2026-11-01"])

    def test_render_enforces_daily_and_per_dimension_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            items = [_item(f"{dim}-{n}", dim=dim) for dim in ("D2", "D3", "D4", "D5")
                     for n in range(6)]
            items.append(_item("D1-only", dim="D1"))
            self.assertEqual(len(items), 25)
            data = build(items, out_path=str(out), summaries_path=self._sum_path(tmp))
            rows = data["days"][0]["items"]
            self.assertLessEqual(len(rows), 20)
            for dim in {r["dimension"] for r in rows}:
                self.assertLessEqual(sum(1 for r in rows if r["dimension"] == dim), 5)

    def test_build_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            items = [_item(f"{dim}-{n}", dim=dim) for dim in ("D2", "D3", "D4", "D5")
                     for n in range(6)]
            first = build(items, out_path=str(out), summaries_path=self._sum_path(tmp))
            second = build(items, out_path=str(out), summaries_path=self._sum_path(tmp))
            self.assertEqual(first["days"], second["days"])

    def test_day_without_required_dimensions_builds_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            items = [_item(f"d6-{n}", dim="D6") for n in range(25)]
            data = build(items, out_path=str(out), summaries_path=self._sum_path(tmp))
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
            data = build(items, out_path=str(out), summaries_path=self._sum_path(tmp))
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
            data = build([failing, passing], out_path=str(out), summaries_path=self._sum_path(tmp))
            ids = [r["id"] for d in data["days"] for r in d["items"]]
            self.assertNotIn("bad", ids)
            self.assertIn("good", ids)

    def test_merges_summaries_by_id(self):
        with tempfile.TemporaryDirectory() as td:
            sum_path = pathlib.Path(td) / "summaries.json"
            sum_path.write_text(
                json.dumps({"a": {"title_zh": "一句话提炼"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            items = [_item("a"), _item("b")]
            out = pathlib.Path(td) / "items.json"
            build(items, out_path=str(out), summaries_path=str(sum_path))
            days = json.loads(out.read_text(encoding="utf-8"))["days"]
        got = {i["id"]: i for i in days[0]["items"]}
        self.assertEqual(got["a"]["title_zh"], "一句话提炼")
        self.assertEqual(got["a"]["why"], "")
        self.assertEqual(got["b"]["title_zh"], "")

    def test_malformed_cache_entries_do_not_raise_or_change_items(self):
        with tempfile.TemporaryDirectory() as td:
            sum_path = pathlib.Path(td) / "summaries.json"
            sum_path.write_text(
                json.dumps(
                    {
                        "a": "plain text",
                        "b": {"title_zh": 123},
                        "c": {"title_zh": "   "},
                        "d": {"title_zh": None},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            items = [_item(i) for i in ("a", "b", "c", "d")]
            out = pathlib.Path(td) / "items.json"
            data = build(items, out_path=str(out), summaries_path=str(sum_path))
        got = {i["id"]: i for i in data["days"][0]["items"]}
        self.assertEqual(set(got), {"a", "b", "c", "d"})
        for item_id in got:
            self.assertEqual(got[item_id]["title_zh"], "", item_id)

    def test_summary_cannot_resurrect_item_rejected_by_gate(self):
        # 提炼在门控之后套用：缓存里的 title_zh 不能把当前门拒绝的条目救回来。
        with tempfile.TemporaryDirectory() as td:
            sum_path = pathlib.Path(td) / "summaries.json"
            sum_path.write_text(
                json.dumps({"bad": {"title_zh": "药品获批"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            bad = _item("bad", source="stat")
            bad["title"] = "Opinion: how meditation helped me"
            out = pathlib.Path(td) / "items.json"
            data = build([bad], out_path=str(out), summaries_path=str(sum_path))
        ids = [r["id"] for d in data["days"] for r in d["items"]]
        self.assertNotIn("bad", ids)

    def test_summaries_reach_rows_that_pass_the_gate(self):
        with tempfile.TemporaryDirectory() as td:
            sum_path = pathlib.Path(td) / "summaries.json"
            sum_path.write_text(
                json.dumps({"good": {"title_zh": "FDA 批准新药"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            good = _item("good", source="stat")
            good["title"] = "FDA approves new drug for NSCLC"
            out = pathlib.Path(td) / "items.json"
            data = build([good], out_path=str(out), summaries_path=str(sum_path))
        got = {r["id"]: r for r in data["days"][0]["items"]}
        self.assertEqual(got["good"]["title_zh"], "FDA 批准新药")

    def test_summaries_do_not_mutate_caller_items(self):
        with tempfile.TemporaryDirectory() as td:
            sum_path = pathlib.Path(td) / "summaries.json"
            sum_path.write_text(
                json.dumps({"a": {"title_zh": "一句话提炼"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            items = [_item("a")]
            out = pathlib.Path(td) / "items.json"
            data = build(items, out_path=str(out), summaries_path=str(sum_path))
        self.assertEqual(items[0]["title_zh"], "")
        self.assertEqual(data["days"][0]["items"][0]["title_zh"], "一句话提炼")
        self.assertEqual(len(items[0]), 18)
        self.assertEqual(len(data["days"][0]["items"][0]), 18)

    def test_js_artifact_matches_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            payload = build([_item("a", m=5), _item("b", date="2026-11-02")], out_path=str(out),
                            summaries_path=self._sum_path(tmp))
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
