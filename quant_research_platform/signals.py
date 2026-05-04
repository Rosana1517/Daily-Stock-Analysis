from __future__ import annotations

from dataclasses import dataclass

from quant_research_platform.data import Bar


@dataclass(frozen=True)
class ForecastSignal:
    symbol: str
    current_close: float
    predicted_close: float
    expected_return: float
    confidence: float
    source: str


def build_signals(
    bars_by_symbol: dict[str, list[Bar]],
    lookback: int,
    prediction_length: int,
    kronos_repo_path: object | None = None,
    kronos_tokenizer: str = "NeoQuasar/Kronos-Tokenizer-base",
    kronos_model: str = "NeoQuasar/Kronos-small",
) -> list[ForecastSignal]:
    try:
        return _build_kronos_signals(
            bars_by_symbol,
            lookback,
            prediction_length,
            kronos_repo_path,
            kronos_tokenizer,
            kronos_model,
        )
    except Exception:
        return [_momentum_signal(symbol, bars[-lookback:]) for symbol, bars in bars_by_symbol.items() if len(bars) >= 3]


def _momentum_signal(symbol: str, bars: list[Bar]) -> ForecastSignal:
    current_close = bars[-1].close
    short_return = current_close / bars[max(0, len(bars) - 6)].close - 1
    medium_return = current_close / bars[0].close - 1
    expected_return = 0.65 * short_return + 0.35 * medium_return
    volatility = _return_volatility(bars)
    confidence = max(0.05, min(0.95, abs(expected_return) / (volatility + 1e-9)))
    return ForecastSignal(
        symbol=symbol,
        current_close=current_close,
        predicted_close=current_close * (1 + expected_return),
        expected_return=expected_return,
        confidence=confidence,
        source="momentum-fallback",
    )


def _return_volatility(bars: list[Bar]) -> float:
    returns = [bars[i].close / bars[i - 1].close - 1 for i in range(1, len(bars)) if bars[i - 1].close]
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / len(returns)
    return variance ** 0.5


def _build_kronos_signals(
    bars_by_symbol: dict[str, list[Bar]],
    lookback: int,
    prediction_length: int,
    kronos_repo_path: object | None,
    kronos_tokenizer: str,
    kronos_model: str,
) -> list[ForecastSignal]:
    if not kronos_repo_path:
        raise RuntimeError("Kronos repo path is not configured.")

    import importlib
    import sys

    sys.path.insert(0, str(kronos_repo_path))
    try:
        import pandas as pd

        model_module = importlib.import_module("model")
        tokenizer = model_module.KronosTokenizer.from_pretrained(kronos_tokenizer)
        model = model_module.Kronos.from_pretrained(kronos_model)
        predictor = model_module.KronosPredictor(model, tokenizer, max_context=min(lookback, 512))

        signals: list[ForecastSignal] = []
        for symbol, bars in bars_by_symbol.items():
            window = bars[-lookback:]
            if len(window) < 3:
                continue
            frame = pd.DataFrame(
                [
                    {
                        "open": item.open,
                        "high": item.high,
                        "low": item.low,
                        "close": item.close,
                        "volume": item.volume,
                        "amount": item.close * item.volume,
                    }
                    for item in window
                ]
            )
            x_timestamp = pd.Series([item.timestamp for item in window])
            last_ts = window[-1].timestamp
            y_timestamp = pd.date_range(last_ts, periods=prediction_length + 1, freq="D")[1:]
            pred = predictor.predict(frame, x_timestamp, pd.Series(y_timestamp), prediction_length)
            predicted_close = float(pred["close"].iloc[-1])
            current_close = window[-1].close
            signals.append(
                ForecastSignal(
                    symbol=symbol,
                    current_close=current_close,
                    predicted_close=predicted_close,
                    expected_return=predicted_close / current_close - 1,
                    confidence=0.75,
                    source="kronos",
                )
            )
        return signals
    finally:
        if sys.path and sys.path[0] == str(kronos_repo_path):
            sys.path.pop(0)
