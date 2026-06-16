from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.data.chip_snapshot import TwseInstitutionalDay, _build_chip_rows_from_twse_days


class ChipSnapshotTest(unittest.TestCase):
    def test_build_chip_rows_computes_foreign_and_dealer_streaks(self):
        days = (
            TwseInstitutionalDay(
                date(2026, 6, 16),
                (
                    {"symbol": "2330", "name": "TSMC", "foreign_net_buy": 20_000_000, "investment_trust_net_buy": 3_000_000, "dealer_net_buy": 1_000_000},
                ),
            ),
            TwseInstitutionalDay(
                date(2026, 6, 15),
                (
                    {"symbol": "2330", "name": "TSMC", "foreign_net_buy": 15_000_000, "investment_trust_net_buy": 1_000_000, "dealer_net_buy": 500_000},
                ),
            ),
            TwseInstitutionalDay(
                date(2026, 6, 12),
                (
                    {"symbol": "2330", "name": "TSMC", "foreign_net_buy": -1_000_000, "investment_trust_net_buy": 0, "dealer_net_buy": 200_000},
                ),
            ),
        )

        rows = _build_chip_rows_from_twse_days(days)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "2330")
        self.assertEqual(rows[0]["foreign_buy_streak_days"], "2")
        self.assertEqual(rows[0]["dealer_buy_streak_days_proxy"], "3")
        self.assertEqual(rows[0]["branch_main_force_buy_streak_days_proxy"], "3")
        self.assertEqual(rows[0]["chip_data_date"], "2026-06-16")


if __name__ == "__main__":
    unittest.main()
