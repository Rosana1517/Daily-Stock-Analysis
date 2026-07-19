"""Market-wide foreign investor flow trend, aggregated from the per-stock
TWSE T86 institutional data the pipeline already fetches daily. Net buy is
summed in shares and reported in lots (張, share/1000)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from stock_signal_system.data.chip_snapshot import TwseInstitutionalDay


@dataclass(frozen=True)
class ForeignFlowTrend:
    daily_net_lots: tuple[tuple[date, float], ...]  # newest first
    streak_days: int  # >0 consecutive net-buy days, <0 consecutive net-sell days
    cumulative_net_lots: float
    bias: str  # 外資偏多 / 外資偏空 / 外資中性


def summarize_market_foreign_flow(days: tuple[TwseInstitutionalDay, ...]) -> ForeignFlowTrend | None:
    if not days:
        return None
    ordered = sorted(days, key=lambda day: day.trade_date, reverse=True)
    daily: list[tuple[date, float]] = []
    for day in ordered:
        net_shares = sum(float(row.get("foreign_net_buy", 0) or 0) for row in day.rows)
        daily.append((day.trade_date, net_shares / 1000.0))
    streak = 0
    for _, net_lots in daily:
        if net_lots > 0:
            if streak < 0:
                break
            streak += 1
        elif net_lots < 0:
            if streak > 0:
                break
            streak -= 1
        else:
            break
    cumulative = sum(net_lots for _, net_lots in daily)
    if cumulative > 0 and streak >= 2:
        bias = "外資偏多"
    elif cumulative < 0 and streak <= -2:
        bias = "外資偏空"
    else:
        bias = "外資中性"
    return ForeignFlowTrend(
        daily_net_lots=tuple(daily),
        streak_days=streak,
        cumulative_net_lots=cumulative,
        bias=bias,
    )
