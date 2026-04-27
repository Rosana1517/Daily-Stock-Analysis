from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.models import PriceBar
from stock_signal_system.training_data import (
    TrainingDataPolicy,
    TrainingSample,
    daily_return_matrix,
    detect_dirty_training_dates,
    filter_training_samples,
)


def bar(symbol: str, day: int, close: float) -> PriceBar:
    return PriceBar(symbol=symbol, date=date(2026, 4, day), open=close, high=close, low=close, close=close)


class TrainingDataTest(unittest.TestCase):
    def test_daily_return_matrix_uses_symbol_history(self):
        returns = daily_return_matrix({"2330": [bar("2330", 1, 100), bar("2330", 2, 110)]})

        self.assertAlmostEqual(returns[date(2026, 4, 2)]["2330"], 0.10)

    def test_detects_broad_rally_as_dirty_training_date(self):
        history = {
            "2330": [bar("2330", 1, 100), bar("2330", 2, 104)],
            "2382": [bar("2382", 1, 100), bar("2382", 2, 105)],
            "2317": [bar("2317", 1, 100), bar("2317", 2, 106)],
            "2308": [bar("2308", 1, 100), bar("2308", 2, 104)],
            "3231": [bar("3231", 1, 100), bar("3231", 2, 103)],
        }

        dirty = detect_dirty_training_dates(history)

        self.assertIn("broad_rally_market", dirty[date(2026, 4, 2)])

    def test_detects_index_black_swan_market_move(self):
        history = {
            "TAIEX": [bar("TAIEX", 1, 20000), bar("TAIEX", 2, 18400)],
            "2330": [bar("2330", 1, 100), bar("2330", 2, 99)],
        }

        dirty = detect_dirty_training_dates(history, market_symbol="TAIEX")

        self.assertIn("black_swan_market_move", dirty[date(2026, 4, 2)])

    def test_filter_training_samples_purges_event_window_and_tags(self):
        policy = TrainingDataPolicy(purge_before_days=1, purge_after_days=1)
        dirty_dates = {date(2026, 4, 10): ("black_swan_market_move",)}
        samples = [
            TrainingSample("2330", date(2026, 4, 8), {"momentum": 0.1}, 1),
            TrainingSample("2330", date(2026, 4, 9), {"momentum": 0.1}, 1),
            TrainingSample("2382", date(2026, 4, 11), {"momentum": 0.2}, 1),
            TrainingSample("2308", date(2026, 4, 12), {"momentum": 0.3}, 1, tags=("limit_up_down",)),
        ]

        clean, dropped = filter_training_samples(samples, dirty_dates, policy)

        self.assertEqual([sample.sample_date for sample in clean], [date(2026, 4, 8)])
        self.assertEqual(len(dropped), 3)
        self.assertTrue(any("tag:limit_up_down" in item.reasons for item in dropped))


if __name__ == "__main__":
    unittest.main()
