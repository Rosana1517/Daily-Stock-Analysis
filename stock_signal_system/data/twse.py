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

FALLBACK_INDUSTRIES = {
    "23": "半導體",
    "24": "半導體",
    "30": "電子零組件",
    "31": "電子零組件",
    "32": "電子通路",
    "33": "光電",
    "34": "電腦及週邊",
    "35": "電腦及週邊",
    "36": "網通",
    "37": "電子零組件",
    "15": "電機機械",
    "16": "電器電纜",
    "17": "化學生技",
    "20": "鋼鐵",
    "26": "航運",
    "28": "金融",
    "29": "貿易百貨",
}

INDUSTRY_CODE_NAMES = {
    "01": "水泥",
    "02": "食品",
    "03": "塑膠",
    "04": "紡織",
    "05": "電機機械",
    "06": "電器電纜",
    "07": "化學生技",
    "08": "玻璃陶瓷",
    "09": "造紙",
    "10": "鋼鐵",
    "11": "橡膠",
    "12": "汽車",
    "14": "建材營造",
    "15": "航運",
    "16": "觀光餐旅",
    "17": "金融",
    "18": "貿易百貨",
    "20": "其他",
    "21": "化學",
    "22": "生技醫療",
    "23": "油電燃氣",
    "24": "半導體",
    "25": "電腦及週邊",
    "26": "光電",
    "27": "通信網路",
    "28": "電子零組件",
    "29": "電子通路",
    "30": "資訊服務",
    "31": "其他電子",
    "32": "文化創意",
    "33": "農業科技",
    "34": "電子商務",
    "80": "管理股票",
}


def fetch_twse_dataset(name: str, cache_dir: Path) -> list[dict]:
    if name not in ENDPOINTS:
        raise ValueError(f"Unknown TWSE dataset: {name}")
    client = RateLimitedHttpClient(cache_dir=cache_dir / "twse", min_interval_seconds=1.0)
    data = client.get_json(
        BASE_URL + ENDPOINTS[name],
        cache_key=f"twse_{name}",
        ttl_seconds=1800,
    )
    if not isinstance(data, list):
        raise RuntimeError(f"TWSE dataset {name} returned unexpected payload: {type(data).__name__}")
    return data


def build_twse_stock_csv(output_path: Path, cache_dir: Path) -> Path:
    daily = _by_code(fetch_twse_dataset("daily_all", cache_dir))
    avg = _by_code(fetch_twse_dataset("daily_avg", cache_dir))
    valuation = _by_code(fetch_twse_dataset("valuation", cache_dir))
    basic = _by_code(fetch_twse_dataset("company_basic", cache_dir))
    revenue = _by_code(fetch_twse_dataset("monthly_revenue", cache_dir))

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
            close = _to_float(_get(row, "ClosingPrice", "收盤價", "收盤價(元)"))
            monthly_avg = _to_float(_get(avg_row, "MonthlyAveragePrice", "月平均價")) or close
            name = _get(row, "Name", "證券名稱", "公司名稱") or _get(basic_row, "公司名稱", "Name")
            industry = _industry_for(code, basic_row, revenue_row)
            writer.writerow(
                {
                    "symbol": code,
                    "name": name,
                    "industry": industry,
                    "price": close,
                    "price_20d_ago": monthly_avg,
                    "volume": _to_float(_get(row, "TradeVolume", "成交股數")),
                    "avg_volume_20d": _to_float(_get(row, "TradeVolume", "成交股數")),
                    "revenue_growth_yoy": _to_float(
                        _get(revenue_row, "去年同月增減(%)", "去年同月增減％", "YoY")
                    ),
                    "gross_margin": 0,
                    "operating_margin": 0,
                    "free_cash_flow_margin": 0,
                    "debt_to_equity": 0,
                    "pe_ratio": _to_float(_get(valuation_row, "PEratio", "本益比")),
                    "notes": "TWSE OpenAPI daily snapshot; margin, cash-flow, leverage fields require FinMind or financial statements.",
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
            code = _code(row)
            if not _is_common_stock_code(code):
                continue
            writer.writerow(
                {
                    "symbol": code,
                    "date": _roc_date_to_iso(_get(row, "Date", "日期")),
                    "open": _to_float(_get(row, "OpeningPrice", "開盤價")),
                    "high": _to_float(_get(row, "HighestPrice", "最高價")),
                    "low": _to_float(_get(row, "LowestPrice", "最低價")),
                    "close": _to_float(_get(row, "ClosingPrice", "收盤價")),
                    "volume": _to_float(_get(row, "TradeVolume", "成交股數")),
                }
            )
    return output_path


def build_twse_material_news_csv(output_path: Path, cache_dir: Path) -> Path:
    news = fetch_twse_dataset("material_news", cache_dir)
    basic = _by_code(fetch_twse_dataset("company_basic", cache_dir))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "title", "source", "body", "industries"])
        writer.writeheader()
        for row in news:
            code = _code(row)
            if not _is_common_stock_code(code):
                continue
            company = _get(row, "公司名稱", "公司簡稱", "Name")
            subject = _get(row, "主旨", "發言人", "公告事項")
            body = _get(row, "說明", "內容", "事實發生日")
            industry = _industry_for(code, basic.get(code, {}), {})
            writer.writerow(
                {
                    "date": _roc_date_to_iso(_get(row, "出表日期", "發言日期", "事實發生日")),
                    "title": f"{code} {company} {subject}".strip(),
                    "source": "TWSE material information",
                    "body": body,
                    "industries": industry,
                }
            )
    return output_path


def _by_code(rows: list[dict]) -> dict[str, dict]:
    return {code: row for row in rows if (code := _code(row))}


def _code(row: dict) -> str:
    return str(_get(row, "Code", "公司代號", "證券代號", "有價證券代號")).strip()


def _industry_for(code: str, basic_row: dict, revenue_row: dict) -> str:
    industry = _get(basic_row, "產業別", "產業名稱", "Industry") or _get(
        revenue_row, "產業別", "產業名稱", "Industry"
    )
    if industry:
        return INDUSTRY_CODE_NAMES.get(industry, industry)
    return FALLBACK_INDUSTRIES.get(code[:2], "其他")


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


def _is_common_stock_code(code: str) -> bool:
    return code.isdigit() and len(code) == 4 and not code.startswith("0")


def _to_float(value) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text in {"--", "N/A", "NaN", "-"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _roc_date_to_iso(value: str) -> str:
    text = str(value).strip().replace("/", "").replace("-", "")
    if len(text) == 7 and text.isdigit():
        year = int(text[:3]) + 1911
        return f"{year:04d}-{text[3:5]}-{text[5:7]}"
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return str(value).strip()
