from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .foreign_flow import evaluate_foreign_flow
from .macro_liquidity import evaluate_macro_liquidity
from .market_breadth import evaluate_market_breadth
from .models import MarketRegimeInput, MarketRegimeResult, RegimeCategory, SignalScore, clamp_score
from .risk_on_off import evaluate_risk_on_off
from .sector_rotation import evaluate_sector_rotation
from .sentiment import evaluate_sentiment


STRATEGY_MAP: dict[RegimeCategory, tuple[tuple[str, ...], tuple[str, ...]]] = {
    RegimeCategory.AI_MOMENTUM_EXPANSION: (
        ("AI supply-chain momentum", "sector leader pullback buy", "breakout continuation"),
        ("deep mean reversion shorts", "defensive-only allocation"),
    ),
    RegimeCategory.LARGE_CAP_ACCUMULATION: (
        ("large-cap relative strength", "institutional accumulation follow-through", "ETF basket momentum"),
        ("illiquid micro-cap chasing", "late-stage parabolic entries"),
    ),
    RegimeCategory.SMALL_CAP_SPECULATION: (
        ("small-cap breakout rotation", "volume shock continuation", "short covering follow-through"),
        ("low-volume defensive carry", "slow fundamental-only entries"),
    ),
    RegimeCategory.DEFENSIVE_ROTATION: (
        ("defensive relative strength", "low-volatility pullback", "dividend and balance-sheet quality"),
        ("high-beta breakout chasing", "crowded AI momentum entries"),
    ),
    RegimeCategory.HIGH_VOLATILITY_RISK_OFF: (
        ("cash preservation", "reduced position sizing", "failed-breakout avoidance"),
        ("overnight leverage", "thin liquidity momentum chasing"),
    ),
    RegimeCategory.BREAKOUT_TREND_MARKET: (
        ("trend breakout", "momentum persistence", "relative strength pyramiding"),
        ("premature mean reversion", "weak-sector dip buying"),
    ),
    RegimeCategory.MEAN_REVERSION_MARKET: (
        ("range support rebound", "overreaction reversal", "partial profit discipline"),
        ("blind breakout chasing", "wide-stop momentum entries"),
    ),
    RegimeCategory.LIQUIDITY_CONTRACTION: (
        ("waitlist only", "small size tactical rebound", "liquidity filter tightening"),
        ("illiquid entries", "gap-up chasing", "full-size swing entries"),
    ),
}


def classify_market_regime(
    market_input: MarketRegimeInput,
    previous_result: MarketRegimeResult | None = None,
) -> MarketRegimeResult:
    breadth = evaluate_market_breadth(market_input.stock_rows)
    liquidity = evaluate_macro_liquidity(market_input.stock_rows, market_input.etf_flow)
    sectors = evaluate_sector_rotation(market_input.stock_rows, market_input.sector_news_scores)
    flows = evaluate_foreign_flow(
        market_input.foreign_flow,
        market_input.investment_trust_flow,
        market_input.dealer_flow,
        market_input.margin_financing,
        market_input.short_covering,
    )
    risk = evaluate_risk_on_off(market_input.prices_by_symbol, market_input.benchmark_symbol, market_input.stock_rows)
    sentiment = evaluate_sentiment(market_input.sector_news_scores)

    signals = _collect_signals(breadth, liquidity, sectors, flows, risk, sentiment)
    signal_map = {signal.name: signal for signal in signals}
    metrics = _merge_metrics(breadth, liquidity, sectors, flows, risk, sentiment)
    category_scores = _score_categories(signal_map, metrics)
    regime = max(category_scores, key=category_scores.get)
    ranked_scores = sorted(category_scores.values(), reverse=True)
    winning_margin = ranked_scores[0] - ranked_scores[1] if len(ranked_scores) > 1 else ranked_scores[0]
    completeness = _data_completeness(signals)
    confidence = clamp_score(45.0 + winning_margin * 0.45 + completeness * 0.25)
    previous_regime = previous_result.regime if previous_result else _parse_previous(market_input.previous_regime)
    transition = detect_regime_transition(regime, previous_regime, category_scores)
    suitable, unsuitable = STRATEGY_MAP[regime]
    explanation = _build_explanation(regime, signal_map, metrics, completeness)
    return MarketRegimeResult(
        report_date=market_input.report_date,
        regime=regime,
        confidence=confidence,
        explanation=explanation,
        suitable_strategies=suitable,
        unsuitable_strategies=unsuitable,
        signal_scores=tuple(signals),
        category_scores={category.value: score for category, score in category_scores.items()},
        transition=transition,
        previous_regime=previous_regime,
        metadata=metrics,
    )


