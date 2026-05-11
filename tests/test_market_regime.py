from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from quant_research_platform.data import Bar
from quant_research_platform.market_regime import (
    MarketRegimeInput,
    RegimeCategory,
    classify_market_regime,
    load_regime_result,
    regime_backtest_features,
    save_regime_result,
)


class MarketRegimeTest(unittest.TestCase):
    def test_classifies_ai_momentum_expansion_from_sector_and_breadth(self):
        rows = [
            _row("2330", "半導體", 110, 95, 2_000_000, 1_000_000),
            _row("2382", "AI 伺服器", 72, 60, 1_800_000, 900_000),
            _row("3661", "AI ASIC", 88, 74, 1_400_000, 700_000),
            _row("2887", "金融", 28, 27, 900_000, 950_000),
        ]

        result = classify_market_regime(
            MarketRegimeInput(
                report_date=date(2026, 5, 11),
                stock_rows=rows,
                prices_by_symbol={"TAIEX": _bars("TAIEX", 20, start=100, step=1.2)},
                sector_news_scores={"半導體": 72, "AI 伺服器": 78, "AI ASIC": 80, "金融": 52},
                foreign_flow={"2330": 220_000_000},
                investment_trust_flow={"2382": 90_000_000},
                etf_flow={"0050": 120_000_000},
                benchmark_symbol="TAIEX",
            )
        )

        self.assertEqual(result.regime, RegimeCategory.AI_MOMENTUM_EXPANSION)
        self.assertGreater(result.confidence, 60)
        self.assertIn("AI supply-chain momentum", result.suitable_strategies)
        self.assertIn("top_sector", result.explanation)

    def test_detects_liquidity_contraction_when_turnover_and_breadth_are_weak(self):
        rows = [
            _row("1101", "水泥", 25, 30, 100_000, 400_000),
            _row("2887", "金融", 22, 26, 120_000, 420_000),
            _row("2303", "半導體", 34, 42, 80_000, 450_000),
            _row("2603", "航運", 18, 21, 60_000, 300_000),
        ]

        result = classify_market_regime(
            MarketRegimeInput(
                report_date=date(2026, 5, 11),
                stock_rows=rows,
                prices_by_symbol={"TAIEX": _bars("TAIEX", 20, start=100, step=-1.4)},
                benchmark_symbol="TAIEX",
            )
        )

        self.assertIn(
            result.regime,
            {RegimeCategory.LIQUIDITY_CONTRACTION, RegimeCategory.HIGH_VOLATILITY_RISK_OFF},
        )
        self.assertLess(regime_backtest_features(result)["position_size_multiplier"], 0.6)

    def test_persists_result_and_reports_transition(self):
        previous = classify_market_regime(
            MarketRegimeInput(
                report_date=date(2026, 5, 10),
                stock_rows=[_row("2887", "金融", 30, 29, 1_000_000, 900_000)],
            )
        )
        current = classify_market_regime(
            MarketRegimeInput(
                report_date=date(2026, 5, 11),
                stock_rows=[
                    _row("2330", "半導體", 110, 96, 2_100_000, 1_000_000),
                    _row("2382", "AI 伺服器", 76, 61, 1_900_000, 850_000),
                ],
                sector_news_scores={"半導體": 75, "AI 伺服器": 81},
            ),
            previous_result=previous,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = save_regime_result(current, Path(tmp_dir) / "regime.json")
            loaded = load_regime_result(path)

        self.assertEqual(loaded.regime, current.regime)
        self.assertEqual(loaded.previous_regime, previous.regime)
        self.assertTrue(loaded.transition.startswith("stable:") or loaded.transition.startswith("transition:"))
        self.assertIn("regime", regime_backtest_features(loaded))


def _row(symbol: str, industry: str, price: float, previous: float, volume: float, avg_volume: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "name": symbol,
        "industry": industry,
        "price": price,
        "price_20d_ago": previous,
        "volume": volume,
        "avg_volume_20d": avg_volume,
    }


def _bars(symbol: str, count: int, start: float, step: float) -> list[Bar]:
    base = datetime(2026, 4, 1)
    bars: list[Bar] = []
    for index in range(count):
        close = start + index * step
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=base + timedelta(days=index),
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000 + index * 50_000,
            )
        )
    return bars


if __name__ == "__main__":
    unittest.main()
