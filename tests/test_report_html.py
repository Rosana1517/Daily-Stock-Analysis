from __future__ import annotations

import unittest
from pathlib import Path

from stock_signal_system.report import markdown_to_html, public_report_url


class ReportHtmlTest(unittest.TestCase):
    def test_markdown_to_html_contains_readable_structure(self):
        html = markdown_to_html("# 標題\n\n## 區塊\n\n- **重點** 內容", "測試")

        self.assertIn("<h1>標題</h1>", html)
        self.assertIn("<h2>區塊</h2>", html)
        self.assertIn("<strong>重點</strong>", html)

    def test_public_report_url_uses_report_filename(self):
        url = public_report_url("https://example.com/reports/", Path("reports/stock_signals_2026-04-27.html"))

        self.assertEqual(url, "https://example.com/reports/stock_signals_2026-04-27.html")

    def test_hybrid_chinese_report_renders_interactive_technical_chart(self):
        markdown = """# Hybrid 量化每日選股報告 - 2026-05-13

## 每日研究名單

| 股票 | 名稱 |
|---|---|
| 2330.TW | 台積電 |

```technical-chart-data
{"defaults":{"maShort":5,"maMid":20,"maLong":60,"rsiLow":20,"rsiHigh":80,"bollingerSigma":2},"stocks":[{"symbol":"2330.TW","name":"台積電","industry":"半導體","decision":"研究觀察","bucket":"include","technicalScore":66,"support":100,"resistance":120,"strategySummary":[{"strategy":"黃金交叉 / 死亡交叉","status":"未出現新交叉","agent":"Technical_Analyst_Agent","use":"研究條件"}],"bars":[{"date":"2026-05-11","open":100,"high":105,"low":99,"close":104,"volume":1000},{"date":"2026-05-12","open":104,"high":108,"low":103,"close":107,"volume":1500}]}]}
```
"""

        html = markdown_to_html(markdown, "Hybrid 量化每日選股報告")

        self.assertIn("互動技術分析", html)
        self.assertIn("technicalChart", html)
        self.assertIn("黃金交叉", html)
        self.assertIn("短均線看短線動能", html)
        self.assertIn("5 代表近 5 根 K 線平均", html)
        self.assertIn("20 代表近 20 根平均", html)
        self.assertIn("60 代表近 60 根平均", html)
        self.assertIn("80 以上標示過熱", html)
        self.assertIn("2 代表上下緣約 2 倍標準差", html)
        self.assertIn("精簡 K 線/三線標記", html)
        self.assertIn("近 10 日漲停", html)
        self.assertIn("月均線 MACD 金叉", html)
        self.assertIn("日均線 20 均線放量陽線", html)
        self.assertIn("strategyVisible", html)
        self.assertIn("flex-wrap: wrap", html)
        self.assertIn("策略條件摘要", html)
        self.assertIn("repeat(auto-fit, minmax(230px, 1fr))", html)
        self.assertNotIn("technical-chart-data", html)


if __name__ == "__main__":
    unittest.main()
