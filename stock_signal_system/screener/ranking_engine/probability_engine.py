from __future__ import annotations

import math

from .score_components import ScoreComponents


def opportunity_probability(composite_score: float, components: ScoreComponents) -> float:
    edge_adjustment = (
        (components.market_regime_alignment - 50.0) * 0.035
        + (components.liquidity_quality - 50.0) * 0.020
        + (components.volatility_contraction - 50.0) * 0.014
    )
    z_score = (composite_score - 58.0) / 10.5 + edge_adjustment
    return round(100.0 / (1.0 + math.exp(-z_score)), 1)


def confidence_score(components: ScoreComponents, composite_score: float) -> float:
    values = list(components.as_dict().values())
    mean = sum(values) / len(values)
    dispersion = (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5
    agreement = max(0.0, 100.0 - dispersion * 1.35)
    return round(max(0.0, min(100.0, agreement * 0.55 + composite_score * 0.45)), 1)


def expected_holding_period(composite_score: float, components: ScoreComponents) -> str:
    if components.breakout_probability >= 72 and components.volume_expansion >= 70:
        return "3-5 trading days"
    if components.volatility_contraction >= 72:
        return "5-10 trading days"
    if composite_score >= 72:
        return "4-8 trading days"
    return "3-10 trading days"


def expected_volatility(components: ScoreComponents) -> str:
    if components.volatility_contraction >= 75 and components.liquidity_quality >= 60:
        return "moderate expansion"
    if components.volume_expansion >= 82 or components.breakout_probability >= 82:
        return "high"
    if components.liquidity_quality < 45:
        return "thin and jumpy"
    return "normal"


def risk_reward_estimate(components: ScoreComponents, probability: float) -> float:
    reward = components.breakout_probability * 0.35 + components.momentum_continuation * 0.25 + components.relative_strength * 0.25
    risk = max(25.0, (100.0 - components.liquidity_quality) * 0.35 + (100.0 - components.volatility_contraction) * 0.25 + (100.0 - probability) * 0.25)
    return round(max(0.5, min(4.5, reward / risk)), 2)
