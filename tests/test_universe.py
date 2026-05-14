from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from quant_research_platform.universe import select_candidate_symbols


class UniverseSelectionTest(unittest.TestCase):
    def test_selects_dynamic_candidates_with_market_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "universe.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["symbol", "market", "industry", "price", "volume", "avg_volume_20d", "revenue_growth_yoy", "pe_ratio", "notes"],
                )
                writer.writeheader()
                writer.writerow({"symbol": "1111", "market": "tse", "industry": "傳產", "price": 50, "volume": 1000, "avg_volume_20d": 1000, "revenue_growth_yoy": 0, "pe_ratio": 20, "notes": ""})
                writer.writerow({"symbol": "2222", "market": "otc", "industry": "半導體", "price": 80, "volume": 9000000, "avg_volume_20d": 9000000, "revenue_growth_yoy": 30, "pe_ratio": 18, "notes": "TPEx"})

            selected = select_candidate_symbols(path, ("2330.TW",), 1)

            self.assertEqual(selected, ("2222.TWO",))


if __name__ == "__main__":
    unittest.main()
