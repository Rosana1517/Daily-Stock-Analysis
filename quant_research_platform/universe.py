from __future__ import annotations

import csv
import math
from pathlib import Path

from stock_signal_system.data.csv_sources import load_news


def select_candidate_symbols(
    universe_path: Path | None,
    fallback_symbols: tuple[str, ...],
    limit: int,
    news_path: Path | None = None,
) -> tuple[str, ...]:
    if not universe_path or not universe_path.exists():
        return fallback_symbols[:limit] if limit > 0 else fallback_symbols
    rows = _load_universe_rows(universe_path)
    if not rows:
        return fallback_symbols[:limit] if limit > 0 else fallback_symbols
    news_terms = _news_terms(news_path)
    ranked = sorted(rows, key=lambda row: _candidate_score(row, news_terms), reverse=True)
    symbols = [_platform_symbol(row) for row in ranked if _platform_symbol(row)]
    unique = []
    for symbol in symbols:
        if symbol not in unique:
            unique.append(symbol)
        if limit > 0 and len(unique) >= limit:
            break
    return tuple(unique or fallback_symbols[:limit])


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
    score = math.log10(max(volume, 1.0)) * 8
    score += _price_bucket_score(price)
    score += max(min(revenue_growth, 80), -40) * 0.08
    score += 4 if 0 < pe_ratio <= 35 else 0
    score += 10 if any(term and term in industry for term in news_terms) else 0
    return score


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
