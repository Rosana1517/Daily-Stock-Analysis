from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from stock_signal_system.data.broker_source import fetch_histock_branch_snapshot, parse_histock_branch_html

_DEGRADED_HTML = '<div class="cfdate">2017.10.18</div><script>var jsonDatas = eval();</script>'
_OK_HTML = """
<table>
  <tr>
    <td><a href="/stock/brokertrace.aspx?bno=1470&amp;no=2330" target="_blank">賣超券商A</a></td>
    <td class="hidecell">132</td><td class="hidecell">654</td><td>-522</td><td>2359.74</td>
    <td><a href="/stock/brokertrace.aspx?bno=9800&amp;no=2330" target="_blank">買超券商A</a></td>
    <td class="hidecell">2,892</td><td class="hidecell">478</td><td>2,414</td><td>2365.37</td>
  </tr>
</table>
"""


class BrokerSourceTest(unittest.TestCase):
    def test_parse_histock_branch_html_extracts_buy_and_sell_tables(self):
        html = """
        <div>更新時間:2026.06.15</div>
        <table>
          <tr class="alt-row">
            <td><a href="/stock/brokertrace.aspx?bno=1470&amp;no=2330" target="_blank">賣超券商A</a></td>
            <td class="hidecell">1,414</td><td class="hidecell">2,209</td><td>-794</td><td>2362</td>
            <td><a href="/stock/brokertrace.aspx?bno=1650&amp;no=2330" target="_blank">買超券商A</a></td>
            <td class="hidecell">3,839</td><td class="hidecell">1,080</td><td>2,759</td><td>2364.44</td>
          </tr>
          <tr>
            <td><a href="/stock/brokertrace.aspx?bno=9200&amp;no=2330" target="_blank">賣超券商B</a></td>
            <td class="hidecell">132</td><td class="hidecell">654</td><td>-522</td><td>2359.74</td>
            <td><a href="/stock/brokertrace.aspx?bno=9800&amp;no=2330" target="_blank">買超券商B</a></td>
            <td class="hidecell">2,892</td><td class="hidecell">478</td><td>2,414</td><td>2365.37</td>
          </tr>
        </table>
        """

        snapshot = parse_histock_branch_html(html, "2330", "https://histock.tw/stock/branch.aspx?no=2330", requested_date=date(2026, 6, 15))

        self.assertEqual(snapshot.source_status, "ok")
        self.assertEqual(snapshot.trade_date, date(2026, 6, 15))
        self.assertEqual(snapshot.buy_trades[0].broker, "買超券商A")
        self.assertEqual(snapshot.buy_trades[0].net_shares, 2759)
        self.assertEqual(snapshot.sell_trades[0].broker, "賣超券商A")
        self.assertEqual(snapshot.sell_trades[0].net_shares, -794)

    def test_parse_histock_branch_html_handles_empty_count_cells(self):
        # 真實頁面裡，一檔券商當天若只出現在買方或賣方，另一側的儲存格會是
        # 完全空的 <td></td>（不是 0）。這種列以前會讓正則配對失敗，導致
        # finditer 從下一列重新配對，把多列券商名稱黏在一起（見
        # project_state.md 2026-08-27 的查證記錄）。
        html = """
        <table>
          <tr>
            <td><a href="/stock/brokertrace.aspx?bno=1470&amp;no=2330" target="_blank">賣超券商A</a></td>
            <td class="hidecell"></td><td class="hidecell">190</td><td>-189</td><td></td>
            <td><a href="/stock/brokertrace.aspx?bno=1650&amp;no=2330" target="_blank">買超券商A</a></td>
            <td class="hidecell">584</td><td class="hidecell">391</td><td>192</td><td>2371.94</td>
          </tr>
          <tr>
            <td><a href="/stock/brokertrace.aspx?bno=9200&amp;no=2330" target="_blank">賣超券商B</a></td>
            <td class="hidecell">132</td><td class="hidecell">654</td><td>-522</td><td>2359.74</td>
            <td><a href="/stock/brokertrace.aspx?bno=9800&amp;no=2330" target="_blank">買超券商B</a></td>
            <td class="hidecell">2,892</td><td class="hidecell">478</td><td>2,414</td><td>2365.37</td>
          </tr>
        </table>
        """

        snapshot = parse_histock_branch_html(html, "2330", "https://histock.tw/stock/branch.aspx?no=2330")

        self.assertEqual(len(snapshot.buy_trades), 2)
        self.assertEqual(len(snapshot.sell_trades), 2)
        self.assertEqual(snapshot.sell_trades[0].broker, "賣超券商A")
        self.assertEqual(snapshot.sell_trades[0].buy_shares, 0)
        self.assertEqual(snapshot.sell_trades[0].average_price, 0.0)
        self.assertEqual(snapshot.buy_trades[1].broker, "買超券商B")
        self.assertEqual(snapshot.buy_trades[1].net_shares, 2414)

    def test_parse_histock_branch_html_returns_degraded_when_rows_missing(self):
        snapshot = parse_histock_branch_html("<html><body>empty</body></html>", "2330", "https://histock.tw/stock/branch.aspx?no=2330")

        self.assertEqual(snapshot.source_status, "degraded")
        self.assertEqual(snapshot.buy_trades, ())
        self.assertEqual(snapshot.sell_trades, ())

    def test_fetch_histock_branch_snapshot_retries_on_degraded_sentinel_response(self):
        # HiStock 有時會回傳一個空的 sentinel 版型（見 broker_source.py 的
        # HISTOCK_BROKER_MAX_ATTEMPTS 註解），即使該日已公告也一樣。重試應該
        # 在收到 degraded 結果後再打一次，換到正常回應就直接用。
        with TemporaryDirectory() as tmp:
            with patch(
                "stock_signal_system.data.broker_source.RateLimitedHttpClient.get_text",
                side_effect=[_DEGRADED_HTML, _OK_HTML],
            ) as mock_get_text, patch("stock_signal_system.data.broker_source.time.sleep"):
                snapshot = fetch_histock_branch_snapshot(
                    "2330", Path(tmp), trade_date=date(2026, 8, 24), max_attempts=3, retry_delay_seconds=0
                )

        self.assertEqual(mock_get_text.call_count, 2)
        self.assertEqual(snapshot.source_status, "ok")
        self.assertEqual(len(snapshot.buy_trades), 1)

    def test_fetch_histock_branch_snapshot_gives_up_after_max_attempts(self):
        with TemporaryDirectory() as tmp:
            with patch(
                "stock_signal_system.data.broker_source.RateLimitedHttpClient.get_text",
                return_value=_DEGRADED_HTML,
            ) as mock_get_text, patch("stock_signal_system.data.broker_source.time.sleep"):
                snapshot = fetch_histock_branch_snapshot(
                    "2330", Path(tmp), trade_date=date(2026, 8, 24), max_attempts=3, retry_delay_seconds=0
                )

        self.assertEqual(mock_get_text.call_count, 3)
        self.assertEqual(snapshot.source_status, "degraded")


if __name__ == "__main__":
    unittest.main()
