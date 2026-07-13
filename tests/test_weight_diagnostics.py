from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from stock_signal_system.weight_diagnostics import (
    SCORE_COMPONENTS,
    append_score_snapshot,
    evaluate_weight_diagnostics,
)


def _write_recommendation_log(path: Path, trades: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["entry_date", "symbol", "name", "bucket", "entry_close", "eval_date", "return_5d", "win"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow(
                {
                    "entry_date": trade["entry_date"],
                    "symbol": trade["symbol"],
                    "name": "測試",
                    "bucket": "chip_confirmed",
                    "entry_close": "30.00",
                    "eval_date": trade["entry_date"],
                    "return_5d": f"{trade['return_5d']:.4f}",
                    "win": "1" if trade["return_5d"] > 0 else "0",
                }
            )


class WeightDiagnosticsTest(unittest.TestCase):
    def test_reports_insufficient_when_below_threshold(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            log_path = base / "log.csv"
            snapshot_path = base / "scores.csv"
            _write_recommendation_log(
                log_path, [{"entry_date": "2026-07-01", "symbol": f"{1000 + i}.TW", "return_5d": 0.02} for i in range(5)]
            )

            result = evaluate_weight_diagnostics(log_path, snapshot_path, min_sample_size=30)

            self.assertFalse(result.sufficient)
            self.assertEqual(result.sample_size, 5)
            self.assertEqual(result.correlations, ())

    def test_computes_correlation_once_sample_size_reached(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            log_path = base / "log.csv"
            snapshot_path = base / "scores.csv"
            trades = []
            for i in range(30):
                symbol = f"{1000 + i}.TW"
                # kronos_score perfectly predicts return; realtime_score is pure noise (inverted)
                kronos = 50.0 + i
                return_5d = i * 0.001
                trades.append({"entry_date": "2026-07-01", "symbol": symbol, "return_5d": return_5d})
                append_score_snapshot(
                    snapshot_path,
                    "2026-07-01",
                    symbol,
                    {
                        "kronos_score": kronos,
                        "news_score": 50.0,
                        "technical_score": 50.0,
                        "realtime_score": 100.0 - kronos,
                        "confidence_score": 50.0,
                        "chip_score": 50.0,
                    },
                )
            _write_recommendation_log(log_path, trades)

            result = evaluate_weight_diagnostics(log_path, snapshot_path, min_sample_size=30)

            self.assertTrue(result.sufficient)
            self.assertEqual(result.sample_size, 30)
            by_component = {item.component: item.correlation for item in result.correlations}
            self.assertAlmostEqual(by_component["kronos_score"], 1.0, places=4)
            self.assertAlmostEqual(by_component["realtime_score"], -1.0, places=4)
            self.assertIsNone(by_component["news_score"])  # constant series -> undefined correlation

    def test_score_snapshot_append_creates_header_once(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "scores.csv"
            append_score_snapshot(path, "2026-07-01", "1111.TW", {name: 50.0 for name in SCORE_COMPONENTS})
            append_score_snapshot(path, "2026-07-02", "2222.TW", {name: 60.0 for name in SCORE_COMPONENTS})

            with path.open("r", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["symbol"], "1111.TW")


if __name__ == "__main__":
    unittest.main()
