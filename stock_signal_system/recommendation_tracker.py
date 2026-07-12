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
    "eval_date",
    "return_5d",
    "max_return_5d",
    "win",
]

EVAL_HORIZON_SESSIONS = 5


@dataclass(frozen=True)
class RecommendationSummary:
    evaluated_count: int
    pending_count: int
    win_rate: float | None
    average_return_5d: float | None
    average_max_return_5d: float | None
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
        existing.append(
            {
                "entry_date": entry_date.isoformat(),
                "symbol": symbol,
                "name": str(pick.get("name", "")).strip(),
                "bucket": str(pick.get("bucket", "")).strip(),
                "entry_close": f"{entry_close:.2f}",
                "stop_loss_price": f"{stop_loss:.2f}" if stop_loss else "",
                "eval_date": "",
                "return_5d": "",
                "max_return_5d": "",
                "win": "",
            }
        )
        seen.add(key)
        added += 1
    if added:
        _save_log(log_path, existing)
    return added


def evaluate_pending(log_path: Path, price_snapshot_dir: Path, as_of: date) -> int:
    """Fill in 5-session outcomes for pending log rows using archived price snapshots."""
    rows = _load_log(log_path)
    if not rows:
        return 0
    closes_by_date = _load_price_snapshots(price_snapshot_dir)
    if not closes_by_date:
        return 0
    session_dates = sorted(closes_by_date)
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
        closes = [closes_by_date[d].get(bare_symbol) for d in window]
        closes = [c for c in closes if c and c > 0]
        if not closes:
            # symbol missing from all forward snapshots (delisted/suspended); mark unresolved
            row["eval_date"] = window[-1]
            row["return_5d"] = ""
            row["max_return_5d"] = ""
            row["win"] = ""
            evaluated += 1
            continue
        final_close = closes[-1]
        return_5d = final_close / entry_close - 1.0
        max_return = max(c / entry_close - 1.0 for c in closes)
        row["eval_date"] = window[-1]
        row["return_5d"] = f"{return_5d:.4f}"
        row["max_return_5d"] = f"{max_return:.4f}"
        row["win"] = "1" if return_5d > 0 else "0"
        evaluated += 1
    if evaluated:
        _save_log(log_path, rows)
    return evaluated


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
        recent_evaluated=recent,
    )


def _load_price_snapshots(snapshot_dir: Path) -> dict[str, dict[str, float]]:
    if not snapshot_dir.exists():
        return {}
    result: dict[str, dict[str, float]] = {}
    for path in sorted(snapshot_dir.glob("tw_price_daily_*.csv")):
        snapshot_date = path.stem.replace("tw_price_daily_", "")
        closes: dict[str, float] = {}
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    symbol = str(row.get("symbol", "")).strip()
                    close = _to_float(row.get("close"))
                    if symbol and close and close > 0:
                        closes[symbol] = close
        except OSError:
            continue
        if closes:
            result[snapshot_date] = closes
    return result


def _load_log(log_path: Path) -> list[dict[str, str]]:
    if not log_path.exists():
        return []
    with log_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _save_log(log_path: Path, rows: list[dict[str, str]]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDNAMES, extrasaction="ignore")
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
