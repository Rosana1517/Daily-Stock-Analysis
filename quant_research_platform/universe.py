from __future__ import annotations

import csv
import math
from pathlib import Path

from quant_research_platform.data import load_csv_ohlcv
from stock_signal_system.data.csv_sources import load_news


def select_candidate_symbols(
    universe_path: Path | None,
    fallback_symbols: tuple[str, ...],
    limit: int,
    news_path: Path | None = None,
    ohlcv_path: Path | None = None,
) -> tuple[str, ...]:
    if not universe_path or not universe_path.exists():
        return fallback_symbols[:limit] if limit > 0 else fallback_symbols
    rows = _load_universe_rows(universe_path)
    if not rows:
        return fallback_symbols[:limit] if limit > 0 else fallback_symbols
    news_terms = _news_terms(news_path)
    bars_by_symbol = _load_price_bars(ohlcv_path)
    ranked = _rank_candidate_rows(rows, news_terms, bars_by_symbol)
    symbols = [_platform_symbol(row) for row in ranked if _platform_symbol(row)]
    unique = []
    for symbol in symbols:
        if symbol not in unique:
            unique.append(symbol)
        if limit > 0 and len(unique) >= limit:
            break
    return tuple(unique or fallback_symbols[:limit])


def _load_price_bars(path: Path | None) -> dict[str, list]:
    if not path or not path.exists():
        return {}
    try:
        return load_csv_ohlcv(path)
    except OSError:
        return {}


def _rank_candidate_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
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
    ranked_source = filtered or rows
    return sorted(
        ranked_source,
        key=lambda row: (
            float(_margin_change_5d(row) or 0.0),
            100.0 - (_stochastic_k_value(_bars_for_row(row, bars_by_symbol)) or 100.0),
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
