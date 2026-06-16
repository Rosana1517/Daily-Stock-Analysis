from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from stock_signal_system.data.broker_source import fetch_histock_branch_snapshot
from stock_signal_system.data.rate_limit import RateLimitedHttpClient


TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"


@dataclass(frozen=True)
class TwseInstitutionalDay:
    trade_date: date
    rows: tuple[dict[str, float | str], ...]


@dataclass(frozen=True)
class BrokerChipSummary:
    symbol: str
    top10_main_force_buy_strength: float
    top10_main_force_net_buy: int
    top10_main_force_brokers: str
    branch_main_force_buy_streak_days: int
    branch_main_force_leader: str
    chip_data_date: str
    chip_data_source: str
    chip_data_source_status: str


def build_tw_chip_snapshot_csv(
    output_path: Path,
    cache_dir: Path,
    as_of: date | None = None,
    lookback_sessions: int = 10,
    max_calendar_days: int = 20,
    broker_symbols: tuple[str, ...] | None = None,
    latest_volume_by_symbol: dict[str, int] | None = None,
) -> Path:
    days = load_recent_twse_institutional_days(
        cache_dir,
        as_of=as_of,
        lookback_sessions=lookback_sessions,
        max_calendar_days=max_calendar_days,
    )
    broker_summaries = load_histock_broker_summaries(
        cache_dir,
        days,
        broker_symbols or (),
        latest_volume_by_symbol or {},
    )
    rows = _build_chip_rows_from_twse_days(days, broker_summaries)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "symbol",
            "top10_main_force_buy_strength",
            "top10_main_force_net_buy",
            "top10_main_force_buy_rank",
            "branch_main_force_buy_streak_days",
            "foreign_buy_streak_days",
            "investment_trust_buy_streak_days",
            "dealer_buy_streak_days",
            "foreign_net_buy",
            "investment_trust_net_buy",
            "dealer_net_buy",
            "chip_data_date",
            "chip_data_source",
            "chip_data_source_status",
            "top10_main_force_brokers",
            "branch_main_force_leader",
            # compatibility grace period
            "top10_main_force_buy_strength_proxy",
            "institutional_main_force_strength_proxy",
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


def load_histock_broker_summaries(
    cache_dir: Path,
    twse_days: tuple[TwseInstitutionalDay, ...],
    broker_symbols: tuple[str, ...],
    latest_volume_by_symbol: dict[str, int],
) -> dict[str, BrokerChipSummary]:
    if not twse_days or not broker_symbols:
        return {}
    official_dates = tuple(day.trade_date for day in twse_days)
    results: dict[str, BrokerChipSummary] = {}
    for raw_symbol in broker_symbols:
        symbol = str(raw_symbol).split(".")[0].strip()
        if not symbol:
            continue
        snapshots = []
        for trade_date in official_dates:
            try:
                snapshot = fetch_histock_branch_snapshot(symbol, cache_dir, trade_date=trade_date)
            except Exception:
                snapshot = None
            if snapshot is not None:
                snapshots.append(snapshot)
        summary = _summarize_broker_snapshots(symbol, snapshots, latest_volume_by_symbol.get(symbol, 0))
        if summary is not None:
            results[symbol] = summary
    ranked = sorted(
        (summary for summary in results.values() if summary.top10_main_force_net_buy > 0),
        key=lambda item: item.top10_main_force_net_buy,
        reverse=True,
    )
    rank_by_symbol = {summary.symbol: rank for rank, summary in enumerate(ranked, start=1)}
    normalized: dict[str, BrokerChipSummary] = {}
    for symbol, summary in results.items():
        normalized[symbol] = BrokerChipSummary(
            symbol=symbol,
            top10_main_force_buy_strength=summary.top10_main_force_buy_strength,
            top10_main_force_net_buy=summary.top10_main_force_net_buy,
            top10_main_force_brokers=summary.top10_main_force_brokers,
            branch_main_force_buy_streak_days=summary.branch_main_force_buy_streak_days,
            branch_main_force_leader=summary.branch_main_force_leader,
            chip_data_date=summary.chip_data_date,
            chip_data_source=summary.chip_data_source,
            chip_data_source_status=f"{summary.chip_data_source_status}|rank={rank_by_symbol.get(symbol, 0)}",
        )
    return normalized


