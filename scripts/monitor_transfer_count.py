import os
import re
import shutil
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL = "https://pip.moi.gov.tw/Publicize/Info/E3030"
TARGET_DATASET_NAME = "全台建物買賣移轉棟數"

PROJECT_ROOT = os.getcwd()
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "csv")
SVG_DIR = os.path.join(PROJECT_ROOT, "data", "svg")
REPORT_DIR = os.path.join(PROJECT_ROOT, "data", "reports")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "temp_download_transfer")

CSV_OUTPUT = os.path.join(DATA_DIR, "taiwan_building_transfer_count.csv")
SVG_OUTPUT = os.path.join(SVG_DIR, "taiwan_building_transfer_count.svg")
REPORT_OUTPUT = os.path.join(REPORT_DIR, "taiwan_building_transfer_monitor.md")


for directory in (DATA_DIR, SVG_DIR, REPORT_DIR, DOWNLOAD_DIR):
    os.makedirs(directory, exist_ok=True)


def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def clear_download_dir():
    for file_name in os.listdir(DOWNLOAD_DIR):
        file_path = os.path.join(DOWNLOAD_DIR, file_name)
        if os.path.isfile(file_path):
            os.remove(file_path)


def read_csv_auto(path):
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception:
            continue
    raise RuntimeError(f"無法讀取 CSV：{path}")


