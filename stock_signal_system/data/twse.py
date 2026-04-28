from __future__ import annotations

import csv
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient


BASE_URL = "https://openapi.twse.com.tw/v1"

ENDPOINTS = {
    "daily_all": "/exchangeReport/STOCK_DAY_ALL",
    "daily_avg": "/exchangeReport/STOCK_DAY_AVG_ALL",
    "valuation": "/exchangeReport/BWIBBU_ALL",
    "company_basic": "/opendata/t187ap03_L",
    "monthly_revenue": "/opendata/t187ap05_L",
    "material_news": "/opendata/t187ap04_L",
    "holiday": "/holidaySchedule/holidaySchedule",
}


def fetch_twse_dataset(name: str, cache_dir: Path) -> list[dict]:
    if name not in ENDPOINTS:
        raise ValueError(f"Unknown TWSE dataset: {name}")
    client = RateLimitedHttpClient(cache_dir=cache_dir / "twse", min_interval_seconds=1.0)
    return client.get_json(
        BASE_URL + ENDPOINTS[name],
        cache_key=f"twse_{name}",
        ttl_seconds=1800,
    )


def build_twse_stock_csv(output_path: Path, cache_dir: Path) -> Path:
    daily = _by_code(fetch_twse_dataset("daily_all", cache_dir), "Code")
    avg = _by_code(fetch_twse_dataset("daily_avg", cache_dir), "Code")
    valuation = _by_code(fetch_twse_dataset("valuation", cache_dir), "Code")
    basic = _by_code(fetch_twse_dataset("company_basic", cache_dir), "公司代號")
    revenue = _by_code(fetch_twse_dataset("monthly_revenue", cache_dir), "公司代號")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = [
            "symbol",
            "name",
            "industry",
            "price",
            "price_20d_ago",
            "volume",
            "avg_volume_20d",
            "revenue_growth_yoy",
            "gross_margin",
            "operating_margin",
            "free_cash_flow_margin",
            "debt_to_equity",
            "pe_ratio",
            "notes",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for code, row in sorted(daily.items()):
            if not _is_common_stock_code(code):
                continue
            basic_row = basic.get(code, {})
            revenue_row = revenue.get(code, {})
            valuation_row = valuation.get(code, {})
            avg_row = avg.get(code, {})
            close = _to_float(row.get("ClosingPrice"))
            monthly_avg = _to_float(avg_row.get("MonthlyAveragePrice")) or close
            writer.writerow(
                {
                    "symbol": code,
                    "name": row.get("Name") or basic_row.get("公司簡稱") or "",
                    "industry": revenue_row.get("產業別") or basic_row.get("產業別") or "未分類",
                    "price": close,
                    "price_20d_ago": monthly_avg,
                    "volume": _to_float(row.get("TradeVolume")),
                    "avg_volume_20d": _to_float(row.get("TradeVolume")),
                    "revenue_growth_yoy": _to_float(revenue_row.get("營業收入-去年同月增減(%)")),
                    "gross_margin": 0,
                    "operating_margin": 0,
                    "free_cash_flow_margin": 0,
                    "debt_to_equity": 0,
                    "pe_ratio": _to_float(valuation_row.get("PEratio")),
                    "notes": "TWSE OpenAPI seed; margin, cash-flow, leverage fields require FinMind or financial statements.",
                }
            )
    return output_path


def build_twse_daily_price_csv(output_path: Path, cache_dir: Path) -> Path:
    daily = fetch_twse_dataset("daily_all", cache_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for row in daily:
            code = row.get("Code", "")
            if not _is_common_stock_code(code):
                continue
            writer.writerow(
                {
                    "symbol": code,
                    "date": _roc_date_to_iso(row.get("Date", "")),
                    "open": _to_float(row.get("OpeningPrice")),
                    "high": _to_float(row.get("HighestPrice")),
                    "low": _to_float(row.get("LowestPrice")),
                    "close": _to_float(row.get("ClosingPrice")),
                    "volume": _to_float(row.get("TradeVolume")),
                }
            )
    return output_path


def build_twse_material_news_csv(output_path: Path, cache_dir: Path) -> Path:
    news = fetch_twse_dataset("material_news", cache_dir)
    basic = _by_code(fetch_twse_dataset("company_basic", cache_dir), "公司代號")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "title", "source", "body", "industries"])
        writer.writeheader()
        for row in news:
            code = row.get("公司代號", "")
            industry = basic.get(code, {}).get("產業別", "")
            writer.writerow(
                {
                    "date": _roc_date_to_iso(row.get("發言日期") or row.get("出表日期") or ""),
                    "title": f"{code} {row.get('公司名稱', '')} {row.get('主旨 ', '').strip()}",
                    "source": "TWSE material information",
                    "body": row.get("說明", "").strip(),
                    "industries": industry,
                }
            )
    return output_path


def _by_code(rows: list[dict], key: str) -> dict[str, dict]:
    return {str(row.get(key, "")).strip(): row for row in rows if str(row.get(key, "")).strip()}


def _is_common_stock_code(code: str) -> bool:
    return code.isdigit() and len(code) == 4 and not code.startswith("0")


def _to_float(value) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "").strip()
    if not text or text in {"--", "N/A", "NaN"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _roc_date_to_iso(value: str) -> str:
    text = str(value).strip()
    if len(text) != 7 or not text.isdigit():
        return text
    year = int(text[:3]) + 1911
    return f"{year:04d}-{text[3:5]}-{text[5:7]}"
