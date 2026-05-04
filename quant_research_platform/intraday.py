from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from stock_signal_system.data.csv_sources import load_intraday_history
from stock_signal_system.models import PriceBar


TW_OTC_SYMBOLS = {"6488", "5274", "8069", "5347", "3324"}


def load_or_fetch_intraday_history(
    path: Path | None,
    symbols: tuple[str, ...],
    interval: str,
    period: str,
) -> dict[str, list[PriceBar]]:
    history = load_intraday_history(path) if path and path.exists() else {}
    missing = [symbol for symbol in symbols if symbol not in history]
    if not missing:
        return history
    fetched = _fetch_yfinance_intraday(missing, interval, period)
    return {**history, **fetched}


def _fetch_yfinance_intraday(symbols: list[str], interval: str, period: str) -> dict[str, list[PriceBar]]:
    try:
        import yfinance as yf
    except ImportError:
        return {}

    history: dict[str, list[PriceBar]] = {}
    for symbol in symbols:
        yahoo_symbol = _tw_yahoo_symbol(symbol)
        try:
            frame = yf.Ticker(yahoo_symbol).history(period=period, interval=interval, auto_adjust=False).reset_index()
        except Exception:
            continue
        bars = []
        for _, row in frame.iterrows():
            close = row.get("Close")
            if close is None:
                continue
            raw_time = row.get("Datetime") or row.get("Date")
            bars.append(
                PriceBar(
                    symbol=symbol,
                    date=_to_date_or_datetime(raw_time),
                    open=float(row.get("Open") or close),
                    high=float(row.get("High") or close),
                    low=float(row.get("Low") or close),
                    close=float(close),
                    volume=float(row.get("Volume") or 0),
                )
            )
        if bars:
            history[symbol] = sorted(bars, key=lambda item: item.date)
    return history


def _to_date_or_datetime(value) -> date | datetime:
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().replace(tzinfo=None)
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return value
    text = str(value)
    return datetime.fromisoformat(text.replace("T", " ")).replace(tzinfo=None)


def _tw_yahoo_symbol(symbol: str) -> str:
    value = symbol.upper().strip()
    if "." in value:
        return value
    if len(value) == 4 and value.isdigit():
        if value in TW_OTC_SYMBOLS:
            return f"{value}.TWO"
        return f"{value}.TW"
    return value
