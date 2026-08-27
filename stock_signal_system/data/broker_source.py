from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient


HISTOCK_BRANCH_URL = "https://histock.tw/stock/branch.aspx"

# HiStock 分點頁面偶爾會回傳一個 sentinel 空版型（cfdate 停在 2017.10.18、
# jsonDatas 為空陣列），即使該日已公告也一樣，這不是我方快取或正則的問題，
# 是網站當下狀態異常（見 project_state.md 2026-08-27 查證記錄）。這種情況
# 短暫重試往往能換到另一台正常回應的伺服器節點，因此對「降級」結果做有限
# 次數的重試，並清掉那次的快取避免重試又讀到同一份壞回應。
HISTOCK_BROKER_MAX_ATTEMPTS = 3
HISTOCK_BROKER_RETRY_DELAY_SECONDS = 4.0

_UPDATED_AT_RE = re.compile(r"更新時間[:：]\s*(\d{4})[./-](\d{2})[./-](\d{2})")
_ROW_RE = re.compile(
    # 數字欄位用 * 而非 +：真實頁面裡，一檔券商當天若只出現在買方或賣方，
    # 另一側的買/賣/均價儲存格會是完全空的 <td></td>（不是 0，是空字串）。
    # 原本用 + 要求至少一位數字，遇到空儲存格整列就配不上，導致 finditer
    # 從下一列重新配對，結果把好幾列的券商名稱黏在一起（見 project_state.md
    # 2026-08-27 的查證記錄）。
    r"<tr[^>]*>\s*"
    r"<td>\s*<a[^>]*?/stock/brokertrace\.aspx\?bno=[^\"']+(?:&amp;|&)no=\d+[^\"']*\"[^>]*>(?P<sell_broker>.*?)</a>\s*</td>\s*"
    r"<td[^>]*>(?P<sell_buy>[\d,]*)</td>\s*"
    r"<td[^>]*>(?P<sell_sell>[\d,]*)</td>\s*"
    r"<td[^>]*>(?P<sell_net>-?[\d,]*)</td>\s*"
    r"<td[^>]*>(?P<sell_avg>[\d,.]*)</td>\s*"
    r"<td>\s*<a[^>]*?/stock/brokertrace\.aspx\?bno=[^\"']+(?:&amp;|&)no=\d+[^\"']*\"[^>]*>(?P<buy_broker>.*?)</a>\s*</td>\s*"
    r"<td[^>]*>(?P<buy_buy>[\d,]*)</td>\s*"
    r"<td[^>]*>(?P<buy_sell>[\d,]*)</td>\s*"
    r"<td[^>]*>(?P<buy_net>-?[\d,]*)</td>\s*"
    r"<td[^>]*>(?P<buy_avg>[\d,.]*)</td>\s*"
    r"</tr>",
    flags=re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class BrokerBranchTrade:
    broker: str
    buy_shares: int
    sell_shares: int
    net_shares: int
    average_price: float


@dataclass(frozen=True)
class BrokerBranchSnapshot:
    symbol: str
    trade_date: date | None
    buy_trades: tuple[BrokerBranchTrade, ...]
    sell_trades: tuple[BrokerBranchTrade, ...]
    source_url: str
    source_status: str


def fetch_histock_branch_snapshot(
    symbol: str,
    cache_dir: Path,
    trade_date: date | None = None,
    max_attempts: int = HISTOCK_BROKER_MAX_ATTEMPTS,
    retry_delay_seconds: float = HISTOCK_BROKER_RETRY_DELAY_SECONDS,
) -> BrokerBranchSnapshot:
    client = RateLimitedHttpClient(cache_dir=cache_dir / "histock_branch", min_interval_seconds=1.2)
    stock_no = str(symbol).split(".")[0].strip()
    params = {"no": stock_no}
    if trade_date is not None:
        day = trade_date.strftime("%Y%m%d")
        params["from"] = day
        params["to"] = day
    cache_key = f"histock_branch_{stock_no}_{trade_date.isoformat() if trade_date else 'latest'}"
    cache_path = client.cache_dir / f"{cache_key}.cache"
    source_url = _build_url(params)

    snapshot: BrokerBranchSnapshot | None = None
    for attempt in range(max(1, max_attempts)):
        html_text = client.get_text(
            HISTOCK_BRANCH_URL,
            params=params,
            headers={"Referer": "https://histock.tw/", "Accept": "text/html,application/xhtml+xml"},
            cache_key=cache_key,
            ttl_seconds=1800,
        )
        snapshot = parse_histock_branch_html(html_text, stock_no, source_url, requested_date=trade_date)
        if snapshot.source_status == "ok" or attempt == max_attempts - 1:
            return snapshot
        print(
            f"warning: histock_branch_degraded_retry symbol={stock_no} date={trade_date} attempt={attempt + 1}",
            flush=True,
        )
        cache_path.unlink(missing_ok=True)
        time.sleep(retry_delay_seconds)
    return snapshot


def parse_histock_branch_html(
    html_text: str,
    symbol: str,
    source_url: str,
    requested_date: date | None = None,
) -> BrokerBranchSnapshot:
    updated_at = _extract_updated_at(html_text) or requested_date
    buy_trades: list[BrokerBranchTrade] = []
    sell_trades: list[BrokerBranchTrade] = []

    for match in _ROW_RE.finditer(html_text):
        sell_broker = _clean_text(match.group("sell_broker"))
        buy_broker = _clean_text(match.group("buy_broker"))
        if sell_broker:
            sell_trades.append(
                BrokerBranchTrade(
                    broker=sell_broker,
                    buy_shares=_int(match.group("sell_buy")),
                    sell_shares=_int(match.group("sell_sell")),
                    net_shares=_int(match.group("sell_net")),
                    average_price=_float(match.group("sell_avg")),
                )
            )
        if buy_broker:
            buy_trades.append(
                BrokerBranchTrade(
                    broker=buy_broker,
                    buy_shares=_int(match.group("buy_buy")),
                    sell_shares=_int(match.group("buy_sell")),
                    net_shares=_int(match.group("buy_net")),
                    average_price=_float(match.group("buy_avg")),
                )
            )

    source_status = "ok" if buy_trades or sell_trades else "degraded"
    return BrokerBranchSnapshot(
        symbol=symbol,
        trade_date=updated_at,
        buy_trades=tuple(buy_trades),
        sell_trades=tuple(sell_trades),
        source_url=source_url,
        source_status=source_status,
    )


def _build_url(params: dict[str, str]) -> str:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{HISTOCK_BRANCH_URL}?{query}"


def _extract_updated_at(html_text: str) -> date | None:
    match = _UPDATED_AT_RE.search(html_text)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<.*?>", "", value or ""))).strip()


def _int(value: str) -> int:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0
    return int(float(text))


def _float(value: str) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0.0
    return float(text)
