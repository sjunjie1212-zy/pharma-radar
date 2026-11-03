import json
import os
import tempfile
import unittest

from pipeline.catalysts import KINDS, load, make_catalyst, merge, prune, write


def cat(**kw):
    base = dict(date="2026-12-01", kind="读出", entity="Novartis",
                drug="LOU064", note="CSU（NCT05677451）", source="clinicaltrials.gov")
    base.update(kw)
    return make_catalyst(**base)


class TestMakeCatalyst(unittest.TestCase):
    def test_fields(self):
        c = cat()
        self.assertEqual(
            set(c), {"id", "date", "kind", "entity", "drug", "note", "source"}
        )
        self.assertEqual(c["kind"], "读出")
        self.assertEqual(c["date"], "2026-12-01")
        self.assertEqual(len(c["id"]), 16)
        int(c["id"], 16)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            cat(kind="发布")

    def test_id_ignores_date_but_tracks_identity(self):
        # 改期后 id 不变（覆盖旧记录），换试验则 id 变化。
        self.assertEqual(cat(date="2026-12-01")["id"], cat(date="2027-01-15")["id"])
        self.assertNotEqual(cat()["id"], cat(note="CSU（NCT99999999）")["id"])


class TestMergePrune(unittest.TestCase):
    def test_merge_overwrites_by_id(self):
        old = cat(date="2026-12-01")
        new = cat(date="2027-01-15")
        other = cat(note="NSCLC（NCT11111111）")
        out = merge([old, other], [new])
        self.assertEqual(len(out), 2)
        self.assertEqual({c["id"]: c["date"] for c in out}[old["id"]], "2027-01-15")

    def test_prune_drops_past_and_bad_dates(self):
        rows = [cat(date="2026-11-02"), cat(date="2026-11-03"), cat(date="2026-13-01")]
        ids = [c["date"] for c in prune(rows, "2026-11-03")]
        self.assertEqual(ids, ["2026-11-03"])


class TestWriteLoad(unittest.TestCase):
    def test_roundtrip_sorted_and_js_parity(self):
        rows = [cat(date="2027-02-01"), cat(date="2026-12-01")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "catalysts.json")
            payload = write(rows, out_path=path)
            self.assertEqual([c["date"] for c in payload["catalysts"]],
                             ["2026-12-01", "2027-02-01"])
            self.assertEqual(load(path), payload["catalysts"])
            js = open(os.path.join(tmp, "catalysts.js"), encoding="utf-8").read()
            self.assertTrue(js.startswith("window.__CATALYSTS__ = "))
            self.assertEqual(json.loads(js[len("window.__CATALYSTS__ = "):].rstrip(";\n")),
                             payload)

    def test_load_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load(os.path.join(tmp, "nope.json")), [])


if __name__ == "__main__":
    unittest.main()
