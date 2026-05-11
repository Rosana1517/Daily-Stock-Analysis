from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.data.capital_flow import CapitalFlowRecord, analyze_capital_flow, top_symbols


class CapitalFlowTest(unittest.TestCase):
    def test_identifies_top_accumulation_candidates(self):
        report = analyze_capital_flow(
            [
                CapitalFlowRecord(
                    symbol="2330",
                    name="台積電",
                    industry="半導體",
                    price=100,
                    volume=2_000_000,
                    avg_volume_20d=1_200_000,
                    foreign_net_buy=180_000_000,
                    investment_trust_net_buy=60_000_000,
                    dealer_net_buy=20_000_000,
                    etf_flow=35_000_000,
                ),
                CapitalFlowRecord(
                    symbol="1101",
                    name="台泥",
                    industry="水泥",
                    price=32,
                    volume=220_000,
                    avg_volume_20d=300_000,
                ),
            ],
            report_date=date(2026, 5, 11),
        )

        self.assertEqual(report.top_accumulation_candidates[0].record.symbol, "2330")
        self.assertGreater(report.top_accumulation_candidates[0].capital_flow_score, 65)
        self.assertIn("半導體", report.sector_scores)

    def test_flags_hidden_accumulation_before_volume_expansion(self):
        report = analyze_capital_flow(
            [
                {
                    "symbol": "2382",
                    "name": "廣達",
                    "industry": "AI伺服器",
                    "price": 72,
                    "volume": 950_000,
                    "avg_volume_20d": 900_000,
                    "foreign_net_buy": 35_000_000,
                    "investment_trust_net_buy": 45_000_000,
                    "dealer_net_buy": 8_000_000,
                }
            ]
        )

        self.assertEqual(top_symbols(report.hidden_accumulation_candidates), ("2382",))
        self.assertIn("hidden accumulation", report.results[0].labels)

    def test_warns_speculative_overheating_without_institutional_confirmation(self):
        report = analyze_capital_flow(
            [
                CapitalFlowRecord(
                    symbol="9999",
                    name="題材股",
                    industry="未知",
                    price=18,
                    volume=5_000_000,
                    avg_volume_20d=900_000,
                    margin_financing_change=2_000_000,
                    short_interest_change=-600_000,
                )
            ]
        )

        self.assertEqual(top_symbols(report.speculative_overheating_warnings), ("9999",))
        self.assertTrue(any("overheating" in warning for warning in report.results[0].warnings))


if __name__ == "__main__":
    unittest.main()
