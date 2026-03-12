"""Visual test for sidebar score display and scroll behavior.

Tests:
1. Email score tiles display in a horizontal row (5 tiles)
2. Conversation scores show chain-level scores + inline badges per email
3. Sidebar scrolls independently without page-level scroll
"""

import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

DB_URL = "postgresql+psycopg2://screenshot_user:screenshot_pass@localhost:5432/screenshot_test"
PORT = 8770
BASE = f"http://127.0.0.1:{PORT}"
OUT = "/tmp/sidebar_test"

os.environ["AUTH_ENABLED"] = "FALSE"
os.environ["CURRENT_USER"] = "test"
os.environ["DATABASE_URL"] = DB_URL

from app.models import ChainScore, Email, EmailChain, Rep, Score, Settings  # noqa: E402
from app.models.base import Base  # noqa: E402
from scripts.seeds.settings import SETTINGS_SEED  # noqa: E402


def seed():
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Settings(
            id=1,
            global_start_date=date(2025, 9, 1),
            company_domains="native.fm",
            scoring_batch_size=5,
            auto_score_after_fetch=True,
            initial_email_prompt_blocks=SETTINGS_SEED["initial_email_prompt_blocks"].copy(),
            chain_email_prompt_blocks=SETTINGS_SEED["chain_email_prompt_blocks"].copy(),
            chain_evaluation_prompt_blocks=SETTINGS_SEED["chain_evaluation_prompt_blocks"].copy(),
            classifier_prompt_blocks=SETTINGS_SEED.get("classifier_prompt_blocks", {}).copy() if SETTINGS_SEED.get("classifier_prompt_blocks") else {"opening": "", "email_type": "", "quoted_emails": "", "closing": ""},
            follow_up_email_prompt_blocks=SETTINGS_SEED.get("follow_up_email_prompt_blocks", {}).copy() if SETTINGS_SEED.get("follow_up_email_prompt_blocks") else {"opening": "", "value_proposition": "", "personalisation": "", "cta": "", "clarity": "", "closing": ""},
        ))

        rep_email = "mark@native.fm"
        prospect = "akvile@prospect.com"

        s.add(Rep(email=rep_email, display_name="Mark Hodge", rep_type="SDR"))
        s.flush()

        # Standalone email with scores
        e1 = Email(
            from_email=rep_email, to_email="tom@deliveroo.com",
            from_name="Jess Weller", to_name="Tom Richards",
            subject="Student Dining Habits - Exclusive Research",
            body_text="Hi Tom,\n\nI noticed Deliveroo recently expanded your student discount programme - congrats on that. We've been tracking student dining and delivery habits across our 53 campus partnerships and the data is pretty striking.\n\n68% of students in our network order delivery at least once a week, with spend peaking on Sunday and Wednesday evenings.\n\nWould you be open to a 15-minute call next week to walk through the numbers?",
            direction="EMAIL", hubspot_id="sidebar-1",
            timestamp=datetime(2026, 3, 7, 10, 30),
        )
        s.add(e1)
        s.flush()
        s.add(Score(email_id=e1.id, personalisation=9, clarity=8, value_proposition=8, cta=7, overall=8,
                     notes="Strong personalisation tying Deliveroo's student discount programme to Native's audience data. Specific data point (68% weekly ordering) is compelling. CTA is clear and time-bound."))

        # Multiple standalone emails for scroll testing
        for i in range(10):
            ei = Email(
                from_email=rep_email, to_email=f"contact{i}@example.com",
                from_name="Mark Hodge", to_name=f"Contact {i}",
                subject=f"Campus partnership opportunity #{i+1}",
                body_text=f"Hi Contact {i},\n\nLet's discuss campus advertising for 2026.",
                direction="EMAIL", hubspot_id=f"scroll-{i}",
                timestamp=datetime(2026, 3, 1 + i % 7, 9 + i, 0),
            )
            s.add(ei)
            s.flush()
            s.add(Score(email_id=ei.id, personalisation=5+i%4, clarity=6+i%3, value_proposition=5+i%5, cta=4+i%4,
                         overall=5+i%4, notes=f"Score notes for email {i+1}."))

        # Conversation with chain scores and individual email scores
        chain = EmailChain(
            normalized_subject="Current Native Exclusive Partners List",
            participants=f"{rep_email},{prospect}",
            started_at=datetime(2026, 3, 2, 9, 15),
            last_activity_at=datetime(2026, 3, 7, 14, 22),
            email_count=3, outgoing_count=2, incoming_count=1,
            is_unanswered=True,
        )
        s.add(chain)
        s.flush()

        ec1 = Email(from_email=rep_email, to_email=prospect,
                     from_name="Mark Hodge", to_name="Akvile Rimkute",
                     subject="Current Native Exclusive Partners List",
                     body_text="Hi Akvile & Chris,\n\nHope you both had a great weekend. Thank you once again for taking the time to talk on Friday, it was great to meet you both.",
                     direction="EMAIL", hubspot_id="chain-s1",
                     timestamp=datetime(2026, 3, 2, 9, 15),
                     chain_id=chain.id, position_in_chain=1)
        s.add(ec1)
        s.flush()
        s.add(Score(email_id=ec1.id, personalisation=8, clarity=7, value_proposition=6, cta=7, overall=7,
                     notes="Good follow-up referencing Friday call with specific contract details (91/112 spaces). Value proposition could be stronger."))

        ec2 = Email(from_email=prospect, to_email=rep_email,
                     from_name="Akvile Rimkute", to_name="Mark Hodge",
                     subject="Re: Current Native Exclusive Partners List",
                     body_text="Hi Mark,\n\nThanks for sending this over. The 91/112 figure looks about right, though Chris may want to double-check.\n\nWe're pulling together our campus priorities for 26/27 and will be in touch.",
                     direction="INCOMING_EMAIL", hubspot_id="chain-s2",
                     timestamp=datetime(2026, 3, 5, 11, 40),
                     chain_id=chain.id, position_in_chain=2)
        s.add(ec2)

        ec3 = Email(from_email=rep_email, to_email=prospect,
                     from_name="Mark Hodge", to_name="Akvile Rimkute",
                     subject="Re: Current Native Exclusive Partners List",
                     body_text="Hi Akvile,\n\nGreat questions. To answer both:\n\n1. We have 3 new SUs joining this term.\n2. Timeline for the campus refresh is mid-April.",
                     direction="EMAIL", hubspot_id="chain-s3",
                     timestamp=datetime(2026, 3, 7, 14, 22),
                     chain_id=chain.id, position_in_chain=3)
        s.add(ec3)
        s.flush()
        s.add(Score(email_id=ec3.id, personalisation=7, clarity=9, value_proposition=7, cta=8, overall=8,
                     notes="Strong response addressing both questions directly. Good use of specifics (3 new SUs named). Clear next step with timeline."))

        s.add(ChainScore(
            chain_id=chain.id,
            progression=7, responsiveness=8, persistence=6, conversation_quality=7,
            avg_response_hours=2.5,
            notes="Good progression with responsive follow-ups.",
        ))

        s.commit()
        chain_id = chain.id

    engine.dispose()
    print("Database seeded.")
    return chain_id


