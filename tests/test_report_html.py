from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_signal_system.models import IndustrySignal, StockRecommendation, StockSnapshot
from stock_signal_system.report import (
    build_report,
    markdown_to_html,
    public_report_url,
    save_report,
)


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
        self.assertIn('id="chipRadarToggle" type="checkbox" checked', html)
        self.assertIn('id="newStrategyToggle" type="checkbox">', html)
        self.assertIn('id="legacyStrategyToggle" type="checkbox">', html)
        self.assertIn("第 1 層：品質底池（選股範圍）", html)
        self.assertIn("第 2 層：主力動向（誰在買）", html)
        self.assertIn("第 3 層：發動確認（何時買）", html)
        self.assertIn("★最佳買點", html)
        self.assertIn("盤整區間突破", html)
        self.assertIn("報告結論", html)
        self.assertIn("official+broker", html)
        self.assertIn("strategyVisible", html)
        self.assertIn("filters: {chipRadar: true, newStrategy: false, oldStrategy: false}", html)
        self.assertIn('data-layer="markers">', html)
        self.assertIn('data-layer="limitUp">', html)
        self.assertIn('data-layer="monthlyMacd">', html)
        self.assertIn('data-layer="ma20Volume">', html)
        self.assertNotIn("technical-chart-data", html)

    def test_hybrid_quant_daily_report_renders_dark_dashboard(self):
        markdown = """# Hybrid Quant Daily Stock Report - 2026-05-13

## Top Ranking

| Symbol | Name | Industry | Hybrid | Kronos | Realtime | Action |
|---|---|---|---|---|---|---|
| 2330.TW | 台積電 | 半導體 | 82 | 5% | 持平 | 買進觀察 |

## RSS Industry Signals

| Industry | RSS Score | Key Catalyst |
|---|---|---|
| 半導體 | 75 | AI 需求成長 |

## Investment Notes

- 留意大盤 20MA 狀態

## Portfolio Simulation

- 觀察倉位 5%

## News Feed

- 台積電法說會優於預期
"""

        html = markdown_to_html(markdown, "Hybrid Quant Daily Stock Report")

        self.assertIn("STOCK RANKING", html)
        self.assertIn("台積電", html)
        self.assertIn("半導體", html)
        self.assertIn("AI 需求成長", html)
        self.assertIn("留意大盤 20MA 狀態", html)
        self.assertIn("台積電法說會優於預期", html)
        self.assertIn("gauge-ring", html)


class BuildReportTest(unittest.TestCase):
    def test_build_report_includes_industry_signal_and_recommendation(self):
        report_date = date(2026, 5, 13)
        industry_signals = [IndustrySignal("半導體", 78.0, ("AI demand",), 3)]
        recommendations = [_recommendation()]

        content = build_report(report_date, industry_signals, recommendations)

        self.assertIn("每日選股觀察報告 - 2026-05-13", content)
        self.assertIn("半導體: 訊號分數 78.0", content)
        self.assertIn("2330 台積電", content)
        self.assertIn("為何值得關注", content)

    def test_build_report_handles_empty_signals_and_recommendations(self):
        content = build_report(date(2026, 5, 13), [], [])

        self.assertIn("今日未偵測到足夠明確且可對應台股供應鏈的產業訊號。", content)
        self.assertIn("今日沒有符合分數、風險收益比與只做多條件的候選標的。", content)
        self.assertIn("今日暫不新增觀察標的。", content)


class SaveReportTest(unittest.TestCase):
    def test_save_report_writes_markdown_file_named_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            path = save_report(report_dir, date(2026, 5, 13), "# 內容")

            self.assertEqual(path, report_dir / "stock_signals_2026-05-13.md")
            self.assertEqual(path.read_text(encoding="utf-8"), "# 內容")


def _recommendation() -> StockRecommendation:
    stock = StockSnapshot(
        symbol="2330",
        name="台積電",
        industry="半導體",
        price=100,
        price_20d_ago=92,
        volume=2_000_000,
        avg_volume_20d=1_000_000,
        revenue_growth_yoy=12,
        gross_margin=35,
        operating_margin=14,
        free_cash_flow_margin=8,
        debt_to_equity=0.4,
        pe_ratio=20,
    )
    return StockRecommendation(
        stock=stock,
        score=75.0,
        rating="買進觀察",
        reasons=("產業訊號強",),
        risks=(),
        entry_plan="站上均線買進",
        stop_loss="跌破均線出場",
        exit_plan="達目標價分批出場",
    )


if __name__ == "__main__":
    unittest.main()
