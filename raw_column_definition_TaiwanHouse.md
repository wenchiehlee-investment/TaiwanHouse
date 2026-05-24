# Raw Column Definitions - Taiwan Housing Loan Default Rate

**Source repo:** `wenchiehlee/TaiwanHouse`  
**Script:** `scripts/fetch_and_plot.py`  
**Raw file:** `data/csv/housing_loan_default_rate.csv`  

**Purpose**: 台灣各縣市購置住宅貸款違約率統計。

| Column | Type | Description | Example |
|---|---|---|---|
| `資料期別` | string | 資料季別，格式 `YYYYQN` (民國) | `114Q4` |
| `縣市` | string | 縣市名稱 | `台北市` |
| `購置住宅貸款違約率` | float | 購置住宅貸款違約率 (單位：%) | `0.07` |
| `download_timestamp` | string | 原始資料下載或取得時間 (CST) | `2026-05-23 22:03:30` |
| `process_timestamp` | string | CSV 產生或清洗完成時間 (CST) | `2026-05-23 22:03:30` |

---

## building_ownership_trend.csv

**Script:** `scripts/fetch_transaction_trend.py`  
**Purpose**: 主要城市各季建物所有權登記「棟數」與「金額/價值」（此處以面積為代理指標，反映交易規模）。

| Column | Type | Description | Example |
|---|---|---|---|
| `period` | string | 資料季別，格式 `YYYYQN` (ROC) | `098Q1` |
| `city` | string | 縣市名稱 | `臺北市` |
| `買賣_棟數` | integer | 買賣移轉登記棟數 | `15092` |
| `買賣_坪數` | float | 買賣移轉登記面積 (單位：坪) | `362688.77` |
| `拍賣_棟數` | integer | 拍賣登記棟數 | `558` |
| `拍賣_坪數` | float | 拍賣登記面積 (單位：坪) | `188545.62` |
| `繼承_棟數` | integer | 繼承登記棟數 | `1521` |
| `繼承_坪數` | float | 繼承登記面積 (單位：坪) | `295316.92` |
| `贈與_棟數` | integer | 贈與登記棟數 (含夫妻贈與) | `1952` |
| `贈與_坪數` | float | 贈與登記面積 (單位：坪) | `306699.54` |
