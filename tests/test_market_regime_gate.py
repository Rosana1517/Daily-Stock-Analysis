from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quant_research_platform.market_regime_gate import evaluate_market_regime_gate


class MarketRegimeGateTest(unittest.TestCase):
    def test_fails_open_when_fetch_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("quant_research_platform.market_regime_gate._fetch_taiex_closes", return_value=[]):
                gate = evaluate_market_regime_gate(Path(tmp_dir))
            self.assertTrue(gate.bullish)
            self.assertFalse(gate.available)
            self.assertIsNone(gate.close)

    def test_bullish_when_close_above_ma20(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            closes = [100.0] * 19 + [110.0]
            with patch("quant_research_platform.market_regime_gate._fetch_taiex_closes", return_value=closes):
                gate = evaluate_market_regime_gate(Path(tmp_dir))
            self.assertTrue(gate.available)
            self.assertTrue(gate.bullish)
            self.assertAlmostEqual(gate.ma20, sum(closes[-20:]) / 20.0)

    def test_bearish_when_close_below_ma20(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            closes = [100.0] * 19 + [80.0]
            with patch("quant_research_platform.market_regime_gate._fetch_taiex_closes", return_value=closes):
                gate = evaluate_market_regime_gate(Path(tmp_dir))
            self.assertTrue(gate.available)
            self.assertFalse(gate.bullish)

    def test_result_is_cached_between_calls(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            closes = [100.0] * 19 + [110.0]
            with patch("quant_research_platform.market_regime_gate._fetch_taiex_closes", return_value=closes) as mocked:
                evaluate_market_regime_gate(Path(tmp_dir))
                evaluate_market_regime_gate(Path(tmp_dir))
            mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
