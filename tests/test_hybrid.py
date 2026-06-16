from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from quant_research_platform.config import QuantPlatformConfig
from quant_research_platform.daily_stock_bridge import load_latest_realtime_states
from quant_research_platform.hybrid import run_tw_hybrid


class HybridTest(unittest.TestCase):
    def test_latest_realtime_state_maps_tw_symbols(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "realtime.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["datetime", "symbol", "market", "close", "previous_close"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "datetime": "2026-04-30 13:30:00",
                        "symbol": "2330",
                        "market": "tse",
                        "close": "2135",
                        "previous_close": "2180",
                    }
                )

            states = load_latest_realtime_states(path)

            self.assertIn("2330.TW", states)
            self.assertLess(states["2330.TW"].intraday_return, 0)

    def test_run_tw_hybrid_writes_outputs_with_fallback_model(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            price_path = base / "prices.csv"
            universe_path = base / "universe.csv"
            with universe_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "market", "name", "industry", "price", "volume"])
                writer.writeheader()
                writer.writerow(
                    {
                        "symbol": "2330",
                        "market": "tse",
                        "name": "台積電",
                        "industry": "半導體",
                        "price": 100,
                        "volume": 1000,
                    }
                )
            with price_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
                writer.writeheader()
                for idx in range(8):
                    writer.writerow(
                        {
                            "symbol": "2330.TW",
                            "date": f"2026-04-{20 + idx:02d}",
                            "open": 100 + idx,
                            "high": 102 + idx,
                            "low": 99 + idx,
                            "close": 101 + idx,
                            "volume": 1000 + idx,
                        }
                    )

            config = QuantPlatformConfig(
                symbols=("2330.TW",),
                data_source="csv",
                ohlcv_path=price_path,
                openbb_provider=None,
                interval="1d",
                lookback=8,
                prediction_length=2,
                top_n=1,
                initial_cash=100000,
                transaction_cost_bps=10,
                benchmark_symbol="2330.TW",
                kronos_repo_path=None,
                kronos_tokenizer="",
                kronos_model="",
                qlib_data_path=None,
                output_dir=base / "reports",
                universe_path=universe_path,
            )

            report_path, csv_path, qlib_path, notification = run_tw_hybrid(
                config,
                date(2026, 4, 30),
                news_path=None,
                stock_snapshot_path=universe_path,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(qlib_path.exists())
            self.assertEqual(notification, "disabled")

            report = report_path.read_text(encoding="utf-8")
            self.assertIn("新版主清單 + 舊版觀察清單", report)
            self.assertIn("<table>", report)
            self.assertIn("台積電", report)
            self.assertIn("半導體", report)
            self.assertNotIn("| 2330.TW | 2330.TW |", report)
            self.assertIn("technical-chart-data", report)
            self.assertIn("選股條件摘要", report)
            self.assertIn("前十大主力強度", report)
            self.assertIn("籌碼狀態", report)
            self.assertIn("K值 < 40", report)
            self.assertIn("近 5 日融資增加前 100 大", report)
            self.assertIn("收盤價 20 日均線上升", report)
            self.assertIn("互動技術分析策略", report)
            self.assertIn("均線、趨勢與支撐壓力", report)
            self.assertIn("動能與波動", report)
            self.assertIn("型態、量價與突破確認", report)
            self.assertNotIn("舊版參數備查", report)
            self.assertNotIn("TW_HYBRID_SELECTION_STRATEGY.md", report)
            self.assertNotIn("五代理決策看板", report)
            self.assertNotIn("產出檔案", report)
            self.assertNotIn("Model Execution Evidence", report)


if __name__ == "__main__":
    unittest.main()
