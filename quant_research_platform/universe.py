from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from quant_research_platform.data import load_csv_ohlcv
from stock_signal_system.data.csv_sources import load_news


@dataclass(frozen=True)
class CandidateSelectionPlan:
    selected_symbols: tuple[str, ...]
    chip_breakout_symbols: tuple[str, ...]
    revised_symbols: tuple[str, ...]
    legacy_watch_symbols: tuple[str, ...]


def select_candidate_symbols(
    universe_path: Path | None,
    fallback_symbols: tuple[str, ...],
    limit: int,
    news_path: Path | None = None,
    ohlcv_path: Path | None = None,
) -> tuple[str, ...]:
    plan = build_candidate_selection_plan(universe_path, fallback_symbols, limit, news_path, ohlcv_path)
    return plan.selected_symbols


def build_candidate_selection_plan(
    universe_path: Path | None,
    fallback_symbols: tuple[str, ...],
    limit: int,
    news_path: Path | None = None,
    ohlcv_path: Path | None = None,
) -> CandidateSelectionPlan:
    if not universe_path or not universe_path.exists():
        selected = fallback_symbols[:limit] if limit > 0 else fallback_symbols
        return CandidateSelectionPlan(selected, (), (), selected)
    rows = _load_universe_rows(universe_path)
    if not rows:
        selected = fallback_symbols[:limit] if limit > 0 else fallback_symbols
        return CandidateSelectionPlan(selected, (), (), selected)
    news_terms = _news_terms(news_path)
    bars_by_symbol = _load_price_bars(ohlcv_path)
    chip_rows = _rank_chip_breakout_rows(rows, news_terms, bars_by_symbol)
    revised_rows = _rank_revised_rows(rows, news_terms, bars_by_symbol)
    legacy_rows = _rank_legacy_rows(rows, news_terms)

    selected_symbols: list[str] = []
    chip_breakout_symbols: list[str] = []
    revised_symbols: list[str] = []
    legacy_watch_symbols: list[str] = []

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
        add_symbols(legacy_rows, legacy_watch_symbols)

    if not selected_symbols:
        selected_symbols = list(fallback_symbols[:limit] if limit > 0 else fallback_symbols)
        legacy_watch_symbols = list(selected_symbols)

    return CandidateSelectionPlan(
        tuple(selected_symbols),
        tuple(chip_breakout_symbols),
        tuple(revised_symbols),
        tuple(legacy_watch_symbols),
    )


def _load_price_bars(path: Path | None) -> dict[str, list]:
    if not path or not path.exists():
        return {}
    try:
        return load_csv_ohlcv(path)
    except OSError:
        return {}


