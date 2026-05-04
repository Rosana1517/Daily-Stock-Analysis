from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median


@dataclass(frozen=True)
class LiquiditySnapshot:
    avg_volume: float
    avg_dollar_volume: float
    turnover_ratio: float | None
    estimated_spread_bps: float | None
    impact_bps_1pct_adv: float | None


def build_liquidity_snapshots(
    bars_by_symbol: dict[str, list[object]],
    fundamentals: dict[str, object],
) -> dict[str, LiquiditySnapshot]:
    snapshots: dict[str, LiquiditySnapshot] = {}
    for symbol, bars in bars_by_symbol.items():
        window = list(bars[-60:])
        if not window:
            continue
        volumes = [float(getattr(bar, "volume", 0) or 0) for bar in window]
        closes = [float(getattr(bar, "close", 0) or 0) for bar in window]
        ranges = [
            (float(getattr(bar, "high", 0) or 0) - float(getattr(bar, "low", 0) or 0)) / float(getattr(bar, "close", 1) or 1)
            for bar in window
            if float(getattr(bar, "close", 0) or 0) > 0
        ]
        avg_volume = mean(volumes) if volumes else 0.0
        avg_dollar_volume = mean(close * volume for close, volume in zip(closes, volumes)) if closes and volumes else 0.0
        snapshot = fundamentals.get(symbol)
        base_volume = float(getattr(snapshot, "avg_volume_20d", 0) or 0) if snapshot else 0.0
        turnover_ratio = avg_volume / base_volume if base_volume > 0 else None
        spread_bps = median(ranges) * 10000 * 0.12 if ranges else None
        impact_bps = _impact_bps(window)
        snapshots[symbol] = LiquiditySnapshot(
            avg_volume=avg_volume,
            avg_dollar_volume=avg_dollar_volume,
            turnover_ratio=turnover_ratio,
            estimated_spread_bps=spread_bps,
            impact_bps_1pct_adv=impact_bps,
        )
    return snapshots


def _impact_bps(bars: list[object]) -> float | None:
    returns = []
    for previous, current in zip(bars, bars[1:]):
        prior_close = float(getattr(previous, "close", 0) or 0)
        close = float(getattr(current, "close", 0) or 0)
        if prior_close > 0:
            returns.append(close / prior_close - 1)
    if len(returns) < 2:
        return None
    avg_return = mean(returns)
    variance = mean((item - avg_return) ** 2 for item in returns)
    daily_volatility = variance**0.5
    return daily_volatility * (0.01**0.5) * 10000
