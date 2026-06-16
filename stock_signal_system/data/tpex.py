from __future__ import annotations

import csv
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient


BASE_URL = "https://www.tpex.org.tw/openapi/v1"
ENDPOINTS = {
    "quotes": "/tpex_mainboard_quotes",
    "peratio": "/tpex_mainboard_peratio_analysis",
}


def fetch_tpex_dataset(name: str, cache_dir: Path) -> list[dict]:
    if name not in ENDPOINTS:
        raise ValueError(f"Unknown TPEx dataset: {name}")
    client = RateLimitedHttpClient(cache_dir=cache_dir / "tpex", min_interval_seconds=1.0)
    data = client.get_json(
        BASE_URL + ENDPOINTS[name],
        headers={"Accept": "application/json,text/plain,*/*", "Referer": "https://www.tpex.org.tw/"},
        cache_key=f"tpex_{name}",
        ttl_seconds=1800,
    )
    if not isinstance(data, list):
        raise RuntimeError(f"TPEx dataset {name} returned unexpected payload: {type(data).__name__}")
    return data


def build_tpex_stock_csv(output_path: Path, cache_dir: Path) -> Path:
    quotes = _by_code(fetch_tpex_dataset("quotes", cache_dir))
    valuation = _by_code(fetch_tpex_dataset("peratio", cache_dir))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_stock_fieldnames())
        writer.writeheader()
        for code, row in sorted(quotes.items()):
            if not _is_common_stock_code(code):
                continue
            close = _to_float(_get(row, "Close"))
            volume = _to_float(_get(row, "TradingShares"))
            writer.writerow(
                {
                    "symbol": code,
                    "market": "otc",
                    "name": _get(row, "CompanyName"),
                    "industry": "上櫃",
                    "price": close,
                    "price_20d_ago": close,
                    "volume": volume,
                    "avg_volume_20d": volume,
                    "revenue_growth_yoy": 0,
                    "gross_margin": 0,
                    "operating_margin": 0,
                    "free_cash_flow_margin": 0,
                    "debt_to_equity": 0,
                    "pe_ratio": _to_float(_get(valuation.get(code, {}), "PriceEarningRatio")),
                    "notes": "TPEx OpenAPI OTC daily snapshot.",
                }
            )
    return output_path


def build_tpex_daily_price_csv(output_path: Path, cache_dir: Path) -> Path:
    quotes = fetch_tpex_dataset("quotes", cache_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for row in quotes:
            code = _code(row)
            if not _is_common_stock_code(code):
                continue
            writer.writerow(
                {
                    "symbol": code,
                    "date": _date_to_iso(_get(row, "Date")),
                    "open": _to_float(_get(row, "Open")),
                    "high": _to_float(_get(row, "High")),
                    "low": _to_float(_get(row, "Low")),
                    "close": _to_float(_get(row, "Close")),
                    "volume": _to_float(_get(row, "TradingShares")),
                }
            )
    return output_path


def combine_csv_files(input_paths: list[Path], output_path: Path, key_field: str = "symbol") -> Path:
    rows_by_key: dict[str, dict] = {}
    fieldnames: list[str] = []
    for path in input_paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = _merge_fieldnames(fieldnames, list(reader.fieldnames or []))
            for row in reader:
                key = str(row.get(key_field, "")).strip()
                if key:
                    existing = rows_by_key.get(key, {})
                    merged = dict(existing)
                    merged.update({field: value for field, value in row.items() if value not in (None, "")})
                    rows_by_key[key] = merged
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(rows_by_key):
            writer.writerow({field: rows_by_key[key].get(field, "") for field in fieldnames})
    return output_path


def _stock_fieldnames() -> list[str]:
    return [
        "symbol",
        "market",
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


def _merge_fieldnames(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    for field in incoming:
        if field not in merged:
            merged.append(field)
    return merged


def _by_code(rows: list[dict]) -> dict[str, dict]:
    return {code: row for row in rows if (code := _code(row))}


def _code(row: dict) -> str:
    return _get(row, "SecuritiesCompanyCode")


def _get(row: dict, *names: str) -> str:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = row.get(name)
        if value is None:
            value = lowered.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _is_common_stock_code(code: str) -> bool:
    return code.isdigit() and len(code) == 4 and not code.startswith("0")


def _to_float(value) -> float:
    text = str(value or "").replace(",", "").replace("%", "").strip()
    if not text or text in {"--", "N/A", "NaN", "-"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _date_to_iso(value: str) -> str:
    text = str(value).strip().replace("/", "").replace("-", "")
    if len(text) == 7 and text.isdigit():
        year = int(text[:3]) + 1911
        return f"{year:04d}-{text[3:5]}-{text[5:7]}"
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return str(value).strip()
