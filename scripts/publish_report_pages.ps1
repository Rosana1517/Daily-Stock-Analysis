param(
    [string]$ReportHtml,
    [string]$RepoDir = "$PSScriptRoot\..\..\Daily-Stock-Analysis",
    [string]$RepoUrl = "https://github.com/Rosana1517/Daily-Stock-Analysis.git",
    [string]$PublicBaseUrl = "https://rosana1517.github.io/Daily-Stock-Analysis/reports"
)

if (-not $ReportHtml) {
    $latest = Get-ChildItem -Path "$PSScriptRoot\..\reports" -Filter "stock_signals_*.html" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) {
        Write-Error "No report HTML found under reports."
        exit 1
    }
    $ReportHtml = $latest.FullName
}

python -m stock_signal_system.cli publish-pages `
    --report-html $ReportHtml `
    --repo-dir $RepoDir `
    --repo-url $RepoUrl `
    --public-base-url $PublicBaseUrl

exit $LASTEXITCODE
