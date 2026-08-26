"""台灣證券櫃檯買賣中心／證交所共同建置的「產業價值鏈資訊平台」
(ic.tpex.org.tw) 上中下游成分股對照表擷取，供 P8「產業鏈上中下游群體共識
判讀」使用。

沒有文件化的 JSON API，但該平台是傳統伺服器端渲染 PHP（非 SPA），資料直接
內嵌在 `introduce.php?ic={產業代碼}` 頁面的 HTML 裡，結構穩定、公開、無需
執行 JS 即可用純 HTTP GET 取得（詳見 PRD.md「P8 資料源查證結果」的逆向
確認過程）。同一頁同時內嵌：
1. 產業鏈圖（`chain-title-panel` 標出上／中／下游，`ic_link_{子分類代碼}`
   標出每個子分類屬於哪一層）
2. 每個子分類的成分股清單（`companyList_{子分類代碼}` 內含
   `company_basic.php?stk_code=` 連結，只有本國上市/上櫃/創櫃公司才有這個
   連結，知名外國企業連到外部官網，天然被排除）

產業鏈結構變動極慢（新增子分類是以年為單位，不是以天），因此呼叫端應使用
長 TTL（預設 30 天）快取，不需要每日重爬。"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient

BASE_URL = "https://ic.tpex.org.tw"
DEFAULT_TTL_SECONDS = 30 * 24 * 3600
CONSENSUS_MIN_MEMBERS = 2

# 2026-08-26 由 ic.tpex.org.tw 首頁導覽列逐一列出（見 PRD.md P8）。「綠色能源」
# 子樹在首頁用另一種尚未連結 introduce.php 的導覽方式呈現，本次刻意不猜測其
# 網址，暫不納入——寧可誠實少一塊,也不要編造錯誤的產業代碼。
INDUSTRY_CHAIN_CODES: tuple[str, ...] = (
    "D000", "C100", "C200", "C300", "C400",
    "5100", "5200", "5300", "5400", "5500", "5600", "5700", "5800", "4100",
    "6000", "R300", "J000", "I000", "K000", "F000", "G000", "H000", "L000",
    "B000", "1000", "M000", "N000", "O000", "P000", "2000", "Q000", "3000",
    "R000", "S000", "T000", "U000", "V000", "W000", "Y000", "X000",
)

INDUSTRY_CHAIN_NAMES: dict[str, str] = {
    "D000": "半導體", "C100": "製藥", "C200": "醫療器材", "C300": "食品生技", "C400": "再生醫療",
    "5100": "區塊鏈", "5200": "金融科技", "5300": "人工智慧", "5400": "雲端運算",
    "5500": "資通訊安全", "5600": "大數據", "5700": "體驗科技", "5800": "運動科技", "4100": "太空衛星科技",
    "6000": "自動化", "R300": "電子商務", "J000": "被動元件", "I000": "通信網路", "K000": "連接器",
    "F000": "電腦及週邊設備", "G000": "平面顯示器", "H000": "觸控面板", "L000": "印刷電路板",
    "B000": "休閒娛樂", "1000": "水泥", "M000": "食品", "N000": "石化及塑橡膠", "O000": "紡織",
    "P000": "電機機械", "2000": "造紙", "Q000": "鋼鐵", "3000": "汽車", "R000": "軟體服務",
    "S000": "建材營造", "T000": "交通運輸及航運", "U000": "金融", "V000": "貿易百貨",
    "W000": "油電燃氣", "Y000": "文化創意", "X000": "其他",
}

_TOKEN_RE = re.compile(
    r'<div class="chain-title-panel">(上游|中游|下游)</div>'
    r'|<div id="ic_link_([A-Za-z0-9]+)"[^>]*>(.*?)</div>',
    re.S,
)
_COMPANY_BLOCK_SPLIT_RE = re.compile(r'<div id="companyList_([A-Za-z0-9]+)"')
_COMPANY_LINK_RE = re.compile(r'<a href="company_basic\.php\?stk_code=(\d+)"[^>]*title="([^"]*)"')
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class IndustryChainMember:
    stock_code: str
    company_name: str
    ic_code: str
    tier: str  # 上游 / 中游 / 下游
    subcategory_code: str
    subcategory_name: str


@dataclass(frozen=True)
class ChainConsensusGroup:
    ic_code: str
    tier: str
    members: tuple[tuple[str, str], ...]  # (stock_code, company_name), sorted


def fetch_industry_chain_page(ic_code: str, cache_dir: Path, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    client = RateLimitedHttpClient(cache_dir)
    return client.get_text(
        f"{BASE_URL}/introduce.php",
        params={"ic": ic_code},
        cache_key=f"industry_chain_{ic_code}",
        ttl_seconds=ttl_seconds,
    )


def parse_industry_chain_html(html_text: str, ic_code: str) -> tuple[IndustryChainMember, ...]:
    """Pure parse of one introduce.php?ic=... page's HTML into member rows.

    Deduplicates on (subcategory_code, stock_code): the live site has been
    observed to repeat the same `id="companyList_{code}"` block (and hence
    the same company row) more than once on some pages (e.g. 聯發科 under
    D000/D100 appeared 10 times in one fetch) — almost certainly a rendering
    artifact on the source site rather than 10 distinct facts, so a stock is
    only counted once per subcategory here."""
    tier_by_subcode: dict[str, str] = {}
    name_by_subcode: dict[str, str] = {}
    current_tier: str | None = None
    for match in _TOKEN_RE.finditer(html_text):
        tier_label, subcode, raw_name = match.group(1), match.group(2), match.group(3)
        if tier_label:
            current_tier = tier_label
            continue
        if subcode and current_tier and subcode not in tier_by_subcode:
            tier_by_subcode[subcode] = current_tier
            name_by_subcode[subcode] = _clean_subcategory_name(raw_name or "")

    members: dict[tuple[str, str], IndustryChainMember] = {}
    parts = _COMPANY_BLOCK_SPLIT_RE.split(html_text)
    for i in range(1, len(parts), 2):
        subcode = parts[i]
        tier = tier_by_subcode.get(subcode)
        if tier is None:
            continue
        chunk = parts[i + 1] if i + 1 < len(parts) else ""
        subcategory_name = name_by_subcode.get(subcode, "")
        for stock_code, raw_company_name in _COMPANY_LINK_RE.findall(chunk):
            key = (subcode, stock_code)
            if key in members:
                continue
            members[key] = IndustryChainMember(
                stock_code=stock_code,
                company_name=html.unescape(raw_company_name),
                ic_code=ic_code,
                tier=tier,
                subcategory_code=subcode,
                subcategory_name=subcategory_name,
            )
    return tuple(members.values())


def build_industry_chain_index(
    cache_dir: Path,
    ic_codes: tuple[str, ...] = INDUSTRY_CHAIN_CODES,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, tuple[IndustryChainMember, ...]]:
    """stock_code -> every (ic_code, tier, subcategory) membership found. A
    stock can legitimately belong to more than one industry chain or tier."""
    index: dict[str, list[IndustryChainMember]] = {}
    for ic_code in ic_codes:
        try:
            page_html = fetch_industry_chain_page(ic_code, cache_dir, ttl_seconds=ttl_seconds)
            members = parse_industry_chain_html(page_html, ic_code)
        except Exception as exc:
            print(f"warning: industry_chain_fetch_failed ic_code={ic_code} error={exc}", flush=True)
            continue
        for member in members:
            index.setdefault(member.stock_code, []).append(member)
    return {stock_code: tuple(members) for stock_code, members in index.items()}


def find_chain_consensus_groups(
    signaling_symbols: dict[str, str],
    index: dict[str, tuple[IndustryChainMember, ...]],
    min_members: int = CONSENSUS_MIN_MEMBERS,
) -> tuple[ChainConsensusGroup, ...]:
    """signaling_symbols: stock_code -> company_name, for candidates that
    show a ★/☆/◆ entry signal today. Groups those candidates by
    (ic_code, tier) and keeps only groups with >= min_members distinct
    stocks — the "同一層同步訊號" consensus rule confirmed with the user."""
    groups: dict[tuple[str, str], dict[str, str]] = {}
    for stock_code, company_name in signaling_symbols.items():
        for member in index.get(stock_code, ()):
            key = (member.ic_code, member.tier)
            groups.setdefault(key, {})[stock_code] = company_name

    result = [
        ChainConsensusGroup(ic_code=ic_code, tier=tier, members=tuple(sorted(members.items())))
        for (ic_code, tier), members in groups.items()
        if len(members) >= min_members
    ]
    return tuple(sorted(result, key=lambda group: (group.ic_code, group.tier)))


def _clean_subcategory_name(raw_html: str) -> str:
    text = raw_html.replace("<br/>", "").replace("<br>", "").replace("<br />", "")
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()
