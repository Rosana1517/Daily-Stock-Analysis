# Stock Signal System

這是一套每日選股與交易觀察系統。它把新聞/政策催化、財務品質、估值風險、日線蠟燭圖、1H 市場結構、5M 掃流動性與 IFVG、LINE 通知串成同一條流程。

輸出是「研究與觀察清單」，不是保證獲利或自動下單訊號。

## 一鍵檢查

```powershell
python -m stock_signal_system.cli validate-config --config configs/local.example.json
```

## 每日執行

```powershell
python -m stock_signal_system.cli run --config configs/local.example.json
```

報告輸出到 `reports/`。

## RSS 新聞

```powershell
python -m stock_signal_system.cli fetch-news --sources configs/rss_sources.example.json --output data/news_rss.csv
```

若要使用真實 RSS 新聞當作每日輸入，改用：

```powershell
python -m stock_signal_system.cli run --config configs/rss.example.json
```

## 市場資料

支援三層價格資料：

- Daily: `price_history_path`
- 1H: `price_1h_path`
- 5M: `price_5m_path`

CSV 格式見 `examples/price_history.csv`、`examples/price_1h.csv`、`examples/price_5m.csv`。

## 文件

- `docs/STRATEGY_FRAMEWORK.md`: 總策略框架
- `docs/DATA_SOURCES.md`: 資料源與合規原則
- `docs/TWSE_OPENAPI.md`: TWSE 官方 OpenAPI 端點選型與嫁接方式
- `docs/CANDLESTICK_STRATEGY.md`: 日本蠟燭圖策略
- `docs/XHS_VIDEO_STRATEGY.md`: 小紅書影片策略
- `docs/LINE_BOT.md`: LINE bot 設定
- `docs/LINE_SETUP_RECOMMENDED.md`: 建議的 LINE 機器人設置方式
- `docs/YOU_NEED_TO_PROVIDE.md`: 你需要提供的資料清單
