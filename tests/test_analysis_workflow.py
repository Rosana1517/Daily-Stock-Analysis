from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from quant_research_platform.analysis_workflow import build_workflow_audits
from quant_research_platform.data import Bar


class AnalysisWorkflowTest(unittest.TestCase):
    def test_builds_sixteen_step_audit_per_stock(self):
        row = SimpleNamespace(
            symbol="2330.TW",
            industry="半導體",
            hybrid_score=72.5,
            kronos_score=66.0,
            kronos_return=0.032,
            news_score=68.0,
            technical_score=63.0,
            current_close=900.0,
            predicted_close=930.0,
            action="觀察偏多",
            risk_note="留意追價風險",
        )
        bar = Bar("2330.TW", datetime(2026, 5, 1), 890, 910, 880, 900, 42000)
        tech = SimpleNamespace(
            bias="bullish",
            structure_bias="higher-high",
            patterns=("MA trend up",),
            entry="突破前高後進場",
            stop_loss="跌破支撐停損",
            exit="到達目標分批出場",
        )
        industry_signal = SimpleNamespace(
            industry="半導體",
            score=68.0,
            evidence_count=3,
            catalysts=("AI server demand",),
        )
        news = [SimpleNamespace(title="AI server supply chain demand improves")]

        audits = build_workflow_audits(
            rows=[row],
            bars_by_symbol={"2330.TW": [bar]},
            technicals={"2330.TW": tech},
            realtime_states={},
            industry_signals=[industry_signal],
            news_items=news,
            qlib_path=Path("reports/qlib.yaml"),
            data_source="csv",
            openbb_provider=None,
        )

        audit = audits["2330.TW"]
        self.assertEqual(audit.total, 16)
        self.assertEqual([item.step for item in audit.steps], list(range(1, 17)))
        self.assertGreaterEqual(audit.passed, 5)
        self.assertTrue(any(item.status == "partial" for item in audit.steps))
        self.assertEqual(audit.steps[10].task, "OpenBB/Qlib/Kronos分析")


if __name__ == "__main__":
    unittest.main()
