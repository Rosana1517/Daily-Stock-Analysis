from __future__ import annotations

import unittest

from stock_signal_system.workflow import ANALYSIS_WORKFLOW, workflow_summary_lines


class WorkflowTest(unittest.TestCase):
    def test_workflow_contains_user_requested_steps(self):
        self.assertEqual(len(ANALYSIS_WORKFLOW), 23)
        self.assertEqual(ANALYSIS_WORKFLOW[0].name, "RSS、新聞、政策、輿情蒐集")
        self.assertEqual(ANALYSIS_WORKFLOW[-1].name, "追蹤成效與回測")

    def test_workflow_maps_stock_skills(self):
        all_skills = {skill for step in ANALYSIS_WORKFLOW for skill in step.skills}

        self.assertIn("stock-analysis", all_skills)
        self.assertIn("stock-checker-analysis", all_skills)
        self.assertIn("finance-sentiment", all_skills)
        self.assertIn("stock-liquidity", all_skills)

    def test_summary_lines_are_report_ready(self):
        lines = workflow_summary_lines()

        self.assertEqual(len(lines), 23)
        self.assertTrue(lines[0].startswith("1. RSS"))


if __name__ == "__main__":
    unittest.main()
