from __future__ import annotations

import csv
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient
from stock_signal_system.models import NewsItem


GLOBAL_NOISE_TERMS = (
    "張員瑛",
    "身材",
    "洋裝",
    "繃帶",
    "鬆緊帶",
    "穿搭",
    "時尚",
    "女星",
    "男星",
    "韓星",
    "藝人",
    "演員",
    "歌手",
    "性感",
    "售罄",
    "妝容",
    "球員",
    "賽事",
    "演唱會",
    "電影",
    "影集",
    "餐廳",
    "食譜",
)


@dataclass(frozen=True)
class RssSource:
    name: str
    url: str
    region: str
    category: str
    quality: str
    source_type: str = "media"
    weight: float = 1.0


def load_rss_sources(path: Path) -> list[RssSource]:
    return [RssSource(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


def fetch_rss_news(sources_path: Path, cache_dir: Path, limit_per_source: int = 30) -> list[NewsItem]:
    client = RateLimitedHttpClient(cache_dir=cache_dir / "rss", min_interval_seconds=2.0)
    news: list[NewsItem] = []
    for source in load_rss_sources(sources_path):
        try:
            xml_text = client.get_text(source.url, cache_key=f"rss_{source.name}", ttl_seconds=1800)
            news.extend(_parse_feed(source, xml_text, limit_per_source))
        except Exception as exc:
            print(f"warning: skipped RSS source {source.name}: {exc}", file=sys.stderr)
    return _dedupe_news(news)


def save_news_csv(news: list[NewsItem], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "title", "source", "source_weight", "body", "industries"])
        writer.writeheader()
        for item in news:
            writer.writerow(
                {
                    "date": item.date.isoformat(),
                    "title": item.title,
                    "source": item.source,
                    "source_weight": item.source_weight,
                    "body": item.body,
                    "industries": ";".join(item.industries),
                }
            )
    return path


def _parse_feed(source: RssSource, xml_text: str, limit: int) -> list[NewsItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        try:
            root = ET.fromstring(_sanitize_xml(xml_text))
        except ET.ParseError:
            return _parse_feed_with_regex(source, xml_text, limit)
    items = root.findall(".//item")[:limit]
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")[:limit]

    parsed = []
    for item in items:
        title = _clean_text(_text(item, "title") or _text(item, "{http://www.w3.org/2005/Atom}title"))
        body = _clean_text(_text(item, "description") or _text(item, "{http://www.w3.org/2005/Atom}summary"))
        published = _parse_published(
            _text(item, "pubDate")
            or _text(item, "{http://www.w3.org/2005/Atom}published")
            or _text(item, "{http://www.w3.org/2005/Atom}updated")
        )
        if _is_stale(published):
            continue
        industries = _classify_industries(title, body)
        if industries:
            parsed.append(
                NewsItem(
                    date=published or date.today(),
                    title=title,
                    source=source.name,
                    body=body,
                    industries=tuple(industries),
                    source_weight=float(source.weight),
                )
            )
    return parsed


def _parse_feed_with_regex(source: RssSource, xml_text: str, limit: int) -> list[NewsItem]:
    parsed: list[NewsItem] = []
    for raw_item in re.findall(r"<item\b.*?</item>", xml_text, flags=re.IGNORECASE | re.DOTALL)[:limit]:
        title = _clean_text(_tag_text(raw_item, "title"))
        body = _clean_text(_tag_text(raw_item, "description"))
        published = _parse_published(_tag_text(raw_item, "pubDate"))
        if _is_stale(published):
            continue
        industries = _classify_industries(title, body)
        if not title or not industries:
            continue
        parsed.append(
            NewsItem(
                date=published or date.today(),
                title=title,
                source=source.name,
                body=body,
                industries=tuple(industries),
                source_weight=float(source.weight),
            )
        )
    return parsed


def _tag_text(xml_fragment: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", xml_fragment, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    text = match.group(1)
    cdata = re.fullmatch(r"\s*<!\[CDATA\[(.*)\]\]>\s*", text, flags=re.DOTALL)
    return cdata.group(1) if cdata else text


def _text(item: ET.Element, tag: str) -> str:
    child = item.find(tag)
    return "" if child is None or child.text is None else child.text.strip()


def _clean_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# 有些來源會混入幾週前、甚至幾年前的舊新聞(CNA health feed 停在 2020 年、
# BBC/Reddit/DIGITIMES 常混入 2~6 週前的項目)。原本一律把日期當成「今天」，
# 舊新聞會被當成當天事件。改用 RSS 的發布時間，超過這個天數就丟掉。
MAX_NEWS_AGE_DAYS = 3


def _parse_published(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, IndexError):
        pass
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def _is_stale(published: date | None, today: date | None = None) -> bool:
    """沒有發布時間的項目保留(無法判斷)；有的話超過 MAX_NEWS_AGE_DAYS 就視為過期。"""
    if published is None:
        return False
    return ((today or date.today()) - published).days > MAX_NEWS_AGE_DAYS


def _sanitize_xml(value: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", value)
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9a-fA-F]+;)", "&amp;", text)
    return text


def _is_noise_story(text: str) -> bool:
    return any(term.lower() in text for term in GLOBAL_NOISE_TERMS)


def _contains_term(text: str, term: str) -> bool:
    term = term.lower().strip()
    if not term:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9.+-]*", term):
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return term in text


def _dedupe_news(news: list[NewsItem]) -> list[NewsItem]:
    seen = set()
    deduped = []
    for item in news:
        key = re.sub(r"\W+", "", item.title.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


INDUSTRY_RULES_ZH = {
    "AI伺服器": {
        "required": ("ai", "人工智慧", "伺服器", "server", "gpu", "nvidia", "gb200", "gb300", "asic", "資料中心", "data center"),
        "context": ("雲端", "散熱", "半導體", "記憶體", "高速傳輸", "電源", "運算", "供應鏈", "機櫃", "cloud", "compute", "data center", "datacenter", "infrastructure"),
        "exclude": ("警察", "法院", "餐廳", "航空", "電影", "學生"),
    },
    "半導體": {
        "required": ("半導體", "晶片", "晶圓", "台積電", "聯發科", "矽", "封測", "先進製程", "foundry", "chip", "wafer", "tsmc"),
        "context": ("ai", "電子", "供應鏈", "製程", "產能", "設備", "封裝", "asic", "gpu"),
        "exclude": ("potato chip", "chocolate chip"),
    },
    "散熱": {
        "required": ("散熱", "水冷", "液冷", "thermal", "cooling", "heat sink", "奇鋐", "雙鴻", "健策"),
        "context": ("ai", "伺服器", "資料中心", "gpu", "電子", "機櫃"),
        "exclude": ("通膨降溫", "天氣轉涼"),
    },
    "電力設備": {
        "required": ("電力", "電網", "重電", "變壓器", "電纜", "電源", "power grid", "transformer", "中興電", "士電", "華城"),
        "context": ("ai", "資料中心", "基建", "台電", "能源", "供電", "訂單"),
        "exclude": ("政治權力", "powerpoint"),
    },
    "儲能": {
        "required": ("儲能", "電池", "battery", "ev", "electric vehicle", "electric car", "battery-powered"),
        "context": ("電網", "再生能源", "太陽能", "充電", "鋰", "lease", "leases", "leased", "utility", "car", "truck"),
        "exclude": ("data storage", "cloud storage", "警察", "學生", "餐廳", "法院"),
    },
    "消費電子": {
        "required": ("消費電子", "iphone", "手機", "pc", "筆電", "realtek", "聯詠", "大立光", "shipment"),
        "context": ("出貨", "庫存", "鏡頭", "面板", "3c", "device", "pc"),
        "exclude": ("航空", "餐廳"),
    },
    # 以下為事件驅動型產業。原本只有上面 6 個科技/電力產業，分類不到的新聞
    # 會被整則丟棄(_parse_feed 的 `if industries:`)，2026-10-06 俄羅斯肺鼠疫
    # 新聞(TechNews 有發)就因此完全沒進報告，醫療股上漲也沒有提示。
    # "standalone"：本身就足以判定產業、不需 context 佐證的強事件詞。
    "生技醫療": {
        "standalone": (
            "鼠疫", "肺鼠疫", "疫情爆發", "大流行", "新冠", "禽流感", "猴痘", "流感疫情",
            "防疫概念股", "疫苗股", "生技股", "醫材股", "plague", "pandemic", "outbreak", "epidemic",
        ),
        "required": (
            "生技", "醫療", "醫材", "新藥", "藥廠", "製藥", "藥品", "疫苗", "疫情", "防疫", "病毒",
            "傳染", "感染", "快篩", "口罩", "biotech", "pharma", "vaccine", "virus", "fda",
        ),
        "context": (
            "股", "概念", "營收", "訂單", "需求", "臨床", "授權", "藥證", "確診", "病例", "擴散",
            "世衛", "who", "疾管署", "衛福部", "公衛", "drug", "approval", "trial", "sales",
        ),
        "exclude": ("彈藥", "農藥", "炸藥", "火藥", "電腦病毒", "勒索", "惡意程式", "資安"),
    },
    "航運": {
        "required": ("航運", "貨櫃", "散裝", "運價", "海運", "長榮", "陽明", "萬海", "shipping", "freight", "container"),
        "context": ("運價", "航線", "塞港", "紅海", "蘇伊士", "需求", "股", "scfi", "bdi", "rates", "port"),
        "exclude": ("食譜",),
    },
    "觀光餐旅": {
        "required": ("觀光", "旅遊", "飯店", "旅行社", "來台旅客", "陸客", "tourism", "travel", "hotel"),
        "context": ("人次", "訂房", "住房率", "營收", "開放", "簽證", "股", "需求", "booking"),
        "exclude": ("太空旅遊",),
    },
    "金融保險": {
        "required": ("金控", "銀行", "壽險", "保險", "券商", "升息", "降息", "聯準會", "央行", "fed"),
        "context": ("獲利", "股利", "配息", "放款", "利差", "股", "eps", "殖利率", "利率", "rate"),
        "exclude": ("食物銀行", "血液銀行", "時間銀行"),
    },
    "鋼鐵": {
        "required": ("鋼鐵", "鋼價", "中鋼", "鋼材", "steel"),
        "context": ("報價", "需求", "股", "產能", "反傾銷", "price", "tariff"),
        "exclude": (),
    },
}


def _classify_industries(title: str, body: str) -> list[str]:
    text = f"{title} {title} {body}".lower()
    if _is_noise_story(text):
        return []
    industries: list[str] = []
    for industry, rule in INDUSTRY_RULES_ZH.items():
        if _matches_clean_rule(text, rule):
            industries.append(industry)
    return industries


def _matches_clean_rule(text: str, rule: dict[str, tuple[str, ...]]) -> bool:
    if any(_contains_term(text, term) for term in rule.get("exclude", ())):
        return False
    if any(_contains_term(text, term) for term in rule.get("standalone", ())):
        return True
    required = any(_contains_term(text, term) for term in rule.get("required", ()))
    context = any(_contains_term(text, term) for term in rule.get("context", ()))
    return required and context
