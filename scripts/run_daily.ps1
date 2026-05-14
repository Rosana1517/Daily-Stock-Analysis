param(
    [string]$Config = "configs/rss.example.json",
    [switch]$PublishPages,
    [switch]$SkipTwse,
    [switch]$SkipQuantOhlcv,
    [string]$QuantOhlcvPeriod = "1y"
)

if ($SkipTwse) {
    python -m stock_signal_system.cli refresh-data --config $Config --skip-twse
} else {
    python -m stock_signal_system.cli refresh-data --config $Config
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not $SkipQuantOhlcv) {
    $quantConfig = python -c "import json, pathlib; raw=json.loads(pathlib.Path('$Config').read_text(encoding='utf-8')); print(raw.get('quant_config_path') or '')"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    if ($quantConfig) {
        python -m stock_signal_system.cli refresh-quant-ohlcv --config $quantConfig --period $QuantOhlcvPeriod
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        $realtimeCache = python -c "import json, pathlib; raw=json.loads(pathlib.Path('$Config').read_text(encoding='utf-8')); print(raw.get('quant_realtime_cache_path') or 'data/twse_common_stock_realtime_cache.csv')"
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        python -m stock_signal_system.cli refresh-quant-realtime --config $quantConfig --cache $realtimeCache
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
}

python -m stock_signal_system.cli validate-config --config $Config
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

python -m stock_signal_system.cli run --config $Config
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($PublishPages) {
    & "$PSScriptRoot\publish_report_pages.ps1"
    exit $LASTEXITCODE
}

exit 0