def read_table_auto(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        return read_csv_auto(path)

    if ext in (".xlsx", ".xls"):
        excel_engines = ("openpyxl", "xlrd", None)
        for engine in excel_engines:
            try:
                if engine is None:
                    return pd.read_excel(path)
                return pd.read_excel(path, engine=engine)
            except Exception:
                continue
        raise RuntimeError(f"無法讀取 Excel：{path}")

    # Unknown extension, try CSV then Excel as fallback.
    try:
        return read_csv_auto(path)
    except Exception:
        pass
    try:
        return pd.read_excel(path)
    except Exception as e:
        raise RuntimeError(f"無法解析資料檔：{path}") from e


def detect_period_column(columns):
    keywords = ("期別", "年月", "月份", "日期", "時間", "month", "date", "year")
    for col in columns:
        lower = str(col).lower()
        if any(keyword in lower for keyword in keywords):
            return col
    return columns[0]


def detect_region_column(columns):
    keywords = ("縣市", "區域", "城市", "地區", "region", "city")
    for col in columns:
        lower = str(col).lower()
        if any(keyword in lower for keyword in keywords):
            return col
    return None


def detect_value_column(df, period_col, region_col):
    candidates = [c for c in df.columns if c not in (period_col, region_col)]
    priority = ("建物買賣移轉棟數", "移轉棟數", "棟數")

    for col in candidates:
        col_name = str(col)
        if any(word in col_name for word in priority):
            return col

    best_col = None
    best_valid = -1
    for col in candidates:
        numeric = pd.to_numeric(
            df[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(r"[^\d\.-]", "", regex=True),
            errors="coerce",
        )
        valid = numeric.notna().sum()
        if valid > best_valid:
            best_valid = valid
            best_col = col

    if best_col is None:
        raise RuntimeError("找不到可用的棟數欄位。")
    return best_col


def parse_period(raw):
    text = str(raw).strip().replace(" ", "")

    m = re.match(r"^(\d{2,4})[Qq季](\d)$", text)
    if m:
        year = int(m.group(1))
        quarter = int(m.group(2))
        year = year + 1911 if year < 1911 else year
        month = (quarter - 1) * 3 + 1
        dt = datetime(year, month, 1)
        return dt, f"{year}Q{quarter}"

    monthly_patterns = [
        r"^(\d{2,4})年(\d{1,2})月$",
        r"^(\d{2,4})[/-](\d{1,2})$",
        r"^(\d{2,4})M(\d{1,2})$",
        r"^(\d{4})(\d{2})$",
        r"^(\d{3})(\d{2})$",
    ]
    for pattern in monthly_patterns:
        m = re.match(pattern, text, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            year = year + 1911 if year < 1911 else year
            dt = datetime(year, month, 1)
            return dt, f"{year}-{month:02d}"

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.notna(parsed):
        dt = datetime(parsed.year, parsed.month, 1)
        return dt, dt.strftime("%Y-%m")

    return None, text


def find_download_link(driver):
    links = driver.find_elements(By.TAG_NAME, "a")
    best_link = None
    best_score = -1
    candidates = []

    for link in links:
        title = (link.get_attribute("title") or "").strip()
        text = (link.text or "").strip()
        href = (link.get_attribute("href") or "").strip()
        aria = (link.get_attribute("aria-label") or "").strip()

        try:
            row_text = link.find_element(By.XPATH, "./ancestor::tr").text.strip()
        except Exception:
            row_text = ""

        haystack = " ".join([title, text, href, aria, row_text])
        if not haystack.strip():
            continue
        candidates.append(haystack)

        score = 0
        if TARGET_DATASET_NAME in haystack:
            score += 100
        if "建物買賣移轉棟數" in haystack:
            score += 60
        if "買賣移轉" in haystack:
            score += 30
        if "建物" in haystack:
            score += 15
        if "移轉" in haystack:
            score += 15
        if "棟數" in haystack:
            score += 15
        if "全台" in haystack or "全國" in haystack:
            score += 8
        if "csv" in haystack.lower():
            score += 10
        if ".xls" in haystack.lower() or ".xlsx" in haystack.lower():
            score += 8

        if score > best_score:
            best_score = score
            best_link = link

    if best_link is not None and best_score >= 30:
        return best_link

    if candidates:
        print("未匹配到目標資料，頁面候選項目如下（前 10 筆）：")
        for item in candidates[:10]:
            print(f"- {item}")
    else:
        print("頁面中沒有可用的連結候選。")

    return None


def wait_for_download(timeout=45):
    start = time.time()
    while time.time() - start < timeout:
        files = [
            f
            for f in os.listdir(DOWNLOAD_DIR)
            if f.lower().endswith((".csv", ".xls", ".xlsx")) and not f.endswith(".crdownload")
        ]
        if files:
            files.sort(
                key=lambda f: os.path.getmtime(os.path.join(DOWNLOAD_DIR, f)),
                reverse=True,
            )
            return os.path.join(DOWNLOAD_DIR, files[0])
        time.sleep(1)
    return None


def merge_or_replace_source(downloaded_file, output_file):
    df_new = read_table_auto(downloaded_file)

    if not os.path.exists(output_file):
        df_new.to_csv(output_file, index=False, encoding="utf-8-sig")
        os.remove(downloaded_file)
        return

    df_old = read_table_auto(output_file)

    if set(df_old.columns) != set(df_new.columns):
        df_new.to_csv(output_file, index=False, encoding="utf-8-sig")
        os.remove(downloaded_file)
        return

    df_all = pd.concat([df_old, df_new], ignore_index=True)
    period_col = detect_period_column(df_all.columns.tolist())
    region_col = detect_region_column(df_all.columns.tolist())

    key_columns = [period_col]
    if region_col:
        key_columns.append(region_col)

    df_all = df_all.drop_duplicates(subset=key_columns, keep="last")
    df_all.to_csv(output_file, index=False, encoding="utf-8-sig")
    os.remove(downloaded_file)


def download_csv():
    driver = None
    try:
        print("初始化 WebDriver...")
        driver = setup_driver()
        print(f"前往資料來源：{BASE_URL}")
        driver.get(BASE_URL)
        WebDriverWait(driver, 20).until(lambda d: d.find_elements(By.TAG_NAME, "a"))

        target_link = find_download_link(driver)
        if target_link is None:
            raise RuntimeError(f"找不到「{TARGET_DATASET_NAME}」CSV 下載連結。")

        clear_download_dir()
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_link)
        time.sleep(0.5)
        try:
            target_link.click()
        except Exception:
            driver.execute_script("arguments[0].click();", target_link)

        downloaded_file = wait_for_download()
        if downloaded_file is None:
            raise RuntimeError("資料檔下載逾時。")

        merge_or_replace_source(downloaded_file, CSV_OUTPUT)
        print(f"CSV 已更新：{CSV_OUTPUT}")
    finally:
        if driver:
            driver.quit()
        if os.path.exists(DOWNLOAD_DIR):
            shutil.rmtree(DOWNLOAD_DIR)


def build_taiwan_series(df):
    period_col = detect_period_column(df.columns.tolist())
    region_col = detect_region_column(df.columns.tolist())
    value_col = detect_value_column(df, period_col, region_col)

    working = df.copy()
    working[value_col] = pd.to_numeric(
        working[value_col]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(r"[^\d\.-]", "", regex=True),
        errors="coerce",
    )
    working = working.dropna(subset=[value_col])

    if region_col:
        working[region_col] = (
            working[region_col].astype(str).str.strip().str.replace("臺", "台", regex=False)
        )
        nationwide_aliases = {"全國", "全台", "全台灣", "台灣", "台閩地區"}
        nationwide = working[working[region_col].isin(nationwide_aliases)].copy()

        if not nationwide.empty:
            working = nationwide
        else:
            working = (
                working.groupby(period_col, as_index=False)[value_col]
                .sum()
            )

    parsed = working[period_col].map(parse_period)
    working["parsed_dt"] = parsed.map(lambda x: x[0])
    working["period_label"] = parsed.map(lambda x: x[1])
    working = working.dropna(subset=["parsed_dt"])

    series_df = (
        working.groupby(["parsed_dt", "period_label"], as_index=False)[value_col]
        .sum()
        .rename(columns={value_col: "value"})
        .sort_values("parsed_dt")
    )
    series_df["parsed_dt"] = pd.to_datetime(series_df["parsed_dt"])

    if series_df.empty:
        raise RuntimeError("處理後沒有可用的全台移轉棟數資料。")

    return series_df


def configure_cjk_font():
    try:
        fm.fontManager = fm._load_fontmanager(try_read_cache=False)
    except Exception:
        pass

    preferred_fonts = [
        "Noto Sans CJK TC",
        "Noto Sans TC",
        "Noto Sans CJK JP",
        "Noto Sans CJK SC",
        "PingFang TC",
        "Microsoft JhengHei",
        "Arial Unicode MS",
        "WenQuanYi Micro Hei",
    ]

    available_fonts = {font.name for font in fm.fontManager.ttflist}
    selected_font = None
    for font_name in preferred_fonts:
        if font_name in available_fonts:
            selected_font = font_name
            break

    if selected_font is None:
        for font_name in available_fonts:
            if ("Noto Sans CJK" in font_name) or ("Noto Serif CJK" in font_name):
                selected_font = font_name
                break

    if selected_font:
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [selected_font, "DejaVu Sans"]
        print(f"使用字體：{selected_font}")
    else:
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
        print("警告：找不到 CJK 字體，將使用英文字樣 fallback。")

    # Convert text to paths to avoid client-side missing-font rendering issues in SVG viewers.
    plt.rcParams["svg.fonttype"] = "path"
    plt.rcParams["axes.unicode_minus"] = False
    return selected_font is not None


def plot_series(series_df):
    has_cjk = configure_cjk_font()

    labels = series_df["period_label"].tolist()
    values = series_df["value"].tolist()
    x = list(range(len(labels)))

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(x, values, color="#1f6aa5", linewidth=2.2, marker="o", markersize=3.8)
    ax.fill_between(x, values, color="#9ec5e5", alpha=0.35)

    if has_cjk:
        ax.set_title("全台建物買賣移轉棟數監控趨勢", fontsize=20, pad=16)
        ax.set_xlabel("期別", fontsize=14)
        ax.set_ylabel("棟數", fontsize=14)
    else:
        ax.set_title("Taiwan Building Transfer Count Trend", fontsize=20, pad=16)
        ax.set_xlabel("Period", fontsize=14)
        ax.set_ylabel("Count", fontsize=14)
    ax.grid(True, linestyle="--", alpha=0.4)

    if len(x) > 24:
        step = max(1, len(x) // 12)
        ticks = list(range(0, len(x), step))
    else:
        ticks = x

    ax.set_xticks(ticks)
    ax.set_xticklabels([labels[i] for i in ticks], rotation=45, ha="right")

    latest_value = int(values[-1])
    latest_label = labels[-1]
    if has_cjk:
        latest_text = f"最新：{latest_label} / {latest_value:,} 棟"
    else:
        latest_text = f"Latest: {latest_label} / {latest_value:,}"
    ax.annotate(
        latest_text,
        xy=(x[-1], values[-1]),
        xytext=(-10, 12),
        textcoords="offset points",
        ha="right",
        fontsize=11,
        color="#0d3b66",
    )

    plt.tight_layout()
    plt.savefig(SVG_OUTPUT, format="svg")
    plt.close(fig)
    print(f"圖表已輸出：{SVG_OUTPUT}")


def calc_change_ratio(current, previous):
    if previous in (None, 0):
        return None
    return (current - previous) / previous * 100


def format_change(current, previous):
    if previous is None:
        return "資料不足"

    delta = current - previous
    ratio = calc_change_ratio(current, previous)
    sign = "+" if delta >= 0 else ""

    if ratio is None:
        return f"{sign}{delta:,} 棟"
    return f"{sign}{delta:,} 棟 ({sign}{ratio:.2f}%)"


def find_same_period_last_year(series_df):
    latest = series_df.iloc[-1]
    latest_dt = latest["parsed_dt"]

    candidates = series_df[
        (series_df["parsed_dt"].dt.year == latest_dt.year - 1)
        & (series_df["parsed_dt"].dt.month == latest_dt.month)
    ]
    if candidates.empty:
        return None

    return candidates.iloc[-1]


def write_monitor_report(series_df):
    latest = series_df.iloc[-1]

    prev = series_df.iloc[-2] if len(series_df) >= 2 else None
    yoy = find_same_period_last_year(series_df)

    latest_value = int(latest["value"])
    prev_value = int(prev["value"]) if prev is not None else None
    yoy_value = int(yoy["value"]) if yoy is not None else None

    now = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S CST")

    content = [
        "# 全台建物買賣移轉棟數監控",
        "",
        f"- 更新時間：{now}",
        f"- 最新期別：{latest['period_label']}",
        f"- 最新棟數：{latest_value:,}",
        f"- 與前一期差異：{format_change(latest_value, prev_value)}",
        f"- 與去年同期差異：{format_change(latest_value, yoy_value)}",
        "",
        "## 檔案位置",
        f"- CSV：`{os.path.relpath(CSV_OUTPUT, PROJECT_ROOT)}`",
        f"- SVG：`{os.path.relpath(SVG_OUTPUT, PROJECT_ROOT)}`",
        "",
        "## 資料來源",
        f"- 內政部不動產資訊平台：{BASE_URL}",
    ]

    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(content) + "\n")

    print(f"監控報告已輸出：{REPORT_OUTPUT}")


def write_unavailable_report(error_message):
    now = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S CST")
    content = [
        "# 全台建物買賣移轉棟數監控",
        "",
        f"- 更新時間：{now}",
        "- 狀態：更新失敗（使用既有資料也不可用）",
        f"- 錯誤訊息：{error_message}",
        "",
        "## 資料來源",
        f"- 內政部不動產資訊平台：{BASE_URL}",
    ]
    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(content) + "\n")
    print(f"監控報告已輸出（失敗狀態）：{REPORT_OUTPUT}")


def summarize_error(error):
    text = str(error).strip()
    if not text:
        return "未知錯誤"
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), text)
    return first_line[:300]


