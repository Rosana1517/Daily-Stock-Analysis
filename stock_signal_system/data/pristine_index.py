"""臺灣指數公司「臺灣璞玉指數」(IX0231) daily close tracking.

The endpoint below is not documented in any official API reference. It was
reverse-engineered from the TIP website's own Nuxt.js frontend bundle, which
calls `GET /indexes/{code}/records?start=...&end=...` against
backend.taiwanindex.com.tw to render its own history chart. Confirmed public
and unauthenticated by direct request; no written contract exists, so treat
response shape changes as a real possibility and fail soft."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient

PRISTINE_INDEX_CODE = "IX0231"
BASE_URL = "https://backend.taiwanindex.com.tw/api"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.taiwanindex.com.tw/",
}


@dataclass(frozen=True)
class PristineIndexPoint:
    trade_date: date
    price: float


@dataclass(frozen=True)
class PristineRelativeStrength:
    pristine_change_pct: float
    taiex_change_pct: float
    lookback_sessions: int
    verdict: str  # 璞玉抗跌(資金避風港) / 璞玉走弱 / 同步


def fetch_pristine_index_history(
    cache_dir: Path,
    as_of: date | None = None,
    lookback_days: int = 30,
) -> tuple[PristineIndexPoint, ...]:
    """Daily closes of the 臺灣璞玉指數 price series, oldest first."""
    end = as_of or date.today()
    start = end - timedelta(days=lookback_days)
    client = RateLimitedHttpClient(cache_dir=cache_dir / "pristine_index", min_interval_seconds=1.0)
    payload = client.get_json(
        f"{BASE_URL}/indexes/{PRISTINE_INDEX_CODE}/records",
        params={"start": start.isoformat(), "end": end.isoformat()},
        headers=_HEADERS,
        cache_key=f"pristine_index_{start.isoformat()}_{end.isoformat()}",
        ttl_seconds=3600 * 4,
    )
    if payload.get("empty"):
        return ()
    data = payload.get("data") or {}
    labels = data.get("labels") or []
    datasets = data.get("datasets") or []
    price_series = next(
        (item.get("data") or [] for item in datasets if item.get("value_type") == "price"),
        [],
    )
    points: list[PristineIndexPoint] = []
    for label, value in zip(labels, price_series):
        parsed_date = _parse_label_date(label)
        if parsed_date is None:
            continue
        try:
            points.append(PristineIndexPoint(parsed_date, float(value)))
        except (TypeError, ValueError):
            continue
    return tuple(points)


def evaluate_relative_strength(
    pristine_points: tuple[PristineIndexPoint, ...],
    taiex_closes: list[float],
    lookback_sessions: int = 5,
) -> PristineRelativeStrength | None:
    """Compare the 璞玉指數 vs TAIEX change over the last lookback_sessions
    sessions. Both series are assumed already sorted oldest-first; alignment
    is by session count, not calendar date, since the two sources don't share
    a common trading-day feed."""
    if len(pristine_points) < lookback_sessions + 1 or len(taiex_closes) < lookback_sessions + 1:
        return None
    pristine_latest = pristine_points[-1].price
    pristine_prior = pristine_points[-1 - lookback_sessions].price
    if pristine_prior <= 0:
        return None
    pristine_change = (pristine_latest / pristine_prior - 1.0) * 100.0
    taiex_latest = taiex_closes[-1]
    taiex_prior = taiex_closes[-1 - lookback_sessions]
    if taiex_prior <= 0:
        return None
    taiex_change = (taiex_latest / taiex_prior - 1.0) * 100.0
    relative_strength = pristine_change - taiex_change
    if taiex_change <= -1.0 and relative_strength >= 1.0:
        verdict = "璞玉抗跌(資金避風港)"
    elif relative_strength <= -1.0:
        verdict = "璞玉走弱"
    else:
        verdict = "同步"
    return PristineRelativeStrength(
        pristine_change_pct=pristine_change,
        taiex_change_pct=taiex_change,
        lookback_sessions=lookback_sessions,
        verdict=verdict,
    )


def _parse_label_date(label: str) -> date | None:
    try:
        return datetime.strptime(str(label).replace("/", "-"), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
