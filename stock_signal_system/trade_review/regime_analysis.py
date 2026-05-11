from __future__ import annotations

from collections.abc import Iterable

from .models import ReviewFinding, TradeRecord


RISK_OFF_REGIMES = {"high-volatility risk-off", "liquidity contraction", "defensive rotation"}
BREAKOUT_SETUPS = {"breakout continuation", "momentum ignition", "trend resumption"}


def detect_regime_mismatch(trade: TradeRecord) -> ReviewFinding | None:
    if trade.regime in RISK_OFF_REGIMES and trade.setup in BREAKOUT_SETUPS:
        return ReviewFinding(
            "regime_mismatch",
            "high",
            "Regime mismatch: breakout setup was taken during risk-off or liquidity contraction.",
            (f"regime={trade.regime}", f"setup={trade.setup}", f"return={trade.realized_return:.2%}"),
        )
    if trade.sector_return < -0.03 and trade.realized_return < 0:
        return ReviewFinding(
            "sector_weakness",
            "medium",
            "Sector weakness: stock entry fought a weak sector tape.",
            (f"sector_return={trade.sector_return:.2%}", f"return={trade.realized_return:.2%}"),
        )
    return None


def detect_market_behavior_shifts(trades: Iterable[TradeRecord], min_count: int = 3) -> tuple[ReviewFinding, ...]:
    trades = tuple(trades)
    if len(trades) < min_count:
        return ()
    failed_breakouts = [
        trade for trade in trades if trade.setup in BREAKOUT_SETUPS and trade.realized_return < 0 and trade.max_favorable_return < 0.04
    ]
    if len(failed_breakouts) >= min_count:
        return (
            ReviewFinding(
                "market_behavior_shift",
                "high",
                "Breakout follow-through is deteriorating across recent trades.",
                (f"failed_breakouts={len(failed_breakouts)}",),
            ),
        )
    return ()
