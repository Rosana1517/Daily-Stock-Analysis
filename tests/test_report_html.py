from __future__ import annotations

import unittest
from pathlib import Path

from stock_signal_system.report import markdown_to_html, public_report_url


class ReportHtmlTest(unittest.TestCase):
    def test_markdown_to_html_contains_readable_structure(self):
        html = markdown_to_html("# 標題\n\n## 小節\n- **重點** 說明", "摘要")

        self.assertIn("<h1>標題</h1>", html)
        self.assertIn("<h2>小節</h2>", html)
        self.assertIn("<strong>重點</strong>", html)

    def test_public_report_url_uses_report_filename(self):
        url = public_report_url("https://example.com/reports/", Path("reports/stock_signals_2026-04-27.html"))

        self.assertEqual(url, "https://example.com/reports/stock_signals_2026-04-27.html")

    def test_markdown_to_html_keeps_supported_raw_html_blocks(self):
        markdown = """# 標題

## 雙欄

<table>
<tr>
<td valign="top" width="50%"><strong>新版主清單</strong><br>1. 2330.TW 台積電</td>
<td valign="top" width="50%"><strong>舊版觀察清單</strong><br>1. 2317.TW 鴻海</td>
</tr>
</table>
"""

        html = markdown_to_html(markdown, "標題")

        self.assertIn("<table>", html)
        self.assertIn("<strong>新版主清單</strong><br>1. 2330.TW 台積電", html)
        self.assertNotIn("&lt;table&gt;", html)

    def test_hybrid_chinese_report_renders_interactive_technical_chart(self):
        markdown = """# Hybrid 量化每日選股報告 - 2026-05-13

## 選股條件摘要

- K值 < 40
- 近 5 日融資增加前 100 大
- 收盤價 20 日均線上升

## 候選全覽

| 股票 | 名稱 |
|---|---|
| 2330.TW | 台積電 |

```technical-chart-data
{"defaults":{"maShort":5,"maMid":20,"maLong":60,"rsiLow":20,"rsiHigh":80,"bollingerSigma":2},"stocks":[{"symbol":"2330.TW","name":"台積電","industry":"半導體","decision":"研究觀察","bucket":"include","technicalScore":66,"support":100,"resistance":120,"chipSnapshot":{"top10MainForceBuyStrength":72.5,"top10MainForceNetBuy":5432,"foreignBuyStreakDays":4,"branchMainForceBuyStreakDays":3,"branchMainForceLeader":"凱基-台北","chipDataDate":"2026-06-16","chipDataSourceStatus":"official+broker","top10MainForceBrokers":"凱基-台北、摩根大通"},"strategySummary":[{"strategy":"均線、趨勢與支撐壓力","status":"未出現新交叉；收盤站上 MA20；支撐 100 / 壓力 120","agent":"Technical_Analyst_Agent","use":"研究條件"}],"bars":[{"date":"2026-05-11","open":100,"high":105,"low":99,"close":104,"volume":1000},{"date":"2026-05-12","open":104,"high":108,"low":103,"close":107,"volume":1500}]}]}
```
"""

        html = markdown_to_html(markdown, "Hybrid 量化每日選股報告")

        self.assertIn("互動技術分析", html)
        self.assertIn("technicalChart", html)
        self.assertIn("均線、趨勢與支撐壓力", html)
        self.assertIn("選股條件摘要", html)
        self.assertIn("K值 &lt; 40", html)
        self.assertIn("近 5 日融資增加前 100 大", html)
        self.assertIn("收盤價 20 日均線上升", html)
        self.assertIn('data-layer="markers">', html)
        self.assertIn('data-layer="limitUp">', html)
        self.assertIn('data-layer="monthlyMacd">', html)
        self.assertIn('data-layer="ma20Volume">', html)
        self.assertNotIn('data-layer="markers" checked', html)
        self.assertNotIn('data-layer="limitUp" checked', html)
        self.assertNotIn('data-layer="monthlyMacd" checked', html)
        self.assertNotIn('data-layer="ma20Volume" checked', html)
        self.assertIn("strategyVisible", html)
        self.assertIn("flex-wrap: wrap", html)
        self.assertIn("strategy-panel", html)
        self.assertIn('id="revisedOnlyToggle"', html)
        self.assertIn('id="legacyStockList"', html)
        self.assertIn('id="revisedStockList"', html)
        self.assertIn('id="chipSnapshotPanel"', html)
        self.assertIn("visibleStocks()", html)
        self.assertIn("renderChipSnapshot(stock)", html)
        self.assertIn("official+broker", html)
        self.assertIn("repeat(auto-fit, minmax(240px, 1fr))", html)
        self.assertIn('summary>策略條件摘要</summary>', html)
        self.assertNotIn("technical-chart-data", html)


if __name__ == "__main__":
    unittest.main()
