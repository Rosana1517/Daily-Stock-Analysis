from __future__ import annotations

import unittest

from stock_signal_system.models import CandlestickSignal, IndustrySignal, StockSnapshot
from stock_signal_system.screener.ranking_engine import RankingModelConfig, SetupType, rank_stocks_probability, ranked_to_recommendations
from stock_signal_system.screener.ranking_engine.ranking_report import build_ranking_markdown, ranking_rows


class RankingEngineTest(unittest.TestCase):
    def test_probability_ranking_prioritizes_short_term_edge(self):
        stocks = [
            _stock("2330", "台積電", "半導體", 100, 92, 2_000_000, 1_000_000),
            _stock("1101", "台泥", "水泥", 34, 35, 120_000, 250_000),
        ]
        signals = [IndustrySignal("半導體", 78, ("AI demand",), 3), IndustrySignal("水泥", 45, (), 0)]
        technicals = {
            "2330": CandlestickSignal(
                symbol="2330",
                bias="bullish",
                score_adjustment=12,
                patterns=("breakout above consolidation",),
                entry="breakout",
                stop_loss="below base",
                exit="trail",
                risk_reward=2.5,
            )
        }

        ranked = rank_stocks_probability(
            stocks,
            signals,
            technicals,
            market_regime="breakout trend market",
            flow_by_symbol={"2330": 150_000_000},
            top_n=2,
        )

        self.assertEqual(ranked[0].stock.symbol, "2330")
        self.assertGreater(ranked[0].probability, ranked[1].probability)
        self.assertIn(ranked[0].setup, {SetupType.BREAKOUT_CONTINUATION, SetupType.MOMENTUM_IGNITION})

    def test_preserves_existing_recommendation_shape(self):
        ranked = rank_stocks_probability(
            [_stock("2382", "廣達", "AI伺服器", 76, 66, 1_500_000, 800_000)],
            [IndustrySignal("AI伺服器", 82, ("server demand",), 4)],
            market_regime="AI momentum expansion",
            config=RankingModelConfig(min_probability=40),
        )

        recommendations = ranked_to_recommendations(ranked)

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].stock.symbol, "2382")
        self.assertEqual(recommendations[0].status, "probability-ranked")
        self.assertTrue(any(reason.startswith("probability=") for reason in recommendations[0].reasons))

    def test_report_rows_are_stable_for_future_html_or_api_consumers(self):
        ranked = rank_stocks_probability(
            [_stock("2454", "聯發科", "半導體", 95, 90, 950_000, 900_000)],
            [IndustrySignal("半導體", 70, (), 2)],
            top_n=1,
        )

        rows = ranking_rows(ranked)
        markdown = build_ranking_markdown(ranked)

        self.assertEqual(rows[0]["symbol"], "2454")
        self.assertIn("probability", rows[0])
        self.assertIn("| Rank | Symbol |", markdown)


def _stock(symbol: str, name: str, industry: str, price: float, previous: float, volume: float, avg_volume: float) -> StockSnapshot:
    return StockSnapshot(
        symbol=symbol,
        name=name,
        industry=industry,
        price=price,
        price_20d_ago=previous,
        volume=volume,
        avg_volume_20d=avg_volume,
        revenue_growth_yoy=12,
        gross_margin=35,
        operating_margin=14,
        free_cash_flow_margin=8,
        debt_to_equity=0.4,
        pe_ratio=20,
    )


if __name__ == "__main__":
    unittest.main()
