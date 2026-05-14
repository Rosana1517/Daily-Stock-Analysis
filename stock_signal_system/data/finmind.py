from __future__ import annotations

from pathlib import Path
from typing import Optional

from stock_signal_system.data.rate_limit import RateLimitedHttpClient


FINMIND_DATA_URL = "https://api.finmindtrade.com/api/v4/data"


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

