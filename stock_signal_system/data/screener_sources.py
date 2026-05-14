from __future__ import annotations

import csv
import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path


TWSE_DIVIDEND_YIELD_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TWSE_EX_DIVIDEND_URL = "https://www.twse.com.tw/exchangeReport/TWT48U_ALL?response=open_data"
TPEX_DIVIDEND_YIELD_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate"
TPEX_EX_DIVIDEND_URL = "https://www.tpex.org.tw/www/zh-tw/bulletin/prePost"
LISTED_REVENUE_URL = "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv"
OTC_REVENUE_URL = "https://mopsfin.twse.com.tw/opendata/t187ap05_O.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,*/*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
}


@dataclass(frozen=True)
class ScreenerDataPaths:
    monthly_revenue_path: Path
    dividend_yield_path: Path
    ex_dividend_path: Path


def refresh_screener_data(
    data_dir: Path = Path("data"),
    common_stock_only: bool = True,
) -> ScreenerDataPaths:
    data_dir.mkdir(parents=True, exist_ok=True)
    monthly_revenue_path = build_monthly_revenue_yoy_csv(data_dir / "monthly_revenue_yoy.csv", common_stock_only)
    dividend_yield_path = build_dividend_yield_csv(data_dir / "dividend_yield.csv", common_stock_only)
    ex_dividend_path = build_ex_dividend_schedule_csv(data_dir / "ex_dividend_schedule.csv", common_stock_only)
    return ScreenerDataPaths(monthly_revenue_path, dividend_yield_path, ex_dividend_path)


def build_yfinance_ohlcv_csv(
    universe_path: Path,
    output_path: Path,
    period: str = "1y",
    batch_size: int = 50,
    sleep_seconds: float = 0.5,
) -> Path:
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("Install optional market dependencies first: pip install .[market]") from exc

    symbols = _load_yahoo_symbols(universe_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for batch in _chunks(symbols, batch_size):
            frame = yf.download(
                tickers=" ".join(batch),
                period=period,
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=False,
            )
            if frame.empty:
                time.sleep(sleep_seconds)
                continue
            for symbol in batch:
                if isinstance(frame.columns, pd.MultiIndex):
                    if symbol not in frame.columns.get_level_values(0):
                        continue
                    symbol_frame = frame[symbol]
                else:
                    symbol_frame = frame
                for index, row in symbol_frame.dropna(subset=["Close"]).iterrows():
                    writer.writerow(
                        {
                            "symbol": symbol,
                            "date": index.strftime("%Y-%m-%d"),
                            "open": _number_text(row.get("Open")),
                            "high": _number_text(row.get("High")),
                            "low": _number_text(row.get("Low")),
                            "close": _number_text(row.get("Close")),
                            "volume": _number_text(row.get("Volume")),
                        }
                    )
            time.sleep(sleep_seconds)
    return output_path


def build_monthly_revenue_yoy_csv(output_path: Path, common_stock_only: bool = True) -> Path:
    rows = []
    rows.extend(_monthly_revenue_rows(LISTED_REVENUE_URL, "tse", common_stock_only))
    rows.extend(_monthly_revenue_rows(OTC_REVENUE_URL, "otc", common_stock_only))
    _write_csv(
        output_path,
        ["symbol", "market", "name", "industry", "revenue_month", "revenue_growth_yoy", "source"],
        rows,
    )
    return output_path


def build_dividend_yield_csv(output_path: Path, common_stock_only: bool = True) -> Path:
    rows = []
    rows.extend(_twse_dividend_yield_rows(common_stock_only))
    rows.extend(_tpex_dividend_yield_rows(common_stock_only))
    _write_csv(
        output_path,
        [
            "symbol",
            "market",
            "name",
            "dividend_yield",
            "cash_dividend",
            "dividend_year",
            "source_date",
            "source",
        ],
        rows,
    )
    return output_path


def build_ex_dividend_schedule_csv(output_path: Path, common_stock_only: bool = True) -> Path:
    rows = []
    rows.extend(_twse_ex_dividend_rows(common_stock_only))
    rows.extend(_tpex_ex_dividend_rows(common_stock_only))
    _write_csv(
        output_path,
        ["symbol", "market", "name", "ex_dividend_date", "ex_right_type", "cash_dividend", "source"],
        rows,
    )
    return output_path


def _monthly_revenue_rows(url: str, market: str, common_stock_only: bool) -> list[dict]:
    text = _fetch_text(url, "utf-8-sig")
    output = []
    for row in csv.DictReader(text.splitlines()):
        symbol = str(row.get("公司代號") or "").strip()
        if common_stock_only and not _is_common_stock(symbol):
            continue
        output.append(
            {
                "symbol": symbol,
                "market": market,
                "name": str(row.get("公司名稱") or "").strip(),
                "industry": str(row.get("產業別") or "").strip(),
                "revenue_month": str(row.get("資料年月") or "").strip(),
                "revenue_growth_yoy": _number_text(row.get("營業收入-去年同月增減(%)")),
                "source": "MOPS monthly revenue",
            }
        )
    return output


def _twse_dividend_yield_rows(common_stock_only: bool) -> list[dict]:
    rows = json.loads(_fetch_text(TWSE_DIVIDEND_YIELD_URL, "utf-8-sig"))
    output = []
    for row in rows:
        symbol = str(row.get("Code") or "").strip()
        if common_stock_only and not _is_common_stock(symbol):
            continue
        output.append(
            {
                "symbol": symbol,
                "market": "tse",
                "name": str(row.get("Name") or "").strip(),
                "dividend_yield": _number_text(row.get("DividendYield")),
                "cash_dividend": "",
                "dividend_year": "",
                "source_date": _roc_date_to_iso(str(row.get("Date") or "")),
                "source": "TWSE BWIBBU_ALL",
            }
        )
    return output


def _tpex_dividend_yield_rows(common_stock_only: bool) -> list[dict]:
    payload = json.loads(_fetch_text(TPEX_DIVIDEND_YIELD_URL, "utf-8-sig"))
    table = payload.get("tables", [{}])[0]
    fields = table.get("fields", [])
    output = []
    for item in table.get("data", []):
        row = dict(zip(fields, item))
        symbol = str(row.get("股票代號") or "").strip()
        if common_stock_only and not _is_common_stock(symbol):
            continue
        output.append(
            {
                "symbol": symbol,
                "market": "otc",
                "name": str(row.get("公司名稱") or "").strip(),
                "dividend_yield": _number_text(row.get("殖利率(%)")),
                "cash_dividend": _number_text(row.get("每股股利")),
                "dividend_year": str(row.get("股利年度") or "").strip(),
                "source_date": _roc_slash_date_to_iso(str(table.get("date") or "")),
                "source": "TPEx peQryDate",
            }
        )
    return output


def _twse_ex_dividend_rows(common_stock_only: bool) -> list[dict]:
    text = _fetch_text(TWSE_EX_DIVIDEND_URL, "utf-8-sig")
    output = []
    for row in csv.DictReader(text.splitlines()):
        symbol = str(row.get("股票代號") or "").strip()
        if common_stock_only and not _is_common_stock(symbol):
            continue
        output.append(
            {
                "symbol": symbol,
                "market": "tse",
                "name": str(row.get("名稱") or "").strip(),
                "ex_dividend_date": _roc_text_date_to_iso(str(row.get("除權息日期") or "")),
                "ex_right_type": str(row.get("除權息") or "").strip(),
                "cash_dividend": _number_text(row.get("現金股利")),
                "source": "TWSE TWT48U_ALL",
            }
        )
    return output


def _tpex_ex_dividend_rows(common_stock_only: bool) -> list[dict]:
    payload = json.loads(_fetch_text(TPEX_EX_DIVIDEND_URL, "utf-8-sig"))
    table = payload.get("tables", [{}])[0]
    fields = table.get("fields", [])
    output = []
    for item in table.get("data", []):
        row = dict(zip(fields, item))
        symbol = str(row.get("代號") or "").strip()
        if common_stock_only and not _is_common_stock(symbol):
            continue
        output.append(
            {
                "symbol": symbol,
                "market": "otc",
                "name": str(row.get("名稱") or "").strip(),
                "ex_dividend_date": _roc_slash_date_to_iso(str(row.get("除權息日期") or "")),
                "ex_right_type": str(row.get("除權息") or "").strip(),
                "cash_dividend": _number_text(row.get("現金股利")),
                "source": "TPEx prePost",
            }
        )
    return output


def _fetch_text(url: str, encoding: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
    return data.decode(encoding, errors="replace")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item.get("market", ""), item.get("symbol", ""))):
            writer.writerow(row)


