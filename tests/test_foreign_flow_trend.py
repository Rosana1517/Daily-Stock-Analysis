from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.data.chip_snapshot import TwseInstitutionalDay
from stock_signal_system.data.foreign_flow_trend import summarize_market_foreign_flow


def _day(trade_date: date, *net_buys: float) -> TwseInstitutionalDay:
    rows = tuple(
        {"symbol": f"{2330 + index}", "name": f"股票{index}", "foreign_net_buy": value}
        for index, value in enumerate(net_buys)
    )
    return TwseInstitutionalDay(trade_date, rows)


class SummarizeMarketForeignFlowTest(unittest.TestCase):
    def test_empty_days_returns_none(self):
        self.assertIsNone(summarize_market_foreign_flow(()))

    def test_buy_streak_reports_bullish_bias(self):
        days = (
            _day(date(2026, 7, 17), 2_000_000, 1_000_000),
            _day(date(2026, 7, 16), 500_000),
            _day(date(2026, 7, 15), 300_000),
        )

        trend = summarize_market_foreign_flow(days)

        self.assertEqual(trend.streak_days, 3)
        self.assertEqual(trend.bias, "外資偏多")
        self.assertAlmostEqual(trend.cumulative_net_lots, 3800.0)
        # 每日彙總為當日所有個股 foreign_net_buy 加總換算成張
        self.assertEqual(trend.daily_net_lots[0], (date(2026, 7, 17), 3000.0))

    def test_sell_streak_reports_bearish_bias(self):
        days = (
            _day(date(2026, 7, 17), -2_000_000),
            _day(date(2026, 7, 16), -1_000_000),
        )

        trend = summarize_market_foreign_flow(days)

        self.assertEqual(trend.streak_days, -2)
        self.assertEqual(trend.bias, "外資偏空")

    def test_mixed_direction_reports_neutral(self):
        days = (
            _day(date(2026, 7, 17), 1_000_000),
            _day(date(2026, 7, 16), -3_000_000),
        )

        trend = summarize_market_foreign_flow(days)

        self.assertEqual(trend.streak_days, 1)
        self.assertEqual(trend.bias, "外資中性")

    def test_days_are_sorted_newest_first_regardless_of_input_order(self):
        days = (
            _day(date(2026, 7, 15), 100_000),
            _day(date(2026, 7, 17), 300_000),
            _day(date(2026, 7, 16), 200_000),
        )

        trend = summarize_market_foreign_flow(days)

        self.assertEqual([item[0] for item in trend.daily_net_lots], [date(2026, 7, 17), date(2026, 7, 16), date(2026, 7, 15)])


if __name__ == "__main__":
    unittest.main()
