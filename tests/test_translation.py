from __future__ import annotations

import unittest

from stock_signal_system.translation import zh_text


class TranslationTest(unittest.TestCase):
    def test_known_title_is_translated(self):
        result = zh_text("White House memo claims mass AI theft by Chinese firms")

        self.assertIn("白宮", result)
        self.assertNotIn("White House", result)

    def test_mixed_technical_terms_are_translated(self):
        result = zh_text("1H 偏多時，等 5M 回測多方 IFVG 不破；方向 bullish")

        self.assertIn("1 小時", result)
        self.assertIn("5 分鐘", result)
        self.assertIn("反轉型公平價值缺口", result)
        self.assertIn("多方", result)
        self.assertNotIn("bullish", result)


if __name__ == "__main__":
    unittest.main()
