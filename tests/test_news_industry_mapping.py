from __future__ import annotations

import unittest
from datetime import date

from quant_research_platform.daily_stock_bridge import industry_news_score
from stock_signal_system.industry import analyze_industries
from stock_signal_system.models import IndustrySignal, NewsItem


def _signal(industry: str, score: float) -> IndustrySignal:
    return IndustrySignal(industry=industry, score=score, catalysts=(), evidence_count=1)


class IndustryNewsScoreTest(unittest.TestCase):
    def test_news_industry_maps_to_twse_stock_industry(self):
        # 「半導體」(新聞產業) 要對到「半導體業」(證交所分類)，舊版只做字串完全相等比對。
        self.assertEqual(industry_news_score("半導體業", [_signal("半導體", 70.0)]), 70.0)
        self.assertEqual(industry_news_score("生技醫療業", [_signal("生技醫療", 66.0)]), 66.0)

    def test_unrelated_industry_stays_neutral(self):
        # 舊版 fallback 會讓任何股票(包括食品股)拿到 AI 新聞的分數。
        self.assertEqual(industry_news_score("食品工業", [_signal("AI伺服器", 80.0)]), 50.0)

    def test_takes_best_of_multiple_matching_signals(self):
        signals = [_signal("AI伺服器", 60.0), _signal("散熱", 72.0)]
        self.assertEqual(industry_news_score("電子零組件業", signals), 72.0)

    def test_no_signals_is_neutral(self):
        self.assertEqual(industry_news_score("半導體業", []), 50.0)


class OutbreakSentimentTest(unittest.TestCase):
    def test_outbreak_news_is_positive_for_biotech_despite_risk_words(self):
        # 「風險」「調查」一般是負面字，但疫情對生技醫療是需求面利多。
        news = [
            NewsItem(
                date=date(2026, 10, 7),
                title="肺鼠疫致死疑雲 全球公衛恐慌再起 疾管署調查感染風險",
                source="test",
                body="",
                industries=("生技醫療",),
            )
        ]
        signal = analyze_industries(news)[0]
        self.assertEqual(signal.industry, "生技醫療")
        self.assertGreater(signal.score, 50.0)


class StaleNewsFilterTest(unittest.TestCase):
    def test_old_items_are_dropped_and_dates_come_from_pubdate(self):
        from stock_signal_system.data.rss_sources import RssSource, _parse_feed

        today = date.today()
        fresh = today.strftime("%a, %d %b %Y 08:00:00 +0800")
        xml = f"""<rss><channel>
          <item><title>敦睦艦群聚累計29人確診 疫情擴散</title><pubDate>Thu, 23 Apr 2020 10:00:00 +0800</pubDate></item>
          <item><title>俄羅斯疑似肺鼠疫外洩 疫苗股走強</title><pubDate>{fresh}</pubDate></item>
        </channel></rss>"""
        source = RssSource(name="t", url="u", region="tw", category="health", quality="q")

        items = _parse_feed(source, xml, limit=10)

        self.assertEqual([i.title for i in items], ["俄羅斯疑似肺鼠疫外洩 疫苗股走強"])
        self.assertEqual(items[0].date, today)


if __name__ == "__main__":
    unittest.main()
