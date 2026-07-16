# project_state — 當前狀態文檔

> 本次為「模式 E:舊專案積木化改造」,以下記錄改造進度,不涉及每日選股系統本身的業務邏輯變動(改造期間行為不變原則)。

## 當前階段

正在做:舊專案積木化改造 — 地基整理階段(切片 1/N),已完成清理與補文檔,下一步等待使用者確認優先拆解目標

已完成:
- 刪除根目錄未進版控的暫存/除錯殘留檔案(`AGENTS.md`、`WORKSPACE_REATTACH_REPORT.md`、`.cache_verify_tpex/`、`.cache_verify_twse/`、`tmp_preview_hybrid/`)
- 刪除已廢棄的 `agents/` 舊架構樁模組與對應測試 `tests/test_legacy_agents.py`(已確認功能完全由 `quant_research_platform/agent_workflow.py` 取代,無其他程式碼引用舊模組,刪除後 107 個測試全數通過,已 commit)
- 完成健檢掃描,產出 PRD.md / ARCH.md 初稿(反推既有系統行為與架構,待使用者逐條確認修正)

## 已知問題

- `stock_signal_system/report.py`(2438行)超出 300 行上限甚多,且**缺乏完整測試覆蓋**(僅有 83 行的 `test_report_html.py` 局部覆蓋),是全案風險最高的巨型檔案
- `quant_research_platform/hybrid.py`(1608行)為核心策略融合邏輯,同樣超標
- `stock_signal_system/low_reversal_screener.py`(1215行)無對應測試檔
- 目前質量閘門只有 `pytest`,缺 lint 與型別檢查
- CI 依賴三個外部 fork repo(`Rosana1517/Kronos`、`qlib`、`OpenBB`)的 default branch,未鎖定 commit hash,屬供應鏈風險(非本次改造範圍,僅記錄)
- `line_bot_server.py` 用途待確認(是否為每日流程必要組件,或僅輔助用途)

## 下一步

- 請使用者確認 PRD.md / ARCH.md 內容是否符合實際「為什麼做」與「不做什麼」的真實意圖
- 確認後,依切片計劃開始拆解 `report.py`(風險最高、影響面最廣,建議先補測試再拆分)

---

## 切片計劃(全部,風險由低到高排序)

| # | 切片 | 涉及積木 | 涉及檔案 | 狀態 |
|---|---|---|---|---|
| 1 | 地基整理:清雜訊、刪廢棄模組、補三份全局文檔 | 版本控制積木 | `agents/`、根目錄暫存檔、PRD.md/ARCH.md/project_state.md | ✅ 已完成 |
| 2 | 確認文檔內容(使用者審閱 PRD/ARCH) | — | PRD.md、ARCH.md | ⬜ 待使用者確認 |
| 3 | 為 `report.py` 補齊測試(在拆分前先固定行為,避免拆分引入回歸) | 檔案積木 | `stock_signal_system/report.py`、`tests/test_report_html.py` | ⬜ |
| 4 | 拆分 `report.py`:依職責切出報告排版/HTML產生/多格式輸出等獨立檔案 | 檔案積木 | `stock_signal_system/report.py` → 拆出新檔 | ⬜ |
| 5 | 為 `low_reversal_screener.py` 補測試後視情況拆分 | AI/邏輯積木 | `stock_signal_system/low_reversal_screener.py` | ⬜ |
| 6 | 為 `hybrid.py` 補充測試覆蓋率後評估拆分範圍(核心策略引擎,風險最高,需最謹慎) | AI 積木 | `quant_research_platform/hybrid.py` | ⬜ |
| 7 | 視需要補上 lint(如 ruff)與型別檢查(如 mypy)質量閘門 | 版本控制積木 | `pyproject.toml`、CI workflow | ⬜ |
| 8 | 其餘 300~620 行區間檔案視情況拆分 | 各工具箱積木 | `universe.py`、`cli_handlers.py`、`candlestick.py` 等 | ⬜ |

---

## 每次開新對話,第一條訊息這樣說:

```
先讀項目根目錄的 PRD.md、ARCH.md、project_state.md,了解當前狀態,然後我們來做「具體任務」
```

## 每個切片完成後,按順序執行:

1. 手動跑一遍,對照 PRD 驗收清單逐條檢查
2. 跑 lint(若已建立)
3. 跑型別檢查(若已建立)
4. 跑 `pytest`
5. 更新本文件(三件事:已完成/已知問題/下一步)
6. git commit,寫清楚這次提交做了什麼
