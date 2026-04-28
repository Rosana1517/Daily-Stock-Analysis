from __future__ import annotations

from pathlib import Path


def download_yfinance_history(symbols: list[str], period: str, cache_dir: Path) -> Path:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("Install optional market dependencies first: pip install .[market]") from exc

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"yfinance_{'_'.join(symbols)}_{period}.csv"
    if cache_file.exists():
        return cache_file

    data = yf.download(
        tickers=" ".join(symbols),
        period=period,
        interval="1d",
        group_by="ticker",
        threads=False,
        progress=False,
    )
    data.to_csv(cache_file)
    return cache_file

