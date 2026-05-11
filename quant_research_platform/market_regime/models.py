from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Mapping, Sequence


class RegimeCategory(str, Enum):
    AI_MOMENTUM_EXPANSION = "AI momentum expansion"
    LARGE_CAP_ACCUMULATION = "large-cap accumulation"
    SMALL_CAP_SPECULATION = "small-cap speculation"
    DEFENSIVE_ROTATION = "defensive rotation"
    HIGH_VOLATILITY_RISK_OFF = "high-volatility risk-off"
    BREAKOUT_TREND_MARKET = "breakout trend market"
    MEAN_REVERSION_MARKET = "mean-reversion market"
    LIQUIDITY_CONTRACTION = "liquidity contraction"


@dataclass(frozen=True)
class SignalScore:
    name: str
    value: float
    weight: float = 1.0
    evidence: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def contribution(self) -> float:
        return self.value * self.weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "weight": self.weight,
            "evidence": list(self.evidence),
            "missing": list(self.missing),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SignalScore":
        return cls(
            name=str(payload["name"]),
            value=float(payload["value"]),
            weight=float(payload.get("weight", 1.0)),
            evidence=tuple(str(item) for item in payload.get("evidence", ())),
            missing=tuple(str(item) for item in payload.get("missing", ())),
        )


@dataclass(frozen=True)
class MarketRegimeInput:
    report_date: date
    stock_rows: Sequence[Mapping[str, Any]] = ()
    prices_by_symbol: Mapping[str, Sequence[Any]] = field(default_factory=dict)
    sector_news_scores: Mapping[str, float] = field(default_factory=dict)
    foreign_flow: Mapping[str, float] = field(default_factory=dict)
    investment_trust_flow: Mapping[str, float] = field(default_factory=dict)
    dealer_flow: Mapping[str, float] = field(default_factory=dict)
    margin_financing: Mapping[str, float] = field(default_factory=dict)
    short_covering: Mapping[str, float] = field(default_factory=dict)
    etf_flow: Mapping[str, float] = field(default_factory=dict)
    benchmark_symbol: str | None = None
    previous_regime: str | None = None


@dataclass(frozen=True)
class MarketRegimeResult:
    report_date: date
    regime: RegimeCategory
    confidence: float
    explanation: str
    suitable_strategies: tuple[str, ...]
    unsuitable_strategies: tuple[str, ...]
    signal_scores: tuple[SignalScore, ...]
    category_scores: Mapping[str, float]
    transition: str
    previous_regime: RegimeCategory | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date.isoformat(),
            "regime": self.regime.value,
            "confidence": round(self.confidence, 4),
            "explanation": self.explanation,
            "suitable_strategies": list(self.suitable_strategies),
            "unsuitable_strategies": list(self.unsuitable_strategies),
            "signal_scores": [signal.to_dict() for signal in self.signal_scores],
            "category_scores": {key: round(float(value), 4) for key, value in self.category_scores.items()},
            "transition": self.transition,
            "previous_regime": self.previous_regime.value if self.previous_regime else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MarketRegimeResult":
        previous = payload.get("previous_regime")
        return cls(
            report_date=date.fromisoformat(str(payload["report_date"])),
            regime=RegimeCategory(str(payload["regime"])),
            confidence=float(payload["confidence"]),
            explanation=str(payload["explanation"]),
            suitable_strategies=tuple(str(item) for item in payload.get("suitable_strategies", ())),
            unsuitable_strategies=tuple(str(item) for item in payload.get("unsuitable_strategies", ())),
            signal_scores=tuple(SignalScore.from_dict(item) for item in payload.get("signal_scores", ())),
            category_scores={str(key): float(value) for key, value in payload.get("category_scores", {}).items()},
            transition=str(payload.get("transition", "unknown")),
            previous_regime=RegimeCategory(str(previous)) if previous else None,
            metadata=dict(payload.get("metadata", {})),
        )


def clamp_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))
