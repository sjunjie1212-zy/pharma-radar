import unittest
from collections import Counter

from pipeline.select import select


def _item(i, dim, m, source_weight=1.0, published_at="2026-11-03T10:00:00"):
    return {
        "id": i,
        "dimension": dim,
        "m": m,
        "source_weight": source_weight,
        "published_at": published_at,
    }


class TestSelect(unittest.TestCase):
    def test_per_dimension_cap(self):
        items = [_item(f"d5-{i}", "D5", 5) for i in range(10)]
        out = select(items, limit=20, per_dim=5)
        self.assertEqual(len([x for x in out if x["dimension"] == "D5"]), 5)

    def test_total_limit(self):
        items = [_item(f"{d}-{i}", d, 4) for d in ("D1", "D2", "D3", "D4", "D5") for i in range(10)]
        out = select(items, limit=20, per_dim=5)
        self.assertEqual(len(out), 20)

    def test_required_dimension_survives_flood(self):
        flood = [_item(f"d5-{i}", "D5", 5) for i in range(40)]
        lone = [_item("d1-only", "D1", 2)]
        out = select(flood + lone, limit=20, per_dim=5)
        self.assertIn("D1", {x["dimension"] for x in out})

    def test_required_dimension_evicts_at_limit(self):
        saturated = [
            _item(f"{d}-{i}", d, 5) for d in ("D2", "D3", "D4", "D5") for i in range(5)
        ]
        lone = [_item("d1-only", "D1", 1)]
        out = select(saturated + lone, limit=20, per_dim=5)
        dimensions = [x["dimension"] for x in out]
        counts = Counter(dimensions)
        self.assertEqual(len(out), 20)
        self.assertIn("D1", dimensions)
        self.assertEqual(sorted(counts.values()), [1, 4, 5, 5, 5])

    def test_eviction_tolerates_missing_dimension_key(self):
        items = [
            {"id": "no-dim-hi", "m": 5, "source_weight": 1.0, "published_at": "2026-11-03T10:00:00"},
            {"id": "no-dim-lo", "m": 4, "source_weight": 1.0, "published_at": "2026-11-03T10:00:00"},
            _item("d1-only", "D1", 1),
        ]
        out = select(items, limit=2, per_dim=5)
        self.assertEqual(len(out), 2)
        self.assertIn("D1", {x.get("dimension") for x in out})

    def test_sorted_by_m_desc(self):
        items = [_item("a", "D1", 2), _item("b", "D1", 5), _item("c", "D2", 4)]
        out = select(items, limit=20, per_dim=5)
        self.assertEqual([x["m"] for x in out], [5, 4, 2])

    def test_sorted_by_rank_key_tiebreakers(self):
        items = [
            _item("a", "D1", 4, source_weight=1.0, published_at="2026-11-03T12:00:00"),
            _item("b", "D1", 4, source_weight=2.0, published_at="2026-11-03T09:00:00"),
            _item("c", "D1", 4, source_weight=1.0, published_at="2026-11-03T11:00:00"),
            _item("d", "D1", 4, source_weight=2.0, published_at="2026-11-03T10:00:00"),
        ]
        out = select(items, limit=20, per_dim=5)
        self.assertEqual([x["id"] for x in out], ["d", "b", "a", "c"])


if __name__ == "__main__":
    unittest.main()
