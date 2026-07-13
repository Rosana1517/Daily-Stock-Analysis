from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from quant_research_platform.data import Bar
from quant_research_platform.hybrid import HybridRow, _has_real_broker_snapshot, _overall_focus_rows, _screening_priority_groups
from quant_research_platform.universe import (
    _breaks_platform_consolidation,
    _is_ma20_rising,
    _passes_chip_breakout_strategy,
    _passes_revised_strategy,
    _platform_box_range,
    _platform_breakout_strength,
    _rank_candidate_rows,
    _stochastic_k_value,
)


def _bar(day_index: int, close: float, high: float | None = None, low: float | None = None, volume: float = 1000) -> Bar:
    return Bar(
        symbol="2330",
        timestamp=datetime(2026, 5, 1) + timedelta(days=day_index),
        open=close,
        high=high if high is not None else close + 1,
        low=low if low is not None else close - 1,
        close=close,
        volume=volume,
    )


def _hybrid_row(
    symbol: str,
    *,
    legacy: bool = False,
    new: bool = False,
    chip: bool = False,
    score: float = 0.0,
) -> HybridRow:
    return HybridRow(
        symbol=symbol,
        name=f"{symbol} 名稱",
        industry="半導體",
        screening_bucket="chip_confirmed" if new and chip else "chip_watch" if new or chip else "legacy_watch",
        legacy_hit=legacy,
        new_strategy_hit=new,
        chip_radar_hit=chip,
        signal_source="realtime",
        kronos_return=0.12,
        kronos_score=60.0,
        news_score=55.0,
        technical_score=score,
        realtime_score=52.0,
        confidence_score=60.0,
        hybrid_score=score,
        current_close=100.0,
        predicted_close=108.0,
        realtime_status="盤中上漲",
        action="研究觀察",
        risk_note="測試用",
        stop_loss_price=95.0,
        take_profit_price=115.0,
        top10_main_force_buy_strength=70.0,
        top10_main_force_net_buy=1000.0,
        foreign_buy_streak_days=4.0,
        branch_main_force_buy_streak_days=3.0,
        branch_main_force_leader="凱基-台北",
        chip_data_date="2026-06-16",
        chip_data_source="official+broker",
        chip_data_source_status="official+broker",
        top10_main_force_brokers="凱基-台北",
        technical_evidence=("close=100.0",),
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

    def test_revised_strategy_requires_pullback_ma20_rising_and_platform_breakout(self):
        bars = [_bar(index, close=100 + index * 0.03, high=100.8, low=99.6) for index in range(20)]
        bars.append(_bar(20, close=101.2, high=110.0, low=99.0, volume=1800))
        self.assertTrue(
            _passes_revised_strategy(
                {"symbol": "2330"},
                {"2330": bars},
                require_margin=False,
                margin_top_100=set(),
            )
        )
        self.assertFalse(
            _passes_revised_strategy(
                {"symbol": "2317", "platform_breakout": False},
                {"2317": bars},
                require_margin=False,
                margin_top_100=set(),
            )
        )

    def test_chip_breakout_strategy_requires_chip_confirmation_and_platform_breakout(self):
        bars = [_bar(index, close=50 + (index % 2) * 0.5, high=51.0, low=49.5) for index in range(20)]
        bars.append(_bar(20, close=56, high=56.5, low=54.8, volume=1600))
        row = {
            "symbol": "2330",
            "top10_main_force_buy_strength": 68,
            "foreign_buy_streak_days": 4,
        }
        self.assertTrue(_passes_chip_breakout_strategy(row, {"2330": bars}))
        self.assertTrue(_breaks_platform_consolidation(row, bars))
        self.assertFalse(
            _passes_chip_breakout_strategy(
                {"symbol": "2330", "top10_main_force_buy_strength": 68, "foreign_buy_streak_days": 1},
                {"2330": bars},
            )
        )

    def test_platform_box_range_uses_real_box_high_and_low(self):
        bars = []
        closes = [50.2, 50.8, 51.1, 50.5, 49.9, 50.4, 51.0, 50.6, 49.8, 50.3, 50.9, 50.1]
        for index, close in enumerate(closes):
            bars.append(_bar(index, close=close, high=51.2, low=49.6, volume=1000))
        for offset in range(12, 21):
            close = 50.1 + ((offset % 3) - 1) * 0.2
            bars.append(_bar(offset, close=close, high=51.15, low=49.65, volume=980))
        bars.append(_bar(21, close=51.9, high=52.2, low=50.8, volume=1650))

        box_range = _platform_box_range(bars)

        self.assertIsNotNone(box_range)
        box_high, box_low, compression, window_size = box_range
        self.assertAlmostEqual(box_high, 51.2, places=2)
        self.assertAlmostEqual(box_low, 49.6, places=2)
        self.assertLess(compression, 0.18)
        self.assertGreaterEqual(window_size, 10)
        self.assertTrue(_breaks_platform_consolidation({}, bars))
        self.assertGreater(_platform_breakout_strength(bars), 18.0)

    def test_platform_breakout_rejects_non_box_volatile_series(self):
        bars = [
            _bar(index, close=55 + ((index % 4) - 1.5) * 3.2, high=60 + (index % 3), low=49 - (index % 2), volume=1000)
            for index in range(21)
        ]
        bars.append(_bar(21, close=60.4, high=61.0, low=55.0, volume=1400))

        self.assertIsNone(_platform_box_range(bars))
        self.assertFalse(_breaks_platform_consolidation({}, bars))

    def test_real_broker_snapshot_requires_broker_fields(self):
        self.assertTrue(
            _has_real_broker_snapshot(
                {
                    "chip_data_source_status": "official+broker|rank=1",
                    "top10_main_force_net_buy": "52306",
                    "branch_main_force_buy_streak_days": "2",
                    "branch_main_force_leader": "台灣摩根士丹利",
                }
            )
        )
        self.assertFalse(
            _has_real_broker_snapshot(
                {
                    "chip_data_source_status": "official-only",
                    "top10_main_force_net_buy": "",
                    "branch_main_force_buy_streak_days": "",
                    "branch_main_force_leader": "",
                }
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

    def test_screening_priority_groups_rank_all_three_first(self):
        groups = _screening_priority_groups(
            [
                _hybrid_row("2330.TW", legacy=True, new=True, chip=True, score=90.0),
                _hybrid_row("2887.TW", legacy=True, new=False, chip=True, score=80.0),
                _hybrid_row("2610.TW", legacy=False, new=True, chip=False, score=70.0),
            ]
        )

        labels = [group["label"] for group in groups]
        self.assertEqual(labels[0], "三者全中")
        self.assertIn("舊版 + 籌碼雷達", labels)
        self.assertIn("單新版", labels)
        self.assertEqual(groups[0]["count"], 1)
        self.assertIn("2330.TW", groups[0]["samples"])
        self.assertIn("2887.TW", next(group for group in groups if group["label"] == "舊版 + 籌碼雷達")["samples"])

    def test_overall_focus_rows_prioritize_all_three_first(self):
        rows = [
            _hybrid_row("2603.TW", legacy=True, new=False, chip=True, score=80.0),
            _hybrid_row("2330.TW", legacy=True, new=True, chip=True, score=95.0),
            _hybrid_row("2609.TW", legacy=False, new=True, chip=False, score=70.0),
        ]

        ranked = _overall_focus_rows(rows)

        self.assertEqual([row.symbol for row in ranked[:3]], ["2330.TW", "2603.TW", "2609.TW"])


if __name__ == "__main__":
    unittest.main()
