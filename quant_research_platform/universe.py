"""Public candidate-universe selection API: loads the raw universe CSV,
ranks rows by the chip-breakout / revised-platform / legacy strategies
(implemented in universe_strategies.py, geometry in
universe_platform_geometry.py), and returns the selected symbol plan.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from quant_research_platform.data import load_csv_ohlcv
from quant_research_platform.universe_platform_geometry import (  # noqa: F401 (re-exported for tests/backtests)
    _platform_box_range,
    _platform_breakout_strength,
    platform_measured_move_target,
    platform_neckline_price,
)
from quant_research_platform.universe_strategies import (  # noqa: F401 (re-exported for tests/backtests)
    _bars_for_row,
    _breaks_platform_consolidation,
    _chip_breakout_score,
    _chip_radar_score,
    _is_ma20_rising,
    _passes_chip_breakout_strategy,
    _passes_chip_confirmation_strategy,
    _passes_chip_radar_strategy,
    _passes_revised_strategy,
    _platform_symbol,
    _stochastic_k_value,
    passes_chip_breakout,
)
from stock_signal_system.data.csv_sources import load_news
from stock_signal_system.data.regulatory_flags import load_regulatory_flag_symbols

__all__ = [
    "CandidateSelectionPlan",
    "select_candidate_symbols",
    "build_candidate_selection_plan",
    "save_candidate_csv",
    "passes_chip_breakout",
    "platform_neckline_price",
    "platform_measured_move_target",
]


@dataclass(frozen=True)
class CandidateSelectionPlan:
    selected_symbols: tuple[str, ...]
    analysis_symbols: tuple[str, ...]
    chip_radar_symbols: tuple[str, ...]
    chip_breakout_symbols: tuple[str, ...]
    revised_symbols: tuple[str, ...]
    legacy_watch_symbols: tuple[str, ...]
    legacy_pool_symbols: tuple[str, ...]


def select_candidate_symbols(
    universe_path: Path | None,
    fallback_symbols: tuple[str, ...],
    limit: int,
    news_path: Path | None = None,
    ohlcv_path: Path | None = None,
    market_bullish: bool = True,
) -> tuple[str, ...]:
    plan = build_candidate_selection_plan(universe_path, fallback_symbols, limit, news_path, ohlcv_path, market_bullish)
    return plan.selected_symbols


def build_candidate_selection_plan(
    universe_path: Path | None,
    fallback_symbols: tuple[str, ...],
    limit: int,
    news_path: Path | None = None,
    ohlcv_path: Path | None = None,
    market_bullish: bool = True,
) -> CandidateSelectionPlan:
    if not universe_path or not universe_path.exists():
        selected = fallback_symbols[:limit] if limit > 0 else fallback_symbols
        return CandidateSelectionPlan(selected, selected, (), (), (), selected, selected)
    rows = _load_universe_rows(universe_path)
    if not rows:
        selected = fallback_symbols[:limit] if limit > 0 else fallback_symbols
        return CandidateSelectionPlan(selected, selected, (), (), (), selected, selected)
    news_terms = _news_terms(news_path)
    bars_by_symbol = _load_price_bars(ohlcv_path)
    margin_ready = [row for row in rows if _margin_change_5d(row) is not None]
    margin_top_100 = {
        str(row.get("symbol", "")).strip().upper()
        for row in sorted(margin_ready, key=lambda row: float(_margin_change_5d(row) or 0.0), reverse=True)[:100]
        if float(_margin_change_5d(row) or 0.0) > 0
    }
    chip_radar_rows = _rank_chip_radar_rows(rows, news_terms, bars_by_symbol)
    chip_rows = [
        row
        for row in chip_radar_rows
        if _passes_chip_confirmation_strategy(
            row,
            bars_by_symbol,
            require_margin=bool(margin_ready),
            margin_top_100=margin_top_100,
        )
    ]
    legacy_ranked_rows = _rank_legacy_rows(rows, news_terms)
    legacy_pool_rows = legacy_ranked_rows[:limit] if limit > 0 else legacy_ranked_rows
    chip_watch_rows = [row for row in chip_radar_rows if row not in chip_rows]
    mother_symbols = {
        str(row.get("symbol", "")).strip().upper()
        for row in legacy_ranked_rows
    } | {
        str(row.get("symbol", "")).strip().upper()
        for row in chip_radar_rows
    }
    # Pure technical breakouts (no institutional chip confirmation) are gated
    # off when TAIEX is below its 20-day MA: false-breakout rate rises sharply
    # in a downtrend. Chip-confirmed breakouts (real capital flow behind them)
    # are left untouched since they carry independent evidence.
    revised_rows = (
        _rank_revised_rows(
            [row for row in rows if str(row.get("symbol", "")).strip().upper() in mother_symbols],
            news_terms,
            bars_by_symbol,
        )
        if market_bullish
        else []
    )
    radar_symbols = {
        str(row.get("symbol", "")).strip().upper()
        for row in chip_radar_rows
    }
    legacy_rows = [
        row
        for row in legacy_ranked_rows
        if str(row.get("symbol", "")).strip().upper() not in radar_symbols
    ]
    selected_symbols: list[str] = []
    analysis_symbols: list[str] = []
    chip_radar_symbols: list[str] = []
    chip_breakout_symbols: list[str] = []
    revised_symbols: list[str] = []
    legacy_watch_symbols: list[str] = []
    legacy_pool_symbols: list[str] = []

    def add_symbols(source_rows: list[dict], target: list[str]) -> None:
        for row in source_rows:
            symbol = _platform_symbol(row)
            if not symbol or symbol in selected_symbols:
                continue
            selected_symbols.append(symbol)
            target.append(symbol)
            if limit > 0 and len(selected_symbols) >= limit:
                break

    add_symbols(chip_rows, chip_breakout_symbols)
    if limit <= 0 or len(selected_symbols) < limit:
        add_symbols(revised_rows, revised_symbols)
    if limit <= 0 or len(selected_symbols) < limit:
        add_symbols(chip_watch_rows, chip_radar_symbols)
    if limit <= 0 or len(selected_symbols) < limit:
        add_symbols(legacy_rows, legacy_watch_symbols)

    for row in chip_radar_rows:
        symbol = _platform_symbol(row)
        if symbol and symbol not in chip_radar_symbols:
            chip_radar_symbols.append(symbol)
    for row in revised_rows:
        symbol = _platform_symbol(row)
        if symbol and symbol not in revised_symbols:
            revised_symbols.append(symbol)

    for row in legacy_pool_rows:
        symbol = _platform_symbol(row)
        if not symbol or symbol in legacy_pool_symbols:
            continue
        legacy_pool_symbols.append(symbol)
        if limit > 0 and len(legacy_pool_symbols) >= limit:
            break

    for symbol in (*legacy_pool_symbols, *chip_radar_symbols, *revised_symbols):
        if symbol and symbol not in analysis_symbols:
            analysis_symbols.append(symbol)

    if not selected_symbols:
        selected_symbols = list(fallback_symbols[:limit] if limit > 0 else fallback_symbols)
        legacy_watch_symbols = list(selected_symbols)
        legacy_pool_symbols = list(selected_symbols)
        analysis_symbols = list(selected_symbols)

    return CandidateSelectionPlan(
        tuple(selected_symbols),
        tuple(analysis_symbols),
        tuple(chip_radar_symbols),
        tuple(chip_breakout_symbols),
        tuple(revised_symbols),
        tuple(legacy_watch_symbols),
        tuple(legacy_pool_symbols),
    )


def _load_price_bars(path: Path | None) -> dict[str, list]:
    if not path or not path.exists():
        return {}
    try:
        return load_csv_ohlcv(path)
    except OSError:
        return {}


def _rank_revised_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
    filtered = [
        row
        for row in rows
        if _passes_revised_strategy(row, bars_by_symbol, require_margin=False, margin_top_100=set())
    ]
    return sorted(
        filtered,
        key=lambda row: (
            _platform_breakout_strength(_bars_for_row(row, bars_by_symbol)),
            100.0 - (_stochastic_k_value(_bars_for_row(row, bars_by_symbol)) or 100.0),
            _candidate_score(row, news_terms),
        ),
        reverse=True,
    )


def _rank_legacy_rows(rows: list[dict], news_terms: set[str]) -> list[dict]:
    return sorted(rows, key=lambda row: _candidate_score(row, news_terms), reverse=True)


def _rank_chip_breakout_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
    filtered = [row for row in rows if _passes_chip_breakout_strategy(row, bars_by_symbol)]
    return sorted(
        filtered,
        key=lambda row: (
            _chip_breakout_score(row, bars_by_symbol),
            _candidate_score(row, news_terms),
        ),
        reverse=True,
    )


def _rank_candidate_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
    chip_rows = _rank_chip_breakout_rows(rows, news_terms, bars_by_symbol)
    if chip_rows:
        return chip_rows
    revised_rows = _rank_revised_rows(rows, news_terms, bars_by_symbol)
    return revised_rows or _rank_legacy_rows(rows, news_terms)


def _rank_chip_radar_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
    filtered = [row for row in rows if _passes_chip_radar_strategy(row)]
    return sorted(
        filtered,
        key=lambda row: (
            _chip_radar_score(row),
            _platform_breakout_strength(_bars_for_row(row, bars_by_symbol)),
            _candidate_score(row, news_terms),
        ),
        reverse=True,
    )


def save_candidate_csv(path: Path, symbols: tuple[str, ...]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rank", "symbol"])
        writer.writeheader()
        for rank, symbol in enumerate(symbols, start=1):
            writer.writerow({"rank": rank, "symbol": symbol})
    return path


# Hard filters for the short-swing strategy: real liquidity plus a floor that
# keeps out penny stocks. No upper price cap — high-price stocks are allowed
# in and labeled by price tier (低/中/高價位) instead.
MIN_UNIVERSE_PRICE = 10.0
MIN_AVG_DAILY_TURNOVER_TWD = 50_000_000.0


def _load_universe_rows(path: Path) -> list[dict]:
    flagged = load_regulatory_flag_symbols(path.parent / "tw_regulatory_flags.csv")
    excluded_regulatory = 0
    excluded_price_band = 0
    excluded_turnover = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            price = _float(row.get("price"))
            volume = _float(row.get("volume"))
            if price <= 0 or volume <= 0:
                continue
            symbol = str(row.get("symbol", "")).strip()
            if flagged.get(symbol):
                excluded_regulatory += 1
                continue
            if price < MIN_UNIVERSE_PRICE:
                excluded_price_band += 1
                continue
            avg_volume = _float(row.get("avg_volume_20d")) or volume
            if price * avg_volume < MIN_AVG_DAILY_TURNOVER_TWD:
                excluded_turnover += 1
                continue
            rows.append(row)
    print(
        "universe_filter_excluded"
        f" regulatory={excluded_regulatory} price_band={excluded_price_band}"
        f" turnover={excluded_turnover} kept={len(rows)}",
        flush=True,
    )
    return rows


def _candidate_score(row: dict, news_terms: set[str]) -> float:
    price = _float(row.get("price"))
    volume = max(_float(row.get("volume")), _float(row.get("avg_volume_20d")))
    revenue_growth = _float(row.get("revenue_growth_yoy"))
    pe_ratio = _float(row.get("pe_ratio"))
    industry = str(row.get("industry", "")).lower()
    # Legacy heuristics stay only as tie-break support after the revised filters:
    # keep liquidity and basic quality, but avoid letting price buckets dominate.
    score = math.log10(max(volume, 1.0)) * 10
    score += _price_bucket_score(price) * 0.25
    score += max(min(revenue_growth, 80), -40) * 0.08
    score += 4 if 0 < pe_ratio <= 35 else 0
    score += 10 if any(term and term in industry for term in news_terms) else 0
    return score


def _margin_change_5d(row: dict) -> float | None:
    for key in (
        "margin_financing_change_5d",
        "margin_change_5d",
        "margin_5d_change",
        "five_day_margin_financing_change",
        "five_day_margin_change",
    ):
        value = str(row.get(key, "")).strip()
        if value:
            return _float(value)
    return None


def _price_bucket_score(price: float) -> float:
    if price < 30:
        return 10
    if price <= 100:
        return 8
    if price <= 200:
        return 4
    if price <= 500:
        return 1
    return -2


def _news_terms(news_path: Path | None) -> set[str]:
    if not news_path or not news_path.exists():
        return set()
    terms = set()
    for item in load_news(news_path):
        for industry in item.industries:
            text = industry.strip().lower()
            if text:
                terms.add(text)
    return terms


def _float(value) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except ValueError:
        return 0.0
