"""E2E test: Rebuild Chains → Score → verify ChainScore records in the database.

Seeds the database with emails that form a reply chain, starts the server,
uses Selenium to click "Rebuild Chains" then "Score" on /settings, polls
for job completion, and queries the database to verify ChainScore rows exist.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

# Environment must be set BEFORE any app imports
E2E_PORT = 8769
DB_URL_SYNC = "postgresql+psycopg2://test:test@localhost:5432/email_reviewer_e2e"
DB_URL_ASYNC = "postgresql+asyncpg://test:test@localhost:5432/email_reviewer_e2e"

os.environ["AUTH_ENABLED"] = "FALSE"
os.environ["CURRENT_USER"] = "test"
os.environ["DATABASE_URL"] = DB_URL_ASYNC
os.environ["REDIS_URL"] = ""

from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import ChainScore, Email, EmailChain, Job, Rep, Score, Settings  # noqa: F401
from app.models.base import Base
from scripts.seeds.settings import SETTINGS_SEED


def seed_database():
    """Seed the E2E database with chainable emails and a typed rep."""
    engine = create_engine(DB_URL_SYNC)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Settings
        session.add(Settings(id=1, **SETTINGS_SEED))

        # Rep with type so scorer doesn't skip
        session.add(Rep(
            email="rep@example.com",
            display_name="Alice Rep",
            rep_type="SDR",
        ))

        # Outgoing email (long enough body to pass MIN_WORD_COUNT=20)
        session.add(Email(
            from_email="rep@example.com",
            to_email="prospect@example.com",
            subject="Quick question about your Q2 plans",
            body_text=(
                "Hi there, I wanted to reach out because I noticed your company "
                "recently expanded into the European market and I think our platform "
                "could help streamline your sales operations significantly. Would you "
                "be open to a quick fifteen minute call this week to discuss how we "
                "have helped similar companies achieve a thirty percent improvement "
                "in outbound response rates?"
            ),
            direction="EMAIL",
            message_id="<msg-001@example.com>",
            timestamp=datetime(2026, 3, 1, 10, 0, 0),
        ))

        # Reply from prospect (creates the chain via in_reply_to)
        session.add(Email(
            from_email="prospect@example.com",
            to_email="rep@example.com",
            subject="Re: Quick question about your Q2 plans",
            body_text="Thanks for reaching out, that sounds interesting. Tell me more about the integration options.",
            direction="RECEIVED",
            message_id="<msg-002@example.com>",
            in_reply_to="<msg-001@example.com>",
            timestamp=datetime(2026, 3, 2, 14, 0, 0),
        ))

        session.commit()

    engine.dispose()
    print("Database seeded.")


def start_server():
    """Start uvicorn as a subprocess."""
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(E2E_PORT), "--log-level", "error"],
        env=os.environ.copy(),
    )
    # Wait for server to be ready
    for _ in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{E2E_PORT}/health", timeout=2)
            print(f"Server ready on port {E2E_PORT}")
            return server
        except Exception:
            pass
    raise RuntimeError("Server did not start within 15 seconds")


def wait_for_job(job_type, timeout=120):
    """Poll the jobs list API until a job of the given type is COMPLETED or FAILED."""
    print(f"  Waiting for {job_type} job...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{E2E_PORT}/api/operations/jobs", timeout=5
            )
            jobs = json.loads(resp.read())
            # Find the most recent job matching this type (list is newest-first)
            for job in jobs:
                if job.get("job_type") == job_type:
                    status = job.get("status", "")
                    if status == "COMPLETED":
                        summary = job.get("result_summary", {})
                        print(f"  {job_type} COMPLETED: {summary}")
                        return summary
                    if status == "FAILED":
                        err = job.get("error_message", "")
                        raise RuntimeError(f"{job_type} FAILED: {err}")
                    print(f"  {job_type} status: {status}")
                    break
        except urllib.error.URLError:
            pass
        time.sleep(2)
    raise RuntimeError(f"{job_type} did not complete within {timeout}s")


def verify_chain_scores():
    """Query the database directly to verify ChainScore records exist."""
    engine = create_engine(DB_URL_SYNC)
    with Session(engine) as session:
        chains = session.execute(text("SELECT * FROM email_chains")).fetchall()
        chain_scores = session.execute(text("SELECT * FROM chain_scores")).fetchall()
        emails_with_chains = session.execute(
            text("SELECT id, chain_id, position_in_chain FROM emails WHERE chain_id IS NOT NULL")
        ).fetchall()

    engine.dispose()
    return chains, chain_scores, emails_with_chains


# ---- Main test flow ----

seed_database()
server = start_server()

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1440,900")
chrome_options.binary_location = "/usr/bin/google-chrome-stable"

driver = webdriver.Chrome(options=chrome_options)

try:
    # ============================
    # STEP 1: Navigate to /settings
    # ============================
    print("\nSTEP 1: Open settings page")
    driver.get(f"http://127.0.0.1:{E2E_PORT}/settings?tab=general")
    time.sleep(2)

    # Screenshot before anything
    driver.save_screenshot("/tmp/e2e_01_settings_initial.png")
    print("  Screenshot: /tmp/e2e_01_settings_initial.png")

    # ============================
    # STEP 2: Click "Rebuild Chains"
    # ============================
    print("\nSTEP 2: Click Rebuild Chains button")
    rebuild_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Rebuild Chains')]")
    rebuild_btn.click()
    print("  Clicked Rebuild Chains")
    time.sleep(1)
    driver.save_screenshot("/tmp/e2e_02_after_rebuild_click.png")

    # Wait for chain-build job to complete
    chain_summary = wait_for_job("Chain_Build", timeout=30)
    assert chain_summary["chains_created"] >= 1, (
        f"Expected at least 1 chain created, got {chain_summary}"
    )
    print(f"  Chains created: {chain_summary['chains_created']}")

    # Refresh to see updated UI
    driver.get(f"http://127.0.0.1:{E2E_PORT}/settings?tab=general")
    time.sleep(2)
    driver.save_screenshot("/tmp/e2e_03_after_rebuild_complete.png")

    # Verify chains exist in DB but NO chain scores yet
    chains, chain_scores, linked_emails = verify_chain_scores()
    assert len(chains) >= 1, f"Expected chains in DB, found {len(chains)}"
    assert len(chain_scores) == 0, f"Expected 0 chain scores before scoring, found {len(chain_scores)}"
    assert len(linked_emails) >= 2, f"Expected emails linked to chain, found {len(linked_emails)}"
    print(f"  DB check: {len(chains)} chain(s), {len(chain_scores)} chain_scores, {len(linked_emails)} linked emails")

    # ============================
    # STEP 3: Click "Score"
    # ============================
    print("\nSTEP 3: Click Score button")
    score_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Score')]")
    score_btn.click()
    print("  Clicked Score")
    time.sleep(1)
    driver.save_screenshot("/tmp/e2e_04_after_score_click.png")

    # Wait for score job to complete
    score_summary = wait_for_job("SCORE", timeout=120)
    print(f"  Score summary: {score_summary}")

    # Refresh and screenshot
    driver.get(f"http://127.0.0.1:{E2E_PORT}/settings?tab=general")
    time.sleep(2)
    driver.save_screenshot("/tmp/e2e_05_after_score_complete.png")

    # ============================
    # STEP 4: Verify ChainScore in DB
    # ============================
    print("\nSTEP 4: Verify chain scores in database")
    chains, chain_scores, linked_emails = verify_chain_scores()

    assert len(chain_scores) >= 1, (
        f"FAIL: Expected at least 1 ChainScore after scoring, found {len(chain_scores)}"
    )

    # Print chain score details
    engine = create_engine(DB_URL_SYNC)
    with Session(engine) as session:
        rows = session.execute(text(
            "SELECT cs.chain_id, cs.progression, cs.responsiveness, "
            "cs.persistence, cs.conversation_quality, cs.notes, cs.score_error "
            "FROM chain_scores cs"
        )).fetchall()
    engine.dispose()

    for row in rows:
        print(f"  ChainScore(chain_id={row[0]}, progression={row[1]}, "
              f"responsiveness={row[2]}, persistence={row[3]}, "
              f"conversation_quality={row[4]}, notes={row[5]!r}, "
              f"score_error={row[6]})")
        assert not row[6], f"Chain score has score_error=True for chain_id={row[0]}"
        assert row[1] is not None, f"progression is None for chain_id={row[0]}"
        assert row[2] is not None, f"responsiveness is None for chain_id={row[0]}"
        assert row[3] is not None, f"persistence is None for chain_id={row[0]}"
        assert row[4] is not None, f"conversation_quality is None for chain_id={row[0]}"

    # Also check that chains_scored appeared in the job summary
    assert score_summary.get("chains_scored", 0) >= 1, (
        f"FAIL: Job summary missing chains_scored. Got: {score_summary}"
    )

    print(f"\n=== E2E TEST PASSED ===")
    print(f"  Chains created: {chain_summary['chains_created']}")
    print(f"  Chains scored:  {score_summary.get('chains_scored', 0)}")
    print(f"  Chain errors:   {score_summary.get('chain_errors', 0)}")
    print(f"  Emails scored:  {score_summary.get('scored', 0)}")
    print(f"Screenshots in /tmp/e2e_*.png")

finally:
    driver.quit()
    server.terminate()
    server.wait(timeout=5)
    print("Server stopped.")
