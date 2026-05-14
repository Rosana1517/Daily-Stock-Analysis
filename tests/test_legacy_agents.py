from __future__ import annotations

import unittest

from agents.agent_orchestrator import run_agent_workflow
from agents.stock_agents import MarketIntelligenceAgent


class LegacyAgentsTest(unittest.TestCase):
    def test_legacy_agent_modules_are_retired(self):
        with self.assertRaisesRegex(RuntimeError, "retired"):
            MarketIntelligenceAgent().analyze(object())

        with self.assertRaisesRegex(RuntimeError, "retired"):
            run_agent_workflow()


if __name__ == "__main__":
    unittest.main()
