from __future__ import annotations

import unittest

from stock_signal_system.data.rss_sources import _classify_industries


class RssClassificationTest(unittest.TestCase):
    def test_unrelated_police_story_is_not_energy_storage(self):
        industries = _classify_industries(
            "Police identify the body of 1 missing USF student",
            "The missing student case involves a roommate and police investigation.",
        )

        self.assertNotIn("儲能", industries)
        self.assertNotIn("AI伺服器", industries)

    def test_ai_server_story_requires_ai_and_compute_context(self):
        industries = _classify_industries(
            "AI data center demand boosts GPU server suppliers",
            "Cloud providers are expanding data center infrastructure.",
        )

        self.assertIn("AI伺服器", industries)

    def test_taiwan_ai_supply_chain_story_is_ai_server(self):
        industries = _classify_industries(
            "台灣AI供應鏈矽谷徵才 半導體、製造專業需求強勁",
            "AI伺服器與半導體供應鏈需求升溫。",
        )

        self.assertIn("AI伺服器", industries)
        self.assertIn("半導體", industries)

    def test_flight_story_is_not_consumer_electronics(self):
        industries = _classify_industries(
            "What to know if your flight is canceled amid rising jet fuel costs",
            "Airlines are cancelling flights.",
        )

        self.assertNotIn("消費電子", industries)

    def test_review_and_event_do_not_trigger_ev_storage(self):
        examples = (
            (
                "FDA plans ultra-fast review of three psychedelic drugs following Trump directive",
                "Regulators will aim to shorten their review timeline from months to weeks.",
            ),
            (
                "Correspondents' Dinner's biggest moments involve laughs and politics",
                "Presidents, comedians, and political staffers attend the annual event.",
            ),
            (
                "Justice Department to allow firing squads for executions",
                "Officials discussed federal court cases and capital punishment.",
            ),
        )

        for title, body in examples:
            with self.subTest(title=title):
                self.assertNotIn("儲能", _classify_industries(title, body))

    def test_ev_lease_story_is_energy_storage_adjacent(self):
        industries = _classify_industries(
            "Thousands of EV Car Leases Are Ending Soon, Giving Buyers a More Affordable Option",
            "Hundreds of thousands of battery-powered cars and trucks will end up on used-car lots.",
        )

        self.assertIn("儲能", industries)

    def test_fashion_story_does_not_trigger_power_equipment(self):
        industries = _classify_industries(
            "張員瑛「不科學身材」全靠黑繃帶洋裝！鬆緊帶勒出凹凸S線 超強效果秒售罄",
            "娛樂與穿搭新聞，和電網、變壓器、輸配電設備無關。",
        )

        self.assertEqual([], industries)

    def test_plague_outbreak_headline_is_classified_as_biotech(self):
        # 2026-10-06 TechNews 的真實標題；舊規則沒有醫療產業，這則被整則丟棄。
        industries = _classify_industries(
            "俄羅斯研究室員工打破活菌試管染病亡，近 200 人隔離防堵疑似「肺鼠疫」外洩",
            "",
        )

        self.assertIn("生技醫療", industries)

    def test_vaccine_stock_news_is_classified_as_biotech(self):
        industries = _classify_industries(
            "俄羅斯鼠疫疑雲升溫 全球肺鼠疫疫苗競賽浮上檯面 高端串起Dynavax技術鏈",
            "疫苗概念股成交量放大",
        )

        self.assertIn("生技醫療", industries)

    def test_computer_virus_and_ammunition_are_not_biotech(self):
        for title in ("勒索病毒攻擊醫院系統 資安股受矚目", "烏克蘭彈藥需求擴大 國防股訂單成長"):
            with self.subTest(title=title):
                self.assertNotIn("生技醫療", _classify_industries(title, ""))

    def test_shipping_freight_news_is_classified(self):
        industries = _classify_industries("紅海危機推升貨櫃運價 長榮陽明股價走強", "")

        self.assertIn("航運", industries)


if __name__ == "__main__":
    unittest.main()
