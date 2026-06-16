from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from quant_research_platform.universe import build_candidate_selection_plan, select_candidate_symbols


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

    def test_selection_plan_splits_revised_and_legacy_watch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            universe_path = base / "universe.csv"
            ohlcv_path = base / "prices.csv"
            with universe_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "symbol",
                        "market",
                        "industry",
                        "price",
                        "volume",
                        "avg_volume_20d",
                        "revenue_growth_yoy",
                        "pe_ratio",
                        "margin_financing_change_5d",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "symbol": "1111",
                        "market": "tse",
                        "industry": "半導體",
                        "price": 80,
                        "volume": 200000,
                        "avg_volume_20d": 200000,
                        "revenue_growth_yoy": 20,
                        "pe_ratio": 18,
                        "margin_financing_change_5d": 5000,
                    }
                )
                writer.writerow(
                    {
                        "symbol": "2222",
                        "market": "tse",
                        "industry": "半導體",
                        "price": 28,
                        "volume": 9000000,
                        "avg_volume_20d": 9000000,
                        "revenue_growth_yoy": 35,
                        "pe_ratio": 16,
                        "margin_financing_change_5d": 0,
                    }
                )
            with ohlcv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
                writer.writeheader()
                revised_closes = [100 + index for index in range(20)] + [105]
                legacy_closes = [40 + index for index in range(20)] + [60]
                for idx, close in enumerate(revised_closes):
                    writer.writerow(
                        {
                            "symbol": "1111.TW",
                            "date": f"2026-05-{idx + 1:02d}",
                            "open": close,
                            "high": close + 1,
                            "low": close - 1,
                            "close": close,
                            "volume": 1000,
                        }
                    )
                for idx, close in enumerate(legacy_closes):
                    writer.writerow(
                        {
                            "symbol": "2222.TW",
                            "date": f"2026-05-{idx + 1:02d}",
                            "open": close,
                            "high": close + 1,
                            "low": close - 1,
                            "close": close,
                            "volume": 1000,
                        }
                    )

            plan = build_candidate_selection_plan(universe_path, ("2330.TW",), 2, ohlcv_path=ohlcv_path)

            self.assertEqual(plan.chip_radar_symbols, ())
            self.assertEqual(plan.revised_symbols, ())
            self.assertEqual(plan.legacy_watch_symbols, ("2222.TW", "1111.TW"))
            self.assertEqual(plan.selected_symbols, ("2222.TW", "1111.TW"))

    def test_selection_plan_prioritizes_chip_breakout_symbols(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            universe_path = base / "universe.csv"
            ohlcv_path = base / "prices.csv"
            with universe_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "symbol",
                        "market",
                        "industry",
                        "price",
                        "volume",
                        "avg_volume_20d",
                        "revenue_growth_yoy",
                        "pe_ratio",
                        "top10_main_force_buy_strength",
                        "foreign_buy_streak_days",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "symbol": "3333",
                        "market": "tse",
                        "industry": "半導體",
                        "price": 55,
                        "volume": 500000,
                        "avg_volume_20d": 400000,
                        "revenue_growth_yoy": 12,
                        "pe_ratio": 20,
                        "top10_main_force_buy_strength": 70,
                        "foreign_buy_streak_days": 4,
                    }
                )
                writer.writerow(
                    {
                        "symbol": "4444",
                        "market": "tse",
                        "industry": "半導體",
                        "price": 80,
                        "volume": 600000,
                        "avg_volume_20d": 600000,
                        "revenue_growth_yoy": 10,
                        "pe_ratio": 18,
                        "top10_main_force_buy_strength": 0,
                        "foreign_buy_streak_days": 0,
                    }
                )
            with ohlcv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
                writer.writeheader()
                closes = [50, 50.5] * 10 + [56]
                for idx, close in enumerate(closes):
                    writer.writerow(
                        {
                            "symbol": "3333.TW",
                            "date": f"2026-05-{idx + 1:02d}",
                            "open": close,
                            "high": close + 0.6,
                            "low": close - 0.6,
                            "close": close,
                            "volume": 1000 if idx < 20 else 1600,
                        }
                    )
                for idx, close in enumerate([70 + (idx % 2) for idx in range(21)]):
                    writer.writerow(
                        {
                            "symbol": "4444.TW",
                            "date": f"2026-05-{idx + 1:02d}",
                            "open": close,
                            "high": close + 0.6,
                            "low": close - 0.6,
                            "close": close,
                            "volume": 1000,
                        }
                    )

            plan = build_candidate_selection_plan(universe_path, ("2330.TW",), 2, ohlcv_path=ohlcv_path)

            self.assertEqual(plan.chip_breakout_symbols, ("3333.TW",))
            self.assertEqual(plan.selected_symbols[0], "3333.TW")

    def test_proxy_branch_streak_alone_does_not_trigger_chip_breakout(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            universe_path = base / "universe.csv"
            ohlcv_path = base / "prices.csv"
            with universe_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "symbol",
                        "market",
                        "industry",
                        "price",
                        "volume",
                        "avg_volume_20d",
                        "revenue_growth_yoy",
                        "pe_ratio",
                        "top10_main_force_buy_strength",
                        "branch_main_force_buy_streak_days_proxy",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "symbol": "5555",
                        "market": "tse",
                        "industry": "半導體",
                        "price": 55,
                        "volume": 500000,
                        "avg_volume_20d": 400000,
                        "revenue_growth_yoy": 12,
                        "pe_ratio": 20,
                        "top10_main_force_buy_strength": 70,
                        "branch_main_force_buy_streak_days_proxy": 4,
                    }
                )
            with ohlcv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
                writer.writeheader()
                closes = [50, 50.5] * 10 + [56]
                for idx, close in enumerate(closes):
                    writer.writerow(
                        {
                            "symbol": "5555.TW",
                            "date": f"2026-05-{idx + 1:02d}",
                            "open": close,
                            "high": close + 0.6,
                            "low": close - 0.6,
                            "close": close,
                            "volume": 1000 if idx < 20 else 1600,
                        }
                    )

            plan = build_candidate_selection_plan(universe_path, ("2330.TW",), 2, ohlcv_path=ohlcv_path)

            self.assertEqual(plan.chip_radar_symbols, ("5555.TW",))
            self.assertEqual(plan.chip_breakout_symbols, ("5555.TW",))


if __name__ == "__main__":
    unittest.main()
