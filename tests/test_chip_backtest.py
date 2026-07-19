from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from stock_signal_system.chip_backtest import run_chip_breakout_backtest, save_backtest_report


def _write_price_snapshot(price_dir: Path, snapshot_date: str, rows: dict[str, dict[str, float]]) -> None:
    price_dir.mkdir(parents=True, exist_ok=True)
    path = price_dir / f"tw_price_daily_{snapshot_date}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for symbol, bar in rows.items():
            writer.writerow({"symbol": symbol, "date": snapshot_date, **bar})


def _write_chip_snapshot(chip_dir: Path, snapshot_date: str, rows: dict[str, dict[str, object]]) -> None:
    chip_dir.mkdir(parents=True, exist_ok=True)
    path = chip_dir / f"tw_chip_snapshot_{snapshot_date}.csv"
    fieldnames = ["symbol", "top10_main_force_net_buy", "foreign_buy_streak_days", "platform_breakout"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for symbol, row in rows.items():
            writer.writerow({"symbol": symbol, **row})


def _dates(count: int) -> list[str]:
    dates = []
    month, day = 5, 1
    for _ in range(count):
        dates.append(f"2026-{month:02d}-{day:02d}")
        day += 1
        if day > 28:
            month += 1
            day = 1
    return dates


class ChipBacktestTest(unittest.TestCase):
    def test_detects_signal_and_computes_forward_returns(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            price_dir = base / "price_snapshots"
            chip_dir = base / "chip_snapshots"
            dates = _dates(27)  # 21 history + signal (idx 21) + 5 forward
            signal_index = 21

            # symbol 1111: liquid 30 NTD stock; chip-strong with explicit breakout
            # flag on the signal date.
            forward_closes = [31.0, 32.0, 33.0, 32.5, 32.0]
            for index, snapshot_date in enumerate(dates):
                if index < signal_index:
                    close = 30.0
                elif index == signal_index:
                    close = 30.5
                else:
                    close = forward_closes[index - signal_index - 1]
                _write_price_snapshot(
                    price_dir,
                    snapshot_date,
                    {"1111": {"open": close, "high": close + 0.2, "low": close - 0.2, "close": close, "volume": 5_000_000}},
                )
            _write_chip_snapshot(
                chip_dir,
                dates[signal_index],
                {"1111": {"top10_main_force_net_buy": 8000, "foreign_buy_streak_days": 3, "platform_breakout": 1}},
            )

            result = run_chip_breakout_backtest(chip_dir, price_dir)

            self.assertEqual(result.signal_dates_scanned, 1)
            self.assertEqual(result.trade_count, 1)
            trade = result.trades[0]
            self.assertEqual(trade.symbol, "1111")
            self.assertEqual(trade.signal_date, dates[signal_index])
            self.assertAlmostEqual(trade.return_5d, 32.0 / 30.5 - 1.0, places=4)
            self.assertAlmostEqual(trade.max_return_5d, 33.0 / 30.5 - 1.0, places=4)
            self.assertTrue(trade.win)
            self.assertEqual(result.win_rate, 1.0)

            output = save_backtest_report(result, base / "out.csv")
            with output.open("r", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["symbol"], "1111")
            self.assertEqual(rows[0]["win"], "1")

    def test_filters_price_band_and_weak_chips(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            price_dir = base / "price_snapshots"
            chip_dir = base / "chip_snapshots"
            dates = _dates(27)
            signal_index = 21

            for index, snapshot_date in enumerate(dates):
                _write_price_snapshot(
                    price_dir,
                    snapshot_date,
                    {
                        # below the 10-yuan floor
                        "9999": {"open": 8, "high": 8.1, "low": 7.9, "close": 8, "volume": 5_000_000},
                        # weak chips
                        "8888": {"open": 30, "high": 30.5, "low": 29.5, "close": 30, "volume": 5_000_000},
                        # illiquid
                        "7777": {"open": 30, "high": 30.5, "low": 29.5, "close": 30, "volume": 1000},
                    },
                )
            _write_chip_snapshot(
                chip_dir,
                dates[signal_index],
                {
                    "9999": {"top10_main_force_net_buy": 8000, "foreign_buy_streak_days": 3, "platform_breakout": 1},
                    "8888": {"top10_main_force_net_buy": 0, "foreign_buy_streak_days": 0, "platform_breakout": 1},
                    "7777": {"top10_main_force_net_buy": 8000, "foreign_buy_streak_days": 3, "platform_breakout": 1},
                },
            )

            result = run_chip_breakout_backtest(chip_dir, price_dir)
            self.assertEqual(result.trade_count, 0)

    def test_no_trades_when_history_too_short(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            price_dir = base / "price_snapshots"
            chip_dir = base / "chip_snapshots"
            dates = _dates(10)
            for snapshot_date in dates:
                _write_price_snapshot(
                    price_dir,
                    snapshot_date,
                    {"1111": {"open": 30, "high": 30.5, "low": 29.5, "close": 30, "volume": 5_000_000}},
                )
                _write_chip_snapshot(
                    chip_dir,
                    snapshot_date,
                    {"1111": {"top10_main_force_net_buy": 8000, "foreign_buy_streak_days": 3, "platform_breakout": 1}},
                )

            result = run_chip_breakout_backtest(chip_dir, price_dir)
            self.assertEqual(result.signal_dates_scanned, 0)
            self.assertEqual(result.trade_count, 0)


if __name__ == "__main__":
    unittest.main()
