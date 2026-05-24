from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

opts = Options()
opts.add_argument('--headless')
driver = webdriver.Chrome(options=opts)
driver.get('https://pip.moi.gov.tw/Publicize/Info/E3030')
time.sleep(5)

print("--- INPUTS ---")
for i in driver.find_elements(By.TAG_NAME, 'input'):
    print(f"ID: {i.get_attribute('id')}, Name: {i.get_attribute('name')}, Type: {i.get_attribute('type')}")

print("\n--- SELECTS ---")
for s in driver.find_elements(By.TAG_NAME, 'select'):
    print(f"ID: {s.get_attribute('id')}, Name: {s.get_attribute('name')}")
    # Print options
    options = s.find_elements(By.TAG_NAME, 'option')
    for o in options[:5]: # Show first 5
        print(f"  Option: {o.text}")

driver.quit()
