"""政治人物(立委)持股觀察名單。

資料來源：legislator-wealth.tw 的公開 JSON API(MIT 授權，資料解析自監察院公報的
公職人員財產申報)。**這份資料本身是落後的**：定期申報一年一次(每年 11 月)，
公報刊出還要再晚幾個月，所以拿到的是「約一年前的持股」，不是他們最近的買賣。

因此這裡只把它當成「觀察名單」：持股市值最高的前 N 位立委、單一部位市值達門檻的
上市櫃股票。每天由既有的進場訊號(☆/★/◆ + 反追高)判斷名單裡哪檔「現在」適合
進場，進場時機是我們自己的判斷，不代表政治人物近期有買賣。

任何抓取/解析失敗都回傳空名單並印 warning，絕不中斷每日排程。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient

LEGISLATORS_API_URL = "https://legislator-wealth.tw/api/legislators.json"
TOP_N_POLITICIANS = 5
# 排除零股與小部位(例如配股留下的 27 股)，只看有實際份量的持股。
MIN_HOLDING_MARKET_VALUE = 1_000_000
# 申報資料一年才更新一次，半天快取足夠，也避免每天多次重複打對方的 API。
CACHE_TTL_SECONDS = 12 * 3600


@dataclass(frozen=True)
class PoliticianHolding:
    symbol: str  # 平台格式，例如 2330.TW / 6488.TWO
    code: str
    name: str
    holders: tuple[str, ...]  # 依持有市值由大到小
    market_value: float  # 名單內立委合計的估計市值
    declaration_date: str  # 持有人中最新的申報日


def fetch_legislators(cache_dir: Path) -> list[dict]:
    client = RateLimitedHttpClient(cache_dir=cache_dir / "politician_holdings", min_interval_seconds=1.0)
    data = client.get_json(
        LEGISLATORS_API_URL,
        headers={"Accept": "application/json"},
        cache_key="legislators",
        ttl_seconds=CACHE_TTL_SECONDS,
    )
    return data if isinstance(data, list) else list(data.get("results", []))


def load_universe_markets(universe_path: Path | None) -> dict[str, str]:
    """股票代號 → 市場(tse/otc)，用來組出 .TW / .TWO。不在名單內的(興櫃、下市)不納入。"""
    if not universe_path or not universe_path.exists():
        return {}
    with universe_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            str(row.get("symbol", "")).strip(): str(row.get("market", "")).strip().lower()
            for row in csv.DictReader(handle)
            if str(row.get("symbol", "")).strip()
        }


def build_politician_pool(
    legislators: list[dict],
    universe_markets: dict[str, str],
    top_n: int = TOP_N_POLITICIANS,
    min_market_value: float = MIN_HOLDING_MARKET_VALUE,
) -> dict[str, PoliticianHolding]:
    ranked = sorted(
        legislators,
        key=lambda item: float((item.get("stockSummary") or {}).get("estimatedMarketValueTotal") or 0),
        reverse=True,
    )[:top_n]
    by_code: dict[str, dict] = {}
    for legislator in ranked:
        holder = str(legislator.get("name", "")).strip()
        declared = str(legislator.get("latestDeclarationDate") or "")
        for holding in legislator.get("holdings") or []:
            code = str(holding.get("stockCode") or "").strip()
            value = float(holding.get("marketValue") or 0)
            if holding.get("source") != "stock" or not code or code not in universe_markets:
                continue
            if value < min_market_value:
                continue
            entry = by_code.setdefault(code, {"name": str(holding.get("name", "")).strip(), "holders": {}, "dates": set()})
            entry["holders"][holder] = entry["holders"].get(holder, 0.0) + value
            entry["dates"].add(declared)
    pool: dict[str, PoliticianHolding] = {}
    for code, entry in by_code.items():
        suffix = "TWO" if universe_markets.get(code) in {"otc", "tpex", "two"} else "TW"
        symbol = f"{code}.{suffix}"
        holders = sorted(entry["holders"].items(), key=lambda kv: kv[1], reverse=True)
        pool[symbol] = PoliticianHolding(
            symbol=symbol,
            code=code,
            name=entry["name"],
            holders=tuple(name for name, _ in holders),
            market_value=sum(value for _, value in holders),
            declaration_date=max((d for d in entry["dates"] if d), default=""),
        )
    return dict(sorted(pool.items(), key=lambda kv: kv[1].market_value, reverse=True))


def load_politician_pool(cache_dir: Path, universe_path: Path | None) -> dict[str, PoliticianHolding]:
    try:
        pool = build_politician_pool(fetch_legislators(cache_dir), load_universe_markets(universe_path))
    except Exception as exc:  # 外部資料源，失敗只降級、不中斷排程
        print(f"warning: politician_pool_unavailable error={exc}", flush=True)
        return {}
    print(f"politician_pool_symbols={len(pool)}", flush=True)
    return pool
