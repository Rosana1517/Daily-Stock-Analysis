"""Static reference table for identifying 官股/公股(state-owned or
state-controlled bank) securities brokerage branches from free-text broker
names such as HiStock's "兆豐-台北". No API publishes an authoritative
"is this an official broker" flag — Taiwan's state-owned bank list is fixed
and well-known, so it is curated here rather than fetched."""

from __future__ import annotations

OFFICIAL_BANK_BROKER_KEYWORDS: tuple[str, ...] = (
    "兆豐",
    "合作金庫",
    "合庫",
    "第一金",
    "華南",
    "彰化銀行",
    "彰銀",
    "臺灣企銀",
    "台灣企銀",
    "臺企銀",
    "台企銀",
    "土地銀行",
    "臺灣銀行",
    "台灣銀行",
    "臺銀",
    "台銀",
)


def is_official_bank_broker(name: str) -> bool:
    text = str(name or "")
    return any(keyword in text for keyword in OFFICIAL_BANK_BROKER_KEYWORDS)
