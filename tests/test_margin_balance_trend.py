from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.data.margin_balance_trend import (
    MarginBalanceDay,
    summarize_margin_balance_trend,
)


def _day(trade_date: date, balance_thousands: float, change_thousands: float) -> MarginBalanceDay:
    return MarginBalanceDay(trade_date, balance_thousands, change_thousands)


class SummarizeMarginBalanceTrendTest(unittest.TestCase):
    def test_empty_days_returns_none(self):
        self.assertIsNone(summarize_margin_balance_trend(()))

    def test_three_day_deep_washout_reports_bottoming_signal(self):
        # Three consecutive days of large decreases totaling more than 300億
        # (30,000,000 仟元) — the methodology's own "洗到散戶脫皮" example.
        days = (
            _day(date(2026, 8, 26), 500_000_000, -12_000_000),
            _day(date(2026, 8, 25), 512_000_000, -11_000_000),
            _day(date(2026, 8, 24), 523_000_000, -10_500_000),
        )

        trend = summarize_margin_balance_trend(days)

        self.assertEqual(trend.streak_days, -3)
        self.assertEqual(trend.verdict, "融資急縮(籌碼清洗，留意落底訊號)")
        self.assertAlmostEqual(trend.window_change_thousands, -33_500_000)

    def test_shallow_decline_is_not_a_washout(self):
        # Consecutive decreases, but well under the 300億 cumulative threshold.
        days = (
            _day(date(2026, 8, 26), 545_000_000, -1_000_000),
            _day(date(2026, 8, 25), 546_000_000, -800_000),
        )

        trend = summarize_margin_balance_trend(days)

        self.assertEqual(trend.streak_days, -2)
        self.assertEqual(trend.verdict, "持平")

    def test_single_day_surge_reports_chase_risk(self):
        days = (_day(date(2026, 8, 26), 560_000_000, 6_000_000),)

        trend = summarize_margin_balance_trend(days)

        self.assertEqual(trend.verdict, "融資急增(散戶追價，留意主力調節風險)")

    def test_flat_change_reports_neutral(self):
        days = (_day(date(2026, 8, 26), 550_000_000, 0.0),)

        trend = summarize_margin_balance_trend(days)

        self.assertEqual(trend.streak_days, 0)
        self.assertEqual(trend.verdict, "持平")

    def test_days_are_sorted_newest_first_regardless_of_input_order(self):
        days = (
            _day(date(2026, 8, 24), 500_000_000, -1_000_000),
            _day(date(2026, 8, 26), 480_000_000, -1_500_000),
            _day(date(2026, 8, 25), 495_000_000, -1_200_000),
        )

        trend = summarize_margin_balance_trend(days)

        self.assertEqual([item.trade_date for item in trend.daily], [date(2026, 8, 26), date(2026, 8, 25), date(2026, 8, 24)])


if __name__ == "__main__":
    unittest.main()
