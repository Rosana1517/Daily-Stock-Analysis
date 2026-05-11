from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from stock_signal_system.models import CandlestickSignal, IndustrySignal, StockSnapshot


@dataclass(frozen=True)
class ScoreComponents:
    volume_expansion: float
    sector_strength: float
    institutional_accumulation: float
    volatility_contraction: float
    breakout_probability: float
    momentum_continuation: float
    relative_strength: float
    liquidity_quality: float
    market_regime_alignment: float
    sentiment_strength: float

    def as_dict(self) -> dict[str, float]:
        return {
            "volume_expansion": self.volume_expansion,
            "sector_strength": self.sector_strength,
            "institutional_accumulation": self.institutional_accumulation,
            "volatility_contraction": self.volatility_contraction,
            "breakout_probability": self.breakout_probability,
            "momentum_continuation": self.momentum_continuation,
            "relative_strength": self.relative_strength,
            "liquidity_quality": self.liquidity_quality,
            "market_regime_alignment": self.market_regime_alignment,
            "sentiment_strength": self.sentiment_strength,
        }


def build_score_components(
    stock: StockSnapshot,
    industry_signals: list[IndustrySignal],
    candlestick_signal: Optional[CandlestickSignal] = None,
    market_regime: object | None = None,
    flow_by_symbol: Mapping[str, float] | None = None,
) -> ScoreComponents:
    industry_score = _best_industry_score(stock, industry_signals)
    momentum = _momentum_20d(stock)
    volume_ratio = _volume_ratio(stock)
    flow_score = _flow_score(stock.symbol, flow_by_symbol)
    technical_bias = _technical_bias_score(candlestick_signal)
    return ScoreComponents(
        volume_expansion=_volume_expansion_score(volume_ratio),
        sector_strength=industry_score,
        institutional_accumulation=flow_score,
        volatility_contraction=_volatility_contraction_score(stock, candlestick_signal),
        breakout_probability=_breakout_score(momentum, volume_ratio, candlestick_signal),
        momentum_continuation=_momentum_score(momentum),
        relative_strength=_relative_strength_score(momentum, industry_score),
        liquidity_quality=_liquidity_score(stock),
        market_regime_alignment=_regime_alignment_score(market_regime, technical_bias, industry_score, momentum),
        sentiment_strength=industry_score,
    )


def _best_industry_score(stock: StockSnapshot, industry_signals: list[IndustrySignal]) -> float:
    scores = {item.industry: item.score for item in industry_signals}
    return _clamp(scores.get(stock.industry, 50.0))


def _momentum_20d(stock: StockSnapshot) -> float:
    if stock.price_20d_ago <= 0:
        return 0.0
    return stock.price / stock.price_20d_ago - 1.0


def _volume_ratio(stock: StockSnapshot) -> float:
    if stock.avg_volume_20d <= 0:
        return 1.0
    return stock.volume / stock.avg_volume_20d


def _volume_expansion_score(volume_ratio: float) -> float:
    if volume_ratio >= 2.0:
        return 88.0
    if volume_ratio >= 1.35:
        return 74.0 + min(12.0, (volume_ratio - 1.35) * 18.0)
    if volume_ratio >= 0.9:
        return 50.0 + (volume_ratio - 0.9) * 45.0
    return max(20.0, 50.0 - (0.9 - volume_ratio) * 55.0)


def _momentum_score(momentum: float) -> float:
    if momentum >= 0.18:
        return 82.0
    if momentum >= 0.06:
        return 62.0 + momentum * 110.0
    if momentum >= -0.04:
        return 50.0 + momentum * 180.0
    return max(20.0, 45.0 + momentum * 180.0)


def _relative_strength_score(momentum: float, industry_score: float) -> float:
    return _clamp(_momentum_score(momentum) * 0.55 + industry_score * 0.45)


def _liquidity_score(stock: StockSnapshot) -> float:
    value_traded = stock.price * stock.volume
    if value_traded >= 500_000_000:
        return 90.0
    if value_traded >= 120_000_000:
        return 76.0
    if value_traded >= 30_000_000:
        return 62.0
    if value_traded >= 8_000_000:
        return 48.0
    return 30.0


def _volatility_contraction_score(stock: StockSnapshot, signal: Optional[CandlestickSignal]) -> float:
    base = 54.0
    if stock.notes and any(term in stock.notes.lower() for term in ("squeeze", "contraction", "整理", "收斂")):
        base += 18.0
    if signal and any("squeeze" in pattern.lower() or "收斂" in pattern for pattern in signal.patterns):
        base += 22.0
    if stock.volume < stock.avg_volume_20d * 0.75:
        base += 8.0
    return _clamp(base)


def _breakout_score(momentum: float, volume_ratio: float, signal: Optional[CandlestickSignal]) -> float:
    base = 46.0 + max(0.0, momentum) * 135.0 + max(0.0, volume_ratio - 1.0) * 18.0
    if signal:
        base += signal.score_adjustment * 0.9
        if signal.bias == "bullish":
            base += 9.0
        if any("breakout" in pattern.lower() or "突破" in pattern for pattern in signal.patterns):
            base += 16.0
    return _clamp(base)


def _flow_score(symbol: str, flow_by_symbol: Mapping[str, float] | None) -> float:
    if not flow_by_symbol or symbol not in flow_by_symbol:
        return 50.0
    return _clamp(50.0 + float(flow_by_symbol[symbol]) / 20_000_000.0)


def _technical_bias_score(signal: Optional[CandlestickSignal]) -> float:
    if not signal:
        return 50.0
    if signal.bias == "bullish":
        return _clamp(62.0 + signal.score_adjustment)
    if signal.bias == "bearish":
        return _clamp(38.0 + signal.score_adjustment)
    return _clamp(50.0 + signal.score_adjustment)


def _regime_alignment_score(market_regime: object | None, technical_bias: float, industry_score: float, momentum: float) -> float:
    regime = _regime_text(market_regime)
    base = technical_bias * 0.35 + industry_score * 0.35 + _momentum_score(momentum) * 0.30
    if not regime:
        return _clamp(base)
    if "risk-off" in regime or "liquidity contraction" in regime:
        return _clamp(base - 18.0 if momentum > 0.08 else base - 8.0)
    if "AI momentum" in regime:
        return _clamp(base + 12.0 if _looks_ai_theme(regime, industry_score) else base)
    if "breakout trend" in regime or "large-cap accumulation" in regime:
        return _clamp(base + 8.0)
    if "mean-reversion" in regime:
        return _clamp(62.0 if -0.08 <= momentum <= 0.04 else base - 10.0)
    return _clamp(base)


def _regime_text(market_regime: object | None) -> str:
    if market_regime is None:
        return ""
    value = getattr(market_regime, "regime", market_regime)
    if hasattr(value, "value"):
        value = value.value
    return str(value)


def _looks_ai_theme(regime: str, industry_score: float) -> bool:
    return "AI" in regime and industry_score >= 55.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))
