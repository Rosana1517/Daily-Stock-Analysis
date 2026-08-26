from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from quant_research_platform.config import QuantPlatformConfig
from quant_research_platform.daily_stock_bridge import load_latest_realtime_states
from quant_research_platform.hybrid import (
    HybridRow,
    _apply_sector_diversification,
    _chip_score,
    _load_bars,
    _screening_priority_groups,
    run_tw_hybrid,
)


def _make_row(symbol: str, industry: str, hybrid_score: float) -> HybridRow:
    return HybridRow(
        symbol=symbol,
        name=symbol,
        industry=industry,
        screening_bucket="chip_watch",
        legacy_hit=True,
        new_strategy_hit=False,
        chip_radar_hit=False,
        signal_source="momentum-fallback",
        kronos_return=0.02,
        kronos_score=60.0,
        news_score=50.0,
        technical_score=50.0,
        realtime_score=50.0,
        confidence_score=50.0,
        hybrid_score=hybrid_score,
        current_close=30.0,
        predicted_close=31.0,
        realtime_status="normal",
        action="watch",
        risk_note="ok",
        stop_loss_price=28.0,
        take_profit_price=34.0,
        top10_main_force_buy_strength=None,
        top10_main_force_net_buy=None,
        official_broker_net_buy=None,
        foreign_buy_streak_days=None,
        branch_main_force_buy_streak_days=None,
        branch_main_force_leader="",
        chip_data_date="",
        chip_data_source="",
        chip_data_source_status="",
        top10_main_force_brokers="",
        technical_evidence=(),
    )


class SectorDiversificationTest(unittest.TestCase):
    def test_caps_picks_per_industry_keeping_priority_order(self):
        rows = [
            _make_row("1111.TW", "半導體", 90.0),
            _make_row("2222.TW", "半導體", 85.0),
            _make_row("3333.TW", "半導體", 80.0),
            _make_row("4444.TW", "傳產", 70.0),
        ]

        kept = _apply_sector_diversification(rows, max_per_industry=2)

        self.assertEqual([row.symbol for row in kept], ["1111.TW", "2222.TW", "4444.TW"])

    def test_zero_or_negative_cap_disables_filtering(self):
        rows = [_make_row("1111.TW", "半導體", 90.0), _make_row("2222.TW", "半導體", 85.0)]
        self.assertEqual(_apply_sector_diversification(rows, max_per_industry=0), rows)


class ChipScoreTest(unittest.TestCase):
    def test_neutral_when_no_chip_data(self):
        self.assertEqual(_chip_score({}), 50.0)

    def test_uses_strength_directly_when_no_streaks(self):
        self.assertEqual(_chip_score({"top10_main_force_buy_strength": 70.0}), 70.0)

    def test_streaks_add_bonus_capped_at_100(self):
        score = _chip_score(
            {
                "top10_main_force_buy_strength": 90.0,
                "foreign_buy_streak_days": 5,
                "branch_main_force_buy_streak_days": 5,
            }
        )
        self.assertEqual(score, 100.0)

    def test_streak_bonus_is_capped_beyond_five_days(self):
        capped = _chip_score(
            {
                "top10_main_force_buy_strength": 40.0,
                "foreign_buy_streak_days": 20,
                "branch_main_force_buy_streak_days": 20,
            }
        )
        five_day = _chip_score(
            {
                "top10_main_force_buy_strength": 40.0,
                "foreign_buy_streak_days": 5,
                "branch_main_force_buy_streak_days": 5,
            }
        )
        self.assertEqual(capped, five_day)


