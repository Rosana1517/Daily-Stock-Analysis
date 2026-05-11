from __future__ import annotations

from .models import ReviewFinding, TradeRecord


BREAKOUT_SETUPS = {"breakout continuation", "momentum ignition", "trend resumption"}


def detect_false_breakout(trade: TradeRecord) -> ReviewFinding | None:
    if trade.setup not in BREAKOUT_SETUPS:
        return None
    failed_quickly = trade.max_favorable_return < 0.035 and trade.realized_return < -0.015
    stop_swept = trade.stop_loss > 0 and trade.min_price_after_entry <= trade.stop_loss and trade.max_favorable_return < 0.05
    weak_volume = trade.volume_ratio < 1.15
    if failed_quickly or stop_swept:
        evidence = (
            f"mfe={trade.max_favorable_return:.2%}",
            f"return={trade.realized_return:.2%}",
            f"volume_ratio={trade.volume_ratio:.2f}",
        )
        severity = "high" if weak_volume else "medium"
        message = "False breakout: price failed to expand after trigger and reversed before payoff developed."
        return ReviewFinding("false_breakout", severity, message, evidence)
    return None
