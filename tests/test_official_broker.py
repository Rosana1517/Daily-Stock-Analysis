from __future__ import annotations

import unittest

from stock_signal_system.data.official_broker import is_official_bank_broker


class IsOfficialBankBrokerTest(unittest.TestCase):
    def test_matches_known_official_bank_branch_names(self):
        for name in ("兆豐-台北", "合作金庫-高雄", "合庫-台中", "第一金-新竹", "華南-台南", "土地銀行-桃園", "台銀-台北"):
            self.assertTrue(is_official_bank_broker(name), name)

    def test_does_not_match_ordinary_brokers(self):
        for name in ("凱基-台北", "元大-桃園", "摩根大通", "富邦-台中"):
            self.assertFalse(is_official_bank_broker(name), name)

    def test_handles_empty_or_none(self):
        self.assertFalse(is_official_bank_broker(""))
        self.assertFalse(is_official_bank_broker(None))


if __name__ == "__main__":
    unittest.main()
