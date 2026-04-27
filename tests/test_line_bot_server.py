from __future__ import annotations

import base64
import hashlib
import hmac
import unittest

from stock_signal_system.line_bot_server import _verify_signature


class LineBotServerTest(unittest.TestCase):
    def test_verify_signature(self):
        body = b'{"events":[]}'
        secret = "secret"
        signature = base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode("utf-8")

        self.assertTrue(_verify_signature(body, secret, signature))
        self.assertFalse(_verify_signature(body, secret, "bad"))


if __name__ == "__main__":
    unittest.main()
