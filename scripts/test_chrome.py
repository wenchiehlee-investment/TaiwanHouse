"""Diagnostic script: test Chrome + Selenium in current environment."""
import os
import sys
import tempfile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Check /tmp writability
print("=== /tmp check ===")
for d in ["/tmp", "/var/tmp", tempfile.gettempdir()]:
    try:
        test_file = os.path.join(d, "chrome_test_write")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        print(f"  {d}: writable")
    except Exception as e:
        print(f"  {d}: NOT writable ({e})")

# Check if Chrome can write to /tmp
print("\n=== Chrome crash log check ===")
os.system("ls -la /tmp/chrome* 2>/dev/null || echo 'No chrome files in /tmp'")
os.system("ls -la /var/tmp/chrome* 2>/dev/null || echo 'No chrome files in /var/tmp'")

def make_options(extra_args=None):
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--remote-allow-origins=*")
    if extra_args:
        for arg in extra_args:
            opts.add_argument(arg)
    return opts

# Test 1: default (should fail)
print("\n=== Test 1: default ===")
try:
    opts = make_options()
    driver = webdriver.Chrome(options=opts)
    print(f"SUCCESS: title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {type(e).__name__}")

# Test 2: explicit user-data-dir and crash-dumps-dir in /var/tmp
print("\n=== Test 2: user-data-dir=/var/tmp/chrome-profile ===")
try:
    os.makedirs("/var/tmp/chrome-profile", exist_ok=True)
    opts = make_options([
        "--user-data-dir=/var/tmp/chrome-profile",
        "--crash-dumps-dir=/var/tmp/chrome-crashes",
    ])
    driver = webdriver.Chrome(options=opts)
    print(f"SUCCESS: title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {type(e).__name__}")

# Test 3: TMPDIR=/var/tmp environment
print("\n=== Test 3: TMPDIR=/var/tmp ===")
try:
    os.environ["TMPDIR"] = "/var/tmp"
    os.environ["TMP"] = "/var/tmp"
    os.environ["TEMP"] = "/var/tmp"
    opts = make_options(["--user-data-dir=/var/tmp/chrome-profile3"])
    driver = webdriver.Chrome(options=opts)
    print(f"SUCCESS: title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {type(e).__name__}")

# Test 4: verbose chromedriver log
print("\n=== Test 4: verbose log ===")
try:
    opts = make_options(["--user-data-dir=/var/tmp/chrome-profile4"])
    svc = Service(service_args=["--verbose"])
    driver = webdriver.Chrome(service=svc, options=opts)
    print(f"SUCCESS: title={driver.title!r}")
    driver.quit()
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {type(e).__name__}")
    # Print any chrome crash logs
    print("\nChrome stderr/crash info:")
    os.system("cat /var/tmp/chrome-crashes/* 2>/dev/null || echo 'No crash logs'")

print("\nAll tests failed.")
sys.exit(1)
