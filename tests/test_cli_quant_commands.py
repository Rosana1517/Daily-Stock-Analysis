from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from stock_signal_system import cli
from stock_signal_system.cli_handlers import _symbol_to_realtime_channel


class CliQuantCommandsTest(unittest.TestCase):
    def test_symbol_to_realtime_channel_maps_tw_and_ttwo(self):
        self.assertEqual(_symbol_to_realtime_channel("2330.TW"), "tse:2330")
        self.assertEqual(_symbol_to_realtime_channel("6488.TWO"), "otc:6488")
        self.assertEqual(_symbol_to_realtime_channel("2454"), "tse:2454")

    def test_cli_dispatches_refresh_quant_ohlcv(self):
        with patch.object(sys, "argv", ["cli.py", "refresh-quant-ohlcv", "--config", "configs/quant_platform.tw.example.json"]):
            with patch("stock_signal_system.cli.handle_refresh_quant_ohlcv") as handler:
                cli.main()
        handler.assert_called_once()

    def test_cli_dispatches_refresh_quant_realtime(self):
        with patch.object(
            sys,
            "argv",
            [
                "cli.py",
                "refresh-quant-realtime",
                "--config",
                "configs/quant_platform.tw.example.json",
                "--cache",
                "data/twse_common_stock_realtime_cache.csv",
            ],
        ):
            with patch("stock_signal_system.cli.handle_refresh_quant_realtime") as handler:
                cli.main()
        handler.assert_called_once()


if __name__ == "__main__":
    unittest.main()
