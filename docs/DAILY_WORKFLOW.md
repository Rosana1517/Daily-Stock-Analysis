# Daily Workflow

Daily reports now use the Hybrid Quant Daily Stock Report flow by default.

## What Runs

1. Refresh RSS news into `data/news_rss.csv`.
2. Load the quant config from `quant_config_path`.
3. Run the hybrid analysis:
   - Kronos forecast / momentum fallback
   - OpenBB or cached OHLCV data
   - Qlib signal handoff config
   - RSS industry scoring
   - candlestick / market-structure strategy scoring
   - realtime TWSE cache, when available
4. Generate the dashboard HTML report.
5. Push the hybrid report content or report link through LINE/webhook.

## Default Command

```powershell
.\scripts\run_daily.ps1 -Config configs/rss.example.json
```

Equivalent manual commands:

```powershell
python -m stock_signal_system.cli refresh-data --config configs/rss.example.json
python -m stock_signal_system.cli validate-config --config configs/rss.example.json
python -m stock_signal_system.cli run --config configs/rss.example.json
```

`configs/local.example.json` is also configured for the same hybrid report flow.

## LINE Content

`notification_mode` controls the LINE body:

- `report_link`: sends the hybrid report summary plus the public HTML link.
- `full_report`: sends the full hybrid Markdown report split across LINE messages.

The current default is `report_link`.
