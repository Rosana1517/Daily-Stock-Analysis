from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class NewsItem:
    date: date
    title: str
    source: str
    body: str
    industries: tuple[str, ...]


@dataclass(frozen=True)
class IndustrySignal:
    industry: str
    score: float
    catalysts: tuple[str, ...]
    evidence_count: int


@dataclass(frozen=True)
class StockSnapshot:
    symbol: str
    name: str
    industry: str
    price: float
    price_20d_ago: float
    volume: float
    avg_volume_20d: float
    revenue_growth_yoy: float
    gross_margin: float
    operating_margin: float
    free_cash_flow_margin: float
    debt_to_equity: float
    pe_ratio: float
    notes: str = ""


@dataclass(frozen=True)
class PriceBar:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


@dataclass(frozen=True)
class CandlestickSignal:
    symbol: str
    bias: str
    score_adjustment: float
    patterns: tuple[str, ...]
    entry: str
    stop_loss: str
    exit: str
    risk_reward: Optional[float] = None
    structure_bias: str = "neutral"


@dataclass(frozen=True)
class StockRecommendation:
    stock: StockSnapshot
    score: float
    rating: str
    reasons: tuple[str, ...]
    risks: tuple[str, ...] = field(default_factory=tuple)
    entry_plan: str = ""
    stop_loss: str = ""
    exit_plan: str = ""
    freshness_score: float = 0.0
    change_score: float = 0.0
    score_delta: Optional[float] = None
    rank_delta: Optional[int] = None
    status: str = "續抱/續觀察"


@dataclass(frozen=True)
class ChangeSummary:
    new_symbols: tuple[str, ...] = ()
    removed_symbols: tuple[str, ...] = ()
    improved_symbols: tuple[str, ...] = ()
    weakened_symbols: tuple[str, ...] = ()
    industry_new: tuple[str, ...] = ()
    industry_removed: tuple[str, ...] = ()
