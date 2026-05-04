from __future__ import annotations

import csv
import json
import random
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


MIS_STOCK_INFO_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
TWSE_LISTED_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_OTC_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Referer": "https://mis.twse.com.tw/stock/fibest.jsp?lang=zh_tw",
    "X-Requested-With": "XMLHttpRequest",
}


@dataclass(frozen=True)
class TwseRealtimeQuote:
    symbol: str
    market: str
    name: str
    timestamp: datetime
    open: float
    high: float
    low: float
    price: float
    previous_close: float
    volume: float
    raw_channel: str


@dataclass(frozen=True)
class TwseUniverseItem:
    symbol: str
    market: str
    name: str
    channel: str


def poll_realtime_quotes(
    symbols: Iterable[str],
    cache_path: Path,
    interval_seconds: float = 10.0,
    batch_size: int = 75,
    iterations: int | None = None,
    default_market: str = "tse",
    random_sleep_min: float = 0.2,
    random_sleep_max: float = 1.2,
) -> None:
    channels = [normalize_channel(symbol, default_market) for symbol in symbols]
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100.")
    iteration = 0
    while iterations is None or iteration < iterations:
        started_at = time.monotonic()
        for batch in _chunks(channels, batch_size):
            quotes = fetch_realtime_quotes(batch)
            append_quote_cache(cache_path, quotes)
            time.sleep(random.uniform(random_sleep_min, random_sleep_max))
        iteration += 1
        elapsed = time.monotonic() - started_at
        if iterations is None or iteration < iterations:
            time.sleep(max(0.0, interval_seconds - elapsed))


def fetch_full_market_universe(common_stock_only: bool = False) -> list[TwseUniverseItem]:
    listed = _fetch_json(TWSE_LISTED_URL)
    otc = _fetch_json(TPEX_OTC_URL)
    items: list[TwseUniverseItem] = []
    for row in listed:
        symbol = str(row.get("Code") or "").strip()
        name = str(row.get("Name") or "").strip()
        if _keep_symbol(symbol, common_stock_only):
            items.append(TwseUniverseItem(symbol, "tse", name, normalize_channel(f"tse:{symbol}")))
    for row in otc:
        symbol = str(row.get("SecuritiesCompanyCode") or "").strip()
        name = str(row.get("CompanyName") or "").strip()
        if _keep_symbol(symbol, common_stock_only):
            items.append(TwseUniverseItem(symbol, "otc", name, normalize_channel(f"otc:{symbol}")))
    return sorted(items, key=lambda item: (item.market, item.symbol))


def save_universe_csv(path: Path, items: list[TwseUniverseItem]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "market", "name", "channel"])
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "symbol": item.symbol,
                    "market": item.market,
                    "name": item.name,
                    "channel": item.channel,
                }
            )
    return path


def load_universe_channels(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [row["channel"].strip() for row in reader if row.get("channel")]


def fetch_realtime_quotes(channels: Iterable[str]) -> list[TwseRealtimeQuote]:
    channel_list = list(channels)
    if not channel_list:
        return []
    params = {
        "ex_ch": "|".join(channel_list),
        "json": "1",
        "delay": "0",
        "_": str(int(time.time() * 1000)),
    }
    url = f"{MIS_STOCK_INFO_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8-sig")
    raw = json.loads(payload)
    rows = raw.get("msgArray", [])
    return [quote for row in rows if (quote := _parse_quote(row)) is not None]


def append_quote_cache(cache_path: Path, quotes: list[TwseRealtimeQuote]) -> Path:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    exists = cache_path.exists()
    with cache_path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "datetime",
                "symbol",
                "market",
                "name",
                "open",
                "high",
                "low",
                "close",
                "previous_close",
                "volume",
                "raw_channel",
            ],
        )
        if not exists:
            writer.writeheader()
        for quote in quotes:
            writer.writerow(
                {
                    "datetime": quote.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "symbol": quote.symbol,
                    "market": quote.market,
                    "name": quote.name,
                    "open": quote.open,
                    "high": quote.high,
                    "low": quote.low,
                    "close": quote.price,
                    "previous_close": quote.previous_close,
                    "volume": quote.volume,
                    "raw_channel": quote.raw_channel,
                }
            )
    return cache_path


def normalize_channel(value: str, default_market: str = "tse") -> str:
    text = value.strip()
    lowered = text.lower()
    if "_" in text and lowered.endswith(".tw"):
        market, symbol = text[:-3].split("_", 1)
        return f"{market.lower()}_{symbol}.tw"
    if ":" in text:
        market, symbol = text.split(":", 1)
        return f"{market.lower()}_{symbol}.tw"
    if "." in text:
        symbol, market = text.split(".", 1)
        return f"{market.lower()}_{symbol}.tw"
    return f"{default_market.lower()}_{text}.tw"


def _parse_quote(row: dict) -> TwseRealtimeQuote | None:
    symbol = str(row.get("c") or "").strip()
    if not symbol:
        return None
    market = str(row.get("ex") or "").strip()
    timestamp = _parse_datetime(str(row.get("d") or ""), str(row.get("t") or ""))
    price = _first_float(row.get("z"), row.get("a"), row.get("b"), row.get("y"))
    return TwseRealtimeQuote(
        symbol=symbol,
        market=market,
        name=str(row.get("n") or "").strip(),
        timestamp=timestamp,
        open=_to_float(row.get("o")),
        high=_to_float(row.get("h")),
        low=_to_float(row.get("l")),
        price=price,
        previous_close=_to_float(row.get("y")),
        volume=_to_float(row.get("v")),
        raw_channel=str(row.get("ch") or "").strip(),
    )


def _parse_datetime(date_value: str, time_value: str) -> datetime:
    date_text = date_value.strip()
    time_text = time_value.strip()
    if len(date_text) == 8 and len(time_text) >= 8:
        return datetime.strptime(f"{date_text} {time_text[:8]}", "%Y%m%d %H:%M:%S")
    return datetime.now()


def _first_float(*values) -> float:
    for value in values:
        number = _to_float(value)
        if number:
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


def _chunks(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _fetch_json(url: str) -> list[dict]:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _keep_symbol(symbol: str, common_stock_only: bool) -> bool:
    if not symbol:
        return False
    if not common_stock_only:
        return True
    return symbol.isdigit() and len(symbol) == 4 and not symbol.startswith("0")
