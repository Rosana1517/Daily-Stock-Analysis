from __future__ import annotations

import tempfile
import unittest
import builtins
from datetime import date
from pathlib import Path
from unittest.mock import patch

from quant_research_platform.config import QuantPlatformConfig
from quant_research_platform.data import fetch_openbb_ohlcv
from quant_research_platform.workflow import run_quant_workflow

_REAL_IMPORT = builtins.__import__


class QuantResearchPlatformTest(unittest.TestCase):
    def test_fetch_openbb_ohlcv_falls_back_to_yfinance_when_openbb_missing(self):
        expected = {"2330.TW": []}
        with patch("builtins.__import__", side_effect=_import_without_openbb):
            with patch("quant_research_platform.data.fetch_yahoo_ohlcv", return_value=expected) as fallback:
                result = fetch_openbb_ohlcv(["2330.TW"], provider="yfinance", period="1y")

        fallback.assert_called_once_with(["2330.TW"], "1y")
        self.assertEqual(result, expected)

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


def _import_without_openbb(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "openbb":
        raise ImportError("No module named 'openbb'")
    return _REAL_IMPORT(name, globals, locals, fromlist, level)


if __name__ == "__main__":
    unittest.main()