def write_unavailable_svg(error_message):
    has_cjk = configure_cjk_font()
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.axis("off")
    if has_cjk:
        title_text = "全台建物買賣移轉棟數"
        desc_text = "目前無法取得資料，已保留上次可用輸出或等待下次更新。"
        err_text = f"錯誤訊息: {error_message}"
    else:
        title_text = "Taiwan Building Transfer Count"
        desc_text = "Data is temporarily unavailable. Using fallback output."
        err_text = f"Error: {error_message}"

    ax.text(
        0.5,
        0.65,
        title_text,
        ha="center",
        va="center",
        fontsize=24,
        fontweight="bold",
        color="#0d3b66",
    )
    ax.text(
        0.5,
        0.48,
        desc_text,
        ha="center",
        va="center",
        fontsize=14,
        color="#444444",
    )
    ax.text(
        0.5,
        0.34,
        err_text,
        ha="center",
        va="center",
        fontsize=11,
        color="#666666",
        wrap=True,
    )
    plt.tight_layout()
    plt.savefig(SVG_OUTPUT, format="svg")
    plt.close(fig)
    print(f"圖表已輸出（失敗狀態）：{SVG_OUTPUT}")


def update_readme_timestamp():
    readme_path = os.path.join(PROJECT_ROOT, "README.md")
    if not os.path.exists(readme_path):
        return

    timestamp_str = datetime.now(ZoneInfo("Asia/Taipei")).strftime(
        "Update time: %Y-%m-%d %H:%M:%S CST"
    )

    section_header = "### 資料視覺化- 全台建物買賣移轉棟數"
    image_line = "![全台建物買賣移轉棟數](data/svg/taiwan_building_transfer_count.svg)"
    update_pattern = r"^Update time: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} CST$"

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    section_start = None
    for i, line in enumerate(lines):
        if line.strip() == section_header:
            section_start = i
            break

    if section_start is None:
        return

    section_end = len(lines)
    for i in range(section_start + 1, len(lines)):
        if lines[i].startswith("### "):
            section_end = i
            break

    section_lines = lines[section_start:section_end]
    section_lines = [line for line in section_lines if not re.match(update_pattern, line.strip())]

    image_index = None
    for idx, line in enumerate(section_lines):
        if line.strip().startswith("![全台建物買賣移轉棟數]"):
            image_index = idx
            break

    if image_index is None:
        insert_index = None
        for idx, line in enumerate(section_lines):
            if line.strip() == "監控內容：":
                insert_index = idx
                break
        if insert_index is None:
            insert_index = len(section_lines)
            while insert_index > 0 and section_lines[insert_index - 1].strip() == "":
                insert_index -= 1

        section_lines[insert_index:insert_index] = [timestamp_str, "", image_line, ""]
    else:
        section_lines[image_index:image_index] = [timestamp_str, ""]

    normalized_section_lines = []
    previous_blank = False
    for line in section_lines:
        current_blank = line.strip() == ""
        if current_blank and previous_blank:
            continue
        normalized_section_lines.append(line)
        previous_blank = current_blank

    merged_lines = lines[:section_start] + normalized_section_lines + lines[section_end:]
    new_content = "\n".join(merged_lines).rstrip() + "\n"

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"README 已更新（全台建物買賣移轉棟數）：{timestamp_str}")


def main():
    try:
        download_csv()
    except Exception as e:
        if not os.path.exists(CSV_OUTPUT):
            error_summary = summarize_error(e)
            print(f"警告：無法下載且本地也沒有既有 CSV。{error_summary}")
            write_unavailable_report(error_summary)
            write_unavailable_svg(error_summary)
            update_readme_timestamp()
            return
        print(f"下載失敗，改用既有資料：{e}")

    df = read_csv_auto(CSV_OUTPUT)
    series_df = build_taiwan_series(df)
    plot_series(series_df)
    write_monitor_report(series_df)
    update_readme_timestamp()


if __name__ == "__main__":
    main()
