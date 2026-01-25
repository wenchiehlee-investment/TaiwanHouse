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

        six_cities = ['台北市', '新北市', '桃園市', '台中市', '台南市', '高雄市']
        # Normalized names for consistent processing
        normalized_cities = {
            '臺北市': '台北市', '臺中市': '台中市', '臺南市': '台南市'
        }
        df[region_col] = df[region_col].replace(normalized_cities)
        df_filtered = df[df[region_col].isin(six_cities)].copy()
        
        df_filtered.loc[:, rate_col] = df_filtered[rate_col].astype(str).str.replace('%', '', regex=False)
        df_filtered.loc[:, rate_col] = pd.to_numeric(df_filtered[rate_col], errors='coerce')
        
        pivot_df = df_filtered.pivot_table(index=time_col, columns=region_col, values=rate_col)
        
        def parse_quarter(q_str):
            match = re.match(r'(\d+)Q(\d+)', str(q_str))
            if match:
                return int(match.group(1)), int(match.group(2))
            return 0, 0 

        sorted_index = sorted(pivot_df.index, key=parse_quarter)
        pivot_df = pivot_df.reindex(sorted_index)
        
        # Plotting
        cities = pivot_df.columns.tolist()
        fig, axes = plt.subplots(nrows=len(cities), ncols=1, sharex=True, figsize=(12, 18))
        
        plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'sans-serif'] 
        plt.rcParams['axes.unicode_minus'] = False
        
        colors = plt.cm.tab10(range(len(cities)))
        
        # Calculate global Y-axis limit for consistent scaling
        global_max = pivot_df.max().max()
        y_limit = max(0.5, global_max * 1.1) # At least 0.5% for visibility of risk line
        
        for i, city in enumerate(cities):
            ax = axes[i]
            ax.plot(pivot_df.index, pivot_df[city], marker='o', linestyle='-', color=colors[i], label=city)
            
            # Add Risk Alarm Line at 0.3%
            ax.axhline(y=0.3, color='red', linestyle='--', linewidth=1.5, alpha=0.8, label='Risk Alarm (0.3%)')
            
            ax.set_title(city, loc='left', fontsize=12, fontweight='bold')
            ax.set_ylabel('Default Rate (%)')
            ax.set_ylim(0, y_limit) # Set uniform scale
            ax.grid(True, which='both', linestyle='--', alpha=0.7)
            ax.legend(loc='upper right')
            
            xticks = ax.get_xticks()
            ax.set_xticks(xticks)

        axes[-1].set_xlabel('Quarter')
        plt.xticks(rotation=45, fontsize=8)
        
        n = len(pivot_df.index)
        if n > 20:
            step = max(1, n // 15)
            axes[-1].set_xticks(range(0, n, step))
            axes[-1].set_xticklabels(pivot_df.index[::step], rotation=45, fontsize=8)

        fig.suptitle('Quarterly Housing Loan Default Rate - Six Special Municipalities\n(六都購置住宅貸款違約率)', fontsize=16)
        plt.tight_layout(rect=[0, 0.03, 1, 0.97])
        
        svg_path = os.path.join(SVG_DIR, "six_cities_default_rate.svg")
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
    
    # Get current time in Taipei
    taipei_tz = pytz.timezone('Asia/Taipei')
    now = datetime.now(taipei_tz)
    timestamp_str = now.strftime("Update time: %Y-%m-%d %H:%M:%S CST")
    
    readme_path = "README.md"
    if not os.path.exists(readme_path):
        return
        
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Target pattern: Any "Update time: ..." line or the line before the SVG
    svg_marker = "![六都購置住宅貸款違約率]"
    
    if "Update time:" in content:
        # Replace existing timestamp
        new_content = re.sub(r"Update time: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} CST", timestamp_str, content)
    else:
        # Insert before the SVG marker
        new_content = content.replace(svg_marker, f"{timestamp_str}\n\n{svg_marker}")
    
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"Updated README.md with timestamp: {timestamp_str}")

if __name__ == "__main__":
    main()
