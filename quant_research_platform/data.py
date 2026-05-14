from __future__ import annotations

import csv
import json
import os
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def load_csv_ohlcv(path: Path, symbols: Iterable[str] = ()) -> dict[str, list[Bar]]:
    allowed = {symbol.upper() for symbol in symbols}
    grouped: dict[str, list[Bar]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = row["symbol"].strip().upper()
            if allowed and symbol not in allowed:
                continue
            grouped[symbol].append(
                Bar(
                    symbol=symbol,
                    timestamp=_parse_timestamp(row.get("date") or row.get("datetime") or row.get("timestamp") or ""),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                )
            )
    return {symbol: sorted(bars, key=lambda item: item.timestamp) for symbol, bars in grouped.items()}


def fetch_openbb_ohlcv(symbols: Iterable[str], provider: str | None = None, period: str = "1y") -> dict[str, list[Bar]]:
    openbb_home = Path(os.environ.get("QUANT_OPENBB_HOME", ".cache/openbb_home")).resolve()
    openbb_home.mkdir(parents=True, exist_ok=True)
    os.environ["USERPROFILE"] = str(openbb_home)
    try:
        from openbb import obb
    except ImportError as exc:
        raise RuntimeError("OpenBB is not installed. Install it with `pip install openbb`.") from exc

    grouped: dict[str, list[Bar]] = {}
    for symbol in symbols:
        kwargs = {"provider": provider} if provider else {}
        try:
            output = obb.equity.price.historical(symbol, **kwargs)
            frame = output.to_dataframe().reset_index()
            grouped[symbol.upper()] = _bars_from_frame(symbol, frame)
        except Exception:
            grouped[symbol.upper()] = _fetch_yfinance_bars(symbol, period)
    return grouped


def fetch_yahoo_ohlcv(symbols: Iterable[str], period: str = "1y") -> dict[str, list[Bar]]:
    grouped: dict[str, list[Bar]] = {}
    for symbol in symbols:
        grouped[symbol.upper()] = _fetch_yfinance_bars(symbol, period)
    return grouped


def _fetch_yfinance_bars(symbol: str, period: str) -> list[Bar]:
    try:
        import yfinance as yf
    except ImportError as exc:
        return _fetch_yahoo_chart_bars(symbol, period)
    try:
        frame = yf.Ticker(symbol).history(period=period, auto_adjust=False).reset_index()
        bars = _bars_from_frame(symbol, frame)
        return bars if bars else _fetch_yahoo_chart_bars(symbol, period)
    except Exception:
        return _fetch_yahoo_chart_bars(symbol, period)


def _fetch_yahoo_chart_bars(symbol: str, period: str) -> list[Bar]:
    range_value = period if period.endswith(("d", "mo", "y", "ytd", "max")) else "1y"
    params = urllib.parse.urlencode({"range": range_value, "interval": "1d"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{params}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    quote = result["indicators"]["quote"][0]
    bars: list[Bar] = []
    for index, ts in enumerate(timestamps):
        close = quote["close"][index]
        if close is None:
            continue
        bars.append(
            Bar(
                symbol=symbol.upper(),
                timestamp=datetime.fromtimestamp(ts),
                open=float(quote["open"][index] or close),
                high=float(quote["high"][index] or close),
                low=float(quote["low"][index] or close),
                close=float(close),
                volume=float(quote["volume"][index] or 0),
            )
        )
    time.sleep(0.2)
    return bars


def _bars_from_frame(symbol: str, frame) -> list[Bar]:
    bars = []
    for _, row in frame.iterrows():
        open_value = row.get("open", row.get("Open"))
        high_value = row.get("high", row.get("High"))
        low_value = row.get("low", row.get("Low"))
        close_value = row.get("close", row.get("Close"))
        volume_value = row.get("volume", row.get("Volume", 0))
        if close_value is None:
            continue
        bars.append(
            Bar(
                symbol=symbol.upper(),
                timestamp=_parse_timestamp(str(row.get("date") or row.get("Date") or row.get("timestamp") or row.iloc[0])),
                open=float(open_value),
                high=float(high_value),
                low=float(low_value),
                close=float(close_value),
                volume=float(volume_value or 0),
            )
        )
    return bars


def save_ohlcv_csv(path: Path, bars_by_symbol: dict[str, list[Bar]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for symbol in sorted(bars_by_symbol):
            for bar in bars_by_symbol[symbol]:
                writer.writerow(
                    {
                        "symbol": bar.symbol,
                        "date": bar.timestamp.strftime("%Y-%m-%d"),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                )
    return path


def _parse_timestamp(value: str) -> datetime:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(value)
