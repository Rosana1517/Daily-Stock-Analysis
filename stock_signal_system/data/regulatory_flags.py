from __future__ import annotations

import csv
import re
from datetime import date, timedelta
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient


TWSE_NOTICE_URL = "https://openapi.twse.com.tw/v1/announcement/notice"
TWSE_PUNISH_URL = "https://openapi.twse.com.tw/v1/announcement/punish"
TPEX_DISPOSAL_URL = "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
}

# Attention designations are day-scoped; treat recent ones as active.
_ATTENTION_ACTIVE_DAYS = 7


def build_tw_regulatory_flags_csv(output_path: Path, cache_dir: Path, as_of: date | None = None) -> Path:
    """Fetch TWSE notice/punish and TPEx disposal lists into a blacklist CSV.

    Each source failure is warned and skipped so one broken endpoint never
    blocks the rest of the blacklist.
    """
    today = as_of or date.today()
    client = RateLimitedHttpClient(cache_dir=cache_dir / "regulatory", min_interval_seconds=1.0)
    rows: list[dict[str, str]] = []

    try:
        for item in client.get_json(TWSE_PUNISH_URL, headers=_HEADERS, cache_key="twse_punish", ttl_seconds=1800):
            symbol = str(item.get("Code", "")).strip()
            if not _is_common_stock_code(symbol):
                continue
            end = _parse_period_end(str(item.get("DispositionPeriod", "")))
            if end is not None and end < today:
                continue
            rows.append({"symbol": symbol, "flag": "disposition", "source": "twse_punish", "end_date": end.isoformat() if end else ""})
    except Exception as exc:
        print(f"warning: regulatory_twse_punish_failed={exc}", flush=True)

    try:
        for item in client.get_json(TPEX_DISPOSAL_URL, headers=_HEADERS, cache_key="tpex_disposal", ttl_seconds=1800):
            symbol = str(item.get("SecuritiesCompanyCode", "")).strip()
            if not _is_common_stock_code(symbol):
                continue
            end = _parse_period_end(str(item.get("DispositionPeriod", "")))
            if end is not None and end < today:
                continue
            rows.append({"symbol": symbol, "flag": "disposition", "source": "tpex_disposal", "end_date": end.isoformat() if end else ""})
    except Exception as exc:
        print(f"warning: regulatory_tpex_disposal_failed={exc}", flush=True)

    try:
        for item in client.get_json(TWSE_NOTICE_URL, headers=_HEADERS, cache_key="twse_notice", ttl_seconds=1800):
            symbol = str(item.get("Code", "")).strip()
            if not _is_common_stock_code(symbol):
                continue
            announced = _parse_roc_date(str(item.get("Date", "")))
            if announced is not None and announced < today - timedelta(days=_ATTENTION_ACTIVE_DAYS):
                continue
            rows.append({"symbol": symbol, "flag": "attention", "source": "twse_notice", "end_date": ""})
    except Exception as exc:
        print(f"warning: regulatory_twse_notice_failed={exc}", flush=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "flag", "source", "end_date"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"regulatory_flags_rows={len(rows)}", flush=True)
    return output_path


def load_regulatory_flag_symbols(path: Path) -> dict[str, str]:
    """Return {symbol: flag} for currently flagged stocks; empty dict when unavailable."""
    if not path.exists():
        return {}
    flags: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = str(row.get("symbol", "")).strip()
                flag = str(row.get("flag", "")).strip()
                if not symbol or not flag:
                    continue
                # disposition dominates attention when both present
                if flags.get(symbol) != "disposition":
                    flags[symbol] = flag
    except OSError:
        return {}
    return flags


def _is_common_stock_code(code: str) -> bool:
    return code.isdigit() and len(code) == 4


def _parse_period_end(period: str) -> date | None:
    # Formats seen: "115/07/03～115/07/16", "1150710~1150723"
    parts = re.split(r"[~～]", period.strip())
    if len(parts) != 2:
        return None
    return _parse_roc_date(parts[1].strip())


def _parse_roc_date(value: str) -> date | None:
    text = value.strip()
    match = re.fullmatch(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", text)
    if match:
        return _roc(date_parts=(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    if re.fullmatch(r"\d{7}", text):
        return _roc(date_parts=(int(text[:3]), int(text[3:5]), int(text[5:7])))
    return None


def _roc(date_parts: tuple[int, int, int]) -> date | None:
    year, month, day = date_parts
    try:
        return date(year + 1911, month, day)
    except ValueError:
        return None
