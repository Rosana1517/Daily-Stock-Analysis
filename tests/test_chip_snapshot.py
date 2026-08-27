from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from stock_signal_system.data.broker_source import BrokerBranchSnapshot, BrokerBranchTrade
from stock_signal_system.data.chip_snapshot import (
    BrokerChipSummary,
    TwseInstitutionalDay,
    _build_chip_rows_from_twse_days,
    _summarize_broker_snapshots,
    load_histock_broker_summaries,
)


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


    def test_official_broker_net_buy_column_round_trips_through_csv_row(self):
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
                top10_main_force_buy_strength=72.5,
                top10_main_force_net_buy=5432,
                top10_main_force_brokers="兆豐-台北、凱基-台北",
                branch_main_force_buy_streak_days=3,
                branch_main_force_leader="兆豐-台北",
                chip_data_date="2026-06-16",
                chip_data_source="TWSE T86 official + HiStock branch",
                chip_data_source_status="official+broker|rank=1",
                official_broker_net_buy=2000,
            )
        }

        rows = _build_chip_rows_from_twse_days(days, broker)

        self.assertEqual(rows[0]["official_broker_net_buy"], "2000")


class SummarizeBrokerSnapshotsOfficialBuyTest(unittest.TestCase):
    def _trade(self, broker: str, net_shares: int) -> BrokerBranchTrade:
        return BrokerBranchTrade(broker=broker, buy_shares=net_shares, sell_shares=0, net_shares=net_shares, average_price=100.0)

    def test_sums_only_official_bank_brokers_among_top_buyers(self):
        snapshot = BrokerBranchSnapshot(
            symbol="2330",
            trade_date=date(2026, 6, 16),
            buy_trades=(self._trade("兆豐-台北", 3000), self._trade("凱基-台北", 5000), self._trade("合庫-高雄", 1000)),
            sell_trades=(),
            source_url="https://histock.tw/stock/branch.aspx?no=2330",
            source_status="ok",
        )

        summary = _summarize_broker_snapshots("2330", [snapshot], latest_volume=100_000)

        self.assertEqual(summary.official_broker_net_buy, 4000)

    def test_zero_when_no_official_broker_among_top_buyers(self):
        snapshot = BrokerBranchSnapshot(
            symbol="2330",
            trade_date=date(2026, 6, 16),
            buy_trades=(self._trade("凱基-台北", 5000), self._trade("元大-桃園", 2000)),
            sell_trades=(),
            source_url="https://histock.tw/stock/branch.aspx?no=2330",
            source_status="ok",
        )

        summary = _summarize_broker_snapshots("2330", [snapshot], latest_volume=100_000)

        self.assertEqual(summary.official_broker_net_buy, 0)

    def test_degraded_summary_when_no_valid_snapshot_defaults_official_buy_to_zero(self):
        snapshot = BrokerBranchSnapshot(
            symbol="2330",
            trade_date=date(2026, 6, 16),
            buy_trades=(),
            sell_trades=(),
            source_url="https://histock.tw/stock/branch.aspx?no=2330",
            source_status="degraded",
        )

        summary = _summarize_broker_snapshots("2330", [snapshot], latest_volume=100_000)

        self.assertEqual(summary.official_broker_net_buy, 0)


class LoadHistockBrokerSummariesCircuitBreakerTest(unittest.TestCase):
    def test_disables_retries_after_consecutive_degraded_exhaustion(self):
        # 2026-08-27 的排程曾經因為 HiStock 整站異常，degraded 重試在
        # symbol x date 的雙層迴圈裡被放大成好幾分鐘，把整個 CI step 拖到逾時、
        # 當天完全沒有報告也沒有發 LINE。斷路器應該在連續 3 次「重試到用盡都還
        # 是 degraded」之後，把剩下的呼叫都改成單次嘗試（不再重試）。
        degraded = BrokerBranchSnapshot(
            symbol="0000",
            trade_date=None,
            buy_trades=(),
            sell_trades=(),
            source_url="https://histock.tw/stock/branch.aspx?no=0000",
            source_status="degraded",
        )
        twse_days = tuple(TwseInstitutionalDay(date(2026, 8, d), ()) for d in (24, 23, 22))
        symbols = ("1111", "2222", "3333", "4444", "5555")

        with patch(
            "stock_signal_system.data.chip_snapshot.fetch_histock_branch_snapshot",
            return_value=degraded,
        ) as mock_fetch:
            load_histock_broker_summaries(
                cache_dir=Path("unused"),
                twse_days=twse_days,
                broker_symbols=symbols,
                latest_volume_by_symbol={},
                broker_lookback_sessions=3,
            )

        attempts_used = [call.kwargs["max_attempts"] for call in mock_fetch.call_args_list]
        self.assertEqual(len(attempts_used), 15)
        self.assertEqual(attempts_used[:3], [3, 3, 3])
        self.assertEqual(attempts_used[3:], [1] * 12)

    def test_keeps_retrying_when_results_are_ok(self):
        ok_snapshot = BrokerBranchSnapshot(
            symbol="0000",
            trade_date=None,
            buy_trades=(BrokerBranchTrade(broker="A", buy_shares=1, sell_shares=0, net_shares=1, average_price=10.0),),
            sell_trades=(),
            source_url="https://histock.tw/stock/branch.aspx?no=0000",
            source_status="ok",
        )
        twse_days = tuple(TwseInstitutionalDay(date(2026, 8, d), ()) for d in (24, 23, 22))
        symbols = ("1111", "2222")

        with patch(
            "stock_signal_system.data.chip_snapshot.fetch_histock_branch_snapshot",
            return_value=ok_snapshot,
        ) as mock_fetch:
            load_histock_broker_summaries(
                cache_dir=Path("unused"),
                twse_days=twse_days,
                broker_symbols=symbols,
                latest_volume_by_symbol={},
                broker_lookback_sessions=3,
            )

        attempts_used = [call.kwargs["max_attempts"] for call in mock_fetch.call_args_list]
        self.assertEqual(attempts_used, [3] * len(attempts_used))


if __name__ == "__main__":
    unittest.main()
