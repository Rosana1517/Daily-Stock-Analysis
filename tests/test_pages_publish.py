from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_signal_system.pages_publish import _prune_published_report_html
from stock_signal_system.report import save_report_html


class ReportRetentionTest(unittest.TestCase):
    def test_save_report_html_keeps_latest_three_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir)
            for day in range(1, 5):
                save_report_html(report_dir, date(2026, 5, day), f"# Report {day}\n")

            names = sorted(path.name for path in report_dir.glob("stock_signals_*.html"))

            self.assertEqual(
                names,
                [
                    "stock_signals_2026-05-02.html",
                    "stock_signals_2026-05-03.html",
                    "stock_signals_2026-05-04.html",
                ],
            )

    def test_publish_report_prune_keeps_latest_three_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            for day in range(1, 5):
                (reports_dir / f"stock_signals_2026-05-0{day}.html").write_text("x", encoding="utf-8")

            _prune_published_report_html(reports_dir)

            names = sorted(path.name for path in reports_dir.glob("stock_signals_*.html"))
            self.assertEqual(
                names,
                [
                    "stock_signals_2026-05-02.html",
                    "stock_signals_2026-05-03.html",
                    "stock_signals_2026-05-04.html",
                ],
            )


if __name__ == "__main__":
    unittest.main()
