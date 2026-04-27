from __future__ import annotations

import unittest

from stock_signal_system.config import AppConfig
from stock_signal_system.validation import has_errors, validate_config


class ValidationTest(unittest.TestCase):
    def test_example_config_is_usable(self):
        config = AppConfig.from_file("configs/local.example.json")
        messages = validate_config(config)

        self.assertFalse(has_errors(messages), messages)


if __name__ == "__main__":
    unittest.main()
