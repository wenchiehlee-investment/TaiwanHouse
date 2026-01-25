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
        
        # Find the link for "本季購置住宅貸款違約率"
        # Since the text might be inside a list item or table, we look for an 'a' tag with 'CSV' text 
        # that is associated with our target label.
        # Based on previous HTML inspection, the structure is roughly:
        # Title text ... <a ...>CSV</a>
        # Or checking all links.
        
        print("Searching for target CSV link...")
        target_text = "本季購置住宅貸款違約率"
        
        # We can try to find the text first, then find the associated CSV link.
        # Often these are in rows.
        # Let's try XPath to find an element containing the text, then a following CSV link.
        # XPath: //*[contains(text(), '本季購置住宅貸款違約率')]/following::a[contains(text(), 'CSV')][1]
        # Or checking the title attribute of the 'a' tag which we saw earlier: title="...本季購置住宅貸款違約率"
        
        # Try finding by title attribute first as it seemed robust in the HTML inspection
        # The title was encoded, but Selenium handles decoded text.
        # The title in the HTML was: (CSV格式下載)住宅金融-購置住宅貸款違約狀況-本季購置住宅貸款違約率
        
        links = driver.find_elements(By.TAG_NAME, "a")
        target_link = None
        
        for link in links:
            title = link.get_attribute("title")
            if title and target_text in title and "CSV" in link.text:
                target_link = link
                print(f"Found link with title: {title}")
                break
        
        if not target_link:
            print("Could not find link by title. Trying generic search...")
            # Fallback: Find "CSV" links and check their context
            csv_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "CSV")
            for link in csv_links:
                # Check parent or nearby text
                # This is harder. Let's rely on the title first.
                pass
            raise Exception(f"Could not locate download link for {target_text}")

        # Clear download directory
        for f in os.listdir(DOWNLOAD_DIR):
            os.remove(os.path.join(DOWNLOAD_DIR, f))

        print("Clicking download link...")
        # Scroll to element to ensure it's clickable
        driver.execute_script("arguments[0].scrollIntoView();", target_link)
        time.sleep(1)
        target_link.click()
        
        # Wait for download to complete
        print("Waiting for download...")
        timeout = 30
        start_time = time.time()
        downloaded_file = None
        
        while time.time() - start_time < timeout:
            files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.csv')]
            if files:
                downloaded_file = os.path.join(DOWNLOAD_DIR, files[0])
                # Ensure it's fully downloaded (not .crdownload)
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
            # Load existing
            try:
                df_old = pd.read_csv(final_path, encoding='utf-8')
            except:
                try:
                    df_old = pd.read_csv(final_path, encoding='big5')
                except:
                    df_old = pd.read_csv(final_path, encoding='cp950')
            
            # Load new
            try:
                df_new = pd.read_csv(downloaded_file, encoding='utf-8')
            except:
                try:
                    df_new = pd.read_csv(downloaded_file, encoding='big5')
                except:
                    df_new = pd.read_csv(downloaded_file, encoding='cp950')
            
            # Combine and drop duplicates based on Time and Region
            # Identifying columns dynamically for new data
            time_col_new = [c for c in df_new.columns if '期別' in c or '季' in c or 'Year' in c][0]
            region_col_new = [c for c in df_new.columns if '縣市' in c or 'City' in c or 'Region' in c][0]
            
            # Identify columns for old data (might be different if we renamed them in previous versions)
            time_col_old = [c for c in df_old.columns if '期別' in c or '季' in c or 'Year' in c][0]
            region_col_old = [c for c in df_old.columns if '縣市' in c or 'City' in c or 'Region' in c][0]
            
            # Standardize column names for merging if they differ
            df_new = df_new.rename(columns={time_col_new: '資料期別', region_col_new: '縣市'})
            df_old = df_old.rename(columns={time_col_old: '資料期別', region_col_old: '縣市'})
            
            # Merge
            df_combined = pd.concat([df_old, df_new], ignore_index=True)
            # Drop duplicates (keep the newer one if there are overlaps)
            df_combined = df_combined.drop_duplicates(subset=['資料期別', '縣市'], keep='last')
            
            # Save combined
            df_combined.to_csv(final_path, index=False, encoding='utf-8-sig')
            print(f"Merged data saved to {final_path} (Total rows: {len(df_combined)})")
        else:
            shutil.move(downloaded_file, final_path)
            print(f"Moved file to: {final_path}")
        
        # Clean up temp dir
        shutil.rmtree(DOWNLOAD_DIR)
        
    except Exception as e:
        print(f"Error during Selenium execution: {e}")
        if os.path.exists(DOWNLOAD_DIR):
             shutil.rmtree(DOWNLOAD_DIR)
        # Clean exit to stop execution if real data isn't found
        # (Since user requested NO sample data)
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
        # Try different encodings
        try:
            df = pd.read_csv(final_path, encoding='utf-8')
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(final_path, encoding='big5')
            except UnicodeDecodeError:
                df = pd.read_csv(final_path, encoding='cp950')

        print("CSV Columns:", df.columns.tolist())
        
        # Identify columns
        time_col = None
        region_col = None
        rate_col = None

        for col in df.columns:
            if '季' in col or 'Year' in col:
                time_col = col
            elif '縣市' in col or 'City' in col:
                region_col = col
            elif '率' in col or 'Rate' in col:
                rate_col = col
        
        if not (time_col and region_col and rate_col):
            # Fallback by index
            time_col = df.columns[0]
            region_col = df.columns[1]
            rate_col = df.columns[2]

        print(f"Mapped columns: Time='{time_col}', Region='{region_col}', Rate='{rate_col}'")
        
        # Filter for 六都 (Six Special Municipalities)
        six_cities = ['臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市']
        normalized_cities = {
            '台北市': '臺北市', '台中市': '臺中市', '台南市': '臺南市'
        }
        
        df[region_col] = df[region_col].replace(normalized_cities)
        df_filtered = df[df[region_col].isin(six_cities)]
        
        if df_filtered.empty:
            print("Warning: No data found for six cities. Check region names.")
            print("Unique regions in data:", df[region_col].unique())
            return

        # Clean Rate column
        df_filtered.loc[:, rate_col] = df_filtered[rate_col].astype(str).str.replace('%', '', regex=False)
        df_filtered.loc[:, rate_col] = pd.to_numeric(df_filtered[rate_col], errors='coerce')
        
        # Pivot for plotting
        pivot_df = df_filtered.pivot_table(index=time_col, columns=region_col, values=rate_col)
        
        # Fix sorting of the index (Time)
        def parse_quarter(q_str):
            # Expect format like "97Q1" or "100Q1"
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
        
        for i, city in enumerate(cities):
            ax = axes[i]
            ax.plot(pivot_df.index, pivot_df[city], marker='o', linestyle='-', color=colors[i], label=city)
            ax.set_title(city, loc='left', fontsize=12, fontweight='bold')
            ax.set_ylabel('Default Rate (%)')
            ax.grid(True, which='both', linestyle='--', alpha=0.7)
            ax.legend(loc='upper right')
            
            # Tick styling
            xticks = ax.get_xticks()
            ax.set_xticks(xticks)

        axes[-1].set_xlabel('Quarter')
        plt.xticks(rotation=45, fontsize=8)
        
        # Reduce tick density
        n = len(pivot_df.index)
        if n > 20:
            step = n // 15 if n // 15 > 0 else 1
            axes[-1].set_xticks(range(0, n, step))
            axes[-1].set_xticklabels(pivot_df.index[::step], rotation=45, fontsize=8)

        fig.suptitle('Quarterly Housing Loan Default Rate - Six Special Municipalities\n(六都購置住宅貸款違約率)', fontsize=16)
        plt.tight_layout(rect=[0, 0.03, 1, 0.97])
        
        svg_path = os.path.join(SVG_DIR, "six_cities_default_rate.svg")
        plt.savefig(svg_path, format='svg')
        print(f"Saved plot to {svg_path}")
        
    except Exception as e:
        print(f"Error processing CSV or plotting: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()