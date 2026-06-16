from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from stock_signal_system.data.tpex import combine_csv_files


class CsvMergeTest(unittest.TestCase):
    def test_combine_csv_files_merges_supplemental_columns_for_same_symbol(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            core = base / "core.csv"
            extra = base / "extra.csv"
            output = base / "merged.csv"
            with core.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "market", "name", "price"])
                writer.writeheader()
                writer.writerow({"symbol": "2330", "market": "tse", "name": "TSMC", "price": "950"})
            with extra.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "top10_main_force_buy_strength", "foreign_buy_streak_days"])
                writer.writeheader()
                writer.writerow({"symbol": "2330", "top10_main_force_buy_strength": "72", "foreign_buy_streak_days": "4"})

            combine_csv_files([core, extra], output)

            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["symbol"], "2330")
            self.assertEqual(row["name"], "TSMC")
            self.assertEqual(row["top10_main_force_buy_strength"], "72")
            self.assertEqual(row["foreign_buy_streak_days"], "4")


if __name__ == "__main__":
    unittest.main()