def _load_yahoo_symbols(universe_path: Path) -> list[str]:
    output = []
    with universe_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol") or "").strip()
            market = str(row.get("market") or "").strip().lower()
            if not _is_common_stock(symbol):
                continue
            suffix = "TWO" if market == "otc" else "TW"
            output.append(f"{symbol}.{suffix}")
    return sorted(set(output))


def _chunks(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _is_common_stock(symbol: str) -> bool:
    return symbol.isdigit() and len(symbol) == 4 and not symbol.startswith("0")


def _number_text(value: object) -> str:
    text = str(value or "").replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "--", "N/A", "NaN", "尚未公告", "待公告實際收益分配金額"}:
        return ""
    try:
        return str(float(text))
    except ValueError:
        return ""


def _roc_date_to_iso(value: str) -> str:
    text = value.strip()
    if len(text) == 7 and text.isdigit():
        return f"{int(text[:3]) + 1911:04d}-{text[3:5]}-{text[5:7]}"
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _roc_slash_date_to_iso(value: str) -> str:
    text = value.strip()
    parts = text.split("/")
    if len(parts) == 3 and parts[0].isdigit():
        year = int(parts[0])
        if year < 1911:
            year += 1911
        return f"{year:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    return text


def _roc_text_date_to_iso(value: str) -> str:
    text = value.strip()
    if "年" in text and "月" in text and "日" in text:
        year_text, rest = text.split("年", 1)
        month_text, day_text = rest.split("月", 1)
        day_text = day_text.replace("日", "")
        year = int(year_text)
        if year < 1911:
            year += 1911
        return f"{year:04d}-{int(month_text):02d}-{int(day_text):02d}"
    return _roc_slash_date_to_iso(text)
