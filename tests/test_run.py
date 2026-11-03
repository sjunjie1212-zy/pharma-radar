import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import run
from pipeline.catalysts import make_catalyst

CST = ZoneInfo("Asia/Shanghai")
ANCHOR = datetime(2026, 11, 3, 19, 0, tzinfo=CST)


class TestUpdateCatalysts(unittest.TestCase):
    def _catalyst(self, day, note="NCT1"):
        return make_catalyst(date=day, kind="读出", entity="Novartis",
                             drug="X", note=note, source="clinicaltrials.gov")

    def test_merges_prunes_and_writes(self):
        existing = [self._catalyst("2026-11-02", "OLD"),   # 已过期
                    self._catalyst("2026-12-01", "KEEP")]  # 应保留
        fresh = [self._catalyst("2026-12-20", "NEW")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "catalysts.json")
            run.catalysts.write(existing, out_path=path)  # 先落一份旧数据
            with mock.patch.object(run.trials, "fetch_catalysts", return_value=fresh):
                run.update_catalysts(ANCHOR, path=path)
            dates = [c["date"] for c in run.catalysts.load(path)]
        self.assertEqual(dates, ["2026-12-01", "2026-12-20"])

    def test_fetch_failure_keeps_existing(self):
        existing = [self._catalyst("2026-12-01", "KEEP")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "catalysts.json")
            run.catalysts.write(existing, out_path=path)
            with mock.patch.object(run.trials, "fetch_catalysts",
                                   side_effect=RuntimeError("boom")):
                run.update_catalysts(ANCHOR, path=path)
            dates = [c["date"] for c in run.catalysts.load(path)]
        self.assertEqual(dates, ["2026-12-01"])


if __name__ == "__main__":
    unittest.main()
