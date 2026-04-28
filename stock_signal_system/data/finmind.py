from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from stock_signal_system.data.rate_limit import RateLimitedHttpClient


FINMIND_DATA_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TICK_SNAPSHOT_URL = "https://api.finmindtrade.com/api/v4/taiwan_stock_tick_snapshot"


class FinMindClient:
    def __init__(self, cache_dir: Path, token: Optional[str] = None) -> None:
        self.token = token
        self.http = RateLimitedHttpClient(cache_dir=cache_dir / "finmind", min_interval_seconds=6.5)

    def taiwan_stock_price(self, stock_id: str, start_date: str, end_date: str) -> list[dict]:
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
        }
        if self.token:
            params["token"] = self.token
        payload = self.http.get_json(
            FINMIND_DATA_URL,
            params=params,
            cache_key=f"finmind_TaiwanStockPrice_{stock_id}_{start_date}_{end_date}",
            ttl_seconds=3600 * 12,
        )
        if payload.get("status") != 200:
            raise RuntimeError(f"FinMind error: {payload}")
        return payload.get("data", [])

    def taiwan_stock_tick_snapshot(self) -> list[dict]:
        params = {}
        if self.token:
            params["token"] = self.token
        payload = self.http.get_json(
            FINMIND_TICK_SNAPSHOT_URL,
            params=params,
            cache_key="finmind_taiwan_stock_tick_snapshot",
            ttl_seconds=60,
        )
        if payload.get("status") != 200:
            raise RuntimeError(f"FinMind tick snapshot error: {payload}")
        return payload.get("data", [])


def save_tick_snapshot_csv(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def enrich_stock_csv_with_tick_snapshot(stock_path: Path, snapshot_rows: list[dict]) -> int:
    if not stock_path.exists() or not snapshot_rows:
        return 0
    snapshots = {_row_symbol(row): row for row in snapshot_rows if _row_symbol(row)}
    with stock_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    updated = 0
    for row in rows:
        snapshot = snapshots.get(row.get("symbol", "").strip())
        if not snapshot:
            continue
        close = _to_float(_get(snapshot, "close", "Close", "last_price", "price", "deal_price"))
        volume = _to_float(_get(snapshot, "volume", "Volume", "total_volume", "trade_volume"))
        if close > 0:
            row["price"] = str(close)
            updated += 1
        if volume > 0:
            row["volume"] = str(volume)

    with stock_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return updated


def _row_symbol(row: dict) -> str:
    return str(_get(row, "stock_id", "symbol", "code", "StockID")).strip()


def _get(row: dict, *names: str) -> str:
    for name in names:
        if name in row and str(row[name]).strip():
            return str(row[name]).strip()
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _to_float(value) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "").strip()
    if not text or text in {"--", "N/A", "NaN", "-"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
