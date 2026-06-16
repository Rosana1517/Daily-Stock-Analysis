from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stock_signal_system.cli_handlers import _validate_chip_snapshot_schema


class CliHandlersTest(unittest.TestCase):
    def test_validate_chip_snapshot_schema_accepts_new_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tw_chip_snapshot.csv"
            path.write_text(
                ",".join(
                    [
                        "symbol",
                        "top10_main_force_buy_strength",
                        "top10_main_force_net_buy",
                        "branch_main_force_buy_streak_days",
                        "foreign_buy_streak_days",
                        "chip_data_source",
                        "chip_data_source_status",
                    ]
                )
                + "\n2330,55.0,1200,2,3,TWSE T86 official + HiStock branch,official+broker\n",
                encoding="utf-8-sig",
            )

            _validate_chip_snapshot_schema(path)

    def test_validate_chip_snapshot_schema_rejects_proxy_only_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tw_chip_snapshot.csv"
            path.write_text(
                "symbol,top10_main_force_buy_strength_proxy,foreign_buy_streak_days,chip_data_source\n"
                "2330,55.0,3,TWSE T86 official proxy\n",
                encoding="utf-8-sig",
            )

            with self.assertRaises(ValueError):
                _validate_chip_snapshot_schema(path)


if __name__ == "__main__":
    unittest.main()
