from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import SetupStats, TradeRecord


def setup_performance(trades: Iterable[TradeRecord]) -> tuple[SetupStats, ...]:
    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        grouped[trade.setup or "unknown"].append(trade)
    return tuple(_stats(setup, rows) for setup, rows in sorted(grouped.items()))


def regime_performance(trades: Iterable[TradeRecord]) -> dict[str, SetupStats]:
    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        grouped[trade.regime or "unknown"].append(trade)
    return {regime: _stats(regime, rows) for regime, rows in sorted(grouped.items())}


def _stats(name: str, trades: list[TradeRecord]) -> SetupStats:
    wins = [trade.realized_return for trade in trades if trade.realized_return > 0]
    losses = [abs(trade.realized_return) for trade in trades if trade.realized_return <= 0]
    average_return = sum(trade.realized_return for trade in trades) / len(trades) if trades else 0.0
    win_rate = len(wins) / len(trades) if trades else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else (avg_win / 0.01 if avg_win else 0.0)
    alert = ""
    if len(trades) >= 3 and win_rate < 0.45:
        alert = "strategy degradation"
    elif len(trades) >= 3 and average_return < -0.02:
        alert = "negative expectancy"
    return SetupStats(
        setup=name,
        trades=len(trades),
        wins=len(wins),
        win_rate=round(win_rate, 4),
        average_return=round(average_return, 4),
        payoff_ratio=round(payoff_ratio, 2),
        alert=alert,
    )
