from __future__ import annotations

import unittest
from datetime import date, timedelta

from stock_signal_system.analysis_dashboard import build_dashboard_metrics
from stock_signal_system.models import PriceBar, StockRecommendation, StockSnapshot


class AnalysisDashboardTest(unittest.TestCase):
    def test_dashboard_metrics_include_trend_volume_and_risk(self):
        stock = StockSnapshot(
            symbol="2330",
            name="台積電",
            industry="半導體",
            price=120,
            price_20d_ago=100,
            volume=2000,
            avg_volume_20d=1000,
            revenue_growth_yoy=20,
            gross_margin=50,
            operating_margin=40,
            free_cash_flow_margin=20,
            debt_to_equity=0.2,
            pe_ratio=20,
        )
        rec = StockRecommendation(
            stock=stock,
            score=82,
            rating="高優先觀察",
            reasons=("測試理由",),
            stop_loss="跌破支撐停損",
        )
        start = date(2026, 1, 1)
        bars = [
            PriceBar("2330", start + timedelta(days=i), 100 + i, 103 + i, 99 + i, 101 + i, 1000 + i)
            for i in range(20)
        ]

        metrics = build_dashboard_metrics([rec], {"2330": bars})["2330"]

        self.assertEqual(metrics.ma_alignment, "多頭排列")
        self.assertGreater(metrics.trend_score, 70)
        self.assertEqual(metrics.volume_ratio, 2.0)
        self.assertEqual(metrics.risk_level, "低")
        self.assertIn("分批", metrics.position_sizing)


if __name__ == "__main__":
    unittest.main()
