from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path


LOG_FIELDNAMES = [
    "entry_date",
    "symbol",
    "name",
    "bucket",
    "entry_close",
    "stop_loss_price",
    "take_profit_price",
    "eval_date",
    "return_5d",
    "max_return_5d",
    "win",
    "exit_reason",
]

EVAL_HORIZON_SESSIONS = 5


@dataclass(frozen=True)
class RecommendationSummary:
    evaluated_count: int
    pending_count: int
    win_rate: float | None
    average_return_5d: float | None
    average_max_return_5d: float | None
    stop_loss_exit_count: int
    take_profit_exit_count: int
    horizon_exit_count: int
    recent_evaluated: tuple[dict[str, str], ...]


def append_recommendations(log_path: Path, entry_date: date, picks: list[dict[str, object]]) -> int:
    """Append today's picks to the log, skipping symbols already logged for the date."""
    existing = _load_log(log_path)
    seen = {(row["entry_date"], row["symbol"]) for row in existing}
    added = 0
    for pick in picks:
        symbol = str(pick.get("symbol", "")).strip()
        if not symbol:
            continue
        key = (entry_date.isoformat(), symbol)
        if key in seen:
            continue
        entry_close = _to_float(pick.get("entry_close"))
        if entry_close is None or entry_close <= 0:
            continue
        stop_loss = _to_float(pick.get("stop_loss_price"))
        take_profit = _to_float(pick.get("take_profit_price"))
        existing.append(
            {
                "entry_date": entry_date.isoformat(),
                "symbol": symbol,
                "name": str(pick.get("name", "")).strip(),
                "bucket": str(pick.get("bucket", "")).strip(),
                "entry_close": f"{entry_close:.2f}",
                "stop_loss_price": f"{stop_loss:.2f}" if stop_loss else "",
                "take_profit_price": f"{take_profit:.2f}" if take_profit else "",
                "eval_date": "",
                "return_5d": "",
                "max_return_5d": "",
                "win": "",
                "exit_reason": "",
            }
        )
        seen.add(key)
        added += 1
    if added:
        _save_log(log_path, existing)
    return added


def evaluate_pending(log_path: Path, price_snapshot_dir: Path, as_of: date) -> int:
    """Resolve pending log rows against archived daily OHLC snapshots.

    Walks forward day-by-day (up to EVAL_HORIZON_SESSIONS sessions): exits
    early at the stop-loss price if that day's low touches it, at the
    take-profit price if that day's high touches it (stop takes priority on a
    day both are touched, the conservative backtest convention), otherwise
    holds to the close of the final session in the horizon.
    """
    rows = _load_log(log_path)
    if not rows:
        return 0
    bars_by_date = _load_price_snapshots(price_snapshot_dir)
    if not bars_by_date:
        return 0
    session_dates = sorted(bars_by_date)
    evaluated = 0
    for row in rows:
        if row.get("eval_date"):
            continue
        entry_date = row.get("entry_date", "")
        entry_close = _to_float(row.get("entry_close"))
        if not entry_date or not entry_close:
            continue
        forward_dates = [d for d in session_dates if d > entry_date]
        if len(forward_dates) < EVAL_HORIZON_SESSIONS:
            continue
        window = forward_dates[:EVAL_HORIZON_SESSIONS]
        bare_symbol = row.get("symbol", "").split(".")[0].strip()
        stop_loss = _to_float(row.get("stop_loss_price"))
        take_profit = _to_float(row.get("take_profit_price"))

        day_bars = [(d, bars_by_date[d].get(bare_symbol)) for d in window]
        day_bars = [(d, bar) for d, bar in day_bars if bar and bar.get("close", 0) > 0]
        if not day_bars:
            # symbol missing from all forward snapshots (delisted/suspended); mark unresolved
            row["eval_date"] = window[-1]
            row["return_5d"] = ""
            row["max_return_5d"] = ""
            row["win"] = ""
            row["exit_reason"] = "unresolved"
            evaluated += 1
            continue

        exit_date, exit_close, exit_reason = _resolve_exit(day_bars, stop_loss, take_profit)
        held_closes = [bar["close"] for d, bar in day_bars if d <= exit_date]
        max_return = max((c / entry_close - 1.0 for c in held_closes), default=0.0)
        return_final = exit_close / entry_close - 1.0

        row["eval_date"] = exit_date
        row["return_5d"] = f"{return_final:.4f}"
        row["max_return_5d"] = f"{max_return:.4f}"
        row["win"] = "1" if return_final > 0 else "0"
        row["exit_reason"] = exit_reason
        evaluated += 1
    if evaluated:
        _save_log(log_path, rows)
    return evaluated


