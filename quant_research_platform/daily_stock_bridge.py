from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from stock_signal_system.data.csv_sources import load_news
from stock_signal_system.data.rss_sources import fetch_rss_news, save_news_csv
from stock_signal_system.industry import analyze_industries
from stock_signal_system.models import IndustrySignal, PriceBar
from stock_signal_system.notify import send_notification
from stock_signal_system.strategies.candlestick import analyze_candlesticks

from quant_research_platform.data import Bar


TW_STOCK_PROFILE = {
    "2330": ("台積電", "半導體"),
    "2317": ("鴻海", "AI 伺服器"),
    "2454": ("聯發科", "IC 設計"),
    "2382": ("廣達", "AI 伺服器"),
    "2308": ("台達電", "電源與散熱"),
    "2881": ("富邦金", "金融"),
    "2882": ("國泰金", "金融"),
    "2891": ("中信金", "金融"),
    "2412": ("中華電", "電信"),
    "3711": ("日月光投控", "半導體"),
    "2357": ("華碩", "PC 與 AI 終端"),
    "2379": ("瑞昱", "IC 設計"),
    "3034": ("聯詠", "IC 設計"),
    "3661": ("世芯-KY", "AI ASIC"),
    "2603": ("長榮", "航運"),
    "2618": ("長榮航", "航空"),
    "6488": ("環球晶", "半導體材料"),
    "5274": ("信驊", "伺服器管理晶片"),
    "8069": ("元太", "電子紙"),
    "5347": ("世界", "晶圓代工"),
    "2330.TW": ("台積電", "半導體"),
    "2317.TW": ("鴻海", "AI 伺服器"),
    "2454.TW": ("聯發科", "IC 設計"),
    "2382.TW": ("廣達", "AI 伺服器"),
    "2308.TW": ("台達電", "電源與散熱"),
    "2881.TW": ("富邦金", "金融"),
    "2882.TW": ("國泰金", "金融"),
    "2891.TW": ("中信金", "金融"),
    "2412.TW": ("中華電", "電信"),
    "3711.TW": ("日月光投控", "半導體"),
    "2357.TW": ("華碩", "PC 與 AI 終端"),
    "2379.TW": ("瑞昱", "IC 設計"),
    "3034.TW": ("聯詠", "IC 設計"),
    "3661.TW": ("世芯-KY", "AI ASIC"),
    "2603.TW": ("長榮", "航運"),
    "2618.TW": ("長榮航", "航空"),
    "6488.TWO": ("環球晶", "半導體材料"),
    "5274.TWO": ("信驊", "伺服器管理晶片"),
    "8069.TWO": ("元太", "電子紙"),
    "5347.TWO": ("世界", "晶圓代工"),
}


@dataclass(frozen=True)
class RealtimeState:
    symbol: str
    price: float
    previous_close: float
    intraday_return: float
    status: str
    timestamp: str


def build_technical_signals(bars_by_symbol: dict[str, list[Bar]]):
    history = {
        symbol: [
            PriceBar(
                symbol=symbol,
                date=bar.timestamp.date(),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in bars
        ]
        for symbol, bars in bars_by_symbol.items()
    }
    return analyze_candlesticks(history)


def load_or_fetch_industry_signals(
    news_path: Path | None = None,
    rss_sources_path: Path | None = None,
    cache_dir: Path = Path(".cache"),
) -> list[IndustrySignal]:
    if rss_sources_path:
        news = fetch_rss_news(rss_sources_path, cache_dir)
        if news:
            if news_path:
                save_news_csv(news, news_path)
            return analyze_industries(news)
        if news_path and news_path.exists():
            return analyze_industries(load_news(news_path))
        if news_path:
            save_news_csv(news, news_path)
        return analyze_industries(news)
    if news_path and news_path.exists():
        return analyze_industries(load_news(news_path))
    return []


def load_latest_realtime_states(path: Path | None) -> dict[str, RealtimeState]:
    if not path or not path.exists():
        return {}
    latest: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = _to_platform_symbol(row.get("symbol", ""), row.get("market", ""))
            if not symbol:
                continue
            latest[symbol] = row
    states = {}
    for symbol, row in latest.items():
        price = _float(row.get("close"))
        previous = _float(row.get("previous_close"))
        intraday_return = price / previous - 1 if previous else 0.0
        states[symbol] = RealtimeState(
            symbol=symbol,
            price=price,
            previous_close=previous,
            intraday_return=intraday_return,
            status=_intraday_status(intraday_return),
            timestamp=row.get("datetime", ""),
        )
    return states


def notification_summary(report_rows: list, report_path: Path) -> str:
    lines = [f"Hybrid AI 選股摘要\n報告: {report_path}", ""]
    for rank, row in enumerate(report_rows[:5], start=1):
        lines.append(
            f"{rank}. {row.symbol} {row.name} | hybrid {row.hybrid_score:.1f} | "
            f"Kronos {row.kronos_return:.2%} | {row.action}"
        )
    return "\n".join(lines)


def send_hybrid_notification(
    body: str,
    webhook_env: str | None,
    line_channel_access_token_env: str | None,
    line_to_env: str | None,
    line_broadcast: bool,
) -> str:
    return send_notification(
        "Hybrid AI 選股",
        body,
        webhook_env,
        line_channel_access_token_env,
        line_to_env,
        line_broadcast,
    )


def stock_name(symbol: str) -> str:
    return TW_STOCK_PROFILE.get(symbol, (symbol, "未知"))[0]


def stock_industry(symbol: str) -> str:
    return TW_STOCK_PROFILE.get(symbol, (symbol, "未知"))[1]


def industry_news_score(industry: str, signals: list[IndustrySignal]) -> float:
    if not signals:
        return 50.0
    direct = {item.industry: item.score for item in signals}
    if industry in direct:
        return direct[industry]
    text = industry.lower()
    best = 50.0
    for item in signals:
        source = item.industry.lower()
        if any(term in source or term in text for term in ("ai", "半導體", "ic", "server", "伺服器")):
            best = max(best, item.score)
    return best


def _intraday_status(value: float) -> str:
    if value >= 0.015:
        return "盤中強勢"
    if value >= 0.003:
        return "小幅走強"
    if value <= -0.015:
        return "盤中弱勢"
    if value <= -0.003:
        return "小幅走弱"
    return "持平"


def _to_platform_symbol(symbol: str, market: str) -> str:
    symbol = symbol.strip()
    market = market.strip().lower()
    if not symbol:
        return ""
    suffix = "TWO" if market == "otc" else "TW"
    return f"{symbol}.{suffix}"


def _float(value) -> float:
    if value in (None, ""):
        return 0.0
    return float(str(value).replace(",", "").strip())
