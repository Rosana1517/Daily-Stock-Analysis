from __future__ import annotations

from pathlib import Path


REPORT_RETENTION_DAYS = 5

_REPORT_GLOBS: tuple[tuple[str, bool], ...] = (
    ("stock_signals_*.html", False),
    ("stock_signals_*.md", False),
    ("tw_hybrid_*.md", False),
    ("tw_hybrid_*.csv", False),
    ("qlib_tw_hybrid_*.yaml", False),
    ("qlib_engine_*.csv", False),
    ("line_sent_*.txt", False),
    ("qlib_provider_*", True),
)


def prune_report_artifacts(report_dir: Path, keep_latest: int = REPORT_RETENTION_DAYS) -> None:
    if keep_latest <= 0 or not report_dir.exists():
        return
    _prune_one_report_dir(report_dir, keep_latest)
    nested_quant_dir = report_dir / "quant_platform_tw"
    if nested_quant_dir.exists():
        _prune_one_report_dir(nested_quant_dir, keep_latest)


def _prune_one_report_dir(report_dir: Path, keep_latest: int) -> None:
    for pattern, is_dir in _REPORT_GLOBS:
        matches = sorted(report_dir.glob(pattern), reverse=True)
        for stale_path in matches[keep_latest:]:
            if is_dir:
                _remove_tree(stale_path)
            else:
                stale_path.unlink(missing_ok=True)


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            child.rmdir()
    path.rmdir()
