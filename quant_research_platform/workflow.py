from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quant_research_platform.artifacts import save_qlib_handoff, save_signal_csv
from quant_research_platform.backtest import BacktestResult, run_top_n_backtest
from quant_research_platform.config import QuantPlatformConfig
from quant_research_platform.data import fetch_openbb_ohlcv, load_csv_ohlcv
from quant_research_platform.report import build_markdown_report, save_report
from quant_research_platform.signals import ForecastSignal, build_signals


@dataclass(frozen=True)
class QuantWorkflowResult:
    report_path: str
    signal_csv_path: str
    qlib_handoff_path: str
    signals: list[ForecastSignal]
    backtest: BacktestResult


def run_quant_workflow(config: QuantPlatformConfig, run_date: date | None = None) -> QuantWorkflowResult:
    bars_by_symbol = _load_data(config)
    signals = build_signals(
        bars_by_symbol,
        lookback=config.lookback,
        prediction_length=config.prediction_length,
        kronos_repo_path=config.kronos_repo_path,
        kronos_tokenizer=config.kronos_tokenizer,
        kronos_model=config.kronos_model,
    )
    backtest = run_top_n_backtest(
        signals,
        bars_by_symbol,
        top_n=config.top_n,
        initial_cash=config.initial_cash,
        transaction_cost_bps=config.transaction_cost_bps,
        benchmark_symbol=config.benchmark_symbol,
    )
    current_date = run_date or date.today()
    report = build_markdown_report(signals, backtest, current_date)
    report_path = save_report(config.output_dir, current_date, report)
    signal_csv = save_signal_csv(config.output_dir, current_date, signals)
    qlib_handoff = save_qlib_handoff(config.output_dir, current_date, signal_csv, config.qlib_data_path)
    return QuantWorkflowResult(str(report_path), str(signal_csv), str(qlib_handoff), signals, backtest)


def _load_data(config: QuantPlatformConfig):
    if config.data_source == "openbb":
        return fetch_openbb_ohlcv(config.symbols, config.openbb_provider)
    if not config.ohlcv_path:
        raise ValueError("ohlcv_path is required when data_source is csv.")
    return load_csv_ohlcv(config.ohlcv_path, config.symbols)
