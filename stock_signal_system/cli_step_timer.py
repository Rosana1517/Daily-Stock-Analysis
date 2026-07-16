"""Tiny context manager shared by cli_handlers submodules to time and log a
named pipeline step."""

from __future__ import annotations

import time


class _step_timer:
    def __init__(self, name: str) -> None:
        self.name = name
        self.started_at = 0.0

    def __enter__(self):
        self.started_at = time.monotonic()
        print(f"step_start={self.name}", flush=True)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        elapsed = time.monotonic() - self.started_at
        if exc_type:
            print(f"step_failed={self.name} elapsed_seconds={elapsed:.1f} error={exc}", flush=True)
            return False
        print(f"step_done={self.name} elapsed_seconds={elapsed:.1f}", flush=True)
        return False
