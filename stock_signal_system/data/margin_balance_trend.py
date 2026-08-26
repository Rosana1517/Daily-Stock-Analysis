"""Market-wide 融資餘額 (margin financing balance) daily trend, from TWSE's
public credit-trading statistics endpoint (MI_MARGN) — a long-standing
public JSON endpoint behind TWSE's own 信用交易統計 page, not part of the
documented openapi.twse.com.tw v1 catalog. Confirmed public, unauthenticated,
and accepts a `date` query param for historical lookback (same shape as the
T86 institutional-investor endpoint this project already uses)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient

MARGIN_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
MARGIN_AMOUNT_ROW_LABEL = "融資金額(仟元)"

# Thresholds mirror the methodology's own example ("連續3天每日大減100億至
# 200億，累積減少300億以上"): amounts below are in 仟元 (thousand NTD).
DAILY_WASHOUT_THRESHOLD_THOUSANDS = 10_000_000.0  # 100億
CUMULATIVE_WASHOUT_THRESHOLD_THOUSANDS = 30_000_000.0  # 300億
DAILY_SURGE_THRESHOLD_THOUSANDS = 5_000_000.0  # 50億

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.twse.com.tw/zh/",
}


@dataclass(frozen=True)
class MarginBalanceDay:
    trade_date: date
    balance_thousands: float  # 今日餘額(仟元)
    change_thousands: float  # 今日餘額 - 前日餘額(仟元)


@dataclass(frozen=True)
class MarginBalanceTrend:
    daily: tuple[MarginBalanceDay, ...]  # newest first
    streak_days: int  # >0 consecutive daily increases, <0 consecutive daily decreases
    window_change_thousands: float  # sum of change_thousands over the streak window
    verdict: str  # 融資急縮(籌碼清洗) / 融資急增(追價風險) / 持平


def load_recent_margin_balance_days(
    cache_dir: Path,
    as_of: date | None = None,
    lookback_sessions: int = 5,
    max_calendar_days: int = 14,
) -> tuple[MarginBalanceDay, ...]:
    """Walk backward from as_of collecting up to lookback_sessions trading
    days of market-wide margin balance, skipping non-trading days (the
    endpoint returns stat != OK for those)."""
    client = RateLimitedHttpClient(cache_dir=cache_dir / "twse_margin", min_interval_seconds=1.0)
    cursor = as_of or date.today()
    collected: list[MarginBalanceDay] = []
    for _ in range(max_calendar_days):
        try:
            payload = client.get_json(
                MARGIN_URL,
                params={"response": "json", "date": cursor.strftime("%Y%m%d")},
                headers=_HEADERS,
                cache_key=f"twse_margin_{cursor:%Y%m%d}",
                ttl_seconds=1800,
            )
        except Exception as exc:
            print(f"warning: margin_balance_fetch_failed date={cursor:%Y%m%d} error={exc}", flush=True)
            payload = None
        if payload is not None:
            day = _parse_margin_payload(payload, cursor)
            if day is not None:
                collected.append(day)
                if len(collected) >= lookback_sessions:
                    break
        cursor -= timedelta(days=1)
    return tuple(collected)


def summarize_margin_balance_trend(days: tuple[MarginBalanceDay, ...]) -> MarginBalanceTrend | None:
    if not days:
        return None
    ordered = tuple(sorted(days, key=lambda item: item.trade_date, reverse=True))
    streak = 0
    for day in ordered:
        if day.change_thousands > 0:
            if streak < 0:
                break
            streak += 1
        elif day.change_thousands < 0:
            if streak > 0:
                break
            streak -= 1
        else:
            break
    window = ordered[: abs(streak)] if streak else ordered[:1]
    window_change = sum(day.change_thousands for day in window)
    if streak <= -3 and window_change <= -CUMULATIVE_WASHOUT_THRESHOLD_THOUSANDS:
        verdict = "融資急縮(籌碼清洗，留意落底訊號)"
    elif ordered[0].change_thousands >= DAILY_SURGE_THRESHOLD_THOUSANDS:
        verdict = "融資急增(散戶追價，留意主力調節風險)"
    else:
        verdict = "持平"
    return MarginBalanceTrend(
        daily=ordered,
        streak_days=streak,
        window_change_thousands=window_change,
        verdict=verdict,
    )


def _parse_margin_payload(payload: dict, requested_date: date) -> MarginBalanceDay | None:
    if str(payload.get("stat", "")).upper() != "OK":
        return None
    tables = payload.get("tables") or []
    if not tables:
        return None
    rows = tables[0].get("data") or []
    for row in rows:
        if not row or str(row[0]).strip() != MARGIN_AMOUNT_ROW_LABEL:
            continue
        try:
            prev_balance = _to_float(row[4])
            today_balance = _to_float(row[5])
        except (IndexError, ValueError):
            return None
        trade_date = _parse_yyyymmdd(str(payload.get("date", "")).strip()) or requested_date
        return MarginBalanceDay(trade_date, today_balance, today_balance - prev_balance)
    return None


def _to_float(value: str) -> float:
    return float(str(value).replace(",", "").strip())


def _parse_yyyymmdd(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
