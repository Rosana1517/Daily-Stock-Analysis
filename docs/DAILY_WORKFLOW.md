# Daily Workflow

## 盤前

1. 更新 RSS/新聞/政策資料。
2. 更新昨日收盤日線資料。
3. 預檢設定。
4. 產出盤前觀察清單。

```powershell
python -m stock_signal_system.cli fetch-news --sources configs/rss_sources.example.json --output data/news_rss.csv
python -m stock_signal_system.cli validate-config --config configs/rss.example.json
python -m stock_signal_system.cli run --config configs/rss.example.json
```

## 盤中

1. 更新 1H 與 5M 資料。
2. 只在大週期方向一致時找機會。
3. 5M 等掃流動性與 IFVG 回測確認。

## 盤後

1. 更新完整日線與財務資料。
2. 檢查持股是否觸發停損、停利或 thesis breaker。
3. 產出隔日觀察清單。

