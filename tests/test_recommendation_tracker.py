from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_signal_system.recommendation_tracker import (
    append_recommendations,
    evaluate_pending,
    summarize,
)


def _write_price_snapshot(snapshot_dir: Path, snapshot_date: str, closes: dict[str, float]) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"tw_price_daily_{snapshot_date}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for symbol, close in closes.items():
            writer.writerow(
                {"symbol": symbol, "date": snapshot_date, "open": close, "high": close, "low": close, "close": close, "volume": 1000}
            )


def _write_price_snapshot_bars(snapshot_dir: Path, snapshot_date: str, bars: dict[str, dict[str, float]]) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"tw_price_daily_{snapshot_date}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for symbol, bar in bars.items():
            writer.writerow({"symbol": symbol, "date": snapshot_date, "volume": 1000, **bar})


class RecommendationTrackerTest(unittest.TestCase):
    def test_append_skips_duplicates_and_invalid_entries(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "log.csv"
            picks = [
                {"symbol": "1111.TW", "name": "測試", "bucket": "chip_confirmed", "entry_close": 45.0, "stop_loss_price": 43.0},
                {"symbol": "1111.TW", "name": "測試", "bucket": "chip_confirmed", "entry_close": 45.0},
                {"symbol": "", "entry_close": 45.0},
                {"symbol": "2222.TW", "name": "無價", "bucket": "legacy_watch", "entry_close": 0},
            ]
            added = append_recommendations(log_path, date(2026, 7, 1), picks)
            self.assertEqual(added, 1)
            added_again = append_recommendations(log_path, date(2026, 7, 1), picks[:1])
            self.assertEqual(added_again, 0)
            added_next_day = append_recommendations(log_path, date(2026, 7, 2), picks[:1])
            self.assertEqual(added_next_day, 1)

    def test_evaluate_pending_computes_5_session_outcome(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            log_path = base / "log.csv"
            snapshot_dir = base / "price_snapshots"
            append_recommendations(
                log_path,
                date(2026, 7, 1),
                [{"symbol": "1111.TW", "name": "贏家", "bucket": "chip_confirmed", "entry_close": 40.0}],
            )
            closes = [41.0, 42.0, 44.0, 43.0, 42.0]
            for offset, close in enumerate(closes, start=2):
                _write_price_snapshot(snapshot_dir, f"2026-07-{offset:02d}", {"1111": close})

            evaluated = evaluate_pending(log_path, snapshot_dir, date(2026, 7, 8))
            self.assertEqual(evaluated, 1)

            summary = summarize(log_path)
            self.assertEqual(summary.evaluated_count, 1)
            self.assertEqual(summary.pending_count, 0)
            self.assertEqual(summary.win_rate, 1.0)
            self.assertAlmostEqual(summary.average_return_5d, 42.0 / 40.0 - 1.0, places=4)
            self.assertAlmostEqual(summary.average_max_return_5d, 44.0 / 40.0 - 1.0, places=4)

    def test_evaluate_waits_until_enough_sessions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            log_path = base / "log.csv"
            snapshot_dir = base / "price_snapshots"
            append_recommendations(
                log_path,
                date(2026, 7, 1),
                [{"symbol": "1111.TW", "name": "等待", "bucket": "legacy_watch", "entry_close": 40.0}],
            )
            for offset in range(2, 5):  # only 3 forward sessions
                _write_price_snapshot(snapshot_dir, f"2026-07-{offset:02d}", {"1111": 41.0})

            evaluated = evaluate_pending(log_path, snapshot_dir, date(2026, 7, 4))
            self.assertEqual(evaluated, 0)
            summary = summarize(log_path)
            self.assertEqual(summary.evaluated_count, 0)
            self.assertEqual(summary.pending_count, 1)

    def test_losing_recommendation_counts_as_loss(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            log_path = base / "log.csv"
            snapshot_dir = base / "price_snapshots"
            append_recommendations(
                log_path,
                date(2026, 7, 1),
                [{"symbol": "3333.TW", "name": "輸家", "bucket": "chip_watch", "entry_close": 40.0}],
            )
            for offset in range(2, 7):
                _write_price_snapshot(snapshot_dir, f"2026-07-{offset:02d}", {"3333": 38.0})

            evaluate_pending(log_path, snapshot_dir, date(2026, 7, 8))
            summary = summarize(log_path)
            self.assertEqual(summary.win_rate, 0.0)

    def test_exits_early_at_stop_loss_when_low_touches_it(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            log_path = base / "log.csv"
            snapshot_dir = base / "price_snapshots"
            append_recommendations(
                log_path,
                date(2026, 7, 1),
                [
                    {
                        "symbol": "4444.TW",
                        "name": "停損測試",
                        "bucket": "chip_confirmed",
                        "entry_close": 40.0,
                        "stop_loss_price": 38.0,
                        "take_profit_price": 46.0,
                    }
                ],
            )
            # Day 1: dips to stop-loss; later days would otherwise rally past
            # take-profit, proving the early exit actually took effect.
            _write_price_snapshot_bars(snapshot_dir, "2026-07-02", {"4444": {"open": 39.5, "high": 39.8, "low": 37.5, "close": 38.2}})
            for offset in range(3, 7):
                _write_price_snapshot_bars(
                    snapshot_dir, f"2026-07-{offset:02d}", {"4444": {"open": 47, "high": 48, "low": 46.5, "close": 47.5}}
                )

            evaluated = evaluate_pending(log_path, snapshot_dir, date(2026, 7, 8))
            self.assertEqual(evaluated, 1)
            summary = summarize(log_path)
            self.assertEqual(summary.stop_loss_exit_count, 1)
            self.assertEqual(summary.take_profit_exit_count, 0)
            self.assertEqual(summary.win_rate, 0.0)
            self.assertAlmostEqual(summary.average_return_5d, 38.0 / 40.0 - 1.0, places=4)
            row = summary.recent_evaluated[0]
            self.assertEqual(row["eval_date"], "2026-07-02")
            self.assertEqual(row["exit_reason"], "stop_loss")

    def test_exits_early_at_take_profit_when_high_touches_it(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            log_path = base / "log.csv"
            snapshot_dir = base / "price_snapshots"
            append_recommendations(
                log_path,
                date(2026, 7, 1),
                [
                    {
                        "symbol": "5555.TW",
                        "name": "停利測試",
                        "bucket": "chip_confirmed",
                        "entry_close": 40.0,
                        "stop_loss_price": 38.0,
                        "take_profit_price": 46.0,
                    }
                ],
            )
            _write_price_snapshot_bars(snapshot_dir, "2026-07-02", {"5555": {"open": 41, "high": 42, "low": 40.5, "close": 41.5}})
            _write_price_snapshot_bars(snapshot_dir, "2026-07-03", {"5555": {"open": 43, "high": 46.5, "low": 42.5, "close": 46.2}})
            for offset in range(4, 7):
                _write_price_snapshot_bars(
                    snapshot_dir, f"2026-07-{offset:02d}", {"5555": {"open": 30, "high": 31, "low": 29, "close": 30}}
                )

            evaluate_pending(log_path, snapshot_dir, date(2026, 7, 8))
            summary = summarize(log_path)
            self.assertEqual(summary.take_profit_exit_count, 1)
            self.assertEqual(summary.stop_loss_exit_count, 0)
            self.assertEqual(summary.win_rate, 1.0)
            row = summary.recent_evaluated[0]
            self.assertEqual(row["eval_date"], "2026-07-03")
            self.assertEqual(row["exit_reason"], "take_profit")
            self.assertAlmostEqual(float(row["return_5d"]), 46.0 / 40.0 - 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
