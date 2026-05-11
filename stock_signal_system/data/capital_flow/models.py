from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping


@dataclass(frozen=True)
class CapitalFlowRecord:
    symbol: str
    name: str
    industry: str
    price: float
    volume: float
    avg_volume_20d: float
    foreign_net_buy: float = 0.0
    investment_trust_net_buy: float = 0.0
    dealer_net_buy: float = 0.0
    margin_financing_change: float = 0.0
    short_interest_change: float = 0.0
    etf_flow: float = 0.0
    free_float_shares: float = 0.0
    previous_volume: float = 0.0
    realtime_volume: float = 0.0

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "CapitalFlowRecord":
        return cls(
            symbol=str(row.get("symbol", "")).strip(),
            name=str(row.get("name", "")).strip(),
            industry=str(row.get("industry", "")).strip() or "未分類",
            price=_float(row.get("price") or row.get("close")),
            volume=_float(row.get("volume")),
            avg_volume_20d=_float(row.get("avg_volume_20d") or row.get("average_volume")),
            foreign_net_buy=_float(row.get("foreign_net_buy")),
            investment_trust_net_buy=_float(row.get("investment_trust_net_buy") or row.get("trust_net_buy")),
            dealer_net_buy=_float(row.get("dealer_net_buy")),
            margin_financing_change=_float(row.get("margin_financing_change") or row.get("margin_change")),
            short_interest_change=_float(row.get("short_interest_change") or row.get("short_change")),
            etf_flow=_float(row.get("etf_flow")),
            free_float_shares=_float(row.get("free_float_shares")),
            previous_volume=_float(row.get("previous_volume")),
            realtime_volume=_float(row.get("realtime_volume")),
        )

    @property
    def turnover_value(self) -> float:
        return self.price * self.volume

    @property
    def volume_ratio(self) -> float:
        if self.avg_volume_20d <= 0:
            return 1.0
        return self.volume / self.avg_volume_20d


@dataclass(frozen=True)
class FlowSignal:
    name: str
    score: float
    evidence: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapitalFlowResult:
    record: CapitalFlowRecord
    capital_flow_score: float
    accumulation_score: float
    speculative_activity_score: float
    institutional_conviction_score: float
    sector_rotation_score: float
    signals: Mapping[str, FlowSignal]
    labels: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_row(self) -> dict[str, str]:
        return {
            "symbol": self.record.symbol,
            "name": self.record.name,
            "industry": self.record.industry,
            "capital_flow_score": f"{self.capital_flow_score:.1f}",
            "accumulation_score": f"{self.accumulation_score:.1f}",
            "speculative_activity_score": f"{self.speculative_activity_score:.1f}",
            "institutional_conviction_score": f"{self.institutional_conviction_score:.1f}",
            "sector_rotation_score": f"{self.sector_rotation_score:.1f}",
            "labels": ";".join(self.labels),
            "warnings": ";".join(self.warnings),
        }


@dataclass(frozen=True)
class CapitalFlowReport:
    report_date: date | None
    results: tuple[CapitalFlowResult, ...]
    top_accumulation_candidates: tuple[CapitalFlowResult, ...]
    hidden_accumulation_candidates: tuple[CapitalFlowResult, ...]
    early_momentum_candidates: tuple[CapitalFlowResult, ...]
    speculative_overheating_warnings: tuple[CapitalFlowResult, ...]
    sector_scores: Mapping[str, float] = field(default_factory=dict)


def clamp_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def flow_intensity(amount: float, record: CapitalFlowRecord, scale: float = 0.12) -> float:
    denominator = max(record.turnover_value * scale, 10_000_000.0)
    return amount / denominator


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
