from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from quant_research_platform.agent_workflow import AgentDecision
from quant_research_platform.data import Bar
from quant_research_platform.hybrid import (
    HybridRow,
    _action,
    _cross_status,
    _group_rows_by_industry,
    _industry_bias,
    _kronos_score,
    _ma_position_status,
    _portfolio_rows,
    _quote_intraday_status,
    _realtime_score,
    _risk_note,
    _rsi_status,
    _support_resistance,
    _volume_ratio,
)


def _make_row(symbol: str, industry: str, hybrid_score: float) -> HybridRow:
    return HybridRow(
        symbol=symbol,
        name=symbol,
        industry=industry,
        screening_bucket="chip_watch",
        legacy_hit=True,
        new_strategy_hit=False,
        chip_radar_hit=False,
        signal_source="momentum-fallback",
        kronos_return=0.02,
        kronos_score=60.0,
        news_score=50.0,
        technical_score=50.0,
        realtime_score=50.0,
        confidence_score=50.0,
        hybrid_score=hybrid_score,
        current_close=30.0,
        predicted_close=31.0,
        realtime_status="normal",
        action="watch",
        risk_note="ok",
        stop_loss_price=28.0,
        take_profit_price=34.0,
        top10_main_force_buy_strength=None,
        top10_main_force_net_buy=None,
        foreign_buy_streak_days=None,
        branch_main_force_buy_streak_days=None,
        branch_main_force_leader="",
        chip_data_date="",
        chip_data_source="",
        chip_data_source_status="",
        top10_main_force_brokers="",
        technical_evidence=(),
    )


def _bar(day_index: int, close: float, high: float | None = None, low: float | None = None, volume: float = 1000) -> Bar:
    return Bar(
        symbol="2330",
        timestamp=datetime(2026, 1, 1) + timedelta(days=day_index),
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
    )


class KronosAndRealtimeScoreTest(unittest.TestCase):
    def test_kronos_score_scales_expected_return_and_clamps(self):
        self.assertEqual(_kronos_score(0.0), 50.0)
        self.assertEqual(_kronos_score(0.1), 100.0)
        self.assertEqual(_kronos_score(-0.5), 0.0)

    def test_realtime_score_scales_intraday_return_and_clamps(self):
        self.assertEqual(_realtime_score(0.0), 50.0)
        self.assertEqual(_realtime_score(0.1), 100.0)
        self.assertEqual(_realtime_score(-0.5), 0.0)


class QuoteIntradayStatusTest(unittest.TestCase):
    def test_all_status_thresholds(self):
        self.assertEqual(_quote_intraday_status(0.02), "盤中偏多")
        self.assertEqual(_quote_intraday_status(0.005), "盤中偏強")
        self.assertEqual(_quote_intraday_status(0.0), "盤中持平")
        self.assertEqual(_quote_intraday_status(-0.005), "盤中走弱")
        self.assertEqual(_quote_intraday_status(-0.02), "盤中偏弱")


class ActionTest(unittest.TestCase):
    def test_research_focus_when_strong_and_positive_and_not_falling(self):
        self.assertEqual(_action(75, 0.05, -0.005), "研究重點")

    def test_watch_confirmation_when_moderately_strong(self):
        self.assertEqual(_action(65, 0.02, -0.02), "等待確認")

    def test_excluded_when_expected_return_deeply_negative(self):
        self.assertEqual(_action(80, -0.05, 0.0), "排除")

    def test_excluded_when_score_too_low(self):
        self.assertEqual(_action(40, 0.05, 0.0), "排除")

    def test_defaults_to_watch(self):
        self.assertEqual(_action(55, 0.01, 0.0), "觀察")


class RiskNoteTest(unittest.TestCase):
    def test_stable_when_no_risk_factors(self):
        self.assertEqual(_risk_note(0.02, "bullish", 0.0), "風險穩定")

    def test_combines_all_triggered_risks(self):
        note = _risk_note(-0.01, "bearish", -0.02)
        self.assertIn("Kronos 預期報酬為負", note)
        self.assertIn("技術結構偏空", note)
        self.assertIn("盤中走弱", note)