class HybridTest(unittest.TestCase):
    def test_screening_priority_groups_count_pair_intersections_including_triple_hits(self):
        row = HybridRow(
            symbol="2353.TW",
            name="宏碁",
            industry="電腦及週邊設備業",
            screening_bucket="chip_confirmed",
            legacy_hit=True,
            new_strategy_hit=True,
            chip_radar_hit=True,
            signal_source="momentum-fallback",
            kronos_return=0.05,
            kronos_score=70.0,
            news_score=60.0,
            technical_score=55.0,
            realtime_score=50.0,
            confidence_score=55.0,
            hybrid_score=72.0,
            current_close=35.0,
            predicted_close=37.0,
            realtime_status="normal",
            action="watch",
            risk_note="ok",
            stop_loss_price=34.0,
            take_profit_price=39.0,
            top10_main_force_buy_strength=40.0,
            top10_main_force_net_buy=9000.0,
            official_broker_net_buy=None,
            foreign_buy_streak_days=3.0,
            branch_main_force_buy_streak_days=2.0,
            branch_main_force_leader="測試分點",
            chip_data_date="2026-06-17",
            chip_data_source="TWSE T86 official + HiStock branch",
            chip_data_source_status="official+broker",
            top10_main_force_brokers="測試券商",
            technical_evidence=(),
        )

        groups = {group["label"]: group for group in _screening_priority_groups([row])}

        self.assertEqual(groups["三者全中"]["count"], 1)
        self.assertEqual(groups["品質底池 + 發動確認"]["count"], 1)
        self.assertEqual(groups["品質底池 + 主力動向"]["count"], 1)
        self.assertEqual(groups["主力動向 + 發動確認"]["count"], 1)
        self.assertIn("2353.TW", groups["品質底池 + 發動確認"]["samples"])

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
            self.assertNotIn("| 2330.TW | 2330.TW |", report)
            self.assertIn("候選股票分析", report)
            self.assertIn("RSS 產業訊號", report)
            self.assertIn('<details class="candidate-panel">', report)
            self.assertIn("technical-chart-data", report)
            self.assertIn("tech-section-marker", report)
            self.assertIn("投組模擬", report)
            self.assertIn("新聞快訊", report)
            self.assertIn('"strategySummary"', report)
            self.assertIn("選股優先順序表", report)
            self.assertIn("可重算驗證指標", report)
            self.assertNotIn("每日研究名單", report)
            self.assertNotIn("候選全覽", report)
            self.assertNotIn("選股條件摘要", report)
            self.assertNotIn("籌碼優先流程摘要", report)
            self.assertNotIn("TW_HYBRID_SELECTION_STRATEGY.md", report)
            self.assertNotIn("Model Execution Evidence", report)

    def test_load_bars_backfills_missing_symbols_into_csv(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            price_path = base / "prices.csv"
            with price_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
                writer.writeheader()
                writer.writerow(
                    {
                        "symbol": "2330.TW",
                        "date": "2026-04-20",
                        "open": 100,
                        "high": 102,
                        "low": 99,
                        "close": 101,
                        "volume": 1000,
                    }
                )

            config = QuantPlatformConfig(
                symbols=("2330.TW", "2801.TW"),
                data_source="csv",
                ohlcv_path=price_path,
                openbb_provider=None,
                interval="1d",
                lookback=60,
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
                universe_path=None,
            )

            def fake_fetch(symbols, period):
                self.assertEqual(symbols, ("2330.TW", "2801.TW"))
                bars = {}
                from datetime import datetime, timedelta

                base_date = datetime(2026, 1, 1)
                for symbol in symbols:
                    bars[symbol] = [
                        {
                            "symbol": symbol,
                            "date": (base_date + timedelta(days=day - 1)).strftime("%Y-%m-%d"),
                            "open": 10 + day,
                            "high": 11 + day,
                            "low": 9 + day,
                            "close": 10.5 + day,
                            "volume": 1000 + day,
                        }
                        for day in range(1, 62)
                    ]
                from quant_research_platform.data import Bar

                converted = {}
                for symbol, rows in bars.items():
                    converted[symbol] = [
                        Bar(
                            symbol=symbol,
                            timestamp=datetime.strptime(row["date"], "%Y-%m-%d"),
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row["volume"]),
                        )
                        for row in rows
                    ]
                return converted

            with patch("quant_research_platform.hybrid.fetch_yahoo_ohlcv", side_effect=fake_fetch):
                bars_by_symbol = _load_bars(config)

            self.assertGreaterEqual(len(bars_by_symbol["2330.TW"]), 60)
            self.assertGreaterEqual(len(bars_by_symbol["2801.TW"]), 60)

            persisted = price_path.read_text(encoding="utf-8-sig")
            self.assertIn("2801.TW", persisted)


if __name__ == "__main__":
    unittest.main()
