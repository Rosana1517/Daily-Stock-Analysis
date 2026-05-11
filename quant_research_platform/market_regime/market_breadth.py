from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import SignalScore, clamp_score


def evaluate_market_breadth(stock_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = advancers = decliners = limit_up = limit_down = 0
    returns: list[float] = []
    for row in stock_rows:
        current = _float(row.get("price") or row.get("close"))
        previous = _float(row.get("price_20d_ago") or row.get("previous_close") or row.get("prev_close"))
        if current <= 0 or previous <= 0:
            continue
        total += 1
        change = (current / previous) - 1.0
        returns.append(change)
        if change > 0:
            advancers += 1
        elif change < 0:
            decliners += 1
        if change >= 0.095:
            limit_up += 1
        if change <= -0.095:
            limit_down += 1

    if total == 0:
        return {
            "breadth": SignalScore("TWSE breadth", 50.0, missing=("stock price and previous price",)),
            "limit_up_distribution": SignalScore("limit-up distribution", 50.0, missing=("cross-sectional returns",)),
            "metrics": {"universe_count": 0},
        }

    advance_ratio = advancers / total
    decline_ratio = decliners / total
    avg_return = sum(returns) / len(returns)
    breadth_score = clamp_score(50.0 + (advance_ratio - 0.5) * 95.0 + avg_return * 180.0)
    limit_score = clamp_score(50.0 + (limit_up / total) * 450.0 - (limit_down / total) * 350.0)
    return {
        "breadth": SignalScore(
            "TWSE breadth",
            breadth_score,
            evidence=(
                f"advancers={advancers}",
                f"decliners={decliners}",
                f"advance_ratio={advance_ratio:.2%}",
            ),
        ),
        "limit_up_distribution": SignalScore(
            "limit-up distribution",
            limit_score,
            evidence=(f"limit_up={limit_up}", f"limit_down={limit_down}", f"universe={total}"),
        ),
        "metrics": {
            "universe_count": total,
            "advancers": advancers,
            "decliners": decliners,
            "advance_ratio": advance_ratio,
            "decline_ratio": decline_ratio,
            "average_cross_section_return": avg_return,
            "limit_up_ratio": limit_up / total,
            "limit_down_ratio": limit_down / total,
        },
    }


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
