from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient


TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"


@dataclass(frozen=True)
class TwseInstitutionalDay:
    trade_date: date
    rows: tuple[dict[str, float | str], ...]


def build_tw_chip_snapshot_csv(
    output_path: Path,
    cache_dir: Path,
    as_of: date | None = None,
    lookback_sessions: int = 10,
    max_calendar_days: int = 20,
) -> Path:
    days = load_recent_twse_institutional_days(cache_dir, as_of=as_of, lookback_sessions=lookback_sessions, max_calendar_days=max_calendar_days)
    rows = _build_chip_rows_from_twse_days(days)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "symbol",
            "top10_main_force_buy_strength_proxy",
            "institutional_main_force_strength_proxy",
            "foreign_buy_streak_days",
            "dealer_buy_streak_days_proxy",
            "branch_main_force_buy_streak_days_proxy",
            "investment_trust_buy_streak_days",
            "foreign_net_buy",
            "investment_trust_net_buy",
            "dealer_net_buy",
            "chip_data_date",
            "chip_data_source",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return output_path


def load_recent_twse_institutional_days(
    cache_dir: Path,
    as_of: date | None = None,
    lookback_sessions: int = 10,
    max_calendar_days: int = 20,
) -> tuple[TwseInstitutionalDay, ...]:
    client = RateLimitedHttpClient(cache_dir=cache_dir / "twse_chip", min_interval_seconds=1.0)
    cursor = as_of or date.today()
    collected: list[TwseInstitutionalDay] = []
    for _ in range(max_calendar_days):
        payload = client.get_json(
            TWSE_T86_URL,
            params={"date": cursor.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"},
            cache_key=f"twse_t86_{cursor:%Y%m%d}",
            ttl_seconds=1800,
        )
        day = _parse_twse_t86_payload(payload)
        if day is not None:
            collected.append(day)
            if len(collected) >= lookback_sessions:
                break
        cursor -= timedelta(days=1)
    return tuple(collected)


def _parse_twse_t86_payload(payload: dict) -> TwseInstitutionalDay | None:
    if str(payload.get("stat", "")).upper() != "OK":
        return None
    raw_date = str(payload.get("date", "")).strip()
    raw_rows = payload.get("data") or []
    if not raw_date or not raw_rows:
        return None
    parsed_date = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
    rows: list[dict[str, float | str]] = []
    for item in raw_rows:
        if not isinstance(item, list) or len(item) < 18:
            continue
        symbol = str(item[0]).strip()
        if not (symbol.isdigit() and len(symbol) == 4):
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": str(item[1]).strip(),
                "foreign_net_buy": _float(item[4]) + _float(item[7]),
                "investment_trust_net_buy": _float(item[10]),
                "dealer_net_buy": _float(item[11]),
            }
        )
    return TwseInstitutionalDay(parsed_date, tuple(rows)) if rows else None


def _build_chip_rows_from_twse_days(days: tuple[TwseInstitutionalDay, ...]) -> list[dict[str, str]]:
    if not days:
        return []
    per_symbol: dict[str, list[dict[str, float | str]]] = {}
    for day in days:
        for row in day.rows:
            per_symbol.setdefault(str(row["symbol"]), []).append({**row, "chip_data_date": day.trade_date.isoformat()})
    latest_date = days[0].trade_date.isoformat()
    results = []
    for symbol, history in sorted(per_symbol.items()):
        latest = history[0]
        foreign_net_buy = float(latest["foreign_net_buy"])
        trust_net_buy = float(latest["investment_trust_net_buy"])
        dealer_net_buy = float(latest["dealer_net_buy"])
        strength = _proxy_strength(foreign_net_buy, trust_net_buy, dealer_net_buy)
        results.append(
            {
                "symbol": symbol,
                "top10_main_force_buy_strength_proxy": f"{strength:.1f}",
                "institutional_main_force_strength_proxy": f"{strength:.1f}",
                "foreign_buy_streak_days": str(_positive_streak(history, "foreign_net_buy")),
                "dealer_buy_streak_days_proxy": str(_positive_streak(history, "dealer_net_buy")),
                "branch_main_force_buy_streak_days_proxy": str(_positive_streak(history, "dealer_net_buy")),
                "investment_trust_buy_streak_days": str(_positive_streak(history, "investment_trust_net_buy")),
                "foreign_net_buy": f"{foreign_net_buy:.0f}",
                "investment_trust_net_buy": f"{trust_net_buy:.0f}",
                "dealer_net_buy": f"{dealer_net_buy:.0f}",
                "chip_data_date": latest_date,
                "chip_data_source": "TWSE T86 official proxy",
            }
        )
    return results


def _positive_streak(history: list[dict[str, float | str]], field: str) -> int:
    streak = 0
    for row in history:
        if float(row[field]) > 0:
            streak += 1
            continue
        break
    return streak


def _proxy_strength(foreign_net_buy: float, trust_net_buy: float, dealer_net_buy: float) -> float:
    weighted = foreign_net_buy * 1.0 + trust_net_buy * 0.8 + dealer_net_buy * 0.6
    if weighted <= 0:
        return 0.0
    return max(0.0, min(100.0, 40.0 + min(weighted / 5_000_000.0, 60.0)))


def _float(value) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
