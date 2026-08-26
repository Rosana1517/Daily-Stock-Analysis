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
        return self._fetch_dataset("TaiwanStockPrice", stock_id, start_date, end_date)

    def taiwan_stock_financial_statements(self, stock_id: str, start_date: str, end_date: str) -> list[dict]:
        """Long-format quarterly income-statement rows (one row per {date, type}),
        e.g. type="EPS", type="IncomeAfterTaxes", type="Revenue"."""
        return self._fetch_dataset("TaiwanStockFinancialStatements", stock_id, start_date, end_date)

    def taiwan_stock_balance_sheet(self, stock_id: str, start_date: str, end_date: str) -> list[dict]:
        """Long-format quarterly balance-sheet rows, e.g. type="Equity",
        type="Liabilities", type="TotalAssets"."""
        return self._fetch_dataset("TaiwanStockBalanceSheet", stock_id, start_date, end_date)

    def taiwan_stock_dividend(self, stock_id: str, start_date: str, end_date: str) -> list[dict]:
        """One row per dividend event, with CashEarningsDistribution /
        StockEarningsDistribution amounts and an ex-dividend `date`."""
        return self._fetch_dataset("TaiwanStockDividend", stock_id, start_date, end_date)

    def _fetch_dataset(self, dataset: str, stock_id: str, start_date: str, end_date: str) -> list[dict]:
        params = {
            "dataset": dataset,
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
        }
        if self.token:
            params["token"] = self.token
        payload = self.http.get_json(
            FINMIND_DATA_URL,
            params=params,
            cache_key=f"finmind_{dataset}_{stock_id}_{start_date}_{end_date}",
            ttl_seconds=3600 * 12,
        )
        if payload.get("status") != 200:
            raise RuntimeError(f"FinMind error: {payload}")
        return payload.get("data", [])
