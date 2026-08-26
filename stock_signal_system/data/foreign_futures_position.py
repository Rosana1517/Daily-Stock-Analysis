"""外資(及陸資)臺股期貨未平倉部位, from TAIFEX's official OpenAPI.

Endpoint documented at https://openapi.taifex.com.tw/swagger.json under
MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate
(三大法人-區分各期貨契約-依日期). It only ever returns the latest available
trading day — there is no historical date parameter — so this module reports
a single-day snapshot with a soft caution note rather than a multi-day trend.

The methodology this integrates explicitly warns against reading a large
foreign net-short position as bearish on its own: it is commonly an
arbitrage/hedge position paired with leveraged-ETF (e.g. 00631L) creation
flows, not a directional bet. This module's description text reflects that
caution instead of emitting a naive bullish/bearish verdict."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient

TAIFEX_URL = "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"
TAIEX_FUTURES_CONTRACT_CODE = "臺股期貨"
FOREIGN_INVESTOR_ITEM = "外資及陸資"

# Large-net-short caution threshold (contracts), per the methodology's own
# example range ("8萬至9萬口").
LARGE_NET_SHORT_THRESHOLD_CONTRACTS = 50_000

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


@dataclass(frozen=True)
class ForeignFuturesPosition:
    trade_date: date
    long_contracts: int
    short_contracts: int
    net_contracts: int  # long - short; negative = net short
    net_value_thousands: float
    caution_note: str


def fetch_foreign_taiex_futures_position(cache_dir: Path) -> ForeignFuturesPosition | None:
    client = RateLimitedHttpClient(cache_dir=cache_dir / "taifex_futures", min_interval_seconds=1.0)
    rows = client.get_json(
        TAIFEX_URL,
        headers=_HEADERS,
        cache_key="taifex_foreign_taiex_futures",
        ttl_seconds=3600,
    )
    return _parse_rows(rows)


def _parse_rows(rows: list[dict]) -> ForeignFuturesPosition | None:
    for row in rows or []:
        if row.get("ContractCode") != TAIEX_FUTURES_CONTRACT_CODE or row.get("Item") != FOREIGN_INVESTOR_ITEM:
            continue
        try:
            trade_date = _parse_yyyymmdd(str(row.get("Date", "")))
            net_contracts = int(str(row.get("OpenInterest(Net)", "0")).replace(",", ""))
            long_contracts = int(str(row.get("OpenInterest(Long)", "0")).replace(",", ""))
            short_contracts = int(str(row.get("OpenInterest(Short)", "0")).replace(",", ""))
            net_value_thousands = float(str(row.get("ContractValueofOpenInterest(Net)(Thousands)", "0")).replace(",", ""))
        except (TypeError, ValueError):
            return None
        if trade_date is None:
            return None
        return ForeignFuturesPosition(
            trade_date=trade_date,
            long_contracts=long_contracts,
            short_contracts=short_contracts,
            net_contracts=net_contracts,
            net_value_thousands=net_value_thousands,
            caution_note=_describe_position(net_contracts),
        )
    return None


def _describe_position(net_contracts: int) -> str:
    if net_contracts <= -LARGE_NET_SHORT_THRESHOLD_CONTRACTS:
        return (
            "外資臺股期貨淨空單處於相對高檔，惟常見成因是搭配槓桿型ETF(如正2)"
            "申購潮的無風險套利避險部位，未必代表看空後市，不宜單獨解讀為崩盤前兆。"
        )
    if net_contracts >= LARGE_NET_SHORT_THRESHOLD_CONTRACTS:
        return "外資臺股期貨呈現顯著淨多單，仍建議搭配其他指標綜合判斷方向。"
    return "外資臺股期貨未平倉部位方向性尚不明顯。"


def _parse_yyyymmdd(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
