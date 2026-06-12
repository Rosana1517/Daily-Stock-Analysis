from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from stock_signal_system.config import AppConfig
from stock_signal_system.pipeline import _notification_body, run_pipeline


class PipelineTest(unittest.TestCase):
    def test_pipeline_generates_ranked_report(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig.from_file("configs/local.example.json")
            config = AppConfig(
                news_path=config.news_path,
                rss_sources_path=config.rss_sources_path,
                stock_path=config.stock_path,
                price_history_path=config.price_history_path,
                price_1h_path=config.price_1h_path,
                price_5m_path=config.price_5m_path,
                watch_industries=config.watch_industries,
                top_n=3,
                min_score=60,
                market_scope=config.market_scope,
                trade_direction=config.trade_direction,
                holding_period_days=config.holding_period_days,
                max_watchlist=3,
                min_industry_signals=3,
                min_recommendations=3,
                trading_session=config.trading_session,
                notification_min_score=config.notification_min_score,
                notification_mode=config.notification_mode,
                report_dir=tmp_path,
                report_public_base_url=None,
                notification_webhook_env=None,
                line_channel_access_token_env=None,
                line_to_env=None,
                line_broadcast=False,
            )

            result = run_pipeline(config, report_date=date(2026, 4, 24))

            self.assertGreaterEqual(len(result.industry_signals), 3)
            self.assertGreaterEqual(len(result.recommendations), 3)
            self.assertGreaterEqual(result.recommendations[0].score, result.recommendations[-1].score)
            self.assertEqual(result.notification_status, "disabled")
            report = (tmp_path / "stock_signals_2026-04-24.md").read_text(encoding="utf-8")
            html_report = (tmp_path / "stock_signals_2026-04-24.html").read_text(encoding="utf-8")
            self.assertIn("資料更新摘要", report)
            self.assertIn("今日產業訊號", report)
            self.assertIn("進場條件", report)
            self.assertIn("停損", report)
            self.assertIn("<html", html_report)

    def test_report_link_notification_contains_only_public_report_url(self):
        body = _notification_body(
            recommendations=[],
            report_path="reports/stock_signals_2026-04-29.md",
            notification_min_score=80,
            notification_mode="report_link",
            report="full report",
            report_url="https://example.com/reports/stock_signals_2026-04-29.html",
        )

        self.assertEqual(body, "https://example.com/reports/stock_signals_2026-04-29.html")
        self.assertNotIn("reports/stock_signals_2026-04-29.md", body)

    def test_quant_pipeline_passes_snapshot_and_intraday_paths_to_hybrid_runner(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            report_path = tmp_path / "tw_hybrid_2026-06-12.md"
            report_path.write_text("hybrid report", encoding="utf-8")
            config = AppConfig.from_file("configs/daily_quant_hybrid.example.json")
            config = AppConfig(
                news_path=config.news_path,
                rss_sources_path=config.rss_sources_path,
                stock_path=config.stock_path,
                price_history_path=config.price_history_path,
                price_1h_path=config.price_1h_path,
                price_5m_path=config.price_5m_path,
                watch_industries=config.watch_industries,
                top_n=config.top_n,
                min_score=config.min_score,
                market_scope=config.market_scope,
                trade_direction=config.trade_direction,
                holding_period_days=config.holding_period_days,
                max_watchlist=config.max_watchlist,
                min_industry_signals=config.min_industry_signals,
                min_recommendations=config.min_recommendations,
                trading_session=config.trading_session,
                notification_min_score=config.notification_min_score,
                notification_mode=config.notification_mode,
                report_dir=tmp_path,
                report_public_base_url=config.report_public_base_url,
                notification_webhook_env=None,
                line_channel_access_token_env=None,
                line_to_env=None,
                line_broadcast=False,
                portfolio_path=config.portfolio_path,
                quant_config_path=config.quant_config_path,
                quant_realtime_cache_path=config.quant_realtime_cache_path,
            )

            with patch("quant_research_platform.hybrid.run_tw_hybrid", return_value=(report_path, tmp_path / "signals.csv", tmp_path / "qlib.yaml", "disabled")) as hybrid_run:
                with patch("stock_signal_system.pipeline.save_report_html", return_value=tmp_path / "stock_signals_2026-06-12.html"):
                    with patch("stock_signal_system.pipeline.send_notification", return_value="disabled"):
                        run_pipeline(config, report_date=date(2026, 6, 12))

            kwargs = hybrid_run.call_args.kwargs
            self.assertEqual(kwargs["stock_snapshot_path"], config.stock_path)
            self.assertEqual(kwargs["price_1h_path"], config.price_1h_path)
            self.assertEqual(kwargs["price_5m_path"], config.price_5m_path)


if __name__ == "__main__":
    unittest.main()
