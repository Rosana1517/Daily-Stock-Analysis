from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import ReviewFinding, TradeRecord


def detect_alpha_decay(trades: Iterable[TradeRecord], min_trades: int = 4) -> tuple[ReviewFinding, ...]:
    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        grouped[trade.setup or "unknown"].append(trade)

    findings: list[ReviewFinding] = []
    for setup, setup_trades in grouped.items():
        if len(setup_trades) < min_trades:
            continue
        midpoint = len(setup_trades) // 2
        early = setup_trades[:midpoint]
        recent = setup_trades[midpoint:]
        early_avg = _average_return(early)
        recent_avg = _average_return(recent)
        recent_win_rate = _win_rate(recent)
        if recent_avg < early_avg - 0.035 and recent_win_rate < 0.45:
            findings.append(
                ReviewFinding(
                    "alpha_decay",
                    "high",
                    "Alpha decay detected: recent setup performance is materially below earlier sample.",
                    (
                        f"setup={setup}",
                        f"early_avg={early_avg:.2%}",
                        f"recent_avg={recent_avg:.2%}",
                        f"recent_win_rate={recent_win_rate:.1%}",
                    ),
                )
            )
    return tuple(findings)


def _average_return(trades: list[TradeRecord]) -> float:
    if not trades:
        return 0.0
    return sum(trade.realized_return for trade in trades) / len(trades)


def _win_rate(trades: list[TradeRecord]) -> float:
    if not trades:
        return 0.0
    return sum(1 for trade in trades if trade.realized_return > 0) / len(trades)
