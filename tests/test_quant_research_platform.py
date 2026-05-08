from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from quant_research_platform.config import QuantPlatformConfig
from quant_research_platform.workflow import run_quant_workflow


class QuantResearchPlatformTest(unittest.TestCase):
    def test_quant_workflow_generates_report(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = QuantPlatformConfig(
                symbols=("2330", "2382", "2454"),
                universe_path=None,
                universe_candidate_limit=150,
                data_source="csv",
                ohlcv_path=Path("examples/price_history.csv"),
                openbb_provider=None,
                interval="1d",
                lookback=20,
                prediction_length=5,
                top_n=2,
                initial_cash=1_000_000,
                transaction_cost_bps=10,
                benchmark_symbol="2330",
                kronos_repo_path=None,
                kronos_tokenizer="NeoQuasar/Kronos-Tokenizer-base",
                kronos_model="NeoQuasar/Kronos-small",
                qlib_data_path=None,
                output_dir=Path(tmp_dir),
            )

            result = run_quant_workflow(config, run_date=date(2026, 4, 30))

            self.assertGreaterEqual(len(result.signals), 1)
            self.assertLessEqual(len(result.backtest.selected), 2)
            self.assertTrue(Path(result.report_path).exists())
            self.assertTrue(Path(result.signal_csv_path).exists())
            self.assertTrue(Path(result.qlib_handoff_path).exists())
            report = Path(result.report_path).read_text(encoding="utf-8")
            self.assertIn("Quant Research Platform Report", report)
            self.assertIn("Signal Ranking", report)
            self.assertIn("Portfolio Simulation", report)


if __name__ == "__main__":
    unittest.main()
