from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional


class RateLimitedHttpClient:
    def __init__(
        self,
        cache_dir: Path,
        min_interval_seconds: float = 1.0,
        user_agent: str = "stock-signal-system/0.1",
    ) -> None:
        self.cache_dir = cache_dir
        self.min_interval_seconds = min_interval_seconds
        self.user_agent = user_agent
        self._last_request_at = 0.0
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_json(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        cache_key: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> dict:
        return json.loads(self.get_text(url, params, headers, cache_key, ttl_seconds))

    def get_text(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        cache_key: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> str:
        final_url = _with_params(url, params)
        cache_path = self.cache_dir / f"{cache_key or _safe_key(final_url)}.cache"
        if cache_path.exists() and time.time() - cache_path.stat().st_mtime < ttl_seconds:
            return cache_path.read_text(encoding="utf-8")

        self._sleep_if_needed()
        request_headers = {"User-Agent": self.user_agent}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(final_url, headers=request_headers)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    text = response.read().decode("utf-8-sig")
                cache_path.write_text(text, encoding="utf-8")
                return text
            except urllib.error.HTTPError as exc:
                if exc.code not in {402, 429, 500, 502, 503, 504} or attempt == 2:
                    raise
                time.sleep((2**attempt) * 5)
        raise RuntimeError("unreachable retry state")

    def _sleep_if_needed(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)
        self._last_request_at = time.time()


def _with_params(url: str, params: Optional[dict]) -> str:
    if not params:
        return url
    return f"{url}?{urllib.parse.urlencode(params)}"


def _safe_key(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value)[:180]

