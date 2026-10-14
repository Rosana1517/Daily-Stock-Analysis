from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from quant_research_platform.hybrid import (
    _politician_alert_lines,
    _politician_entry,
    _politician_watch_section,
    _write_politician_alert,
)
from stock_signal_system.data.politician_holdings import PoliticianHolding, build_politician_pool
from tests.test_hybrid_scoring import _make_row


def _legislator(name: str, total: float, holdings: list[dict], declared: str = "2025-11-01") -> dict:
    return {
        "name": name,
        "latestDeclarationDate": declared,
        "stockSummary": {"estimatedMarketValueTotal": total},
        "holdings": holdings,
    }


def _stock(code: str, name: str, value: float) -> dict:
    return {"source": "stock", "stockCode": code, "name": name, "marketValue": value}


MARKETS = {"2330": "tse", "2317": "tse", "6488": "otc", "1702": "tse"}


class BuildPoliticianPoolTest(unittest.TestCase):
    def test_keeps_top_n_by_market_value_and_meaningful_positions_only(self):
        legislators = [
            _legislator("小咖", 10.0, [_stock("2330", "台積電", 50_000_000)]),  # 不在前 2 名
            _legislator("甲", 300.0, [_stock("2330", "台積電", 9_000_000), _stock("1702", "南僑", 907)]),  # 南僑是零股
            _legislator("乙", 200.0, [_stock("2330", "台積電", 3_000_000), _stock("6488", "環球晶", 2_000_000)]),
        ]

        pool = build_politician_pool(legislators, MARKETS, top_n=2, min_market_value=1_000_000)

        self.assertEqual(list(pool), ["2330.TW", "6488.TWO"])
        self.assertEqual(pool["2330.TW"].holders, ("甲", "乙"))
        self.assertEqual(pool["2330.TW"].market_value, 12_000_000)
        self.assertEqual(pool["6488.TWO"].holders, ("乙",))

    def test_skips_funds_and_codes_not_in_listed_or_otc_universe(self):
        legislators = [
            _legislator(
                "甲",
                1.0,
                [
                    {"source": "fund", "stockCode": "0050", "name": "元大台灣50", "marketValue": 9e6},
                    _stock("9999", "興櫃股", 9e6),
                    {"source": "stock", "name": "未上市", "marketValue": 9e6},
                ],
            )
        ]
        self.assertEqual(build_politician_pool(legislators, MARKETS, top_n=5), {})


class PoliticianEntryTest(unittest.TestCase):
    def _row(self, **kwargs):
        return replace(_make_row("2317.TW", "其他電子業", 60.0), politician_holders=("蘇清泉",), **kwargs)

    def test_entry_needs_buy_signal_and_no_chasing(self):
        self.assertTrue(_politician_entry(self._row(short_entry=True, runup_5d=-0.02)))
        self.assertFalse(_politician_entry(self._row(short_entry=True, runup_5d=0.08)))  # 已漲多
        self.assertFalse(_politician_entry(self._row(runup_5d=-0.02)))  # 沒有買點
        self.assertFalse(_politician_entry(replace(self._row(short_entry=True), politician_holders=())))

    def test_alert_lines_and_file_lifecycle(self):
        pool = {"2317.TW": PoliticianHolding("2317.TW", "2317", "鴻海", ("蘇清泉",), 8.4e6, "2025-11-05")}
        rows = [self._row(dip_reversal=True, runup_5d=-0.05)]

        lines = _politician_alert_lines(rows, pool)
        self.assertEqual(lines[0], "🏛️ 政治人物持股 進場訊號")
        self.assertIn("2317", lines[1])
        self.assertIn("蘇清泉", lines[1])
        self.assertIn("◆超跌抄底", lines[1])
        self.assertIn("2025-11", lines[-1])

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "alert.txt"
            _write_politician_alert(rows, pool, path)
            self.assertTrue(path.exists())
            # 隔天沒有訊號 → 檔案要被清掉，不能把前一天的通知再發一次
            _write_politician_alert([self._row(runup_5d=0.1)], pool, path)
            self.assertFalse(path.exists())

    def test_report_section_states_data_lag(self):
        text = "\n".join(_politician_watch_section([self._row(best_entry=True, runup_5d=0.0)]))
        self.assertIn("約一年前的申報資料", text)
        self.assertIn("進場訊號", text)


if __name__ == "__main__":
    unittest.main()
