from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional


def send_notification(
    title: str,
    body: str,
    webhook_env: Optional[str],
    line_channel_access_token_env: Optional[str] = None,
    line_to_env: Optional[str] = None,
    line_broadcast: bool = False,
) -> str:
    message_texts = _split_line_text(f"{title}\n\n{body}")
    statuses = []
    if webhook_env:
        statuses.append(_send_webhook(title, body, webhook_env))
    if line_broadcast and line_channel_access_token_env:
        statuses.append(_send_line_broadcast(message_texts, line_channel_access_token_env))
    elif line_channel_access_token_env and line_to_env:
        statuses.append(_send_line_push(message_texts, line_channel_access_token_env, line_to_env))
    return ",".join(statuses) if statuses else "disabled"


def _send_webhook(title: str, body: str, webhook_env: str) -> str:
    webhook_url = os.getenv(webhook_env)
    if not webhook_url:
        return f"webhook_missing_env:{webhook_env}"
    request = _json_request(webhook_url, {"title": title, "body": body})
    with urllib.request.urlopen(request, timeout=10) as response:
        return f"webhook_sent:{response.status}"


def _send_line_push(message_texts: list[str], token_env: str, to_env: str) -> str:
    token = os.getenv(token_env)
    to = os.getenv(to_env)
    if not token:
        return f"line_missing_env:{token_env}"
    if not to:
        return f"line_missing_env:{to_env}"

    request = _json_request(
        "https://api.line.me/v2/bot/message/push",
        {"to": to, "messages": [{"type": "text", "text": text} for text in message_texts]},
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return f"line_sent:{response.status}"


def _send_line_broadcast(message_texts: list[str], token_env: str) -> str:
    token = os.getenv(token_env)
    if not token:
        return f"line_missing_env:{token_env}"

    request = _json_request(
        "https://api.line.me/v2/bot/message/broadcast",
        {"messages": [{"type": "text", "text": text} for text in message_texts]},
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return f"line_broadcast_sent:{response.status}"


def _json_request(url: str, payload_obj: dict, headers: Optional[dict] = None) -> urllib.request.Request:
    payload = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        request_headers.update(headers)
    return urllib.request.Request(url, data=payload, headers=request_headers, method="POST")


def _split_line_text(text: str, max_chars: int = 4500, max_messages: int = 5) -> list[str]:
    chunks = []
    remaining = text.strip()
    while remaining and len(chunks) < max_messages:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, max_chars)
        if split_at < max_chars * 0.5:
            split_at = max_chars
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining and len(chunks) == max_messages:
        chunks[-1] = chunks[-1][: max_chars - 80].rstrip() + "\n\n[報告過長，後續內容請看本機 Markdown 報告]"
    return chunks or [""]
