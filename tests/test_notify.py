from __future__ import annotations

import unittest

from stock_signal_system.notify import _split_line_text


class NotifyTest(unittest.TestCase):
    def test_split_line_text_limits_to_five_messages(self):
        chunks = _split_line_text("A" * 25000, max_chars=4500, max_messages=5)

        self.assertEqual(len(chunks), 5)
        self.assertTrue(all(len(chunk) <= 4500 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
