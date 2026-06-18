from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from quant_research_platform.data import Bar
from stock_signal_system.cli_handlers import _should_tolerate_short_history, _validate_chip_snapshot_schema


class CliHandlersTest(unittest.TestCase):
    def test_short_history_tolerance_allows_recent_listing(self):
        current_date = date(2026, 6, 18)
        bars = [
            Bar(
                symbol="7803.TW",
                timestamp=datetime(2026, 5, 28) + timedelta(days=index),
                open=20.0,
                high=21.0,
                low=19.5,
                close=20.5,
                volume=1000.0,
            )
            for index in range(22)
        ]

        self.assertTrue(_should_tolerate_short_history("7803.TW", bars, 120, current_date))

    def test_short_history_tolerance_rejects_stale_or_too_short_history(self):
        current_date = date(2026, 6, 18)
        stale_bars = [
            Bar(
                symbol="1234.TW",
                timestamp=datetime(2026, 5, 1) + timedelta(days=index),
                open=20.0,
                high=21.0,
                low=19.5,
                close=20.5,
                volume=1000.0,
            )
            for index in range(22)
        ]
        tiny_bars = stale_bars[:10]

        self.assertFalse(_should_tolerate_short_history("1234.TW", stale_bars, 120, current_date))
        self.assertFalse(_should_tolerate_short_history("1234.TW", tiny_bars, 120, current_date))

    def test_validate_chip_snapshot_schema_accepts_new_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tw_chip_snapshot.csv"
            path.write_text(
                ",".join(
                    [
                        "symbol",
                        "top10_main_force_buy_strength",
                        "top10_main_force_net_buy",
                        "branch_main_force_buy_streak_days",
                        "foreign_buy_streak_days",
                        "chip_data_source",
                        "chip_data_source_status",
                    ]
                )
                + "\n2330,55.0,1200,2,3,TWSE T86 official + HiStock branch,official+broker\n",
                encoding="utf-8-sig",
            )

            _validate_chip_snapshot_schema(path)

    def test_validate_chip_snapshot_schema_rejects_proxy_only_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tw_chip_snapshot.csv"
            path.write_text(
                "symbol,top10_main_force_buy_strength_proxy,foreign_buy_streak_days,chip_data_source\n"
                "2330,55.0,3,TWSE T86 official proxy\n",
                encoding="utf-8-sig",
            )

            with self.assertRaises(ValueError):
                _validate_chip_snapshot_schema(path)


if __name__ == "__main__":
    unittest.main()