def start_server():
    env = os.environ.copy()
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "error"],
        env=env,
    )
    for _ in range(20):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"{BASE}/settings", timeout=2)
            print("Server ready.")
            return server
        except Exception:
            pass
    print("Server failed to start.")
    server.kill()
    sys.exit(1)


def screenshot(driver, name, full_page=True):
    time.sleep(0.8)
    if full_page:
        total_height = driver.execute_script("return document.body.scrollHeight")
        driver.set_window_size(1440, max(900, total_height + 200))
        time.sleep(0.3)
    path = f"{OUT}/{name}.png"
    driver.save_screenshot(path)
    print(f"  [{name}] saved")
    if full_page:
        driver.set_window_size(1440, 900)
    return path


def run_tests(driver, chain_id):
    from selenium.webdriver.common.by import By

    issues = []

    # ===== 1. FEED PAGE - CLICK STANDALONE EMAIL =====
    print("\n=== Feed: Standalone Email Sidebar ===")
    driver.get(f"{BASE}/feed")
    time.sleep(1)
    # Keep viewport at 1440x900 (desktop) so sidebar is visible
    driver.set_window_size(1440, 900)
    time.sleep(0.5)

    # Click first standalone email
    email_items = driver.find_elements(By.CSS_SELECTOR, ".feed-item[data-type='email']")
    if not email_items:
        issues.append("Feed: no standalone email items found")
        return issues

    email_items[0].click()
    time.sleep(1)
    screenshot(driver, "01_email_sidebar", full_page=False)

    # Verify score tiles are displayed as horizontal row
    tiles = driver.find_elements(By.CSS_SELECTOR, "#detail-score-tiles .score-tile")
    print(f"  Score tiles count: {len(tiles)}")
    if len(tiles) != 5:
        issues.append(f"Email sidebar: expected 5 score tiles, got {len(tiles)}")

    # Verify tiles are in a horizontal line (all same Y position)
    if len(tiles) >= 2:
        tile_tops = [t.location['y'] for t in tiles]
        if max(tile_tops) - min(tile_tops) > 5:
            issues.append(f"Email sidebar: tiles not in horizontal row, Y positions: {tile_tops}")
        else:
            print("  Tiles layout: horizontal row (correct)")

    # Check tile labels
    labels = [t.find_element(By.CSS_SELECTOR, ".score-tile-label").text for t in tiles]
    print(f"  Tile labels: {labels}")
    expected_labels = ["OVERALL", "PERS.", "CLARITY", "VALUE", "CTA"]
    for exp in expected_labels:
        if exp not in labels:
            issues.append(f"Email sidebar: missing tile label '{exp}', got {labels}")

    # Check score values have correct color classes
    values = driver.find_elements(By.CSS_SELECTOR, "#detail-score-tiles .score-tile-value")
    colored_values = [v for v in values if 'score-high' in v.get_attribute('class') or 'score-mid' in v.get_attribute('class') or 'score-low' in v.get_attribute('class')]
    print(f"  Colored score values: {len(colored_values)}/{len(values)}")
    if not colored_values:
        issues.append("Email sidebar: no colored score values found")

    # Check AI notes section visible
    notes_section = driver.find_element(By.ID, "detail-notes-section")
    notes_visible = notes_section.is_displayed()
    print(f"  AI notes visible: {notes_visible}")

    # ===== 2. FEED PAGE - CLICK CONVERSATION =====
    print("\n=== Feed: Conversation Sidebar ===")
    driver.get(f"{BASE}/feed")
    time.sleep(1)
    driver.set_window_size(1440, 900)
    time.sleep(0.5)

    conv_items = driver.find_elements(By.CSS_SELECTOR, ".feed-item[data-type='conversation']")
    if not conv_items:
        issues.append("Feed: no conversation items found")
        return issues

    conv_items[0].click()
    time.sleep(2)  # Wait for thread to load via API
    screenshot(driver, "02_conversation_sidebar", full_page=False)

    # Verify conversation score tiles appear (chain-level scores)
    conv_tiles = driver.find_elements(By.CSS_SELECTOR, "#detail-score-tiles .score-tile")
    print(f"  Conversation score tiles: {len(conv_tiles)}")
    if len(conv_tiles) != 4:
        issues.append(f"Conversation sidebar: expected 4 chain score tiles, got {len(conv_tiles)}")

    # Check conversation tile labels
    if conv_tiles:
        conv_labels = [t.find_element(By.CSS_SELECTOR, ".score-tile-label").text for t in conv_tiles]
        print(f"  Conversation tile labels: {conv_labels}")
        for exp in ["QUALITY", "PROGRESS", "RESPONSE", "PERSIST"]:
            if exp not in conv_labels:
                issues.append(f"Conversation sidebar: missing label '{exp}', got {conv_labels}")

    # Check thread emails are shown
    thread_emails = driver.find_elements(By.CSS_SELECTOR, "#detail-thread-container .thread-email")
    print(f"  Thread emails: {len(thread_emails)}")
    if len(thread_emails) != 3:
        issues.append(f"Conversation sidebar: expected 3 thread emails, got {len(thread_emails)}")

    # Check score badges on outgoing emails
    score_badges = driver.find_elements(By.CSS_SELECTOR, "#detail-thread-container .score-badge-pill")
    print(f"  Score badge pills: {len(score_badges)}")
    if len(score_badges) < 4:
        issues.append(f"Conversation sidebar: expected at least 4 score badges (P,CI,VP,CTA for first outgoing), got {len(score_badges)}")

    # Check badge content (should have P, CI, VP, CTA labels)
    badge_labels_found = set()
    for badge in score_badges:
        label_el = badge.find_elements(By.CSS_SELECTOR, ".badge-label")
        if label_el:
            badge_labels_found.add(label_el[0].text)
    print(f"  Badge labels found: {badge_labels_found}")
    for exp in ["P", "CI", "VP", "CTA"]:
        if exp not in badge_labels_found:
            issues.append(f"Conversation sidebar: missing badge label '{exp}'")

    # Check badges have correct color classes
    high_badges = driver.find_elements(By.CSS_SELECTOR, "#detail-thread-container .score-badge-pill.badge-high")
    mid_badges = driver.find_elements(By.CSS_SELECTOR, "#detail-thread-container .score-badge-pill.badge-mid")
    low_badges = driver.find_elements(By.CSS_SELECTOR, "#detail-thread-container .score-badge-pill.badge-low")
    print(f"  Badge colors: high={len(high_badges)} mid={len(mid_badges)} low={len(low_badges)}")

    # ===== 3. SCROLL BEHAVIOR =====
    print("\n=== Scroll Behavior ===")
    driver.get(f"{BASE}/feed")
    time.sleep(1)
    driver.set_window_size(1440, 900)
    time.sleep(0.5)

    # Check that body doesn't scroll (no page-level scrollbar)
    body_scroll = driver.execute_script("return document.body.scrollHeight")
    viewport_height = driver.execute_script("return window.innerHeight")
    print(f"  Body scroll height: {body_scroll}")
    print(f"  Viewport height: {viewport_height}")

    # The body scroll height should be close to viewport height (no significant overflow)
    overflow = body_scroll - viewport_height
    print(f"  Body overflow: {overflow}px")
    if overflow > 20:
        issues.append(f"Scroll: page-level overflow detected ({overflow}px). Feed columns should scroll independently.")

    # Check that feed-list-col is scrollable
    list_col = driver.find_element(By.CSS_SELECTOR, ".feed-list-col")
    list_col_scroll = driver.execute_script("return arguments[0].scrollHeight", list_col)
    list_col_height = driver.execute_script("return arguments[0].clientHeight", list_col)
    print(f"  Feed list col: scrollHeight={list_col_scroll}, clientHeight={list_col_height}")
    if list_col_scroll > list_col_height + 10:
        print("  Feed list column is scrollable: correct")
    else:
        print("  Feed list column fits (not enough items to scroll)")

    # Click an email and check sidebar has scroll capability
    email_items = driver.find_elements(By.CSS_SELECTOR, ".feed-item[data-type='email']")
    if email_items:
        email_items[0].click()
        time.sleep(1)

        detail_content = driver.find_element(By.ID, "detail-content")
        detail_scroll = driver.execute_script("return arguments[0].scrollHeight", detail_content)
        detail_height = driver.execute_script("return arguments[0].clientHeight", detail_content)
        print(f"  Detail panel content: scrollHeight={detail_scroll}, clientHeight={detail_height}")

    # ===== 4. VERIFY SIDEBAR POSITION RELATIVE TO NAV =====
    print("\n=== Sidebar Position ===")
    detail_panel = driver.find_element(By.ID, "feed-detail-panel")
    panel_top = driver.execute_script("return arguments[0].getBoundingClientRect().top", detail_panel)
    nav_bottom = driver.execute_script("return document.querySelector('nav').getBoundingClientRect().bottom")
    print(f"  Nav bottom: {nav_bottom}px, Panel top: {panel_top}px")

    # Panel top should be reasonably close to where main content starts
    if panel_top < nav_bottom:
        issues.append(f"Sidebar overlaps nav: panel top={panel_top}, nav bottom={nav_bottom}")

    # ===== 5. CHECK BOTH EMAIL AND CONVERSATION IN SEQUENCE =====
    print("\n=== Switching between email and conversation ===")
    driver.get(f"{BASE}/feed")
    time.sleep(1)
    driver.set_window_size(1440, 900)
    time.sleep(0.5)

    # Click email first
    email_items = driver.find_elements(By.CSS_SELECTOR, ".feed-item[data-type='email']")
    conv_items = driver.find_elements(By.CSS_SELECTOR, ".feed-item[data-type='conversation']")

    if email_items:
        email_items[0].click()
        time.sleep(1)
        tiles_after_email = driver.find_elements(By.CSS_SELECTOR, "#detail-score-tiles .score-tile")
        print(f"  After email click - tiles: {len(tiles_after_email)}")
        if len(tiles_after_email) != 5:
            issues.append(f"After email click: expected 5 tiles, got {len(tiles_after_email)}")

    if conv_items:
        conv_items[0].click()
        time.sleep(2)
        tiles_after_conv = driver.find_elements(By.CSS_SELECTOR, "#detail-score-tiles .score-tile")
        print(f"  After conversation click - tiles: {len(tiles_after_conv)}")
        if len(tiles_after_conv) != 4:
            issues.append(f"After conversation click: expected 4 tiles, got {len(tiles_after_conv)}")

        # Switch back to email
        if email_items:
            email_items[0].click()
            time.sleep(1)
            tiles_back = driver.find_elements(By.CSS_SELECTOR, "#detail-score-tiles .score-tile")
            print(f"  After switching back to email - tiles: {len(tiles_back)}")
            if len(tiles_back) != 5:
                issues.append(f"After switching back to email: expected 5 tiles, got {len(tiles_back)}")

    screenshot(driver, "03_final_state", full_page=False)

    # ===== SUMMARY =====
    print("\n" + "=" * 60)
    if issues:
        print(f"ISSUES FOUND: {len(issues)}")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("ALL SIDEBAR CHECKS PASSED")
    print("=" * 60)

    return issues


def main():
    os.makedirs(OUT, exist_ok=True)

    chain_id = seed()
    server = start_server()

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1440,900")
    chrome_options.binary_location = "/usr/bin/chromium-browser"

    driver = webdriver.Chrome(options=chrome_options)

    try:
        issues = run_tests(driver, chain_id)
    finally:
        driver.quit()
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=5)

    if issues:
        print(f"\nFAILED with {len(issues)} issues")
        sys.exit(1)
    else:
        print("\nPASSED - all sidebar visual checks OK")


if __name__ == "__main__":
    main()
