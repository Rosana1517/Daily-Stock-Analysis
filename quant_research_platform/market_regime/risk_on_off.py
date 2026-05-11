from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import SignalScore, clamp_score


def evaluate_risk_on_off(
    prices_by_symbol: Mapping[str, Sequence[Any]],
    benchmark_symbol: str | None,
    stock_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    bars = _select_benchmark_bars(prices_by_symbol, benchmark_symbol)
    if len(bars) >= 20:
        closes = [_bar_value(bar, "close") for bar in bars if _bar_value(bar, "close") > 0]
        volumes = [_bar_value(bar, "volume") for bar in bars if _bar_value(bar, "volume") >= 0]
        trend_strength = _trend_strength(closes)
        volatility = _volatility(closes)
        volume_expansion = _tail_average(volumes, 5) / max(_tail_average(volumes, 20), 1.0)
        trend_signal = SignalScore(
            "TAIEX trend strength",
            trend_strength,
            evidence=(f"close_20d_return={(closes[-1] / closes[-20] - 1.0):.2%}",),
        )
        volatility_signal = SignalScore("volatility regime", clamp_score(100.0 - volatility * 850.0), evidence=(f"realized_vol={volatility:.2%}",))
    else:
        fallback = _cross_section_fallback(stock_rows)
        trend_signal = SignalScore("TAIEX trend strength", fallback["trend"], missing=("benchmark OHLCV >= 20 bars",))
        volatility_signal = SignalScore("volatility regime", fallback["volatility"], missing=("benchmark OHLCV >= 20 bars",))
        volume_expansion = fallback["volume_expansion"]

    return {
        "taiex_trend_strength": trend_signal,
        "volatility_regime": volatility_signal,
        "metrics": {
            "benchmark_symbol": benchmark_symbol or "cross_section_fallback",
            "volume_expansion": volume_expansion,
            "risk_on_score": (trend_signal.value + volatility_signal.value) / 2.0,
        },
    }


def _select_benchmark_bars(prices_by_symbol: Mapping[str, Sequence[Any]], benchmark_symbol: str | None) -> Sequence[Any]:
    if benchmark_symbol:
        normalized = benchmark_symbol.upper()
        for symbol, bars in prices_by_symbol.items():
            if symbol.upper() == normalized:
                return bars
    return next(iter(prices_by_symbol.values()), ())


def _trend_strength(closes: Sequence[float]) -> float:
    if len(closes) < 20:
        return 50.0
    short_return = closes[-1] / closes[-5] - 1.0 if closes[-5] else 0.0
    long_return = closes[-1] / closes[-20] - 1.0 if closes[-20] else 0.0
    ma5 = sum(closes[-5:]) / 5.0
    ma20 = sum(closes[-20:]) / 20.0
    return clamp_score(50.0 + long_return * 260.0 + short_return * 160.0 + ((ma5 / ma20) - 1.0) * 190.0)


def _volatility(closes: Sequence[float]) -> float:
    returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes)) if closes[index - 1] > 0]
    if not returns:
        return 0.03
    mean = sum(returns[-20:]) / min(20, len(returns))
    variance = sum((item - mean) ** 2 for item in returns[-20:]) / min(20, len(returns))
    return variance ** 0.5


def _cross_section_fallback(stock_rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    returns = []
    volume = avg_volume = 0.0
    for row in stock_rows:
        current = _float(row.get("price") or row.get("close"))
        previous = _float(row.get("price_20d_ago") or row.get("previous_close") or row.get("prev_close"))
        if current > 0 and previous > 0:
            returns.append(current / previous - 1.0)
        volume += _float(row.get("volume"))
        avg_volume += _float(row.get("avg_volume_20d") or row.get("average_volume"))
    if not returns:
        return {"trend": 50.0, "volatility": 50.0, "volume_expansion": 1.0}
    avg_return = sum(returns) / len(returns)
    dispersion = (sum((item - avg_return) ** 2 for item in returns) / len(returns)) ** 0.5
    return {
        "trend": clamp_score(50.0 + avg_return * 220.0),
        "volatility": clamp_score(100.0 - dispersion * 550.0),
        "volume_expansion": volume / avg_volume if avg_volume > 0 else 1.0,
    }


def _tail_average(values: Sequence[float], count: int) -> float:
    if not values:
        return 0.0
    tail = values[-count:]
    return sum(tail) / len(tail)


def _bar_value(bar: Any, name: str) -> float:
    if isinstance(bar, Mapping):
        return _float(bar.get(name))
    return _float(getattr(bar, name, 0.0))


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
