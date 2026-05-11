from __future__ import annotations

from typing import Mapping, Optional

from stock_signal_system.models import CandlestickSignal, IndustrySignal, StockRecommendation, StockSnapshot

from .ranking_model import MLRankingModel, RankingModelConfig, RankingResult, rank_one
from .score_components import build_score_components


def rank_stocks_probability(
    stocks: list[StockSnapshot],
    industry_signals: list[IndustrySignal],
    candlestick_signals: Optional[dict[str, CandlestickSignal]] = None,
    market_regime: object | None = None,
    flow_by_symbol: Mapping[str, float] | None = None,
    top_n: int | None = None,
    config: RankingModelConfig | None = None,
    ml_model: MLRankingModel | None = None,
) -> list[RankingResult]:
    technicals = candlestick_signals or {}
    model_config = config or RankingModelConfig()
    ranked = [
        rank_one(
            stock,
            build_score_components(
                stock,
                industry_signals,
                technicals.get(stock.symbol),
                market_regime=market_regime,
                flow_by_symbol=flow_by_symbol,
            ),
            config=model_config,
            ml_model=ml_model,
        )
        for stock in stocks
    ]
    ranked = [item for item in ranked if item.probability >= model_config.min_probability]
    ranked.sort(key=lambda item: (item.probability, item.composite_score, item.confidence), reverse=True)
    return ranked[:top_n] if top_n else ranked


def ranked_to_recommendations(ranked: list[RankingResult]) -> list[StockRecommendation]:
    recommendations: list[StockRecommendation] = []
    for item in ranked:
        recommendations.append(
            StockRecommendation(
                stock=item.stock,
                score=item.composite_score,
                rating=_rating(item.probability),
                reasons=tuple(
                    list(item.reasons)
                    + [
                        f"probability={item.probability:.1f}",
                        f"confidence={item.confidence:.1f}",
                        f"holding_period={item.expected_holding_period}",
                        f"risk_reward={item.risk_reward:.2f}:1",
                    ]
                ),
                risks=item.risks,
                entry_plan=f"{item.setup.value}; wait for price confirmation and volume follow-through.",
                stop_loss="Use setup invalidation low or 5-7% stop, whichever is tighter.",
                exit_plan=f"Review after {item.expected_holding_period}; scale out if momentum or volume fades.",
                status="probability-ranked",
            )
        )
    return recommendations


def _rating(probability: float) -> str:
    if probability >= 70:
        return "high probability"
    if probability >= 58:
        return "qualified"
    return "watchlist"
