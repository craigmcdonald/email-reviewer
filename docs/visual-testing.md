# Visual Testing

Visual testing renders pages in a real browser and captures screenshots. Use it to verify layout, styling, and conditional UI elements after template or CSS changes.

## Prerequisites

- Google Chrome (`google-chrome-stable`)
- PostgreSQL running locally
- Python packages: `selenium` (dev dependency)
- Node packages: `tailwindcss`, `@tailwindcss/cli` (for CSS rebuild)

```bash
pipenv install --dev selenium
```

Chrome is available via direct download if not already installed:

```bash
wget -q 'https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb' -O /tmp/chrome.deb
sudo dpkg -i /tmp/chrome.deb
sudo apt-get install -f -y
```

## How It Works

1. Seed a PostgreSQL database with test data using sync SQLAlchemy (psycopg2).
2. Start uvicorn as a subprocess (separate process, own event loop).
3. Wait for the server to respond to HTTP requests.
4. Launch headless Chrome via Selenium and navigate to each page.
5. Resize the viewport to match the page's scroll height for a full-page capture.
6. Save screenshots as PNG files.

The script lives at `tests/visual/screenshot.py`.

## Database Setup

Use a dedicated PostgreSQL database and sync SQLAlchemy for seeding. The app's async engine is created fresh in the uvicorn subprocess, avoiding cross-thread event loop issues.

```python
import os

os.environ["AUTH_ENABLED"] = "FALSE"
os.environ["CURRENT_USER"] = "test"
os.environ["DATABASE_URL"] = "postgresql+psycopg2://user:pass@localhost:5432/screenshot_test"

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Email, Job, Rep, Score, Settings  # noqa: F401
from app.models.base import Base

sync_engine = create_engine(
    "postgresql+psycopg2://user:pass@localhost:5432/screenshot_test"
)

Base.metadata.drop_all(sync_engine)
Base.metadata.create_all(sync_engine)

with Session(sync_engine) as session:
    session.add(Settings(id=1, ...))
    session.commit()

sync_engine.dispose()
```

**Use PostgreSQL, not SQLite.** The app's async engine uses asyncpg, which binds connections to the event loop that created them. Seeding with async SQLAlchemy in the main process and then running uvicorn in a subprocess (or thread) causes `RuntimeError: Task got Future attached to a different loop`. Sync psycopg2 for seeding avoids this entirely.

## Starting the Server

Run uvicorn as a subprocess so it gets its own event loop. The `DATABASE_URL` environment variable is inherited.

```python
import subprocess
import sys
import time
import urllib.request

server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app",
     "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "error"],
    env=os.environ.copy(),
)

# Wait for server
for i in range(20):
    time.sleep(0.5)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/settings", timeout=2)
        break
    except Exception:
        pass
```

## Taking Screenshots

```python
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
    "team": "http://127.0.0.1:8769/",
    "settings": "http://127.0.0.1:8769/settings",
}

for name, url in urls.items():
    driver.get(url)
    time.sleep(1)
    total_height = driver.execute_script("return document.body.scrollHeight")
    driver.set_window_size(1440, max(900, total_height + 200))
    time.sleep(0.5)
    driver.save_screenshot(f"/tmp/{name}.png")

driver.quit()
```

Key Selenium options:

| Flag | Purpose |
|------|---------|
| `--headless=new` | Run without a display server |
| `--no-sandbox` | Required when running as root or in containers |
| `--disable-dev-shm-usage` | Prevents `/dev/shm` memory issues in Docker |
| `--window-size=1440,900` | Set initial viewport; resized per page for full-height capture |

## Rebuilding Tailwind CSS

Templates use a pre-built Tailwind CSS file (`app/static/css/tailwind.css`) instead of the CDN. After changing Tailwind classes in templates, rebuild:

```bash
npx @tailwindcss/cli -i app/static/css/input.css -o app/static/css/tailwind.css --minify
```

## Reviewing Screenshots

Open the PNG files directly or use any image viewer. In CI, screenshots can be archived as build artifacts for manual review or fed into a visual diff tool.
