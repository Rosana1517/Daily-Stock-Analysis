from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from stock_signal_system.models import NewsItem, PriceBar, StockSnapshot


def load_news(path: Path) -> list[NewsItem]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [
            NewsItem(
                date=date.fromisoformat(row["date"]),
                title=row["title"].strip(),
                source=row["source"].strip(),
                body=row["body"].strip(),
                industries=tuple(_split_industries(row.get("industries", ""))),
            )
            for row in csv.DictReader(f)
        ]


def load_stocks(path: Path) -> list[StockSnapshot]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [
            StockSnapshot(
                symbol=row["symbol"].strip(),
                name=row["name"].strip(),
                industry=row["industry"].strip(),
                price=float(row["price"]),
                price_20d_ago=float(row["price_20d_ago"]),
                volume=float(row["volume"]),
                avg_volume_20d=float(row["avg_volume_20d"]),
                revenue_growth_yoy=float(row["revenue_growth_yoy"]),
                gross_margin=float(row["gross_margin"]),
                operating_margin=float(row["operating_margin"]),
                free_cash_flow_margin=float(row["free_cash_flow_margin"]),
                debt_to_equity=float(row["debt_to_equity"]),
                pe_ratio=float(row["pe_ratio"]),
                notes=row.get("notes", "").strip(),
            )
            for row in csv.DictReader(f)
        ]


def load_price_history(path: Path) -> dict[str, list[PriceBar]]:
    history: dict[str, list[PriceBar]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            bar = PriceBar(
                symbol=row["symbol"].strip(),
                date=date.fromisoformat(row["date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume") or 0),
            )
            history.setdefault(bar.symbol, []).append(bar)
    for symbol in history:
        history[symbol] = sorted(history[symbol], key=lambda item: item.date)
    return history


def load_intraday_history(path: Path) -> dict[str, list[PriceBar]]:
    history: dict[str, list[PriceBar]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            raw_time = row.get("datetime") or row.get("date")
            if not raw_time:
                raise ValueError("intraday CSV requires a datetime column")
            bar = PriceBar(
                symbol=row["symbol"].strip(),
                date=_parse_date_or_datetime(raw_time),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume") or 0),
            )
            history.setdefault(bar.symbol, []).append(bar)
    for symbol in history:
        history[symbol] = sorted(history[symbol], key=lambda item: item.date)
    return history


def _split_industries(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def _parse_date_or_datetime(value: str):
    value = value.strip()
    if " " in value or "T" in value:
        return datetime.fromisoformat(value.replace("T", " "))
    return date.fromisoformat(value)
