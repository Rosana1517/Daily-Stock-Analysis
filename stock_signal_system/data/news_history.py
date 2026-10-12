"""Rolling news history so the daily analysis sees the whole day's news.

單一媒體 RSS 只回傳最新 20~40 則；像自由時報這種一天發幾百則的來源，17:30
抓一次只看得到最後 1~2 小時，中午的重大新聞早就被擠出去了(2026-10 的俄羅斯
肺鼠疫新聞就是這樣漏掉)。news-collector workflow 每 2 小時抓一次並併進這個
歷史檔(透過 GitHub Actions cache 在執行之間傳遞，不 commit 進 repo，避免跟
主排程的 git push 互相衝突)，主排程分析時再把歷史裡近期的新聞一起納入。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from stock_signal_system.data.csv_sources import load_news
from stock_signal_system.data.rss_sources import MAX_NEWS_AGE_DAYS, save_news_csv
from stock_signal_system.models import NewsItem

NEWS_HISTORY_PATH = Path("data/news_history.csv")
# 分析時納入「今天 + 前一天」的新聞：發布時間只精確到日，且 17:30 的排程要能看到
# 前一晚到當天盤中的事件。
ANALYSIS_WINDOW_DAYS = 1


def _title_key(title: str) -> str:
    # Google News 標題結尾會帶「 - 媒體名」，同一則新聞被不同媒體轉載時要能去重。
    title = re.sub(r"\s+-\s+[^-]{1,30}$", "", title)
    return re.sub(r"\W+", "", title.lower())


def merge_news(
    existing: list[NewsItem],
    fresh: list[NewsItem],
    today: date | None = None,
    keep_days: int = MAX_NEWS_AGE_DAYS,
) -> list[NewsItem]:
    """合併新舊新聞：同標題以先出現的為準，丟掉超過 keep_days 的，依日期新到舊排序。"""
    cutoff = (today or date.today()) - timedelta(days=keep_days)
    merged: dict[str, NewsItem] = {}
    for item in [*existing, *fresh]:
        if item.date < cutoff:
            continue
        merged.setdefault(_title_key(item.title), item)
    return sorted(merged.values(), key=lambda item: item.date, reverse=True)


def update_news_history(
    fresh: list[NewsItem],
    path: Path = NEWS_HISTORY_PATH,
    today: date | None = None,
) -> list[NewsItem]:
    existing = load_news(path) if path.exists() else []
    merged = merge_news(existing, fresh, today)
    save_news_csv(merged, path)
    return merged


def with_history(
    fresh: list[NewsItem],
    path: Path | None = NEWS_HISTORY_PATH,
    today: date | None = None,
    window_days: int = ANALYSIS_WINDOW_DAYS,
) -> list[NewsItem]:
    """把累積的新聞併進本次抓到的新聞(只取近 window_days 天)，並順便更新歷史檔。"""
    if path is None:
        return fresh
    today = today or date.today()
    merged = update_news_history(fresh, path, today)
    cutoff = today - timedelta(days=window_days)
    return [item for item in merged if item.date >= cutoff]
