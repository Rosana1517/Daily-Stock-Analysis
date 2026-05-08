from __future__ import annotations

import unittest
from datetime import datetime

from quant_research_platform.hybrid import _realtime_state_from_quote
from quant_research_platform.twstock_fallback import _dedupe_symbols, _parse_twstock_payload
from quant_research_platform.twse_realtime import TwseRealtimeQuote


class TwstockFallbackTest(unittest.TestCase):
    def test_dedupe_symbols_accepts_channels_and_platform_symbols(self):
        symbols = _dedupe_symbols(["2330.TW", "tse_2330.tw", "otc:6488", "6488.TWO"])

        self.assertEqual(symbols, ["2330", "6488"])

    def test_parse_twstock_payload_maps_quote_fields(self):
        payload = {
            "2330": {
                "timestamp": "2026-05-08 13:30:00",
                "info": {"code": "2330", "name": "台積電", "channel": "tse_2330.tw"},
                "realtime": {
                    "latest_trade_price": "900",
                    "open": "890",
                    "high": "905",
                    "low": "880",
                    "accumulate_trade_volume": "12345",
                },
            }
        }

        quotes = _parse_twstock_payload(payload)

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].symbol, "2330")
        self.assertEqual(quotes[0].market, "tse")
        self.assertEqual(quotes[0].price, 900)
        self.assertEqual(quotes[0].previous_close, 890)
        self.assertEqual(quotes[0].volume, 12345)

    def test_realtime_state_from_twstock_quote_uses_otc_suffix(self):
        quote = TwseRealtimeQuote(
            symbol="6488",
            market="otc",
            name="環球晶",
            timestamp=datetime(2026, 5, 8, 13, 30),
            open=100,
            high=105,
            low=99,
            price=104,
            previous_close=100,
            volume=1000,
            raw_channel="otc_6488.tw",
        )

        state = _realtime_state_from_quote(quote)

        self.assertEqual(state.symbol, "6488.TWO")
        self.assertAlmostEqual(state.intraday_return, 0.04)
        self.assertIn("盤中偏多", state.status)


if __name__ == "__main__":
    unittest.main()
