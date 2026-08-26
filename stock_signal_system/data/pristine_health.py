"""璞玉健康指標: re-derives the publicly-disclosed 臺灣璞玉指數 (IX0231)
screening rule from FinMind fundamentals, instead of needing the index
provider's proprietary 331-stock membership list (confirmed not public — see
PRD.md P4). Official rule, per TIP's own index factsheet: 最近3年及最近4季
EPS皆為正、最近3年皆有發放股利、排除成交量/週轉率/漲幅/波動度前10%過熱股
(the crowding filter already exists in this codebase via _price_tier /
universe.py's turnover floor and is applied separately, not here).

This module intentionally does NOT compute the full weighted "璞玉評分"
formula the methodology also describes (30% 估值 + 30% 成長性 + 20% 產業地位
/AI含金量 + 10% ROE現金流 + 10% 市場非擁擠度). The 20% industry/AI-content
term and the 10% market-crowding percentile both require data this project
doesn't have (subjective industry tagging, a full-market percentile rank) —
faking those with placeholder numbers would be false precision. Instead this
module surfaces the fully-computable pieces (EPS/dividend screen, ROE, debt
ratio, a PE-based valuation read) as an honest subset, documented as such."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class StockFundamentals:
    symbol: str
    quarterly_eps: tuple[float, ...] = field(default_factory=tuple)  # newest first
    annual_eps: dict = field(default_factory=dict)  # year(int) -> summed EPS that year
    dividend_years: frozenset = field(default_factory=frozenset)  # years with any cash/stock dividend > 0
    equity: float | None = None
    liabilities: float | None = None
    total_assets: float | None = None
    ttm_net_income: float | None = None  # trailing-twelve-month net income, for ROE
    pe_ratio: float | None = None


@dataclass(frozen=True)
class PristineScreenResult:
    passes: bool
    reasons: tuple[str, ...]  # failure reasons; empty when passes is True


REQUIRED_CONSECUTIVE_YEARS = 3
REQUIRED_CONSECUTIVE_QUARTERS = 4
PE_UPPER_BOUND = 20.0
PE_SWEET_SPOT_LOW = 10.0
PE_SWEET_SPOT_HIGH = 15.0
ROE_HEALTHY_THRESHOLD_PCT = 10.0


def evaluate_pristine_screen(fundamentals: StockFundamentals) -> PristineScreenResult:
    """The official hard filter: 3 consecutive years + the latest 4 quarters
    of EPS all positive, and a dividend paid in each of those 3 years."""
    reasons: list[str] = []

    recent_quarters = fundamentals.quarterly_eps[:REQUIRED_CONSECUTIVE_QUARTERS]
    if len(recent_quarters) < REQUIRED_CONSECUTIVE_QUARTERS or any(eps <= 0 for eps in recent_quarters):
        reasons.append(f"最近{REQUIRED_CONSECUTIVE_QUARTERS}季EPS未全數為正")

    recent_years = sorted(fundamentals.annual_eps.keys(), reverse=True)[:REQUIRED_CONSECUTIVE_YEARS]
    if len(recent_years) < REQUIRED_CONSECUTIVE_YEARS or any(fundamentals.annual_eps[year] <= 0 for year in recent_years):
        reasons.append(f"最近{REQUIRED_CONSECUTIVE_YEARS}年EPS未全數為正")
    elif any(year not in fundamentals.dividend_years for year in recent_years):
        reasons.append(f"最近{REQUIRED_CONSECUTIVE_YEARS}年未皆配息")

    return PristineScreenResult(passes=not reasons, reasons=tuple(reasons))


def compute_roe_pct(fundamentals: StockFundamentals) -> float | None:
    if fundamentals.ttm_net_income is None or not fundamentals.equity:
        return None
    return fundamentals.ttm_net_income / fundamentals.equity * 100.0


def compute_debt_ratio_pct(fundamentals: StockFundamentals) -> float | None:
    if fundamentals.liabilities is None or not fundamentals.total_assets:
        return None
    return fundamentals.liabilities / fundamentals.total_assets * 100.0


def describe_valuation(pe_ratio: float | None) -> str:
    """PE-based read only — the 30% "估值" weight in the full formula; the
    other four weighted terms are not computed by this module (see module
    docstring)."""
    if pe_ratio is None or pe_ratio <= 0:
        return "本益比資料暫缺"
    if PE_SWEET_SPOT_LOW <= pe_ratio <= PE_SWEET_SPOT_HIGH:
        return f"PE {pe_ratio:.1f}，落在建議甜蜜區間(10~15倍)"
    if pe_ratio < PE_UPPER_BOUND:
        return f"PE {pe_ratio:.1f}，低於20倍門檻但高於甜蜜區間"
    return f"PE {pe_ratio:.1f}，超過建議上限(20倍)"


def build_annual_eps(quarterly_rows: list[tuple[str, float]]) -> dict:
    """quarterly_rows: list of (date_str, eps) pairs. Returns {year: summed EPS}."""
    annual: dict = {}
    for date_str, eps in quarterly_rows:
        year = _year_from_date(date_str)
        if year is None:
            continue
        annual[year] = annual.get(year, 0.0) + eps
    return annual


def build_dividend_years(dividend_rows: list[dict]) -> frozenset:
    years = set()
    for row in dividend_rows:
        cash = _to_float(row.get("CashEarningsDistribution"))
        stock = _to_float(row.get("StockEarningsDistribution"))
        if cash <= 0 and stock <= 0:
            continue
        year = _year_from_date(str(row.get("date", "")))
        if year is not None:
            years.add(year)
    return frozenset(years)


def _year_from_date(date_str: str) -> int | None:
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").year
    except (TypeError, ValueError):
        return None


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
