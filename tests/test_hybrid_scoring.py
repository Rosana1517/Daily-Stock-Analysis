from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from dataclasses import replace
from pathlib import Path

from quant_research_platform.agent_workflow import AgentDecision
from quant_research_platform.daily_stock_bridge import notification_summary
from quant_research_platform.data import Bar
from quant_research_platform.hybrid import (
    HybridRow,
    _action,
    _cross_status,
    _group_rows_by_industry,
    _fresh_ma_breakout,
    _industry_bias,
    _is_best_entry,
    _is_short_entry,
    _kronos_score,
    _ma_position_status,
    _overall_focus_label,
    _overall_focus_priority,
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


class BestEntryTest(unittest.TestCase):
    def test_fresh_60ma_breakout_with_fresh_macd_cross_is_best_entry(self):
        # A dip below the 60MA, then two up bars: the close crosses back above
        # the 60MA and the MACD DIF crosses its signal line, both within the
        # 2-session freshness window.
        bars = [_bar(i, 100.0) for i in range(66)] + [_bar(66, 98.0), _bar(67, 99.0), _bar(68, 103.0), _bar(69, 106.0)]
        self.assertTrue(_is_best_entry(bars))

    def test_long_held_above_60ma_is_not_best_entry(self):
        # The cross above the 60MA fired ~10 sessions ago; no longer fresh.
        bars = [_bar(i, 100.0) for i in range(60)] + [_bar(60 + i, 101.0 + i) for i in range(10)]
        self.assertFalse(_is_best_entry(bars))

    def test_close_below_60ma_is_not_best_entry(self):
        bars = [_bar(i, 100.0) for i in range(68)] + [_bar(68, 80.0), _bar(69, 81.0)]
        self.assertFalse(_is_best_entry(bars))

    def test_insufficient_history_is_not_best_entry(self):
        bars = [_bar(i, 100.0 + i) for i in range(50)]
        self.assertFalse(_is_best_entry(bars))


class ShortEntryTest(unittest.TestCase):
    def test_fresh_20ma_breakout_with_fresh_macd_cross_is_short_entry(self):
        bars = [_bar(i, 100.0) for i in range(26)] + [_bar(26, 98.0), _bar(27, 99.0), _bar(28, 103.0), _bar(29, 106.0)]
        self.assertTrue(_is_short_entry(bars))

    def test_stale_20ma_breakout_is_not_short_entry(self):
        bars = [_bar(i, 100.0) for i in range(20)] + [_bar(20 + i, 101.0 + i) for i in range(10)]
        self.assertFalse(_is_short_entry(bars))


class FreshMaBreakoutTest(unittest.TestCase):
    def test_cross_on_latest_bar_is_fresh(self):
        closes = [100.0] * 20 + [98.0, 103.0]
        self.assertTrue(_fresh_ma_breakout(closes, 20))

    def test_cross_three_sessions_ago_is_stale(self):
        closes = [100.0] * 20 + [98.0, 103.0, 104.0, 105.0]
        self.assertFalse(_fresh_ma_breakout(closes, 20))

    def test_fallen_back_below_ma_is_not_a_breakout(self):
        closes = [100.0] * 20 + [98.0, 103.0, 90.0]
        self.assertFalse(_fresh_ma_breakout(closes, 20))


class BestEntryDisplayTest(unittest.TestCase):
    def test_best_entry_row_gets_star_label_and_top_priority(self):
        row = replace(_make_row("2330.TW", "半導體", 80.0), best_entry=True)
        self.assertEqual(_overall_focus_label(row), "★最佳買點")
        self.assertEqual(_overall_focus_priority(row), 0)

    def test_short_entry_row_ranks_just_below_best_entry(self):
        row = replace(_make_row("2317.TW", "電子", 75.0), short_entry=True)
        self.assertEqual(_overall_focus_label(row), "☆短線買點")
        self.assertEqual(_overall_focus_priority(row), 1)

    def test_best_entry_wins_when_both_flags_set(self):
        row = replace(_make_row("2330.TW", "半導體", 80.0), best_entry=True, short_entry=True)
        self.assertEqual(_overall_focus_label(row), "★最佳買點")
        self.assertEqual(_overall_focus_priority(row), 0)

    def test_notification_summary_marks_entries_with_star_symbols(self):
        starred = replace(_make_row("2330.TW", "半導體", 80.0), best_entry=True)
        short = replace(_make_row("2454.TW", "半導體", 76.0), short_entry=True)
        plain = _make_row("2317.TW", "電子", 70.0)

        summary = notification_summary([starred, short, plain], Path("reports/x.md"))

        self.assertIn("★2330.TW", summary)
        self.assertIn("☆2454.TW", summary)
        self.assertNotIn("★2317.TW", summary)
        self.assertNotIn("☆2317.TW", summary)


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