def _resolve_exit(
    day_bars: list[tuple[str, dict[str, float]]],
    stop_loss: float | None,
    take_profit: float | None,
) -> tuple[str, float, str]:
    for snapshot_date, bar in day_bars:
        if stop_loss and stop_loss > 0 and bar.get("low", bar["close"]) <= stop_loss:
            return snapshot_date, stop_loss, "stop_loss"
        if take_profit and take_profit > 0 and bar.get("high", bar["close"]) >= take_profit:
            return snapshot_date, take_profit, "take_profit"
    final_date, final_bar = day_bars[-1]
    return final_date, final_bar["close"], "horizon_close"


def summarize(log_path: Path, recent_limit: int = 10) -> RecommendationSummary:
    rows = _load_log(log_path)
    evaluated = [row for row in rows if row.get("win") in {"0", "1"}]
    pending = [row for row in rows if not row.get("eval_date")]
    wins = sum(1 for row in evaluated if row["win"] == "1")
    returns = [_to_float(row.get("return_5d")) for row in evaluated]
    returns = [r for r in returns if r is not None]
    max_returns = [_to_float(row.get("max_return_5d")) for row in evaluated]
    max_returns = [r for r in max_returns if r is not None]
    recent = tuple(sorted(evaluated, key=lambda row: row.get("eval_date", ""), reverse=True)[:recent_limit])
    return RecommendationSummary(
        evaluated_count=len(evaluated),
        pending_count=len(pending),
        win_rate=wins / len(evaluated) if evaluated else None,
        average_return_5d=sum(returns) / len(returns) if returns else None,
        average_max_return_5d=sum(max_returns) / len(max_returns) if max_returns else None,
        stop_loss_exit_count=sum(1 for row in evaluated if row.get("exit_reason") == "stop_loss"),
        take_profit_exit_count=sum(1 for row in evaluated if row.get("exit_reason") == "take_profit"),
        horizon_exit_count=sum(1 for row in evaluated if row.get("exit_reason") == "horizon_close"),
        recent_evaluated=recent,
    )


def _load_price_snapshots(snapshot_dir: Path) -> dict[str, dict[str, dict[str, float]]]:
    if not snapshot_dir.exists():
        return {}
    result: dict[str, dict[str, dict[str, float]]] = {}
    for path in sorted(snapshot_dir.glob("tw_price_daily_*.csv")):
        snapshot_date = path.stem.replace("tw_price_daily_", "")
        bars: dict[str, dict[str, float]] = {}
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    symbol = str(row.get("symbol", "")).strip()
                    close = _to_float(row.get("close"))
                    if not symbol or not close or close <= 0:
                        continue
                    bars[symbol] = {
                        "high": _to_float(row.get("high")) or close,
                        "low": _to_float(row.get("low")) or close,
                        "close": close,
                    }
        except OSError:
            continue
        if bars:
            result[snapshot_date] = bars
    return result


def _load_log(log_path: Path) -> list[dict[str, str]]:
    if not log_path.exists():
        return []
    with log_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _save_log(log_path: Path, rows: list[dict[str, str]]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDNAMES, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)


def _to_float(value) -> float | None:
    text = str(value if value is not None else "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
