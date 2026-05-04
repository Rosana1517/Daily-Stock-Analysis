# Operations

## Daily Hybrid Report

Run the default daily workflow:

```powershell
.\scripts\run_daily.ps1 -Config configs/rss.example.json
```

This generates:

- `reports/tw_hybrid_YYYY-MM-DD.md`
- `reports/stock_signals_YYYY-MM-DD.html`
- `reports/tw_hybrid_YYYY-MM-DD.csv`
- `reports/qlib_tw_hybrid_YYYY-MM-DD.yaml`

## LINE Push

The daily LINE push now uses the Hybrid Quant Daily Stock Report output.

Recommended config:

```json
{
  "notification_mode": "report_link",
  "report_public_base_url": "https://rosana1517.github.io/Daily-Stock-Analysis/reports",
  "line_channel_access_token_env": "LINE_CHANNEL_ACCESS_TOKEN",
  "line_broadcast": true,
  "quant_config_path": "configs/quant_platform.tw.example.json",
  "quant_realtime_cache_path": "data/twse_common_stock_realtime_cache.csv"
}
```

Use `notification_mode: "full_report"` only when you want LINE to push the full Markdown content instead of a short summary plus link.

## Validation

Before scheduling, run:

```powershell
python -m stock_signal_system.cli validate-config --config configs/rss.example.json
```

Validation checks the Daily inputs and confirms the quant config path exists.
