"""Platform (box-range consolidation) breakout geometry: detecting a
consolidation box, and deriving stop-loss/take-profit reference prices
and a breakout-strength score from it."""

from __future__ import annotations


def _platform_box_range(bars: list) -> tuple[float, float, float, int] | None:
    if len(bars) < 21:
        return None
    latest = bars[-1]
    best: tuple[float, float, float, int] | None = None
    for window_size in range(10, min(20, len(bars) - 1) + 1):
        setup = bars[-(window_size + 1) : -1]
        if len(setup) != window_size:
            continue
        highs = [bar.high for bar in setup if getattr(bar, "high", 0) > 0]
        lows = [bar.low for bar in setup if getattr(bar, "low", 0) > 0]
        closes = [bar.close for bar in setup if getattr(bar, "close", 0) > 0]
        if len(highs) != window_size or len(lows) != window_size or len(closes) != window_size:
            continue
        box_high = max(highs)
        box_low = min(lows)
        average_close = sum(closes) / len(closes)
        if average_close <= 0 or box_high <= box_low:
            continue
        compression = (box_high - box_low) / average_close
        if compression > 0.18:
            continue
        top_touch_count = sum(1 for bar in setup if bar.high >= box_high * 0.992)
        low_touch_count = sum(1 for bar in setup if bar.low <= box_low * 1.008)
        if top_touch_count < 2 or low_touch_count < 2:
            continue
        last_setup_close = setup[-1].close
        if last_setup_close >= box_high * 1.02 or last_setup_close <= box_low * 0.98:
            continue
        breakout_pct = latest.close / max(box_high, 0.01) - 1.0
        if breakout_pct <= 0:
            continue
        score = (0.18 - compression) * 1000.0 + breakout_pct * 1800.0 + window_size
        candidate = (box_high, box_low, compression, window_size)
        if best is None or score > ((0.18 - best[2]) * 1000.0 + (latest.close / max(best[0], 0.01) - 1.0) * 1800.0 + best[3]):
            best = candidate
    return best


def platform_neckline_price(bars: list) -> float | None:
    """Return the breakout platform's box-high (neckline) as a stop-loss reference."""
    box_range = _platform_box_range(bars)
    if box_range is None:
        return None
    return box_range[0]


def platform_measured_move_target(bars: list) -> float | None:
    """Classic measured-move take-profit target: box_high + box_height,
    projecting the consolidation range's height above the breakout point."""
    box_range = _platform_box_range(bars)
    if box_range is None:
        return None
    box_high, box_low, _compression, _window_size = box_range
    return box_high + (box_high - box_low)


def _platform_breakout_strength(bars: list) -> float:
    if len(bars) < 21:
        return 0.0
    latest = bars[-1]
    box_range = _platform_box_range(bars)
    if box_range is None:
        return 0.0
    box_high, box_low, compression, window_size = box_range
    if latest.close <= box_high:
        return 0.0
    breakout_pct = latest.close / max(box_high, 0.01) - 1.0
    if breakout_pct < 0.003:
        return 0.0
    breakout_body = (latest.close - max(latest.open, box_high)) / max(box_high, 0.01)
    if breakout_body < -0.002:
        return 0.0
    average_volume = sum(bar.volume for bar in bars[-(window_size + 1) : -1]) / float(window_size)
    volume_ratio = latest.volume / average_volume if average_volume else 1.0
    if volume_ratio < 1.2:
        return 0.0
    rebound_from_low = box_high / max(box_low, 0.01) - 1.0
    return (
        breakout_pct * 2600.0
        + max(0.0, 0.18 - compression) * 220.0
        + volume_ratio * 12.0
        + rebound_from_low * 80.0
    )
