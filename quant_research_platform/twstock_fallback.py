from __future__ import annotations

import time
from datetime import datetime
from typing import Iterable

from quant_research_platform.twse_realtime import TwseRealtimeQuote, normalize_channel


def fetch_twstock_realtime_quotes(
    symbols: Iterable[str],
    max_symbols: int = 15,
    sleep_seconds: float = 1.8,
) -> list[TwseRealtimeQuote]:
    """Low-frequency realtime fallback backed by twstock.

    twstock uses TWSE/TPEx data underneath, so this should only be used for a small
    missing subset after the primary batch APIs fail or return incomplete rows.
    """
    clean_symbols = _dedupe_symbols(symbols)[: max(0, max_symbols)]
    if not clean_symbols:
        return []
    try:
        import twstock
    except ImportError:
        return []
    try:
        payload = twstock.realtime.get(clean_symbols if len(clean_symbols) > 1 else clean_symbols[0])
    except Exception:
        return []
    finally:
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return _parse_twstock_payload(payload)


def _dedupe_symbols(symbols: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    clean: list[str] = []
    for value in symbols:
        symbol = _bare_symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            clean.append(symbol)
    return clean


def _bare_symbol(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "_" in text and text.lower().endswith(".tw"):
        return text[:-3].split("_", 1)[1]
    if ":" in text:
        return text.split(":", 1)[1]
    if "." in text:
        return text.split(".", 1)[0]
    return text


def _parse_twstock_payload(payload) -> list[TwseRealtimeQuote]:
    rows = []
    if isinstance(payload, dict) and "realtime" in payload:
        rows = [payload]
    elif isinstance(payload, dict):
        rows = [row for row in payload.values() if isinstance(row, dict)]
    elif isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
    return [quote for row in rows if (quote := _parse_twstock_row(row)) is not None]


def _parse_twstock_row(row: dict) -> TwseRealtimeQuote | None:
    info = row.get("info") or {}
    realtime = row.get("realtime") or {}
    symbol = str(info.get("code") or row.get("code") or "").strip()
    if not symbol:
        return None
    price = _first_float(
        realtime.get("latest_trade_price"),
        realtime.get("best_bid_price"),
        realtime.get("best_ask_price"),
    )
    previous_close = _to_float(realtime.get("open")) or price
    if price <= 0:
        return None
    channel = str(info.get("channel") or normalize_channel(symbol))
    market = "otc" if channel.lower().startswith("otc_") else "tse"
    return TwseRealtimeQuote(
        symbol=symbol,
        market=market,
        name=str(info.get("name") or "").strip(),
        timestamp=_parse_twstock_time(row.get("timestamp")),
        open=_to_float(realtime.get("open")),
        high=_to_float(realtime.get("high")),
        low=_to_float(realtime.get("low")),
        price=price,
        previous_close=previous_close,
        volume=_to_float(realtime.get("accumulate_trade_volume") or realtime.get("trade_volume")),
        raw_channel=channel,
    )


def _parse_twstock_time(value) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            pass
    return datetime.now()


def _first_float(*values) -> float:
    for value in values:
        number = _to_float(value)
        if number > 0:
            return number
    return 0.0


def _to_float(value) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"-", "--", "N/A", "NaN"}:
        return 0.0
    if "_" in text:
        text = text.split("_", 1)[0]
    try:
        return float(text)
    except ValueError:
        return 0.0
