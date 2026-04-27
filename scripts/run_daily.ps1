param(
    [string]$Config = "configs/rss.example.json",
    [switch]$PublishPages,
    [switch]$SkipTwse
)

if ($SkipTwse) {
    python -m stock_signal_system.cli refresh-data --config $Config --skip-twse
} else {
    python -m stock_signal_system.cli refresh-data --config $Config
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
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
