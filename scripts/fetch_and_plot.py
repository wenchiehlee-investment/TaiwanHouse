import os
import sys
import time
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
import matplotlib.font_manager as fm

try:
    from selenium_stealth import stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# Set up paths
BASE_URL = "https://pip.moi.gov.tw/Publicize/Info/E3030"
PROJECT_ROOT = os.getcwd()
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "csv")
SVG_DIR = os.path.join(PROJECT_ROOT, "data", "svg")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "temp_download")
CSV_OUTPUT = os.path.join(DATA_DIR, "housing_loan_default_rate.csv")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SVG_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-allow-origins=*")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--ignore-certificate-errors")

    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    try:
        # Selenium 4.6+ has built-in driver management
        driver = webdriver.Chrome(options=chrome_options)
    except Exception:
        # Fallback to webdriver_manager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

    if HAS_STEALTH:
        stealth(
            driver,
            languages=["zh-TW", "zh", "en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
    else:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

    return driver


def is_rejected_page(driver):
    text = ((driver.page_source or "") + " " + (driver.title or "")).lower()
    rejected_signals = [
        "request rejected",
        "the requested url was rejected",
        "access denied",
        "forbidden",
        "security policy",
    ]
    return any(signal in text for signal in rejected_signals)


def clear_download_dir():
    for f in os.listdir(DOWNLOAD_DIR):
        file_path = os.path.join(DOWNLOAD_DIR, f)
        if os.path.isfile(file_path):
            os.remove(file_path)


def wait_for_download(timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.csv')]
        if files:
            if not any(f.endswith('.crdownload') for f in os.listdir(DOWNLOAD_DIR)):
                return os.path.join(DOWNLOAD_DIR, files[0])
        time.sleep(1)
    return None


def read_csv_auto(path):
    for encoding in ("utf-8", "utf-8-sig", "big5", "cp950"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception:
            continue
    raise RuntimeError(f"無法讀取 CSV：{path}")


def download_csv():
    """Download CSV with retry logic. Returns True if fresh data obtained."""
    last_error = None
    for attempt in range(1, 4):
        driver = None
        try:
            print(f"初始化 WebDriver...（第 {attempt} 次嘗試）")
            driver = setup_driver()

            print(f"前往資料來源：{BASE_URL}")
            driver.get(BASE_URL)
            WebDriverWait(driver, 25).until(
                lambda d: d.find_elements(By.TAG_NAME, "a")
            )

            if is_rejected_page(driver):
                raise RuntimeError("來源網站拒絕請求（Request Rejected / Access Denied）。")

            print("搜尋目標 CSV 下載連結...")
            target_text = "本季購置住宅貸款違約率"

            links = driver.find_elements(By.TAG_NAME, "a")
            target_link = None

            for link in links:
                title = link.get_attribute("title")
                if title and target_text in title and "CSV" in link.text:
                    target_link = link
                    print(f"找到連結：{title}")
                    break

            if not target_link:
                raise RuntimeError(f"找不到「{target_text}」CSV 下載連結。")

            clear_download_dir()

            print("點擊下載連結...")
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", target_link
            )
            time.sleep(1)
            try:
                target_link.click()
            except Exception:
                driver.execute_script("arguments[0].click();", target_link)

            downloaded_file = wait_for_download()
            if downloaded_file is None:
                raise RuntimeError("資料檔下載逾時。")

            print(f"已下載：{downloaded_file}")

            # Merge or replace
            if os.path.exists(CSV_OUTPUT):
                print("合併既有資料...")
                df_old = read_csv_auto(CSV_OUTPUT)
                df_new = read_csv_auto(downloaded_file)

                time_col_new = [c for c in df_new.columns if '期別' in c or '季' in c or 'Year' in c][0]
                region_col_new = [c for c in df_new.columns if '縣市' in c or 'City' in c or 'Region' in c][0]

                time_col_old = [c for c in df_old.columns if '期別' in c or '季' in c or 'Year' in c][0]
                region_col_old = [c for c in df_old.columns if '縣市' in c or 'City' in c or 'Region' in c][0]

                df_new = df_new.rename(columns={time_col_new: '資料期別', region_col_new: '縣市'})
                df_old = df_old.rename(columns={time_col_old: '資料期別', region_col_old: '縣市'})

                df_combined = pd.concat([df_old, df_new], ignore_index=True)
                df_combined = df_combined.drop_duplicates(subset=['資料期別', '縣市'], keep='last')

                df_combined.to_csv(CSV_OUTPUT, index=False, encoding='utf-8-sig')
                print(f"合併完成：{CSV_OUTPUT}（共 {len(df_combined)} 筆）")
            else:
                shutil.move(downloaded_file, CSV_OUTPUT)
                print(f"檔案已儲存：{CSV_OUTPUT}")

            return True

        except Exception as e:
            last_error = e
            print(f"第 {attempt} 次嘗試失敗：{e}")
            time.sleep(2 * attempt)
        finally:
            if driver:
                driver.quit()
            if os.path.exists(DOWNLOAD_DIR):
                shutil.rmtree(DOWNLOAD_DIR)

    if last_error:
        raise last_error
    return False


def process_and_plot():
    """Process CSV and generate plot. Returns True on success."""
    print("處理 CSV 資料...")
    df = read_csv_auto(CSV_OUTPUT)

    time_col = [c for c in df.columns if '期別' in c or '季' in c or 'Year' in c][0]
    region_col = [c for c in df.columns if '縣市' in c or 'City' in c or 'Region' in c][0]
    rate_col = [c for c in df.columns if '率' in c or 'Rate' in c][0]

    target_cities = ['桃園市', '新竹市', '新竹縣', '苗栗縣', '台北市', '新北市', '台中市', '台南市', '高雄市']

    normalized_cities = {
        '臺北市': '台北市', '臺中市': '台中市', '臺南市': '台南市', '臺東縣': '台東縣'
    }
    df[region_col] = df[region_col].replace(normalized_cities)
    df_filtered = df[df[region_col].isin(target_cities)].copy()

    df_filtered.loc[:, rate_col] = df_filtered[rate_col].astype(str).str.replace('%', '', regex=False)
    df_filtered.loc[:, rate_col] = pd.to_numeric(df_filtered[rate_col], errors='coerce')

    pivot_df = df_filtered.pivot_table(index=time_col, columns=region_col, values=rate_col)
    existing_cities = [c for c in target_cities if c in pivot_df.columns]
    pivot_df = pivot_df[existing_cities]

    def parse_quarter(q_str):
        match = re.match(r'(\d+)Q(\d+)', str(q_str))
        if match:
            return int(match.group(1)), int(match.group(2))
        return 0, 0

    def format_quarter_label(q_str):
        match = re.match(r'(\d+)Q(\d+)', str(q_str))
        if match:
            minguo_year = int(match.group(1))
            quarter = int(match.group(2))
            return f"{minguo_year + 1911}Q{quarter}"
        return q_str

    sorted_index = sorted(pivot_df.index, key=parse_quarter)
    pivot_df = pivot_df.reindex(sorted_index)

    # Plotting
    cities = pivot_df.columns.tolist()
    fig, axes = plt.subplots(nrows=len(cities), ncols=1, sharex=True, figsize=(12, 3 * len(cities)))

    cjk_fonts = ['Noto Sans CJK TC', 'Noto Sans CJK JP', 'Noto Sans CJK SC', 'Noto Sans CJK KR',
                 'Microsoft JhengHei', 'Arial Unicode MS', 'WenQuanYi Micro Hei', 'TakaoPGothic', 'Ubuntu Mono', 'sans-serif']

    found_cjk_font = False
    for font_name in cjk_fonts:
        if any(font_name in font.name for font in fm.fontManager.ttflist):
            plt.rcParams['font.sans-serif'] = [font_name, 'sans-serif']
            found_cjk_font = True
            break

    if not found_cjk_font:
        plt.rcParams['font.sans-serif'] = ['sans-serif']

    plt.rcParams['axes.unicode_minus'] = False

    colors = plt.cm.tab20(range(len(cities)))
    y_limit = 2.0

    for i, city in enumerate(cities):
        ax = axes[i]
        data = pivot_df[city]

        ax.plot(pivot_df.index, data, linestyle='-', color=colors[i], alpha=0.6, label=city)

        normal_mask = data <= 0.3
        ax.scatter(pivot_df.index[normal_mask], data[normal_mask], marker='o', color=colors[i], s=30)

        risk_mask = data > 0.3
        if risk_mask.any():
            ax.scatter(pivot_df.index[risk_mask], data[risk_mask], marker='^', color=colors[i], s=60, edgecolor='red', linewidth=1, zorder=5)

        ax.axhline(y=0.3, color='red', linestyle='--', linewidth=1.5, alpha=0.8, label='Risk Alarm (0.3%)')

        ax.set_title(city, loc='left', fontsize=16, fontweight='bold')
        ax.set_ylabel('Default Rate (%)')
        ax.set_ylim(0, y_limit)
        ax.grid(True, which='both', linestyle='--', alpha=0.7)
        ax.legend(loc='upper right')

        xticks = ax.get_xticks()
        ax.set_xticks(xticks)

    axes[-1].set_xlabel('Quarter')
    plt.xticks(rotation=45, fontsize=12)

    n = len(pivot_df.index)
    if n > 20:
        step = max(1, n // 15)
        axes[-1].set_xticks(range(0, n, step))
        axes[-1].set_xticklabels([format_quarter_label(q) for q in pivot_df.index[::step]], rotation=45, fontsize=12)
    else:
        axes[-1].set_xticklabels([format_quarter_label(q) for q in pivot_df.index], rotation=45, fontsize=12)

    fig.suptitle('Quarterly Housing Loan Default Rate - Major Cities\n(主要城市購置住宅貸款違約率)', fontsize=20)
    plt.tight_layout(rect=[0, 0.03, 1, 0.97])

    svg_path = os.path.join(SVG_DIR, "major_cities_default_rate.svg")
    plt.savefig(svg_path, format='svg')
    print(f"圖表已輸出：{svg_path}")
    return True


def update_readme_timestamp():
    import pytz
    from datetime import datetime

    taipei_tz = pytz.timezone('Asia/Taipei')
    now = datetime.now(taipei_tz)
    timestamp_str = now.strftime("Update time: %Y-%m-%d %H:%M:%S CST")

    readme_path = "README.md"
    if not os.path.exists(readme_path):
        return

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    section_header = "### 資料視覺化- 本季購置住宅貸款違約率"
    next_section_header = "### 資料視覺化- 全台建物買賣移轉棟數"
    image_prefix = "![主要城市購置住宅貸款違約率]"
    update_pattern = r"^Update time: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} CST$"

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
        if lines[i].strip() == next_section_header:
            section_end = i
            break

    section_lines = lines[section_start:section_end]
    section_lines = [line for line in section_lines if not re.match(update_pattern, line.strip())]

    image_index = None
    for idx, line in enumerate(section_lines):
        if line.strip().startswith(image_prefix):
            image_index = idx
            break

    if image_index is not None:
        section_lines.insert(image_index, "")
        section_lines.insert(image_index, timestamp_str)
    else:
        insert_index = len(section_lines)
        while insert_index > 0 and section_lines[insert_index - 1].strip() == "":
            insert_index -= 1
        section_lines.insert(insert_index, "")
        section_lines.insert(insert_index, timestamp_str)

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
    print(f"README 已更新：{timestamp_str}")


def main():
    # Phase 1: Download
    fresh_download = False
    try:
        fresh_download = download_csv()
    except Exception as e:
        if not os.path.exists(CSV_OUTPUT):
            print(f"錯誤：無法下載且本地也沒有既有 CSV。{e}")
            sys.exit(2)
        print(f"下載失敗，改用既有資料：{e}")

    # Phase 2: Process and plot
    try:
        process_and_plot()
    except Exception as e:
        print(f"處理 CSV 或繪圖時發生錯誤：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)

    # Phase 3: Update README only if fresh data
    if fresh_download:
        update_readme_timestamp()
    else:
        print("使用既有資料，不更新 README 時間戳。")

    # Exit code: 0 = fresh data, 1 = used cache
    if not fresh_download:
        sys.exit(1)


if __name__ == "__main__":
    main()
