from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


TAIEX_SYMBOL = "^TWII"
_CACHE_TTL_SECONDS = 3600 * 4


@dataclass(frozen=True)
class MarketRegimeGate:
    """TAIEX trend gate: is the broad market above its 20-day moving average?

    Chasing box breakouts on individual mid/low-price stocks has a much higher
    false-breakout rate when the index itself is in a downtrend. When data is
    unavailable we fail open (bullish=True) so a data hiccup never silently
    kills every recommendation.
    """

    bullish: bool
    close: float | None
    ma20: float | None
    distance_pct: float | None
    available: bool


def evaluate_market_regime_gate(cache_dir: Path) -> MarketRegimeGate:
    cache_path = cache_dir / "market_regime" / "taiex_ma20.json"
    cached = _read_cache(cache_path)
    if cached is not None:
        return cached

    closes = _fetch_taiex_closes()
    if not closes or len(closes) < 20:
        gate = MarketRegimeGate(bullish=True, close=None, ma20=None, distance_pct=None, available=False)
        return gate

    close = closes[-1]
    ma20 = sum(closes[-20:]) / 20.0
    distance_pct = (close / ma20 - 1.0) * 100.0 if ma20 else None
    gate = MarketRegimeGate(bullish=close >= ma20, close=close, ma20=ma20, distance_pct=distance_pct, available=True)
    _write_cache(cache_path, gate)
    return gate


def _fetch_taiex_closes() -> list[float]:
    try:
        import yfinance as yf

        data = yf.download(TAIEX_SYMBOL, period="2mo", interval="1d", progress=False, threads=False)
        if data is None or data.empty:
            return []
        closes = data["Close"]
        if hasattr(closes, "iloc") and closes.ndim > 1:
            closes = closes.iloc[:, 0]
        return [float(value) for value in closes.dropna().tolist()]
    except Exception as exc:
        print(f"warning: taiex_regime_fetch_failed={exc}", flush=True)
        return []


def _read_cache(path: Path) -> MarketRegimeGate | None:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > _CACHE_TTL_SECONDS:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return MarketRegimeGate(**payload)
    except (OSError, ValueError, TypeError):
        return None


def _write_cache(path: Path, gate: MarketRegimeGate) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "bullish": gate.bullish,
                    "close": gate.close,
                    "ma20": gate.ma20,
                    "distance_pct": gate.distance_pct,
                    "available": gate.available,
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
