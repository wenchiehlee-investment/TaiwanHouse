import os
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
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import matplotlib.font_manager as fm

# Set up paths
BASE_URL = "https://pip.moi.gov.tw/Publicize/Info/E3030"
PROJECT_ROOT = os.getcwd()
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "csv")
SVG_DIR = os.path.join(PROJECT_ROOT, "data", "svg")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "temp_download") # Temporary folder for download

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SVG_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def main():
    print("Initializing Selenium WebDriver...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless") # Run in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Configure download preferences
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print(f"Navigating to {BASE_URL}")
        driver.get(BASE_URL)
        
        # Wait for the page to load
        wait = WebDriverWait(driver, 20)
        
        print("Searching for target CSV link...")
        target_text = "本季購置住宅貸款違約率"
        
        links = driver.find_elements(By.TAG_NAME, "a")
        target_link = None
        
        for link in links:
            title = link.get_attribute("title")
            if title and target_text in title and "CSV" in link.text:
                target_link = link
                print(f"Found link with title: {title}")
                break
        
        if not target_link:
            raise Exception(f"Could not locate download link for {target_text}")

        # Clear download directory
        for f in os.listdir(DOWNLOAD_DIR):
            os.remove(os.path.join(DOWNLOAD_DIR, f))

        print("Clicking download link...")
        driver.execute_script("arguments[0].scrollIntoView();", target_link)
        time.sleep(1)
        target_link.click()
        
        print("Waiting for download...")
        timeout = 30
        start_time = time.time()
        downloaded_file = None
        
        while time.time() - start_time < timeout:
            files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.csv')]
            if files:
                downloaded_file = os.path.join(DOWNLOAD_DIR, files[0])
                if not any(f.endswith('.crdownload') for f in os.listdir(DOWNLOAD_DIR)):
                    break
            time.sleep(1)
            
        if not downloaded_file:
            raise Exception("Download timed out or failed.")
            
        print(f"Downloaded: {downloaded_file}")
        
        # Move to final location or merge with existing
        final_path = os.path.join(DATA_DIR, "housing_loan_default_rate.csv")
        
        if os.path.exists(final_path):
            print("Merging with existing data...")
            try:
                df_old = pd.read_csv(final_path, encoding='utf-8')
            except:
                try:
                    df_old = pd.read_csv(final_path, encoding='big5')
                except:
                    df_old = pd.read_csv(final_path, encoding='cp950')
            
            try:
                df_new = pd.read_csv(downloaded_file, encoding='utf-8')
            except:
                try:
                    df_new = pd.read_csv(downloaded_file, encoding='big5')
                except:
                    df_new = pd.read_csv(downloaded_file, encoding='cp950')
            
            time_col_new = [c for c in df_new.columns if '期別' in c or '季' in c or 'Year' in c][0]
            region_col_new = [c for c in df_new.columns if '縣市' in c or 'City' in c or 'Region' in c][0]
            
            time_col_old = [c for c in df_old.columns if '期別' in c or '季' in c or 'Year' in c][0]
            region_col_old = [c for c in df_old.columns if '縣市' in c or 'City' in c or 'Region' in c][0]
            
            df_new = df_new.rename(columns={time_col_new: '資料期別', region_col_new: '縣市'})
            df_old = df_old.rename(columns={time_col_old: '資料期別', region_col_old: '縣市'})
            
            df_combined = pd.concat([df_old, df_new], ignore_index=True)
            df_combined = df_combined.drop_duplicates(subset=['資料期別', '縣市'], keep='last')
            
            df_combined.to_csv(final_path, index=False, encoding='utf-8-sig')
            print(f"Merged data saved to {final_path} (Total rows: {len(df_combined)})")
        else:
            shutil.move(downloaded_file, final_path)
            print(f"Moved file to: {final_path}")
        
        shutil.rmtree(DOWNLOAD_DIR)
        
    except Exception as e:
        print(f"Error during Selenium execution: {e}")
        if os.path.exists(DOWNLOAD_DIR):
             shutil.rmtree(DOWNLOAD_DIR)
        try:
            driver.quit()
        except:
            pass
        return

    finally:
        try:
            driver.quit()
        except:
            pass

    # Process Data
    print("Processing CSV...")
    try:
        try:
            df = pd.read_csv(final_path, encoding='utf-8')
        except:
            try:
                df = pd.read_csv(final_path, encoding='big5')
            except:
                df = pd.read_csv(final_path, encoding='cp950')

        time_col = [c for c in df.columns if '期別' in c or '季' in c or 'Year' in c][0]
        region_col = [c for c in df.columns if '縣市' in c or 'City' in c or 'Region' in c][0]
        rate_col = [c for c in df.columns if '率' in c or 'Rate' in c][0]

        # Target cities with new order: Taoyuan, Hsinchu City, Hsinchu County, Miaoli, Taipei, New Taipei, Taichung, Tainan, Kaohsiung
        target_cities = ['桃園市', '新竹市', '新竹縣', '苗栗縣', '台北市', '新北市', '台中市', '台南市', '高雄市']
        
        # Normalized names for consistent processing
        normalized_cities = {
            '臺北市': '台北市', '臺中市': '台中市', '臺南市': '台南市', '臺東縣': '台東縣'
        }
        df[region_col] = df[region_col].replace(normalized_cities)
        df_filtered = df[df[region_col].isin(target_cities)].copy()
        
        df_filtered.loc[:, rate_col] = df_filtered[rate_col].astype(str).str.replace('%', '', regex=False)
        df_filtered.loc[:, rate_col] = pd.to_numeric(df_filtered[rate_col], errors='coerce')
        
        pivot_df = df_filtered.pivot_table(index=time_col, columns=region_col, values=rate_col)
        # Ensure columns follow the specified order
        # Only include columns that actually exist in data
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
            return q_str # Return original string if format doesn't match

        sorted_index = sorted(pivot_df.index, key=parse_quarter)
        pivot_df = pivot_df.reindex(sorted_index)
        
        # Plotting
        cities = pivot_df.columns.tolist()
        # Adjust figure size for more subplots
        fig, axes = plt.subplots(nrows=len(cities), ncols=1, sharex=True, figsize=(12, 3 * len(cities)))
        
        # Configure font for CJK characters
        # List of preferred CJK fonts
        cjk_fonts = ['Noto Sans CJK TC', 'Noto Sans CJK JP', 'Noto Sans CJK SC', 'Noto Sans CJK KR',
                     'Microsoft JhengHei', 'Arial Unicode MS', 'WenQuanYi Micro Hei', 'TakaoPGothic', 'Ubuntu Mono', 'sans-serif']

        # Find a suitable CJK font
        found_cjk_font = False
        for font_name in cjk_fonts:
            if any(font_name in font.name for font in fm.fontManager.ttflist):
                plt.rcParams['font.sans-serif'] = [font_name, 'sans-serif']
                found_cjk_font = True
                break

        if not found_cjk_font:
            print("Warning: No suitable CJK font found. Chinese characters may not display correctly.")
            print("Please install a CJK font like 'Noto Sans CJK TC' for optimal display.")
            plt.rcParams['font.sans-serif'] = ['sans-serif'] # Fallback to generic sans-serif

        plt.rcParams['axes.unicode_minus'] = False
        print(f"Matplotlib is using font(s) for sans-serif: {plt.rcParams['font.sans-serif']}")
        
        # Use a colormap that can handle more unique values
        colors = plt.cm.tab20(range(len(cities)))
        
        # Calculate global Y-axis limit for consistent scaling
        y_limit = 2.0 # Fixed max Y at 2% as requested
        
        for i, city in enumerate(cities):
            ax = axes[i]
            data = pivot_df[city]
            
            # Plot the connecting line
            ax.plot(pivot_df.index, data, linestyle='-', color=colors[i], alpha=0.6, label=city)
            
            # Plot normal points (<= 0.3) as circles
            normal_mask = data <= 0.3
            ax.scatter(pivot_df.index[normal_mask], data[normal_mask], marker='o', color=colors[i], s=30)
            
            # Plot risk points (> 0.3) as triangles
            risk_mask = data > 0.3
            if risk_mask.any():
                ax.scatter(pivot_df.index[risk_mask], data[risk_mask], marker='^', color=colors[i], s=60, edgecolor='red', linewidth=1, zorder=5)
            
            # Add Risk Alarm Line at 0.3%
            ax.axhline(y=0.3, color='red', linestyle='--', linewidth=1.5, alpha=0.8, label='Risk Alarm (0.3%)')
            
            ax.set_title(city, loc='left', fontsize=16, fontweight='bold')
            ax.set_ylabel('Default Rate (%)')
            ax.set_ylim(0, y_limit) # Set uniform scale
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
        print(f"Saved plot to {svg_path}")
        
        # Update README.md with timestamp
        update_readme_timestamp()
        
    except Exception as e:
        print(f"Error processing CSV or plotting: {e}")
        import traceback
        traceback.print_exc()

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
    print(f"Updated README.md with timestamp: {timestamp_str}")

if __name__ == "__main__":
    main()
