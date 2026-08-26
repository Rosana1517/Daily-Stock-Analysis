from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.data.pristine_index import (
    PristineIndexPoint,
    _parse_label_date,
    evaluate_relative_strength,
)


def _points(*prices: float, start: date = date(2026, 8, 1)) -> tuple[PristineIndexPoint, ...]:
    return tuple(PristineIndexPoint(date.fromordinal(start.toordinal() + i), price) for i, price in enumerate(prices))


class ParseLabelDateTest(unittest.TestCase):
    def test_parses_slash_separated_label(self):
        self.assertEqual(_parse_label_date("2026/08/26"), date(2026, 8, 26))

    def test_invalid_label_returns_none(self):
        self.assertIsNone(_parse_label_date("not-a-date"))
        self.assertIsNone(_parse_label_date(None))


class EvaluateRelativeStrengthTest(unittest.TestCase):
    def test_insufficient_history_returns_none(self):
        points = _points(100, 101, 102)
        closes = [1000.0, 1001.0, 1002.0]
        self.assertIsNone(evaluate_relative_strength(points, closes, lookback_sessions=5))

    def test_market_selloff_with_pristine_resilience_is_safe_haven(self):
        # Pristine roughly flat while TAIEX drops hard over the window.
        points = _points(100, 100.2, 100.4, 100.3, 100.5, 100.6)
        closes = [1000.0, 990.0, 980.0, 970.0, 960.0, 950.0]

        result = evaluate_relative_strength(points, closes, lookback_sessions=5)

        self.assertAlmostEqual(result.taiex_change_pct, -5.0, places=2)
        self.assertGreater(result.pristine_change_pct, -1.0)
        self.assertEqual(result.verdict, "璞玉抗跌(資金避風港)")

    def test_pristine_underperforming_market_is_weak(self):
        points = _points(100, 99, 98, 97, 96, 95)
        closes = [1000.0, 1000.5, 1001.0, 1001.5, 1002.0, 1002.0]

        result = evaluate_relative_strength(points, closes, lookback_sessions=5)

        self.assertEqual(result.verdict, "璞玉走弱")

    def test_moving_together_is_neutral(self):
        points = _points(100, 100.3, 100.6, 100.9, 101.2, 101.5)
        closes = [1000.0, 1003.0, 1006.0, 1009.0, 1012.0, 1015.0]

        result = evaluate_relative_strength(points, closes, lookback_sessions=5)

        self.assertEqual(result.verdict, "同步")

    def test_zero_prior_price_returns_none(self):
        points = _points(0, 100, 101, 102, 103, 104)
        closes = [1000.0, 1001.0, 1002.0, 1003.0, 1004.0, 1005.0]
        self.assertIsNone(evaluate_relative_strength(points, closes, lookback_sessions=5))


if __name__ == "__main__":
    unittest.main()
