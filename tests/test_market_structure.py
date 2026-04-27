from __future__ import annotations

import unittest
from datetime import date, timedelta

from stock_signal_system.models import PriceBar
from stock_signal_system.strategies.market_structure import liquidity_sweep_signal, market_structure_bias


class MarketStructureTest(unittest.TestCase):
    def test_bearish_sweep_detects_failed_breakout(self):
        start = date(2026, 1, 1)
        bars = [
            PriceBar("T", start + timedelta(days=i), 100 + i, 104 + i, 98 + i, 101 + i)
            for i in range(5)
        ]
        bars.append(PriceBar("T", start + timedelta(days=5), 108, 115, 103, 104))

        self.assertEqual(liquidity_sweep_signal(bars), "bearish_sweep")

    def test_market_structure_defaults_neutral_without_swings(self):
        bars = [
            PriceBar("T", date(2026, 1, 1), 100, 101, 99, 100),
            PriceBar("T", date(2026, 1, 2), 100, 102, 100, 101),
            PriceBar("T", date(2026, 1, 3), 101, 103, 101, 102),
        ]

        self.assertEqual(market_structure_bias(bars), "neutral")


if __name__ == "__main__":
    unittest.main()
