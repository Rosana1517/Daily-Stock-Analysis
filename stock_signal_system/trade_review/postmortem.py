from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

from .alpha_decay import detect_alpha_decay
from .false_breakout import detect_false_breakout
from .missed_runner import analyze_missed_runners
from .models import MissedCandidate, ReviewedTrade, ReviewFinding, TradeRecord, TradeReviewReport
from .regime_analysis import detect_market_behavior_shifts, detect_regime_mismatch
from .setup_performance import regime_performance, setup_performance


def review_trade(trade: TradeRecord | Mapping[str, object]) -> ReviewedTrade:
    trade_record = _coerce_trade(trade)
    findings = [
        finding
        for finding in (
            detect_false_breakout(trade_record),
            detect_regime_mismatch(trade_record),
            _detect_timing_issue(trade_record),
            _detect_liquidity_issue(trade_record),
            _detect_late_entry(trade_record),
        )
        if finding is not None
    ]
    return ReviewedTrade(
        trade=trade_record,
        outcome="win" if trade_record.realized_return > 0 else "loss",
        pnl_pct=round(trade_record.realized_return * 100.0, 2),
        findings=tuple(findings),
    )


def build_trade_review(
    trades: Iterable[TradeRecord | Mapping[str, object]],
    missed_candidates: Iterable[MissedCandidate] = (),
    report_date: date | None = None,
) -> TradeReviewReport:
    trade_records = tuple(_coerce_trade(trade) for trade in trades)
    reviewed = tuple(review_trade(trade) for trade in trade_records)
    return TradeReviewReport(
        report_date=report_date,
        reviewed_trades=reviewed,
        setup_stats=setup_performance(trade_records),
        regime_stats=regime_performance(trade_records),
        missed_runners=analyze_missed_runners(missed_candidates),
        alpha_decay_alerts=detect_alpha_decay(trade_records),
        market_behavior_shifts=detect_market_behavior_shifts(trade_records),
        metadata={"trade_count": len(trade_records)},
    )


def _detect_timing_issue(trade: TradeRecord) -> ReviewFinding | None:
    if trade.entry_delay_days >= 2 and trade.realized_return < 0:
        return ReviewFinding(
            "timing_issue",
            "medium",
            "Timing issue: entry occurred after the original trigger window.",
            (f"entry_delay_days={trade.entry_delay_days}", f"return={trade.realized_return:.2%}"),
        )
    return None


def _detect_liquidity_issue(trade: TradeRecord) -> ReviewFinding | None:
    if trade.liquidity_score < 45 and (trade.slippage_bps > 35 or trade.realized_return < 0):
        return ReviewFinding(
            "liquidity_issue",
            "medium",
            "Liquidity issue: low tradability or slippage degraded the setup.",
            (f"liquidity_score={trade.liquidity_score:.1f}", f"slippage_bps={trade.slippage_bps:.1f}"),
        )
    return None


def _detect_late_entry(trade: TradeRecord) -> ReviewFinding | None:
    if trade.planned_entry <= 0 or trade.entry_price <= 0:
        return None
    chase_pct = trade.entry_price / trade.planned_entry - 1.0
    if chase_pct >= 0.035 and trade.realized_return <= 0.01:
        return ReviewFinding(
            "late_entry",
            "medium",
            "Late entry: execution price was meaningfully above planned trigger without payoff.",
            (f"chase_pct={chase_pct:.2%}", f"return={trade.realized_return:.2%}"),
        )
    return None


def _coerce_trade(trade: TradeRecord | Mapping[str, object]) -> TradeRecord:
    if isinstance(trade, TradeRecord):
        return trade
    return TradeRecord.from_mapping(trade)
