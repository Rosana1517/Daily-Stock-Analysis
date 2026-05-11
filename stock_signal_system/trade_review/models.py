from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping


@dataclass(frozen=True)
class TradeRecord:
    symbol: str
    name: str = ""
    industry: str = ""
    setup: str = ""
    regime: str = ""
    ranking_probability: float = 0.0
    ranking_confidence: float = 0.0
    entry_date: date | None = None
    exit_date: date | None = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    planned_entry: float = 0.0
    stop_loss: float = 0.0
    max_price_after_entry: float = 0.0
    min_price_after_entry: float = 0.0
    days_held: int = 0
    volume_ratio: float = 1.0
    liquidity_score: float = 50.0
    sector_return: float = 0.0
    market_return: float = 0.0
    entry_delay_days: int = 0
    slippage_bps: float = 0.0
    notes: str = ""

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "TradeRecord":
        return cls(
            symbol=str(row.get("symbol", "")).strip(),
            name=str(row.get("name", "")).strip(),
            industry=str(row.get("industry", "")).strip(),
            setup=str(row.get("setup", "")).strip(),
            regime=str(row.get("regime", "")).strip(),
            ranking_probability=_float(row.get("ranking_probability") or row.get("probability")),
            ranking_confidence=_float(row.get("ranking_confidence") or row.get("confidence")),
            entry_date=_date(row.get("entry_date")),
            exit_date=_date(row.get("exit_date")),
            entry_price=_float(row.get("entry_price")),
            exit_price=_float(row.get("exit_price")),
            planned_entry=_float(row.get("planned_entry")),
            stop_loss=_float(row.get("stop_loss")),
            max_price_after_entry=_float(row.get("max_price_after_entry") or row.get("max_price")),
            min_price_after_entry=_float(row.get("min_price_after_entry") or row.get("min_price")),
            days_held=int(_float(row.get("days_held"))),
            volume_ratio=_float(row.get("volume_ratio")) or 1.0,
            liquidity_score=_float(row.get("liquidity_score")) or 50.0,
            sector_return=_float(row.get("sector_return")),
            market_return=_float(row.get("market_return")),
            entry_delay_days=int(_float(row.get("entry_delay_days"))),
            slippage_bps=_float(row.get("slippage_bps")),
            notes=str(row.get("notes", "")).strip(),
        )

    @property
    def realized_return(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return self.exit_price / self.entry_price - 1.0

    @property
    def max_favorable_return(self) -> float:
        if self.entry_price <= 0 or self.max_price_after_entry <= 0:
            return 0.0
        return self.max_price_after_entry / self.entry_price - 1.0

    @property
    def max_adverse_return(self) -> float:
        if self.entry_price <= 0 or self.min_price_after_entry <= 0:
            return 0.0
        return self.min_price_after_entry / self.entry_price - 1.0


@dataclass(frozen=True)
class MissedCandidate:
    symbol: str
    name: str = ""
    industry: str = ""
    setup: str = ""
    regime: str = ""
    ranking_probability: float = 0.0
    close_on_signal: float = 0.0
    max_price_next_10d: float = 0.0
    sector_return: float = 0.0
    liquidity_score: float = 50.0
    reason_not_taken: str = ""

    @property
    def missed_return(self) -> float:
        if self.close_on_signal <= 0:
            return 0.0
        return self.max_price_next_10d / self.close_on_signal - 1.0


@dataclass(frozen=True)
class ReviewFinding:
    code: str
    severity: str
    message: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewedTrade:
    trade: TradeRecord
    outcome: str
    pnl_pct: float
    findings: tuple[ReviewFinding, ...]


@dataclass(frozen=True)
class SetupStats:
    setup: str
    trades: int
    wins: int
    win_rate: float
    average_return: float
    payoff_ratio: float
    alert: str = ""


@dataclass(frozen=True)
class TradeReviewReport:
    report_date: date | None
    reviewed_trades: tuple[ReviewedTrade, ...]
    setup_stats: tuple[SetupStats, ...]
    regime_stats: Mapping[str, SetupStats]
    missed_runners: tuple[ReviewFinding, ...] = ()
    alpha_decay_alerts: tuple[ReviewFinding, ...] = ()
    market_behavior_shifts: tuple[ReviewFinding, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


def ranking_snapshot(ranking_result: object) -> dict[str, Any]:
    stock = getattr(ranking_result, "stock", None)
    setup = getattr(ranking_result, "setup", "")
    if hasattr(setup, "value"):
        setup = setup.value
    return {
        "symbol": getattr(stock, "symbol", ""),
        "name": getattr(stock, "name", ""),
        "industry": getattr(stock, "industry", ""),
        "setup": str(setup),
        "ranking_probability": _float(getattr(ranking_result, "probability", 0.0)),
        "ranking_confidence": _float(getattr(ranking_result, "confidence", 0.0)),
    }


def regime_text(regime: object | None) -> str:
    if regime is None:
        return ""
    value = getattr(regime, "regime", regime)
    if hasattr(value, "value"):
        value = value.value
    return str(value)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
