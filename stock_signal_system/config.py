from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union


@dataclass(frozen=True)
class AppConfig:
    news_path: Path
    rss_sources_path: Optional[Path]
    stock_path: Path
    price_history_path: Optional[Path]
    price_1h_path: Optional[Path]
    price_5m_path: Optional[Path]
    watch_industries: tuple[str, ...]
    top_n: int
    min_score: float
    market_scope: str
    trade_direction: str
    holding_period_days: str
    max_watchlist: int
    min_industry_signals: int
    min_recommendations: int
    trading_session: str
    notification_min_score: float
    notification_mode: str
    report_dir: Path
    report_public_base_url: Optional[str]
    notification_webhook_env: Optional[str]
    line_channel_access_token_env: Optional[str]
    line_to_env: Optional[str]
    line_broadcast: bool

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "AppConfig":
        config_path = Path(path)
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        base = config_path.parent.parent
        return cls(
            news_path=_resolve(base, raw["news_path"]),
            rss_sources_path=_resolve_optional(base, raw.get("rss_sources_path")),
            stock_path=_resolve(base, raw["stock_path"]),
            price_history_path=_resolve_optional(base, raw.get("price_history_path")),
            price_1h_path=_resolve_optional(base, raw.get("price_1h_path")),
            price_5m_path=_resolve_optional(base, raw.get("price_5m_path")),
            watch_industries=tuple(raw.get("watch_industries", [])),
            top_n=int(raw.get("top_n", 10)),
            min_score=float(raw.get("min_score", 60)),
            market_scope=raw.get("market_scope", "tw_listed_otc"),
            trade_direction=raw.get("trade_direction", "long_only"),
            holding_period_days=raw.get("holding_period_days", "3-20"),
            max_watchlist=int(raw.get("max_watchlist", raw.get("top_n", 10))),
            min_industry_signals=int(raw.get("min_industry_signals", 3)),
            min_recommendations=int(raw.get("min_recommendations", 5)),
            trading_session=raw.get("trading_session", "tw_intraday"),
            notification_min_score=float(raw.get("notification_min_score", 80)),
            notification_mode=raw.get("notification_mode", "high_priority_summary"),
            report_dir=_resolve(base, raw.get("report_dir", "reports")),
            report_public_base_url=raw.get("report_public_base_url"),
            notification_webhook_env=raw.get("notification_webhook_env"),
            line_channel_access_token_env=raw.get("line_channel_access_token_env"),
            line_to_env=raw.get("line_to_env"),
            line_broadcast=bool(raw.get("line_broadcast", False)),
        )


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _resolve_optional(base: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    return _resolve(base, value)
