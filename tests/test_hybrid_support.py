from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from quant_research_platform.data import Bar
from quant_research_platform.universe import (
    _is_ma20_rising,
    _passes_revised_strategy,
    _rank_candidate_rows,
    _stochastic_k_value,
)


def _bar(day_index: int, close: float, high: float | None = None, low: float | None = None) -> Bar:
    return Bar(
        symbol="2330",
        timestamp=datetime(2026, 5, 1) + timedelta(days=day_index),
        open=close,
        high=high if high is not None else close + 1,
        low=low if low is not None else close - 1,
        close=close,
        volume=1000,
    )


class HybridSupportTest(unittest.TestCase):
    def test_stochastic_k_value_prefers_pullback_under_40(self):
        bars = [_bar(index, close=20 + index) for index in range(8)]
        bars.append(_bar(8, close=22, high=29, low=19))

        k_value = _stochastic_k_value(bars)

        self.assertIsNotNone(k_value)
        self.assertLess(k_value, 40)

    def test_ma20_rising_requires_latest_average_above_previous(self):
        rising_bars = [_bar(index, close=100 + index) for index in range(21)]
        falling_bars = [_bar(index, close=121 - index) for index in range(21)]

        self.assertTrue(_is_ma20_rising(rising_bars))
        self.assertFalse(_is_ma20_rising(falling_bars))

    def test_revised_strategy_requires_margin_top100_when_available(self):
        bars = [_bar(index, close=100 + index) for index in range(20)]
        bars.append(_bar(20, close=105, high=121, low=99))
        self.assertTrue(
            _passes_revised_strategy(
                {"symbol": "2330"},
                {"2330": bars},
                require_margin=True,
                margin_top_100={"2330"},
            )
        )
        self.assertFalse(
            _passes_revised_strategy(
                {"symbol": "2317"},
                {"2317": bars},
                require_margin=True,
                margin_top_100={"2330"},
            )
        )

    def test_rank_candidates_falls_back_to_legacy_sort_when_no_symbol_passes(self):
        ranked = _rank_candidate_rows(
            [
                {
                    "symbol": "1101",
                    "price": 20,
                    "volume": 100000,
                    "avg_volume_20d": 100000,
                    "score": 12.0,
                    "revenue_growth_yoy": 0,
                    "pe_ratio": 10,
                    "industry": "半導體",
                },
                {
                    "symbol": "1102",
                    "price": 20,
                    "volume": 1000000,
                    "avg_volume_20d": 1000000,
                    "score": 15.0,
                    "revenue_growth_yoy": 0,
                    "pe_ratio": 10,
                    "industry": "半導體",
                },
            ],
            set(),
            {},
        )

        self.assertEqual([item["symbol"] for item in ranked], ["1102", "1101"])


if __name__ == "__main__":
    unittest.main()
