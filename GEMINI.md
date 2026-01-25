# 專案背景：TaiwanHouse

## 概述
此目錄作為 **TaiwanHouse** 專案的工作空間。目前，它似乎是一個剛初始化的儲存庫或文件根目錄，主要包含一個基本的 README。
*   **授權：** MIT

## 結構

*   `README.md`：包含專案標題和簡短描述。

*   `scripts/`：包含資料處理與視覺化的 Python 腳本。

    *   `fetch_and_plot.py`：從內政部不動產資訊平台抓取購置住宅貸款違約率並繪圖。

*   `data/`：

    *   `csv/`：儲存下載或生成的 CSV 資料檔案。

    *   `svg/`：儲存生成的 SVG 圖表。



## 用法



*   **資料分析：** 執行 `python scripts/fetch_and_plot.py` 以獲取最新的違約率資料並生成圖表。腳本會自動使用 Selenium 從內政部下載真實 CSV 檔案。



*   **目前狀態：** 已切換至官方真實數據。資料範圍從 98Q1 開始（平台限制），涵蓋金融海嘯高點至今。







## 開發注意事項



*   **技術要求：** 腳本需安裝 `selenium` 與 `webdriver-manager` 以處理動態下載。



*   **語言要求：** 所有報告和 Markdown 檔案（.md）必須使用 **繁體中文 (Traditional Chinese)**。

*   **類型：** 資料分析與視覺化專案。

*   **Git：** 此目錄是 Git 儲存庫根目錄。
