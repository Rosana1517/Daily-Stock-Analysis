from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from stock_signal_system.data.news_history import merge_news, update_news_history, with_history
from stock_signal_system.models import NewsItem

TODAY = date(2026, 10, 9)


def _news(title: str, day: date, industries=("生技醫療",)) -> NewsItem:
    return NewsItem(date=day, title=title, source="s", body="", industries=tuple(industries))


class MergeNewsTest(unittest.TestCase):
    def test_dedupes_same_story_from_different_outlets(self):
        merged = merge_news(
            [_news("俄羅斯疑似肺鼠疫外洩 - 中央社 CNA", TODAY)],
            [_news("俄羅斯疑似肺鼠疫外洩 - 自由健康網", TODAY)],
            today=TODAY,
        )
        self.assertEqual(len(merged), 1)

    def test_drops_items_older_than_keep_days(self):
        merged = merge_news([_news("舊聞", date(2026, 10, 1))], [_news("新聞", TODAY)], today=TODAY, keep_days=3)
        self.assertEqual([item.title for item in merged], ["新聞"])


class WithHistoryTest(unittest.TestCase):
    def test_noon_news_collected_earlier_is_visible_at_evening_run(self):
        # 中午 collector 抓到的新聞，17:30 主排程那一刻已經被擠出 RSS 了，
        # 但仍要出現在分析用的新聞裡。
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "news_history.csv"
            update_news_history([_news("中午：俄羅斯肺鼠疫第二例死亡", TODAY)], path, today=TODAY)

            evening = with_history([_news("傍晚：AI 伺服器出貨創高", TODAY, ("AI伺服器",))], path, today=TODAY)

        titles = {item.title for item in evening}
        self.assertIn("中午：俄羅斯肺鼠疫第二例死亡", titles)
        self.assertIn("傍晚：AI 伺服器出貨創高", titles)

    def test_analysis_window_excludes_news_older_than_yesterday(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "news_history.csv"
            update_news_history([_news("三天前", date(2026, 10, 6)), _news("昨天", date(2026, 10, 8))], path, today=TODAY)

            result = with_history([], path, today=TODAY)

        self.assertEqual({item.title for item in result}, {"昨天"})

    def test_none_path_disables_history(self):
        fresh = [_news("x", TODAY)]
        self.assertEqual(with_history(fresh, None, today=TODAY), fresh)


if __name__ == "__main__":
    unittest.main()
