from __future__ import annotations

from enum import Enum

from .score_components import ScoreComponents


class SetupType(str, Enum):
    BREAKOUT_CONTINUATION = "breakout continuation"
    VOLATILITY_SQUEEZE = "volatility squeeze"
    INSTITUTIONAL_ACCUMULATION = "institutional accumulation"
    MOMENTUM_IGNITION = "momentum ignition"
    MEAN_REVERSION_BOUNCE = "mean reversion bounce"
    SECTOR_ROTATION_ENTRY = "sector rotation entry"
    TREND_RESUMPTION = "trend resumption"


def classify_setup(components: ScoreComponents) -> SetupType:
    scores = {
        SetupType.BREAKOUT_CONTINUATION: components.breakout_probability * 0.6 + components.momentum_continuation * 0.4,
        SetupType.VOLATILITY_SQUEEZE: components.volatility_contraction * 0.7 + components.breakout_probability * 0.3,
        SetupType.INSTITUTIONAL_ACCUMULATION: components.institutional_accumulation * 0.7 + components.liquidity_quality * 0.3,
        SetupType.MOMENTUM_IGNITION: components.volume_expansion * 0.35 + components.momentum_continuation * 0.45 + components.sentiment_strength * 0.2,
        SetupType.MEAN_REVERSION_BOUNCE: (100.0 - components.momentum_continuation) * 0.55 + components.liquidity_quality * 0.2 + components.market_regime_alignment * 0.25,
        SetupType.SECTOR_ROTATION_ENTRY: components.sector_strength * 0.7 + components.relative_strength * 0.3,
        SetupType.TREND_RESUMPTION: components.relative_strength * 0.4 + components.market_regime_alignment * 0.35 + components.breakout_probability * 0.25,
    }
    return max(scores, key=scores.get)
