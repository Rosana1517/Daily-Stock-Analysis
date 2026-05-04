from __future__ import annotations

import unittest
from pathlib import Path

from stock_signal_system.pipeline import _quant_notification_body
from stock_signal_system.report import markdown_to_html, public_report_url


class ReportHtmlTest(unittest.TestCase):
    def test_markdown_to_html_contains_readable_structure(self):
        html = markdown_to_html("# 每日報告\n\n## 工作台總覽\n\n- **重點** 觀察", "測試")

        self.assertIn("<h1>每日報告</h1>", html)
        self.assertIn("<h2>工作台總覽</h2>", html)
        self.assertIn("<strong>重點</strong>", html)

    def test_markdown_to_html_renders_dashboard_tables(self):
        html = markdown_to_html(
            "| 標的 | 分數 |\n|---|---:|\n| 2330 台積電 | 88.0 |",
            "測試",
        )

        self.assertIn("<table>", html)
        self.assertIn("<th>標的</th>", html)
        self.assertIn("<td>2330 台積電</td>", html)

    def test_public_report_url_uses_report_filename(self):
        url = public_report_url("https://example.com/reports/", Path("reports/stock_signals_2026-04-27.html"))

        self.assertEqual(url, "https://example.com/reports/stock_signals_2026-04-27.html")

    def test_hybrid_html_embeds_workflow_coverage(self):
        markdown = """# Hybrid Quant Daily Stock Report - 2026-05-04

## Top Ranking

| Rank | Symbol | Name | Industry | Hybrid | Kronos | News | Tech | Realtime | Action |
|---:|---|---|---|---:|---:|---:|---:|---|---|
| 1 | 2330.TW | 台積電 | 半導體 | 72.5 | 3.20% | 68.0 | 63.0 | 盤中穩定 | 觀察偏多 |

## RSS Industry Signals

| Industry | RSS Score | Evidence | Key Catalyst |
|---|---:|---:|---|
| 半導體 | 68.0 | 3 | AI server demand |

## Industry Groups

| Industry | Symbols | Average Hybrid | Bias |
|---|---|---:|---|
| 半導體 | 2330.TW 台積電 | 72.5 | 偏多 |

## Investment Notes

- 2330.TW 台積電: current 900.00, predicted 930.00, hybrid 72.5. 觀察偏多.

## Portfolio Simulation

- Gross expected return: 3.20%

## News Feed

- [半導體] AI server demand improves (news, 2026-05-04)

## Workflow Coverage Matrix

| Symbol | Step | Task | Status | Evidence | Missing | Modules |
|---|---:|---|---|---|---|---|
| 2330.TW | 1 | RSS、新聞、政策、輿情蒐集 | pass | RSS/news rows: 1 | - | rss_sources.py |
| 2330.TW | 2 | 新聞清洗與排除雜訊 | partial | structured rows | No dedicated sentiment score | finance-sentiment |
"""
        html = markdown_to_html(markdown, "Hybrid Quant Daily Stock Report - 2026-05-04")

        self.assertIn("流程覆蓋檢查", html)
        self.assertIn("workflowCoverageHtml", html)
        self.assertIn("RSS、新聞、政策、輿情蒐集", html)
        self.assertIn("No dedicated sentiment score", html)

    def test_hybrid_html_embeds_actual_ohlcv_chart_data(self):
        markdown = """# Hybrid Quant Daily Stock Report - 2026-05-04

## Top Ranking

| Rank | Symbol | Name | Industry | Hybrid | Kronos | News | Tech | Realtime | Action |
|---:|---|---|---|---:|---:|---:|---:|---|---|
| 1 | 2330.TW | 台積電 | 半導體 | 72.5 | 3.20% | 68.0 | 63.0 | 有資料 | 觀察 |

## OHLCV Chart Data

| Symbol | Date | Open | High | Low | Close | Volume |
|---|---|---:|---:|---:|---:|---:|
| 2330.TW | 2026-05-01 | 900 | 920 | 890 | 910 | 1000000 |
| 2330.TW | 2026-05-04 | 910 | 935 | 905 | 930 | 1200000 |

## Workflow Coverage Matrix

| Symbol | Step | Task | Status | Evidence | Missing | Modules |
|---|---:|---|---|---|---|---|
| 2330.TW | 1 | RSS、新聞、政策、輿情蒐集 | pass | RSS/新聞筆數：1 | - | rss_sources.py |
"""
        html = markdown_to_html(markdown, "Hybrid Quant Daily Stock Report - 2026-05-04")

        self.assertIn('"ohlcv"', html)
        self.assertIn('"date": "2026-05-04"', html)
        self.assertIn("近3個月實際K線", html)

    def test_report_link_notification_body_is_only_url(self):
        body = _quant_notification_body("full report", "reports/tw_hybrid_2026-05-04.md", "report_link", "https://example.com/report.html")

        self.assertEqual(body, "https://example.com/report.html")


if __name__ == "__main__":
    unittest.main()
