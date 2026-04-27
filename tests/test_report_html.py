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


if __name__ == "__main__":
    unittest.main()
