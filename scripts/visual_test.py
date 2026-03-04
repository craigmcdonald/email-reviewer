"""Take full-page screenshots of every UI route for visual review.

Starts the FastAPI app against the PostgreSQL database configured in .env,
launches headless Chrome via Selenium, and saves PNGs to /tmp.

The Tailwind Play CDN <script> tag is blocked via CDP and replaced with
pre-compiled Tailwind CSS injected into each page after load. The CSS is
compiled from the project templates using the Tailwind CLI.

Prerequisites:
    - PostgreSQL running with migrations applied and seed data loaded
    - google-chrome-stable installed
    - selenium installed (pipenv install --dev selenium)
    - tailwindcss npm package (npm install -g tailwindcss@3)

Usage:
    pipenv run python -m scripts.visual_test
"""

import os
import subprocess
import threading
import time
from pathlib import Path

os.environ.setdefault("AUTH_ENABLED", "FALSE")
os.environ.setdefault("CURRENT_USER", "test")

import uvicorn
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from app.main import app

APP_PORT = 8765
BASE = f"http://127.0.0.1:{APP_PORT}"
TAILWIND_CSS_CACHE = "/tmp/tailwind_compiled.css"


def _compile_tailwind():
    """Compile Tailwind CSS from the project templates."""
    templates = str(Path(__file__).resolve().parent.parent / "app" / "templates" / "**" / "*.html")
    subprocess.run(
        ["npx", "tailwindcss", "--content", templates, "-o", TAILWIND_CSS_CACHE, "--minify"],
        check=True,
        timeout=30,
        capture_output=True,
    )


def _run_app_server():
    uvicorn.run(app, host="127.0.0.1", port=APP_PORT, log_level="error")


def _take_screenshots():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1440,900")
    chrome_options.binary_location = "/usr/bin/google-chrome-stable"

    service = Service("/opt/node22/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)

    # Block the Tailwind CDN so Chrome doesn't hang on the <script> tag.
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd(
        "Network.setBlockedURLs",
        {"urls": ["*cdn.tailwindcss.com*"]},
    )

    with open(TAILWIND_CSS_CACHE) as f:
        tailwind_css = f.read()

    # Inject compiled CSS as a <style> element to replace the blocked CDN.
    inject_css = """
    var style = document.createElement('style');
    style.textContent = arguments[0];
    document.head.appendChild(style);
    """

    urls = {
        "leaderboard": f"{BASE}/",
        "rep_detail": f"{BASE}/reps/inderpalgill@nativecampusadvertising.com",
        "settings": f"{BASE}/settings",
    }

    for name, url in urls.items():
        print(f"  loading {name}...")
        driver.get(url)
        time.sleep(1)
        driver.execute_script(inject_css, tailwind_css)
        time.sleep(1)
        total_height = driver.execute_script("return document.body.scrollHeight")
        driver.set_window_size(1440, max(900, total_height + 200))
        time.sleep(0.5)
        path = f"/tmp/{name}.png"
        driver.save_screenshot(path)
        print(f"  saved {path}")

    driver.quit()


def main():
    print("Compiling Tailwind CSS...")
    _compile_tailwind()

    app_thread = threading.Thread(target=_run_app_server, daemon=True)
    app_thread.start()
    time.sleep(2)

    print("Taking screenshots...")
    _take_screenshots()
    print("Done.")


if __name__ == "__main__":
    main()
