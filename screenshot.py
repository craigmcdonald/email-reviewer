"""Visual test: take screenshots of the settings page.

Seeds PostgreSQL via sync psycopg2, starts uvicorn as a subprocess,
takes screenshots with Selenium.
"""

import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

DB_URL = "postgresql+psycopg2://screenshot_user:screenshot_pass@localhost:5432/screenshot_test"
PORT = 8769

# Set env before importing app models
os.environ["AUTH_ENABLED"] = "FALSE"
os.environ["CURRENT_USER"] = "test"
os.environ["DATABASE_URL"] = DB_URL

from app.models import Email, Job, Rep, Score, Settings  # noqa: F401
from app.models.base import Base

# Seed database
sync_engine = create_engine(DB_URL)
Base.metadata.drop_all(sync_engine)
Base.metadata.create_all(sync_engine)

with Session(sync_engine) as session:
    session.add(Settings(
        id=1,
        global_start_date=date(2025, 9, 1),
        company_domains="nativecampusadvertising.com,native.fm",
        scoring_batch_size=5,
        auto_score_after_fetch=True,
    ))
    session.commit()

sync_engine.dispose()
print("Database seeded.")

# Start uvicorn as subprocess
env = os.environ.copy()
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app",
     "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "error"],
    env=env,
)

# Wait for server
for i in range(20):
    time.sleep(0.5)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/settings", timeout=2)
        print("Server ready.")
        break
    except Exception:
        pass
else:
    print("Server failed to start.")
    server.kill()
    sys.exit(1)

# Take screenshots
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1440,900")
chrome_options.binary_location = "/usr/bin/google-chrome-stable"

driver = webdriver.Chrome(options=chrome_options)

urls = {
    "team": f"http://127.0.0.1:{PORT}/",
    "settings": f"http://127.0.0.1:{PORT}/settings",
}

for name, url in urls.items():
    driver.get(url)
    time.sleep(1)
    total_height = driver.execute_script("return document.body.scrollHeight")
    driver.set_window_size(1440, max(900, total_height + 200))
    time.sleep(0.5)
    driver.save_screenshot(f"/tmp/{name}.png")
    print(f"Saved /tmp/{name}.png")

driver.quit()

# Cleanup
server.send_signal(signal.SIGTERM)
server.wait(timeout=5)
