from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.data.chip_snapshot import BrokerChipSummary, TwseInstitutionalDay, _build_chip_rows_from_twse_days


class ChipSnapshotTest(unittest.TestCase):
    def test_build_chip_rows_prefers_real_broker_fields(self):
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
        )
        broker = {
            "2330": BrokerChipSummary(
                symbol="2330",
                top10_main_force_buy_strength=72.5,
                top10_main_force_net_buy=5432,
                top10_main_force_brokers="凱基-台北、摩根大通",
                branch_main_force_buy_streak_days=3,
                branch_main_force_leader="凱基-台北",
                chip_data_date="2026-06-16",
                chip_data_source="TWSE T86 official + HiStock branch",
                chip_data_source_status="official+broker|rank=1",
            )
        }

        rows = _build_chip_rows_from_twse_days(days, broker)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "2330")
        self.assertEqual(rows[0]["top10_main_force_buy_strength"], "72.5")
        self.assertEqual(rows[0]["top10_main_force_net_buy"], "5432")
        self.assertEqual(rows[0]["top10_main_force_buy_rank"], "1")
        self.assertEqual(rows[0]["branch_main_force_buy_streak_days"], "3")
        self.assertEqual(rows[0]["branch_main_force_leader"], "凱基-台北")
        self.assertEqual(rows[0]["foreign_buy_streak_days"], "2")
        self.assertEqual(rows[0]["dealer_buy_streak_days"], "2")
        self.assertEqual(rows[0]["chip_data_source_status"], "official+broker")

    def test_build_chip_rows_marks_degraded_when_broker_fetch_failed(self):
        days = (
            TwseInstitutionalDay(
                date(2026, 6, 16),
                (
                    {"symbol": "2330", "name": "TSMC", "foreign_net_buy": 20_000_000, "investment_trust_net_buy": 3_000_000, "dealer_net_buy": 1_000_000},
                ),
            ),
        )
        broker = {
            "2330": BrokerChipSummary(
                symbol="2330",
                top10_main_force_buy_strength=0.0,
                top10_main_force_net_buy=0,
                top10_main_force_brokers="",
                branch_main_force_buy_streak_days=0,
                branch_main_force_leader="",
                chip_data_date="2026-06-16",
                chip_data_source="TWSE T86 official",
                chip_data_source_status="degraded",
            )
        }

        rows = _build_chip_rows_from_twse_days(days, broker)

        self.assertEqual(rows[0]["chip_data_source_status"], "degraded")
        self.assertEqual(rows[0]["top10_main_force_buy_strength"], "0.0")
        self.assertEqual(rows[0]["top10_main_force_net_buy"], "0")


if __name__ == "__main__":
    unittest.main()
