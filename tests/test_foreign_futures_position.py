from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.data.foreign_futures_position import (
    LARGE_NET_SHORT_THRESHOLD_CONTRACTS,
    _parse_rows,
)


def _row(contract_code: str, item: str, net: int, long_: int = 0, short_: int = 0) -> dict:
    return {
        "Date": "20260825",
        "ContractCode": contract_code,
        "Item": item,
        "OpenInterest(Long)": str(long_),
        "OpenInterest(Short)": str(short_),
        "OpenInterest(Net)": str(net),
        "ContractValueofOpenInterest(Net)(Thousands)": "123456",
    }


class ParseRowsTest(unittest.TestCase):
    def test_extracts_foreign_taiex_futures_row_among_many(self):
        rows = [
            _row("電子期貨", "外資及陸資", -1000),
            _row("臺股期貨", "自營商", 500),
            _row("臺股期貨", "外資及陸資", -60000, long_=5000, short_=65000),
            _row("臺股期貨", "投信", 200),
        ]

        position = _parse_rows(rows)

        self.assertIsNotNone(position)
        self.assertEqual(position.trade_date, date(2026, 8, 25))
        self.assertEqual(position.net_contracts, -60000)
        self.assertEqual(position.long_contracts, 5000)
        self.assertEqual(position.short_contracts, 65000)

    def test_missing_target_row_returns_none(self):
        rows = [_row("臺股期貨", "自營商", 500), _row("電子期貨", "外資及陸資", -100)]
        self.assertIsNone(_parse_rows(rows))

    def test_empty_rows_returns_none(self):
        self.assertIsNone(_parse_rows([]))

    def test_large_net_short_gets_arbitrage_caution_note(self):
        rows = [_row("臺股期貨", "外資及陸資", -LARGE_NET_SHORT_THRESHOLD_CONTRACTS - 1)]

        position = _parse_rows(rows)

        self.assertIn("無風險套利", position.caution_note)
        self.assertIn("不宜單獨解讀為崩盤前兆", position.caution_note)

    def test_large_net_long_gets_bullish_leaning_note(self):
        rows = [_row("臺股期貨", "外資及陸資", LARGE_NET_SHORT_THRESHOLD_CONTRACTS + 1)]

        position = _parse_rows(rows)

        self.assertIn("淨多單", position.caution_note)

    def test_small_net_position_gets_neutral_note(self):
        rows = [_row("臺股期貨", "外資及陸資", 100)]

        position = _parse_rows(rows)

        self.assertIn("方向性尚不明顯", position.caution_note)


if __name__ == "__main__":
    unittest.main()
