"""Diagnostic script: test Chrome + Selenium in current environment."""
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")
opts.add_argument("--disable-gpu")
opts.add_argument("--remote-allow-origins=*")

# Test 1: with --allowed-ips= (fix for Docker bind() failure)
print("=== Test 1: Selenium built-in driver + --allowed-ips ===")
try:
    svc = Service(service_args=["--allowed-ips=", "--allowed-origins=*"])
    driver = webdriver.Chrome(service=svc, options=opts)
    print(f"SUCCESS: session created, title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {e}")

# Test 2: webdriver_manager + --allowed-ips
print("\n=== Test 2: webdriver_manager + --allowed-ips ===")
try:
    from webdriver_manager.chrome import ChromeDriverManager
    path = ChromeDriverManager().install()
    print(f"chromedriver path: {path}")
    svc = Service(executable_path=path, service_args=["--allowed-ips=", "--allowed-origins=*"])
    driver = webdriver.Chrome(service=svc, options=opts)
    print(f"SUCCESS: session created, title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {e}")

# Test 3: old --headless flag
print("\n=== Test 3: old --headless flag ===")
try:
    opts2 = Options()
    opts2.add_argument("--headless")
    opts2.add_argument("--no-sandbox")
    opts2.add_argument("--disable-dev-shm-usage")
    opts2.add_argument("--disable-gpu")
    opts2.add_argument("--remote-allow-origins=*")
    svc = Service(service_args=["--allowed-ips=", "--allowed-origins=*"])
    driver = webdriver.Chrome(service=svc, options=opts2)
    print(f"SUCCESS: session created with old --headless, title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {e}")

print("\nAll tests failed.")
sys.exit(1)
