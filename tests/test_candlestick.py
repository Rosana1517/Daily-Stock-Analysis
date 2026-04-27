from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.models import PriceBar
from stock_signal_system.strategies.candlestick import analyze_candlesticks


class CandlestickStrategyTest(unittest.TestCase):
    def test_bullish_engulfing_after_decline_is_detected(self):
        bars = [
            PriceBar("T", date(2026, 1, 1), 100, 101, 95, 96),
            PriceBar("T", date(2026, 1, 2), 96, 97, 92, 93),
            PriceBar("T", date(2026, 1, 3), 93, 94, 89, 90),
            PriceBar("T", date(2026, 1, 4), 90, 91, 85, 86),
            PriceBar("T", date(2026, 1, 5), 86, 87, 81, 82),
            PriceBar("T", date(2026, 1, 6), 81, 99, 80, 98),
        ]

        signal = analyze_candlesticks({"T": bars})["T"]

        self.assertEqual(signal.bias, "bullish")
        self.assertTrue(any("多頭吞噬" in pattern for pattern in signal.patterns))


if __name__ == "__main__":
    unittest.main()
