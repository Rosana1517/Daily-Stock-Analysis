from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import SignalScore, clamp_score


def evaluate_macro_liquidity(
    stock_rows: Sequence[Mapping[str, Any]],
    etf_flow: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    volume = average_volume = turnover_value = 0.0
    liquid_names = 0
    for row in stock_rows:
        price = _float(row.get("price") or row.get("close"))
        row_volume = _float(row.get("volume"))
        avg_volume = _float(row.get("avg_volume_20d") or row.get("average_volume"))
        volume += row_volume
        average_volume += avg_volume
        turnover_value += price * row_volume
        if row_volume > 0 and avg_volume > 0:
            liquid_names += 1

    if volume <= 0 or average_volume <= 0:
        turnover = SignalScore("market turnover", 50.0, missing=("volume", "avg_volume_20d"))
    else:
        expansion = volume / average_volume
        turnover = SignalScore(
            "market turnover",
            clamp_score(50.0 + (expansion - 1.0) * 42.0),
            evidence=(f"volume_expansion={expansion:.2f}x", f"liquid_names={liquid_names}"),
        )

    flow_value = sum(float(value) for value in (etf_flow or {}).values())
    if etf_flow:
        etf_score = SignalScore("ETF capital flow", clamp_score(50.0 + flow_value / 50_000_000.0), evidence=(f"flow={flow_value:.0f}",))
    else:
        etf_score = SignalScore("ETF capital flow", 50.0, missing=("ETF flow dataset",))

    return {
        "turnover": turnover,
        "etf_flow": etf_score,
        "metrics": {
            "market_volume": volume,
            "market_average_volume": average_volume,
            "turnover_value": turnover_value,
            "volume_expansion": (volume / average_volume) if average_volume > 0 else 1.0,
            "etf_flow": flow_value,
        },
    }


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
