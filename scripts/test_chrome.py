"""Diagnostic script: test Chrome + Selenium in current environment."""
import sys

# Test 1: Selenium built-in driver management
print("=== Test 1: Selenium built-in driver ===")
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--remote-allow-origins=*")

    svc = Service(log_output=sys.stdout)
    driver = webdriver.Chrome(service=svc, options=opts)
    print(f"SUCCESS: session created, title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {e}")

# Test 2: webdriver_manager
print("\n=== Test 2: webdriver_manager ===")
try:
    from webdriver_manager.chrome import ChromeDriverManager

    path = ChromeDriverManager().install()
    print(f"chromedriver path: {path}")

    svc = Service(executable_path=path, log_output=sys.stdout)
    driver = webdriver.Chrome(service=svc, options=opts)
    print(f"SUCCESS: session created, title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {e}")

# Test 3: Try --headless (old style) instead of --headless=new
print("\n=== Test 3: old --headless flag ===")
try:
    opts2 = Options()
    opts2.add_argument("--headless")
    opts2.add_argument("--no-sandbox")
    opts2.add_argument("--disable-dev-shm-usage")
    opts2.add_argument("--disable-gpu")
    opts2.add_argument("--remote-allow-origins=*")

    driver = webdriver.Chrome(options=opts2)
    print(f"SUCCESS: session created with old --headless, title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {e}")

print("\nAll tests failed.")
sys.exit(1)
