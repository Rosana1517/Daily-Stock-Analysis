from __future__ import annotations

import unittest
from dataclasses import dataclass

from quant_research_platform.agent_workflow import AGENT_NAMES, agent_workflow_markdown, run_five_agent_workflow


@dataclass(frozen=True)
class Row:
    symbol: str
    name: str
    industry: str
    kronos_return: float
    kronos_score: float
    news_score: float
    technical_score: float
    realtime_score: float
    hybrid_score: float
    risk_note: str
    technical_evidence: tuple[str, ...] = ()


class AgentWorkflowTest(unittest.TestCase):
    def test_five_agent_names_and_technical_evidence_are_rendered(self):
        result = run_five_agent_workflow(
            [
                Row(
                    symbol="ABC",
                    name="Alpha",
                    industry="AI",
                    kronos_return=0.03,
                    kronos_score=68,
                    news_score=70,
                    technical_score=66,
                    realtime_score=62,
                    hybrid_score=68,
                    risk_note="風險穩定",
                    technical_evidence=("support=95.00", "resistance=105.00", "volume_ratio=1.30"),
                )
            ]
        )

        markdown = "\n".join(agent_workflow_markdown(result))

        for name in AGENT_NAMES:
            self.assertIn(name, markdown)
        self.assertEqual(result.portfolio_manager[0].stance, "include_daily_report")
        self.assertIn("納入每日報告", markdown)
        self.assertIn("Technical_Analyst_Agent 證據", markdown)
        self.assertIn("support=95.00", markdown)

    def test_devil_advocate_veto_blocks_daily_report(self):
        result = run_five_agent_workflow(
            [
                Row(
                    symbol="XYZ",
                    name="Xeno",
                    industry="AI",
                    kronos_return=-0.02,
                    kronos_score=38,
                    news_score=42,
                    technical_score=40,
                    realtime_score=41,
                    hybrid_score=72,
                    risk_note="negative divergence",
                    technical_evidence=("ohlcv=data_limited",),
                )
            ]
        )

        self.assertTrue(result.devil_advocate[0].veto)
        self.assertEqual(result.devil_advocate[0].stance, "veto")
        self.assertIn("veto_level=block", result.devil_advocate[0].evidence)
        self.assertEqual(result.portfolio_manager[0].stance, "exclude_by_veto")
        self.assertTrue(result.portfolio_manager[0].veto)
        self.assertIn("veto_level=block", result.portfolio_manager[0].evidence)
        self.assertEqual(result.portfolio_manager[0].score, 0.0)
        self.assertIn("因否決排除", "\n".join(agent_workflow_markdown(result)))

    def test_stable_chinese_risk_note_is_not_red_flag(self):
        result = run_five_agent_workflow(
            [
                Row(
                    symbol="SAFE",
                    name="SafeCo",
                    industry="AI",
                    kronos_return=0.02,
                    kronos_score=68,
                    news_score=72,
                    technical_score=64,
                    realtime_score=63,
                    hybrid_score=67,
                    risk_note="風險穩定",
                )
            ]
        )

        devil = result.devil_advocate[0]

        self.assertFalse(devil.veto)
        self.assertIn("red_flags=0", devil.evidence)
        self.assertIn("veto_level=none", devil.evidence)
        self.assertEqual(result.portfolio_manager[0].stance, "include_daily_report")


if __name__ == "__main__":
    unittest.main()