def _rank_revised_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
    margin_ready = [row for row in rows if _margin_change_5d(row) is not None]
    margin_top_100 = {
        str(row.get("symbol", "")).strip().upper()
        for row in sorted(margin_ready, key=lambda row: float(_margin_change_5d(row) or 0.0), reverse=True)[:100]
        if float(_margin_change_5d(row) or 0.0) > 0
    }
    filtered = [
        row
        for row in rows
        if _passes_revised_strategy(row, bars_by_symbol, require_margin=bool(margin_ready), margin_top_100=margin_top_100)
    ]
    return sorted(
        filtered,
        key=lambda row: (
            float(_margin_change_5d(row) or 0.0),
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


def save_candidate_csv(path: Path, symbols: tuple[str, ...]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rank", "symbol"])
        writer.writeheader()
        for rank, symbol in enumerate(symbols, start=1):
            writer.writerow({"rank": rank, "symbol": symbol})
    return path


def _load_universe_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            if _float(row.get("price")) > 0 and _float(row.get("volume")) > 0:
                rows.append(row)
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


def _passes_revised_strategy(
    row: dict,
    bars_by_symbol: dict[str, list],
    require_margin: bool,
    margin_top_100: set[str],
) -> bool:
    bars = _bars_for_row(row, bars_by_symbol)
    k_value = _stochastic_k_value(bars)
    if k_value is None or k_value >= 40:
        return False
    if not _is_ma20_rising(bars):
        return False
    if require_margin:
        symbol = str(row.get("symbol", "")).strip().upper()
        return symbol in margin_top_100
    return True


def _passes_chip_breakout_strategy(row: dict, bars_by_symbol: dict[str, list]) -> bool:
    bars = _bars_for_row(row, bars_by_symbol)
    if not _breaks_platform_consolidation(row, bars):
        return False
    if not _top10_main_force_strong(row):
        return False
    return _foreign_buy_streak_days(row) >= 3 or _branch_buy_streak_days(row) >= 2


def _bars_for_row(row: dict, bars_by_symbol: dict[str, list]) -> list:
    symbol = str(row.get("symbol", "")).strip().upper()
    platform_symbol = _platform_symbol(row).upper()
    return bars_by_symbol.get(symbol) or bars_by_symbol.get(platform_symbol) or []


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


def _chip_breakout_score(row: dict, bars_by_symbol: dict[str, list]) -> float:
    bars = _bars_for_row(row, bars_by_symbol)
    breakout_strength = _platform_breakout_strength(bars)
    top10_strength = _top10_main_force_strength(row)
    foreign_streak = min(10.0, _foreign_buy_streak_days(row)) * 6.0
    branch_streak = min(10.0, _branch_buy_streak_days(row)) * 7.0
    return top10_strength + foreign_streak + branch_streak + breakout_strength


def _stochastic_k_value(bars: list) -> float | None:
    if len(bars) < 9:
        return None
    window = bars[-9:]
    highest_high = max(bar.high for bar in window)
    lowest_low = min(bar.low for bar in window)
    if highest_high <= lowest_low:
        return 50.0
    return (window[-1].close - lowest_low) / (highest_high - lowest_low) * 100.0


def _is_ma20_rising(bars: list) -> bool:
    closes = [bar.close for bar in bars if getattr(bar, "close", 0) > 0]
    if len(closes) < 21:
        return False
    latest = sum(closes[-20:]) / 20.0
    previous = sum(closes[-21:-1]) / 20.0
    return latest > previous


def _breaks_platform_consolidation(row: dict, bars: list) -> bool:
    explicit = _bool_flag(
        row,
        "platform_breakout",
        "platform_breakout_flag",
        "breakout_platform",
        "breakout_of_platform",
    )
    if explicit is not None:
        return explicit
    return _platform_breakout_strength(bars) >= 18.0


def _platform_breakout_strength(bars: list) -> float:
    if len(bars) < 21:
        return 0.0
    setup = bars[-21:-1]
    latest = bars[-1]
    base_high = max(bar.high for bar in setup)
    base_low = min(bar.low for bar in setup)
    base_avg = sum(bar.close for bar in setup) / len(setup)
    if base_avg <= 0:
        return 0.0
    compression = (base_high - base_low) / base_avg
    if compression > 0.12:
        return 0.0
    breakout_pct = latest.close / max(base_high, 0.01) - 1.0
    if breakout_pct <= 0.0:
        return 0.0
    average_volume = sum(bar.volume for bar in setup) / len(setup)
    volume_ratio = latest.volume / average_volume if average_volume else 1.0
    if volume_ratio < 1.1:
        return 0.0
    return breakout_pct * 2500.0 + max(0.0, 0.12 - compression) * 250.0 + volume_ratio * 10.0


def _top10_main_force_strong(row: dict) -> bool:
    rank = _optional_float(row, "top10_main_force_buy_rank", "top10_main_force_rank")
    if rank is not None and rank > 0 and rank <= 10:
        return True
    strength = _top10_main_force_strength(row)
    if strength >= 60.0:
        return True
    net_buy = _optional_float(row, "top10_main_force_net_buy", "main_force_top10_net_buy")
    return net_buy is not None and net_buy > 0


def _top10_main_force_strength(row: dict) -> float:
    score = _optional_float(row, "top10_main_force_buy_strength", "top10_main_force_strength")
    if score is None:
        score = _optional_float(row, "top10_main_force_buy_strength_proxy", "institutional_main_force_strength_proxy")
    if score is not None:
        return score
    ratio = _optional_float(
        row,
        "top10_main_force_buy_ratio",
        "top10_main_force_ratio",
        "top10_buy_share_pct",
        "top10_main_force_share_pct",
    )
    if ratio is None:
        return 0.0
    normalized = ratio * 100.0 if abs(ratio) <= 1.0 else ratio
    return max(0.0, min(100.0, normalized * 2.0))


def _foreign_buy_streak_days(row: dict) -> float:
    return _optional_float(row, "foreign_buy_streak_days", "foreign_net_buy_streak_days", "foreign_buy_days") or 0.0


def _branch_buy_streak_days(row: dict) -> float:
    return _optional_float(
        row,
        "branch_main_force_buy_streak_days",
        "branch_main_force_buy_streak_days_proxy",
        "main_broker_buy_streak_days",
        "broker_buy_streak_days",
        "branch_buy_streak_days",
        "dealer_buy_streak_days_proxy",
    ) or 0.0


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


def _platform_symbol(row: dict) -> str:
    symbol = str(row.get("symbol", "")).strip().upper()
    if not symbol:
        return ""
    if "." in symbol:
        return symbol
    market = str(row.get("market", "")).strip().lower()
    if market in {"otc", "tpex", "two"} or "tpex" in str(row.get("notes", "")).lower():
        return f"{symbol}.TWO"
    return f"{symbol}.TW"


def _float(value) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except ValueError:
        return 0.0


def _optional_float(row: dict, *keys: str) -> float | None:
    for key in keys:
        value = str(row.get(key, "")).replace(",", "").strip()
        if not value:
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return None


def _bool_flag(row: dict, *keys: str) -> bool | None:
    truthy = {"1", "true", "yes", "y", "pass", "passed"}
    falsy = {"0", "false", "no", "n", "fail", "failed"}
    for key in keys:
        value = str(row.get(key, "")).strip().lower()
        if not value:
            continue
        if value in truthy:
            return True
        if value in falsy:
            return False
    return None