def _summarize_broker_snapshots(
    symbol: str,
    snapshots,
    latest_volume: int,
) -> BrokerChipSummary | None:
    valid = [snapshot for snapshot in snapshots if snapshot and snapshot.buy_trades]
    if not snapshots:
        return None
    if not valid:
        latest_trade_date = next((snapshot.trade_date for snapshot in snapshots if snapshot and snapshot.trade_date), None)
        return BrokerChipSummary(
            symbol=symbol,
            top10_main_force_buy_strength=0.0,
            top10_main_force_net_buy=0,
            top10_main_force_brokers="",
            branch_main_force_buy_streak_days=0,
            branch_main_force_leader="",
            chip_data_date=latest_trade_date.isoformat() if latest_trade_date else "",
            chip_data_source="TWSE T86 official",
            chip_data_source_status="degraded",
        )
    latest = valid[0]
    positive_buy_trades = [trade for trade in latest.buy_trades if trade.net_shares > 0]
    top_buy_trades = positive_buy_trades[:10]
    total_net_buy = sum(trade.net_shares for trade in top_buy_trades)
    leader = top_buy_trades[0].broker if top_buy_trades else ""
    streak = _positive_leader_streak(valid, leader)
    strength = _top10_main_force_strength(total_net_buy, latest_volume)
    return BrokerChipSummary(
        symbol=symbol,
        top10_main_force_buy_strength=strength,
        top10_main_force_net_buy=total_net_buy,
        top10_main_force_brokers="、".join(trade.broker for trade in top_buy_trades),
        branch_main_force_buy_streak_days=streak,
        branch_main_force_leader=leader,
        chip_data_date=(latest.trade_date.isoformat() if latest.trade_date else ""),
        chip_data_source="TWSE T86 official + HiStock branch",
        chip_data_source_status="official+broker",
    )


def _positive_leader_streak(snapshots, leader: str) -> int:
    if not leader:
        return 0
    streak = 0
    for snapshot in snapshots:
        found = next((trade for trade in snapshot.buy_trades if trade.broker == leader), None)
        if found is None or found.net_shares <= 0:
            break
        streak += 1
    return streak


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


def _build_chip_rows_from_twse_days(
    days: tuple[TwseInstitutionalDay, ...],
    broker_summaries: dict[str, BrokerChipSummary] | None = None,
) -> list[dict[str, str]]:
    if not days:
        return []
    broker_summaries = broker_summaries or {}
    per_symbol: dict[str, list[dict[str, float | str]]] = {}
    for day in days:
        for row in day.rows:
            per_symbol.setdefault(str(row["symbol"]), []).append({**row, "chip_data_date": day.trade_date.isoformat()})
    results = []
    latest_date = days[0].trade_date.isoformat()
    for symbol, history in sorted(per_symbol.items()):
        latest = history[0]
        foreign_net_buy = float(latest["foreign_net_buy"])
        trust_net_buy = float(latest["investment_trust_net_buy"])
        dealer_net_buy = float(latest["dealer_net_buy"])
        proxy_strength = _proxy_strength(foreign_net_buy, trust_net_buy, dealer_net_buy)
        broker = broker_summaries.get(symbol)
        rank = _extract_rank(broker.chip_data_source_status) if broker else 0
        row = {
            "symbol": symbol,
            "top10_main_force_buy_strength": f"{broker.top10_main_force_buy_strength:.1f}" if broker else "",
            "top10_main_force_net_buy": str(broker.top10_main_force_net_buy) if broker else "",
            "top10_main_force_buy_rank": str(rank) if rank > 0 else "",
            "branch_main_force_buy_streak_days": str(broker.branch_main_force_buy_streak_days) if broker else "",
            "foreign_buy_streak_days": str(_positive_streak(history, "foreign_net_buy")),
            "investment_trust_buy_streak_days": str(_positive_streak(history, "investment_trust_net_buy")),
            "dealer_buy_streak_days": str(_positive_streak(history, "dealer_net_buy")),
            "foreign_net_buy": f"{foreign_net_buy:.0f}",
            "investment_trust_net_buy": f"{trust_net_buy:.0f}",
            "dealer_net_buy": f"{dealer_net_buy:.0f}",
            "chip_data_date": broker.chip_data_date if broker else latest_date,
            "chip_data_source": broker.chip_data_source if broker else "TWSE T86 official",
            "chip_data_source_status": broker.chip_data_source_status.split("|", 1)[0] if broker else "official-only",
            "top10_main_force_brokers": broker.top10_main_force_brokers if broker else "",
            "branch_main_force_leader": broker.branch_main_force_leader if broker else "",
            "top10_main_force_buy_strength_proxy": f"{proxy_strength:.1f}",
            "institutional_main_force_strength_proxy": f"{proxy_strength:.1f}",
        }
        results.append(row)
    return results


def _extract_rank(status: str) -> int:
    if "|rank=" not in status:
        return 0
    try:
        return int(status.split("|rank=", 1)[1])
    except ValueError:
        return 0


def _positive_streak(history: list[dict[str, float | str]], field: str) -> int:
    streak = 0
    for row in history:
        if float(row[field]) > 0:
            streak += 1
            continue
        break
    return streak


def _top10_main_force_strength(total_net_buy: int, latest_volume: int) -> float:
    if total_net_buy <= 0 or latest_volume <= 0:
        return 0.0
    ratio = total_net_buy / max(latest_volume, 1)
    return max(0.0, min(100.0, ratio * 100.0))


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
