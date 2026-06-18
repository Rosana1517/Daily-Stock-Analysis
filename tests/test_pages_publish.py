from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_signal_system.pages_publish import _prune_published_report_html
from stock_signal_system.report_retention import prune_report_artifacts
from stock_signal_system.report import save_report_html


class ReportRetentionTest(unittest.TestCase):
    def test_save_report_html_keeps_latest_five_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir)
            for day in range(1, 7):
                save_report_html(report_dir, date(2026, 5, day), f"# Report {day}\n")

            names = sorted(path.name for path in report_dir.glob("stock_signals_*.html"))

            self.assertEqual(
                names,
                [
                    "stock_signals_2026-05-02.html",
                    "stock_signals_2026-05-03.html",
                    "stock_signals_2026-05-04.html",
                    "stock_signals_2026-05-05.html",
                    "stock_signals_2026-05-06.html",
                ],
            )

    def test_publish_report_prune_keeps_latest_five_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            for day in range(1, 7):
                (reports_dir / f"stock_signals_2026-05-0{day}.html").write_text("x", encoding="utf-8")

            _prune_published_report_html(reports_dir)

            names = sorted(path.name for path in reports_dir.glob("stock_signals_*.html"))
            self.assertEqual(
                names,
                [
                    "stock_signals_2026-05-02.html",
                    "stock_signals_2026-05-03.html",
                    "stock_signals_2026-05-04.html",
                    "stock_signals_2026-05-05.html",
                    "stock_signals_2026-05-06.html",
                ],
            )

    def test_prune_report_artifacts_trims_other_report_types_and_provider_dirs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            for day in range(1, 7):
                stamp = f"2026-05-0{day}"
                (reports_dir / f"tw_hybrid_{stamp}.md").write_text("x", encoding="utf-8")
                (reports_dir / f"tw_hybrid_{stamp}.csv").write_text("x", encoding="utf-8")
                (reports_dir / f"qlib_tw_hybrid_{stamp}.yaml").write_text("x", encoding="utf-8")
                (reports_dir / f"qlib_engine_{stamp}.csv").write_text("x", encoding="utf-8")
                provider_dir = reports_dir / f"qlib_provider_{stamp}"
                provider_dir.mkdir()
                (provider_dir / "features.txt").write_text("x", encoding="utf-8")

            prune_report_artifacts(reports_dir)

            self.assertEqual(len(list(reports_dir.glob("tw_hybrid_*.md"))), 5)
            self.assertEqual(len(list(reports_dir.glob("tw_hybrid_*.csv"))), 5)
            self.assertEqual(len(list(reports_dir.glob("qlib_tw_hybrid_*.yaml"))), 5)
            self.assertEqual(len(list(reports_dir.glob("qlib_engine_*.csv"))), 5)
            self.assertFalse((reports_dir / "qlib_provider_2026-05-01").exists())
            self.assertTrue((reports_dir / "qlib_provider_2026-05-06").exists())


if __name__ == "__main__":
    unittest.main()
