from __future__ import annotations

import unittest
from pathlib import Path

from stock_signal_system.report import markdown_to_html, public_report_url


class ReportHtmlTest(unittest.TestCase):
    def test_markdown_to_html_contains_readable_structure(self):
        html = markdown_to_html("# 標題\n\n## 小節\n- **重點** 說明", "測試報告")

        self.assertIn("<h1>標題</h1>", html)
        self.assertIn("<h2>小節</h2>", html)
        self.assertIn("<strong>重點</strong>", html)

    def test_public_report_url_uses_report_filename(self):
        url = public_report_url("https://example.com/reports/", Path("reports/stock_signals_2026-04-27.html"))

        self.assertEqual(url, "https://example.com/reports/stock_signals_2026-04-27.html")

    def test_markdown_to_html_keeps_supported_raw_html_blocks(self):
        markdown = """# 測試報告

## 版面檢查

<table>
<tr>
<td valign="top" width="50%"><strong>新版主清單</strong><br>1. 2330.TW 台積電</td>
<td valign="top" width="50%"><strong>舊版觀察</strong><br>1. 2317.TW 鴻海</td>
</tr>
</table>
"""

        html = markdown_to_html(markdown, "測試報告")

        self.assertIn("<table>", html)
        self.assertIn("<strong>新版主清單</strong><br>1. 2330.TW 台積電", html)
        self.assertNotIn("&lt;table&gt;", html)

    def test_hybrid_chinese_report_renders_interactive_technical_chart(self):
        markdown = """# Hybrid 台股每日分析報告 - 2026-05-13

## 選股結果

| 股票 | 名稱 |
|---|---|
| 2330.TW | 台積電 |

```technical-chart-data
{"defaults":{"maShort":5,"maMid":20,"maLong":60,"rsiLow":20,"rsiHigh":80,"bollingerSigma":2},"stocks":[{"symbol":"2330.TW","name":"台積電","industry":"半導體","decision":"納入每日報告","bucket":"include","technicalScore":66,"riskLevel":"低","riskNote":"風險穩定","marketBias":"偏多","currentClose":107,"predictedClose":112,"priceRange":{"low":102,"high":112},"support":100,"resistance":120,"chipSnapshot":{"top10MainForceBuyStrength":72.5,"top10MainForceNetBuy":5432,"foreignBuyStreakDays":4,"branchMainForceBuyStreakDays":3,"branchMainForceLeader":"凱基-台北","chipDataDate":"2026-06-16","chipDataSourceStatus":"official+broker","top10MainForceBrokers":"凱基-台北、摩根大通"},"screeningFlags":{"legacyMotherPoolHit":true,"legacy":true,"newStrategy":true,"chipRadar":true},"strategySummary":[{"strategy":"均線、趨勢與支撐壓力","status":"收盤站上 MA20；支撐 100 / 壓力 120","agent":"Technical_Analyst_Agent","use":"研究條件"},{"strategy":"新版策略","status":"K 值 < 40；MA20 上升；盤整區間突破","agent":"Quant_Research_Agent","use":"發動確認"}],"bars":[{"date":"2026-05-11","open":100,"high":105,"low":99,"close":104,"volume":1000},{"date":"2026-05-12","open":104,"high":108,"low":103,"close":107,"volume":1500}]}],"focusStocks":[{"rank":1,"symbol":"2330.TW","name":"台積電","label":"三者全中","reason":"品質、籌碼、發動點都成立","action":"主清單優先","hybridScore":88.0,"technicalScore":66.0}]}
```
"""

        html = markdown_to_html(markdown, "Hybrid 台股每日分析報告")

        self.assertIn("互動技術分析", html)
        self.assertIn("technicalChart", html)
        self.assertIn('id="chartInfoPanel"', html)
        self.assertIn('id="stockSummaryPanel"', html)
        self.assertIn('id="chipRadarToggle"', html)
        self.assertIn('id="newStrategyToggle"', html)
        self.assertIn('id="legacyStrategyToggle"', html)
        self.assertIn("第 1 層：籌碼雷達", html)
        self.assertIn("第 2 層：新版策略", html)
        self.assertIn("第 3 層：舊版策略", html)
        self.assertIn("盤整區間突破", html)
        self.assertIn("報告結論", html)
        self.assertIn("official+broker", html)
        self.assertIn("strategyVisible", html)
        self.assertIn('data-layer="markers">', html)
        self.assertIn('data-layer="limitUp">', html)
        self.assertIn('data-layer="monthlyMacd">', html)
        self.assertIn('data-layer="ma20Volume">', html)
        self.assertNotIn("technical-chart-data", html)


if __name__ == "__main__":
    unittest.main()
