"""Live visual test: drives the actual browser UI through the full workflow.

1. Settings page: uncheck auto-score, set max=100, click Fetch
2. Wait for fetch job to complete
3. Team page: assign rep types via dropdown
4. Rep detail page: verify four sections, screenshot everything
"""

import json
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

BASE = "http://127.0.0.1:8000"


def full_page_screenshot(driver, path):
    time.sleep(1)
    total_height = driver.execute_script("return document.body.scrollHeight")
    driver.set_window_size(1440, max(900, total_height + 200))
    time.sleep(0.5)
    driver.save_screenshot(path)
    print(f"  Saved {path}")


def wait_for_fetch_complete(timeout=120):
    """Poll the jobs list API until the fetch job is COMPLETED."""
    print("  Waiting for fetch job to complete...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(f"{BASE}/api/operations/last-run", timeout=5)
            data = json.loads(resp.read())
            fetch = data.get("fetch")
            if fetch:
                status = fetch.get("status", "")
                if status == "COMPLETED":
                    summary = fetch.get("result_summary", {})
                    print(f"  Fetch completed: {summary}")
                    return True
                if status == "FAILED":
                    err = fetch.get("error_message", "")
                    print(f"  Fetch FAILED: {err}")
                    return False
                print(f"  Fetch status: {status}")
        except Exception as e:
            print(f"  Poll error: {e}")
        time.sleep(2)
    print("  Fetch timed out!")
    return False


chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1440,900")
chrome_options.binary_location = "/usr/bin/google-chrome-stable"

driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 10)

try:
    # =========================================================
    # STEP 1: Settings page - uncheck auto-score, fetch 100
    # =========================================================
    print("STEP 1: Settings page - configure and fetch")
    driver.get(f"{BASE}/settings?tab=general")
    time.sleep(2)
    full_page_screenshot(driver, "/tmp/01_settings_before_fetch.png")

    # Uncheck "Score after fetch" if checked
    auto_score_cb = driver.find_element(By.ID, "fetch_auto_score")
    if auto_score_cb.is_selected():
        auto_score_cb.click()
        print("  Unchecked auto-score")
        time.sleep(0.5)

    # Set max emails to 100
    max_input = driver.find_element(By.ID, "fetch_max_count")
    max_input.clear()
    max_input.send_keys("100")
    print("  Set max emails to 100")

    full_page_screenshot(driver, "/tmp/02_settings_auto_score_off.png")

    # Click the Fetch button
    fetch_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Fetch')]")
    fetch_btn.click()
    print("  Clicked Fetch button")
    time.sleep(2)
    full_page_screenshot(driver, "/tmp/03_settings_fetch_clicked.png")

    # Wait for fetch to complete
    wait_for_fetch_complete(timeout=120)

    # Refresh settings page to see updated jobs list
    driver.get(f"{BASE}/settings?tab=general")
    time.sleep(3)
    full_page_screenshot(driver, "/tmp/04_settings_after_fetch.png")

    # =========================================================
    # STEP 2: Team page - verify reps appear, assign types
    # =========================================================
    print("\nSTEP 2: Team page - assign rep types")
    driver.get(BASE)
    time.sleep(2)
    full_page_screenshot(driver, "/tmp/05_team_before_types.png")

    # Count reps
    selects = driver.find_elements(By.CSS_SELECTOR, "select.rep-type-select")
    num_reps = len(selects)
    print(f"  Found {num_reps} reps with type dropdowns")

    # Assign types one at a time, navigating fresh each time to avoid stale refs.
    # After selecting a value, the JS fires a PATCH then window.location.reload().
    # We must wait for the reload to complete before navigating again.
    rep_types = ["SDR", "BizDev", "AM"]
    assigned = 0
    for attempt in range(num_reps * 2):  # safety limit
        driver.get(BASE)
        time.sleep(2)
        all_selects = driver.find_elements(By.CSS_SELECTOR, "select.rep-type-select")
        # Find first dropdown still on default/empty value
        target = None
        for sel in all_selects:
            current_val = Select(sel).first_selected_option.get_attribute("value")
            if current_val in ("", None):
                target = sel
                break
        if target is None:
            print(f"  All reps assigned ({assigned} total)")
            break
        rep_email = target.get_attribute("data-rep-email")
        assigned_type = rep_types[assigned % len(rep_types)]
        # Store a reference to detect page reload
        body_ref = driver.find_element(By.TAG_NAME, "body")
        Select(target).select_by_value(assigned_type)
        print(f"  Set {rep_email} -> {assigned_type}")
        # Wait for page to reload (body element becomes stale)
        for _ in range(20):
            try:
                body_ref.tag_name  # will throw if page reloaded
                time.sleep(0.5)
            except Exception:
                break
        time.sleep(1)  # let new page settle
        assigned += 1

    # Refresh to see the changes persisted
    driver.get(BASE)
    time.sleep(2)
    full_page_screenshot(driver, "/tmp/06_team_with_types.png")

    # =========================================================
    # STEP 3: Rep detail pages - verify four sections
    # =========================================================
    print("\nSTEP 3: Rep detail pages")

    # Get all rep links from team page
    rep_links = driver.find_elements(By.CSS_SELECTOR, "a[href^='/reps/']")
    rep_urls = list(dict.fromkeys(link.get_attribute("href") for link in rep_links))
    print(f"  Found {len(rep_urls)} rep detail links")

    for idx, url in enumerate(rep_urls[:5]):  # Screenshot first 5 reps
        rep_email = url.split("/reps/")[-1] if "/reps/" in url else url
        print(f"\n  Visiting rep: {rep_email}")
        driver.get(url)
        time.sleep(2)

        page_source = driver.page_source
        has_outreach = "Outreach" in page_source
        has_followup = ">Follow-up<" in page_source
        has_unanswered = "Unanswered Replies" in page_source
        has_chains = ">Chains<" in page_source

        print(f"    Outreach:    {'YES' if has_outreach else 'no'}")
        print(f"    Follow-up:   {'YES' if has_followup else 'no'}")
        print(f"    Unanswered:  {'YES' if has_unanswered else 'no'}")
        print(f"    Chains:      {'YES' if has_chains else 'no'}")

        safe_name = rep_email.replace("@", "_at_").replace(".", "_")[:40]
        full_page_screenshot(driver, f"/tmp/07_rep_detail_{idx}_{safe_name}.png")

    print("\n=== ALL DONE ===")
    print("Screenshots saved to /tmp/01_*.png through /tmp/07_*.png")

finally:
    driver.quit()
