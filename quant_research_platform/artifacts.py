from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from quant_research_platform.signals import ForecastSignal


def save_signal_csv(output_dir: Path, run_date: date, signals: list[ForecastSignal]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"kronos_signals_{run_date.isoformat()}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "datetime",
                "instrument",
                "score",
                "expected_return",
                "confidence",
                "source",
                "current_close",
                "predicted_close",
            ],
        )
        writer.writeheader()
        for item in sorted(signals, key=lambda x: x.expected_return, reverse=True):
            writer.writerow(
                {
                    "datetime": run_date.isoformat(),
                    "instrument": item.symbol,
                    "score": item.expected_return,
                    "expected_return": item.expected_return,
                    "confidence": item.confidence,
                    "source": item.source,
                    "current_close": item.current_close,
                    "predicted_close": item.predicted_close,
                }
            )
    return path


def save_qlib_handoff(output_dir: Path, run_date: date, signal_csv: Path, qlib_data_path: Path | None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"qlib_handoff_{run_date.isoformat()}.md"
    qlib_path_text = str(qlib_data_path) if qlib_data_path else "<your qlib data directory>"
    content = f"""# Qlib Handoff - {run_date.isoformat()}

Signal file:

```text
{signal_csv}
```

Suggested next steps:

1. Convert your market OHLCV data into Qlib format if it is not already prepared.
2. Place the signal file where your Qlib workflow can read it as model prediction output.
3. Evaluate the signal with top-k, long-short, IC, Rank IC, transaction cost, turnover, and drawdown reports.

Reference command shape:

```powershell
python -m qlib.cli.run examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

Configured Qlib data path:

```text
{qlib_path_text}
```
"""
    path.write_text(content, encoding="utf-8")
    return path