def save_regime_result(result: MarketRegimeResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_regime_result(path: Path) -> MarketRegimeResult:
    return MarketRegimeResult.from_dict(json.loads(path.read_text(encoding="utf-8")))


def detect_regime_transition(
    current: RegimeCategory,
    previous: RegimeCategory | None,
    category_scores: Mapping[RegimeCategory, float] | Mapping[str, float] | None = None,
) -> str:
    if previous is None:
        return "initial classification"
    if current == previous:
        return f"stable: {current.value}"
    if category_scores:
        current_score = float(category_scores.get(current, category_scores.get(current.value, 0.0)))  # type: ignore[arg-type]
        previous_score = float(category_scores.get(previous, category_scores.get(previous.value, 0.0)))  # type: ignore[arg-type]
        return f"transition: {previous.value} -> {current.value}; score_gap={current_score - previous_score:.1f}"
    return f"transition: {previous.value} -> {current.value}"


def regime_backtest_features(result: MarketRegimeResult) -> dict[str, Any]:
    return {
        "regime": result.regime.value,
        "confidence": result.confidence,
        "is_risk_on": result.regime
        in {
            RegimeCategory.AI_MOMENTUM_EXPANSION,
            RegimeCategory.LARGE_CAP_ACCUMULATION,
            RegimeCategory.SMALL_CAP_SPECULATION,
            RegimeCategory.BREAKOUT_TREND_MARKET,
        },
        "is_risk_off": result.regime
        in {
            RegimeCategory.DEFENSIVE_ROTATION,
            RegimeCategory.HIGH_VOLATILITY_RISK_OFF,
            RegimeCategory.LIQUIDITY_CONTRACTION,
        },
        "position_size_multiplier": _position_size_multiplier(result),
        "avoid_breakouts": result.regime
        in {
            RegimeCategory.HIGH_VOLATILITY_RISK_OFF,
            RegimeCategory.MEAN_REVERSION_MARKET,
            RegimeCategory.LIQUIDITY_CONTRACTION,
        },
    }


def _score_categories(signal_map: Mapping[str, SignalScore], metrics: Mapping[str, Any]) -> dict[RegimeCategory, float]:
    breadth = _value(signal_map, "TWSE breadth")
    trend = _value(signal_map, "TAIEX trend strength")
    sector = _value(signal_map, "sector relative strength")
    ai = _value(signal_map, "AI sector strength")
    defensive = _value(signal_map, "defensive sector strength")
    foreign = _value(signal_map, "foreign investor flow")
    trust = _value(signal_map, "investment trust accumulation")
    turnover = _value(signal_map, "market turnover")
    volatility = _value(signal_map, "volatility regime")
    limit_up = _value(signal_map, "limit-up distribution")
    etf = _value(signal_map, "ETF capital flow")
    sentiment = _value(signal_map, "news and policy sentiment")
    volume_expansion = float(metrics.get("volume_expansion", 1.0))
    advance_ratio = float(metrics.get("advance_ratio", 0.5))

    return {
        RegimeCategory.AI_MOMENTUM_EXPANSION: _avg(ai * 1.55, sector * 1.05, sentiment, trend, turnover, limit_up),
        RegimeCategory.LARGE_CAP_ACCUMULATION: _avg(foreign * 1.2, trust * 1.15, etf, trend, turnover, volatility),
        RegimeCategory.SMALL_CAP_SPECULATION: _avg(limit_up * 1.25, turnover * 1.2, breadth, sentiment, 50.0 + max(volume_expansion - 1.0, 0.0) * 45.0),
        RegimeCategory.DEFENSIVE_ROTATION: _avg(
            defensive * 1.4,
            volatility,
            100.0 - abs(trend - 40.0) * 1.2,
            100.0 - abs(breadth - 45.0) * 1.0,
        ),
        RegimeCategory.HIGH_VOLATILITY_RISK_OFF: _avg(100.0 - volatility, 100.0 - breadth, 100.0 - trend, 100.0 - foreign),
        RegimeCategory.BREAKOUT_TREND_MARKET: _avg(trend * 1.25, breadth, sector, turnover, limit_up),
        RegimeCategory.MEAN_REVERSION_MARKET: _avg(
            100.0 - abs(trend - 50.0) * 1.35,
            100.0 - abs(breadth - 50.0) * 1.15,
            100.0 - abs(sector - 50.0) * 0.8,
            volatility,
        ),
        RegimeCategory.LIQUIDITY_CONTRACTION: _avg(
            100.0 - turnover * 1.35,
            100.0 - etf * 0.8,
            100.0 - breadth * 0.55,
            100.0 - volume_expansion * 55.0,
        ),
    }


def _collect_signals(*groups: Mapping[str, Any]) -> list[SignalScore]:
    signals: list[SignalScore] = []
    for group in groups:
        for value in group.values():
            if isinstance(value, SignalScore):
                signals.append(value)
    return signals


def _merge_metrics(*groups: Mapping[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for group in groups:
        metrics.update(group.get("metrics", {}))
    return metrics


def _data_completeness(signals: list[SignalScore]) -> float:
    if not signals:
        return 0.0
    complete = sum(1 for signal in signals if not signal.missing)
    return complete / len(signals) * 100.0


def _build_explanation(
    regime: RegimeCategory,
    signal_map: Mapping[str, SignalScore],
    metrics: Mapping[str, Any],
    completeness: float,
) -> str:
    top_sector = metrics.get("top_sector", "unknown")
    return (
        f"{regime.value} classified from breadth={_value(signal_map, 'TWSE breadth'):.1f}, "
        f"trend={_value(signal_map, 'TAIEX trend strength'):.1f}, "
        f"turnover={_value(signal_map, 'market turnover'):.1f}, "
        f"volatility={_value(signal_map, 'volatility regime'):.1f}, "
        f"top_sector={top_sector}, data_completeness={completeness:.0f}%."
    )


def _position_size_multiplier(result: MarketRegimeResult) -> float:
    if result.regime in {RegimeCategory.HIGH_VOLATILITY_RISK_OFF, RegimeCategory.LIQUIDITY_CONTRACTION}:
        return 0.35
    if result.regime == RegimeCategory.DEFENSIVE_ROTATION:
        return 0.55
    if result.regime == RegimeCategory.MEAN_REVERSION_MARKET:
        return 0.7
    return min(1.2, 0.75 + result.confidence / 250.0)


def _value(signal_map: Mapping[str, SignalScore], name: str) -> float:
    signal = signal_map.get(name)
    return signal.value if signal else 50.0


def _avg(*values: float) -> float:
    return clamp_score(sum(values) / len(values))


def _parse_previous(value: str | None) -> RegimeCategory | None:
    if not value:
        return None
    try:
        return RegimeCategory(value)
    except ValueError:
        return None
