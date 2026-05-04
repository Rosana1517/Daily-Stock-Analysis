from __future__ import annotations

from pathlib import Path

from stock_signal_system.data.csv_sources import load_stocks
from stock_signal_system.models import StockSnapshot


def load_fundamental_snapshots(path: Path | None) -> dict[str, StockSnapshot]:
    if not path or not path.exists():
        return {}
    return {item.symbol: item for item in load_stocks(path)}
