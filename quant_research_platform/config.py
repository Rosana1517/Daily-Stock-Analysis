from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union


@dataclass(frozen=True)
class QuantPlatformConfig:
    symbols: tuple[str, ...]
    universe_path: Optional[Path]
    universe_candidate_limit: int
    data_source: str
    ohlcv_path: Optional[Path]
    openbb_provider: Optional[str]
    interval: str
    lookback: int
    prediction_length: int
    top_n: int
    initial_cash: float
    transaction_cost_bps: float
    benchmark_symbol: Optional[str]
    kronos_repo_path: Optional[Path]
    kronos_tokenizer: str
    kronos_model: str
    qlib_data_path: Optional[Path]
    output_dir: Path

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "QuantPlatformConfig":
        config_path = Path(path)
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        base = config_path.parent.parent
        return cls(
            symbols=tuple(raw.get("symbols", [])),
            universe_path=_resolve_optional(base, raw.get("universe_path")),
            universe_candidate_limit=int(raw.get("universe_candidate_limit", 150)),
            data_source=raw.get("data_source", "csv"),
            ohlcv_path=_resolve_optional(base, raw.get("ohlcv_path")),
            openbb_provider=raw.get("openbb_provider"),
            interval=raw.get("interval", "1d"),
            lookback=int(raw.get("lookback", 60)),
            prediction_length=int(raw.get("prediction_length", 5)),
            top_n=int(raw.get("top_n", 5)),
            initial_cash=float(raw.get("initial_cash", 1_000_000)),
            transaction_cost_bps=float(raw.get("transaction_cost_bps", 10)),
            benchmark_symbol=raw.get("benchmark_symbol"),
            kronos_repo_path=_resolve_optional(base, raw.get("kronos_repo_path")),
            kronos_tokenizer=raw.get("kronos_tokenizer", "NeoQuasar/Kronos-Tokenizer-base"),
            kronos_model=raw.get("kronos_model", "NeoQuasar/Kronos-small"),
            qlib_data_path=_resolve_optional(base, raw.get("qlib_data_path")),
            output_dir=_resolve(base, raw.get("output_dir", "reports/quant_platform")),
        )


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _resolve_optional(base: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    return _resolve(base, value)
