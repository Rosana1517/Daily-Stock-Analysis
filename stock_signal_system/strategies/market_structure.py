from __future__ import annotations

from typing import Optional

from stock_signal_system.models import PriceBar


def market_structure_bias(bars: list[PriceBar]) -> str:
    swings = _swing_points(bars)
    highs = [item for item in swings if item[0] == "high"]
    lows = [item for item in swings if item[0] == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return "neutral"

    higher_high = highs[-1][2] > highs[-2][2]
    higher_low = lows[-1][2] > lows[-2][2]
    lower_high = highs[-1][2] < highs[-2][2]
    lower_low = lows[-1][2] < lows[-2][2]

    if higher_high and higher_low:
        return "bullish"
    if lower_high and lower_low:
        return "bearish"
    return "neutral"


def liquidity_sweep_signal(bars: list[PriceBar]) -> Optional[str]:
    if len(bars) < 6:
        return None
    cur = bars[-1]
    prior = bars[-6:-1]
    prior_high = max(bar.high for bar in prior)
    prior_low = min(bar.low for bar in prior)
    if cur.low < prior_low and cur.close > prior_low:
        return "bullish_sweep"
    if cur.high > prior_high and cur.close < prior_high:
        return "bearish_sweep"
    return None


def inverse_fvg_signal(bars: list[PriceBar]) -> Optional[str]:
    if len(bars) < 3:
        return None
    left, middle, right = bars[-3], bars[-2], bars[-1]
    # Three-candle fair value gap approximation:
    # bullish gap if the right candle low stays above the left candle high,
    # bearish gap if the right candle high stays below the left candle low.
    bullish_fvg = right.low > left.high and right.close > middle.high
    bearish_fvg = right.high < left.low and right.close < middle.low
    if bullish_fvg:
        return "bullish_ifvg"
    if bearish_fvg:
        return "bearish_ifvg"
    return None


def previous_session_targets(bars: list[PriceBar], bias: str) -> tuple[float, float]:
    if len(bars) < 2:
        last = bars[-1].close
        return last, last
    previous = bars[-2]
    if bias == "bearish":
        return previous.low, previous.high
    return previous.high, previous.low


def _swing_points(bars: list[PriceBar]) -> list[tuple[str, int, float]]:
    swings: list[tuple[str, int, float]] = []
    for idx in range(1, len(bars) - 1):
        prev_bar, bar, next_bar = bars[idx - 1], bars[idx], bars[idx + 1]
        if bar.high > prev_bar.high and bar.high > next_bar.high:
            swings.append(("high", idx, bar.high))
        if bar.low < prev_bar.low and bar.low < next_bar.low:
            swings.append(("low", idx, bar.low))
    return swings

