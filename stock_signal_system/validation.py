from __future__ import annotations

import csv
import os
from pathlib import Path

from stock_signal_system.config import AppConfig


REQUIRED_NEWS_COLUMNS = {"date", "title", "source", "body", "industries"}
REQUIRED_STOCK_COLUMNS = {
    "symbol",
    "name",
    "industry",
    "price",
    "price_20d_ago",
    "volume",
    "avg_volume_20d",
    "revenue_growth_yoy",
    "gross_margin",
    "operating_margin",
    "free_cash_flow_margin",
    "debt_to_equity",
    "pe_ratio",
}
REQUIRED_DAILY_COLUMNS = {"symbol", "date", "open", "high", "low", "close", "volume"}
REQUIRED_INTRADAY_COLUMNS = {"symbol", "datetime", "open", "high", "low", "close", "volume"}


def validate_config(config: AppConfig) -> list[str]:
    messages: list[str] = []
    if config.market_scope != "tw_listed_otc":
        messages.append(f"WARN market_scope is {config.market_scope}; current workflow is tuned for tw_listed_otc.")
    if config.trade_direction != "long_only":
        messages.append(f"WARN trade_direction is {config.trade_direction}; current preference is long_only.")
    if config.max_watchlist > 5:
        messages.append("WARN max_watchlist is above 5; current preference is daily max 5 names.")
    if config.notification_mode not in {"high_priority_summary", "full_report", "report_link"}:
        messages.append(f"ERROR unsupported notification_mode: {config.notification_mode}")
    if config.notification_mode == "report_link" and not config.report_public_base_url:
        messages.append("WARN report_link mode is enabled but report_public_base_url is not set.")

    _check_csv(config.news_path, REQUIRED_NEWS_COLUMNS, "news_path", messages)
    _check_csv(config.stock_path, REQUIRED_STOCK_COLUMNS, "stock_path", messages)

    if config.price_history_path:
        _check_csv(config.price_history_path, REQUIRED_DAILY_COLUMNS, "price_history_path", messages)
    else:
        messages.append("WARN price_history_path is not set; daily candlestick rules will be disabled.")

    if config.price_1h_path:
        _check_csv(config.price_1h_path, REQUIRED_INTRADAY_COLUMNS, "price_1h_path", messages)
    else:
        messages.append("WARN price_1h_path is not set; HH/HL and LH/LL market structure will fall back to daily bars.")

    if config.price_5m_path:
        _check_csv(config.price_5m_path, REQUIRED_INTRADAY_COLUMNS, "price_5m_path", messages)
    else:
        messages.append("WARN price_5m_path is not set; liquidity sweep and IFVG triggers will fall back to daily bars.")

    if config.rss_sources_path and not config.rss_sources_path.exists():
        messages.append(f"ERROR rss_sources_path does not exist: {config.rss_sources_path}")

    if config.notification_webhook_env and not os.getenv(config.notification_webhook_env):
        messages.append(f"WARN webhook env var is not set: {config.notification_webhook_env}")

    if config.line_channel_access_token_env and not os.getenv(config.line_channel_access_token_env):
        messages.append(f"WARN LINE token env var is not set: {config.line_channel_access_token_env}")

    if config.line_broadcast and config.line_to_env:
        messages.append("WARN line_broadcast is true, so line_to_env will be ignored.")

    if config.line_to_env and not config.line_broadcast and not os.getenv(config.line_to_env):
        messages.append(f"WARN LINE recipient env var is not set: {config.line_to_env}")

    if not any(message.startswith("ERROR") for message in messages):
        messages.insert(0, "OK config is usable.")
    return messages


def has_errors(messages: list[str]) -> bool:
    return any(message.startswith("ERROR") for message in messages)


def _check_csv(path: Path, required_columns: set[str], label: str, messages: list[str]) -> None:
    if not path.exists():
        messages.append(f"ERROR {label} does not exist: {path}")
        return
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            columns = set(reader.fieldnames or [])
            missing = sorted(required_columns - columns)
            if missing:
                messages.append(f"ERROR {label} is missing columns {missing}: {path}")
            else:
                first_row = next(reader, None)
                if first_row is None:
                    messages.append(f"WARN {label} has headers but no data rows: {path}")
    except Exception as exc:
        messages.append(f"ERROR cannot read {label}: {path} ({exc})")
