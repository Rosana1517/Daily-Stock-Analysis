from __future__ import annotations

import unittest
from datetime import date

from stock_signal_system.data.broker_source import parse_histock_branch_html


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

    def test_parse_histock_branch_html_returns_degraded_when_rows_missing(self):
        snapshot = parse_histock_branch_html("<html><body>empty</body></html>", "2330", "https://histock.tw/stock/branch.aspx?no=2330")

        self.assertEqual(snapshot.source_status, "degraded")
        self.assertEqual(snapshot.buy_trades, ())
        self.assertEqual(snapshot.sell_trades, ())


if __name__ == "__main__":
    unittest.main()