class IndustryBiasTest(unittest.TestCase):
    def test_bias_thresholds(self):
        self.assertEqual(_industry_bias(75), "強勢觀察")
        self.assertEqual(_industry_bias(65), "偏多觀察")
        self.assertEqual(_industry_bias(55), "中性觀察")
        self.assertEqual(_industry_bias(40), "偏弱")


class GroupRowsByIndustryTest(unittest.TestCase):
    def test_groups_sorted_by_average_score_then_by_row_score(self):
        rows = [
            _make_row("A", "半導體", 60.0),
            _make_row("B", "半導體", 80.0),
            _make_row("C", "傳產", 90.0),
        ]

        groups = _group_rows_by_industry(rows)

        self.assertEqual(list(groups.keys()), ["傳產", "半導體"])
        self.assertEqual([row.symbol for row in groups["半導體"]], ["B", "A"])


class PortfolioRowsTest(unittest.TestCase):
    def test_filters_rows_by_decision_bucket(self):
        rows = [_make_row("A", "半導體", 90.0), _make_row("B", "半導體", 40.0)]
        decisions = {
            "A": AgentDecision(agent="x", symbol="A", score=90, stance="include_daily_report", evidence=()),
            "B": AgentDecision(agent="x", symbol="B", score=40, stance="exclude_by_veto", evidence=()),
        }

        included = _portfolio_rows(rows, decisions, "include")

        self.assertEqual([row.symbol for row in included], ["A"])

    def test_missing_decision_defaults_to_exclude_bucket(self):
        rows = [_make_row("A", "半導體", 90.0)]
        excluded = _portfolio_rows(rows, {}, "exclude")
        self.assertEqual([row.symbol for row in excluded], ["A"])


class VolumeRatioAndSupportResistanceTest(unittest.TestCase):
    def test_volume_ratio_none_with_fewer_than_two_bars(self):
        self.assertIsNone(_volume_ratio([_bar(0, 10, volume=100)]))

    def test_volume_ratio_compares_latest_to_window_average(self):
        bars = [_bar(i, 10, volume=100) for i in range(19)] + [_bar(19, 10, volume=300)]
        ratio = _volume_ratio(bars)
        self.assertAlmostEqual(ratio, 300 / 110, places=4)

    def test_support_resistance_uses_last_60_bars(self):
        bars = [_bar(i, close=10 + i, high=10 + i + 1, low=10 + i - 1) for i in range(70)]
        support, resistance = _support_resistance(bars)
        self.assertEqual(support, min(bar.low for bar in bars[-60:]))
        self.assertEqual(resistance, max(bar.high for bar in bars[-60:]))

    def test_support_resistance_empty_bars(self):
        self.assertEqual(_support_resistance([]), (None, None))


class TechnicalStatusTest(unittest.TestCase):
    def test_cross_status_insufficient_data(self):
        self.assertEqual(_cross_status([1, 2, 3], 5, 20), "資料不足")

    def test_cross_status_detects_golden_cross(self):
        # Flat prices, then a sharp final uptick pulls the short MA above the long MA.
        values = [10.0] * 25 + [30.0]
        self.assertEqual(_cross_status(values, 5, 20), "黃金交叉成立")

    def test_ma_position_status_above_and_below(self):
        values = [10.0] * 19 + [20.0]
        self.assertEqual(_ma_position_status(values, 20), "收盤站上均線")
        values_below = [10.0] * 19 + [1.0]
        self.assertEqual(_ma_position_status(values_below, 20), "收盤低於均線")

    def test_rsi_status_insufficient_data(self):
        self.assertEqual(_rsi_status([1.0, 2.0], 14, 20, 80), "資料不足")

    def test_rsi_status_overheated_when_all_gains(self):
        values = [float(i) for i in range(20)]
        status = _rsi_status(values, 14, 20, 80)
        self.assertIn("過熱風險", status)


if __name__ == "__main__":
    unittest.main()
