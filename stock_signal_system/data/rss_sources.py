from __future__ import annotations

import csv
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from stock_signal_system.data.rate_limit import RateLimitedHttpClient
from stock_signal_system.models import NewsItem


INDUSTRY_RULES = {
    "AI伺服器": {
        "required_any": ("ai", "artificial intelligence", "nvidia", "gpu", "人工智慧", "ai代理", "算力"),
        "context_any": (
            "data center",
            "datacenter",
            "server",
            "semiconductor",
            "chip",
            "accelerator",
            "cloud",
            "model",
            "compute",
            "memory",
            "台積電",
            "晶片",
            "伺服器",
            "資料中心",
            "供應鏈",
            "記憶體",
            "半導體",
        ),
        "exclude_any": ("student", "police", "murder", "shooting", "airline", "flight", "restaurant", "drug", "槍擊", "車禍"),
    },
    "半導體": {
        "required_any": ("semiconductor", "chip", "foundry", "tsmc", "wafer", "晶片", "半導體", "台積電", "製程"),
        "context_any": ("wafer", "fab", "gpu", "ai", "electronics", "supply chain", "製程", "晶圓", "先進製程", "封裝"),
        "exclude_any": ("potato chip", "chocolate chip"),
    },
    "電力設備": {
        "required_any": ("power grid", "electric grid", "grid", "transformer", "electricity", "電網", "變壓器", "輸配電", "電力"),
        "context_any": ("infrastructure", "utility", "substation", "transmission", "energy demand", "電力", "輸配電", "台電", "電廠"),
        "exclude_any": ("political power", "powerful", "powerpoint", "battery power", "police", "court", "asylum", "槍擊"),
    },
    "儲能": {
        "required_any": ("energy storage", "battery storage", "battery", "ev", "electric vehicle", "儲能", "電池", "電動車", "充電"),
        "context_any": ("grid", "renewable", "solar", "lease", "leases", "leased", "lithium", "charging", "utility", "能源", "綠能"),
        "exclude_any": ("data storage", "cloud storage", "student", "police", "body", "roommate", "oil refinery", "槍擊"),
    },
    "散熱": {
        "required_any": ("cooling", "thermal", "liquid cooling", "heat sink", "散熱", "水冷", "液冷"),
        "context_any": ("server", "data center", "gpu", "ai", "electronics", "資料中心", "伺服器", "晶片"),
        "exclude_any": ("cooling inflation", "cooling economy"),
    },
    "消費電子": {
        "required_any": ("smartphone", "pc", "consumer electronics", "iphone", "laptop", "手機", "筆電", "消費電子", "3c"),
        "context_any": ("shipment", "inventory", "device", "gaming", "console", "品牌", "出貨", "庫存"),
        "exclude_any": ("flight", "airline", "jet fuel", "槍擊"),
    },
}

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
        industries = _classify_industries(title, body)
        if industries:
            parsed.append(
                NewsItem(
                    date=date.today(),
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
        industries = _classify_industries(title, body)
        if not title or not industries:
            continue
        parsed.append(
            NewsItem(
                date=date.today(),
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


def _sanitize_xml(value: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", value)
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9a-fA-F]+;)", "&amp;", text)
    return text


def _classify_industries(title: str, body: str) -> list[str]:
    text = f"{title} {title} {body}".lower()
    if _is_noise_story(text):
        return []
    industries = []
    for industry, rule in INDUSTRY_RULES.items():
        if _matches_rule(text, rule):
            industries.append(industry)
    return industries


def _is_noise_story(text: str) -> bool:
    return any(term.lower() in text for term in GLOBAL_NOISE_TERMS)


def _matches_rule(text: str, rule: dict[str, tuple[str, ...]]) -> bool:
    if any(_contains_term(text, term) for term in rule.get("exclude_any", ())):
        return False
    required = any(_contains_term(text, term) for term in rule.get("required_any", ()))
    context = any(_contains_term(text, term) for term in rule.get("context_any", ()))
    return required and context


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
