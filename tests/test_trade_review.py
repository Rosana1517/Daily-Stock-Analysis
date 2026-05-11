from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.trade_review import MissedCandidate, TradeRecord, build_review_markdown, build_trade_review, review_trade


class TradeReviewTest(unittest.TestCase):
    def test_false_breakout_and_regime_mismatch_are_detected(self):
        reviewed = review_trade(
            TradeRecord(
                symbol="2330",
                setup="breakout continuation",
                regime="high-volatility risk-off",
                ranking_probability=72,
                entry_price=100,
                exit_price=97,
                planned_entry=98,
                stop_loss=96,
                max_price_after_entry=102,
                min_price_after_entry=95.8,
                volume_ratio=0.9,
                liquidity_score=70,
                sector_return=-0.04,
                entry_delay_days=2,
            )
        )

        codes = {finding.code for finding in reviewed.findings}

        self.assertEqual(reviewed.outcome, "loss")
        self.assertIn("false_breakout", codes)
        self.assertIn("regime_mismatch", codes)
        self.assertIn("timing_issue", codes)

    def test_missed_runner_and_daily_report_are_generated(self):
        report = build_trade_review(
            trades=[
                TradeRecord(
                    symbol="2382",
                    setup="sector rotation entry",
                    regime="AI momentum expansion",
                    entry_price=70,
                    exit_price=75,
                    max_price_after_entry=77,
                    min_price_after_entry=69,
                    sector_return=0.04,
                )
            ],
            missed_candidates=[
                MissedCandidate(
                    symbol="3661",
                    setup="momentum ignition",
                    regime="AI momentum expansion",
                    ranking_probability=76,
                    close_on_signal=80,
                    max_price_next_10d=92,
                    reason_not_taken="position limit",
                )
            ],
            report_date=date(2026, 5, 11),
        )

        markdown = build_review_markdown(report)

        self.assertEqual(len(report.missed_runners), 1)
        self.assertIn("Missed runner", markdown)
        self.assertIn("Setup Performance", markdown)

    def test_alpha_decay_alerts_when_setup_performance_deteriorates(self):
        trades = [
            TradeRecord(symbol="A1", setup="trend resumption", entry_price=100, exit_price=106),
            TradeRecord(symbol="A2", setup="trend resumption", entry_price=100, exit_price=105),
            TradeRecord(symbol="A3", setup="trend resumption", entry_price=100, exit_price=96),
            TradeRecord(symbol="A4", setup="trend resumption", entry_price=100, exit_price=95),
            TradeRecord(symbol="A5", setup="trend resumption", entry_price=100, exit_price=94),
        ]

        report = build_trade_review(trades)

        self.assertEqual(report.alpha_decay_alerts[0].code, "alpha_decay")
        self.assertEqual(report.setup_stats[0].alert, "strategy degradation")


if __name__ == "__main__":
    unittest.main()
