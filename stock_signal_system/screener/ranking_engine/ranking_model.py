from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from stock_signal_system.models import StockSnapshot

from .probability_engine import (
    confidence_score,
    expected_holding_period,
    expected_volatility,
    opportunity_probability,
    risk_reward_estimate,
)
from .score_components import ScoreComponents
from .setup_classifier import SetupType, classify_setup


DEFAULT_WEIGHTS: dict[str, float] = {
    "volume_expansion": 0.12,
    "sector_strength": 0.12,
    "institutional_accumulation": 0.10,
    "volatility_contraction": 0.09,
    "breakout_probability": 0.14,
    "momentum_continuation": 0.12,
    "relative_strength": 0.11,
    "liquidity_quality": 0.08,
    "market_regime_alignment": 0.08,
    "sentiment_strength": 0.04,
}


@dataclass(frozen=True)
class RankingModelConfig:
    weights: dict[str, float] | None = None
    min_probability: float = 0.0

    def normalized_weights(self) -> dict[str, float]:
        raw = dict(self.weights or DEFAULT_WEIGHTS)
        total = sum(raw.values()) or 1.0
        return {key: value / total for key, value in raw.items()}


@dataclass(frozen=True)
class RankingResult:
    stock: StockSnapshot
    composite_score: float
    probability: float
    confidence: float
    setup: SetupType
    expected_holding_period: str
    expected_volatility: str
    risk_reward: float
    components: ScoreComponents
    reasons: tuple[str, ...]
    risks: tuple[str, ...]


class MLRankingModel(Protocol):
    """Future ML integration point for calibrated 3-10 day opportunity probabilities."""

    feature_names: tuple[str, ...]

    def predict_probability(self, features: dict[str, float]) -> float:
        ...


def rank_one(
    stock: StockSnapshot,
    components: ScoreComponents,
    config: RankingModelConfig | None = None,
    ml_model: MLRankingModel | None = None,
) -> RankingResult:
    model_config = config or RankingModelConfig()
    weights = model_config.normalized_weights()
    composite = sum(components.as_dict()[key] * weights.get(key, 0.0) for key in components.as_dict())
    probability = (
        round(float(ml_model.predict_probability(components.as_dict())), 1)
        if ml_model
        else opportunity_probability(composite, components)
    )
    setup = classify_setup(components)
    confidence = confidence_score(components, composite)
    return RankingResult(
        stock=stock,
        composite_score=round(composite, 1),
        probability=probability,
        confidence=confidence,
        setup=setup,
        expected_holding_period=expected_holding_period(composite, components),
        expected_volatility=expected_volatility(components),
        risk_reward=risk_reward_estimate(components, probability),
        components=components,
        reasons=_ranking_reasons(components, setup),
        risks=_ranking_risks(components, probability),
    )


def _ranking_reasons(components: ScoreComponents, setup: SetupType) -> tuple[str, ...]:
    leaders = sorted(components.as_dict().items(), key=lambda item: item[1], reverse=True)[:3]
    return tuple([f"setup={setup.value}"] + [f"{name}={value:.1f}" for name, value in leaders])


def _ranking_risks(components: ScoreComponents, probability: float) -> tuple[str, ...]:
    risks: list[str] = []
    if components.liquidity_quality < 45:
        risks.append("liquidity quality below ranking threshold")
    if components.market_regime_alignment < 45:
        risks.append("market regime alignment is weak")
    if probability < 55:
        risks.append("probability is only watchlist quality")
    return tuple(risks)
