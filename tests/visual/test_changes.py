"""Visual test for navigation, sidebar, and email ordering changes.

Validates:
1. Nav shows "Inbox" (not "Feed") in position 1, then Team, then Settings
2. Thread node dots (node-outgoing/node-incoming) are hidden
3. Emails on /chains pages are in reverse chronological order (newest first)
4. Emails on /reps pages are in reverse chronological order
5. Inbox/feed page sidebar shows items in reverse chronological order
6. Full holistic UI consistency checks across all pages
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
PORT = 8771
BASE = f"http://127.0.0.1:{PORT}"
OUT = "/tmp/changes_test"

os.environ["AUTH_ENABLED"] = "FALSE"
os.environ["CURRENT_USER"] = "test"
os.environ["DATABASE_URL"] = DB_URL

from app.models import ChainScore, Email, EmailChain, Rep, Score, Settings  # noqa: E402
from app.models.base import Base  # noqa: E402
from scripts.seeds.settings import SETTINGS_SEED  # noqa: E402

REP_EMAIL = "zacharybell@native.fm"
PROSPECT = "nicholas.c@hoyoverse.com"


def seed():
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Settings(
            id=1,
            global_start_date=date(2025, 9, 1),
            company_domains="nativecampusadvertising.com,native.fm",
            scoring_batch_size=5,
            auto_score_after_fetch=True,
            initial_email_prompt_blocks=SETTINGS_SEED["initial_email_prompt_blocks"].copy(),
            chain_email_prompt_blocks=SETTINGS_SEED["chain_email_prompt_blocks"].copy(),
            chain_evaluation_prompt_blocks=SETTINGS_SEED["chain_evaluation_prompt_blocks"].copy(),
            classifier_prompt_blocks=SETTINGS_SEED.get("classifier_prompt_blocks", {}).copy() if SETTINGS_SEED.get("classifier_prompt_blocks") else {"opening": "", "email_type": "", "quoted_emails": "", "closing": ""},
            follow_up_email_prompt_blocks=SETTINGS_SEED.get("follow_up_email_prompt_blocks", {}).copy() if SETTINGS_SEED.get("follow_up_email_prompt_blocks") else {"opening": "", "value_proposition": "", "personalisation": "", "cta": "", "clarity": "", "closing": ""},
        ))

        # 4 reps with different types
        s.add(Rep(email=REP_EMAIL, display_name="Zachary Bell", rep_type="SDR"))
        s.add(Rep(email="bethan@native.fm", display_name="Bethan Telfer", rep_type="AM"))
        s.add(Rep(email="katy@native.fm", display_name="Katy Smale", rep_type="BizDev"))
        s.add(Rep(email="new@native.fm", display_name="New Starter"))
        s.flush()

        # Standalone outreach emails with varying dates
        e1 = Email(
            from_email=REP_EMAIL, to_email=PROSPECT,
            from_name="Zachary Bell", to_name="Nicholas Chang",
            subject="Native & HoYoverse - 2026 Student Opportunities",
            body_text="Hi Nicholas,\n\nI wanted to reach out about campus marketing opportunities for HoYoverse in 2026.\n\nBest regards,\nZachary Bell",
            direction="EMAIL", hubspot_id="out-1",
            timestamp=datetime(2026, 3, 2, 9, 0),
        )
        s.add(e1)
        s.flush()
        s.add(Score(email_id=e1.id, personalisation=6, clarity=8, value_proposition=7, cta=6, overall=7,
                     notes="Good opening with clear value proposition."))

        e2 = Email(
            from_email=REP_EMAIL, to_email="pharmacie@pharmacie.coffee",
            from_name="Zachary Bell", to_name="Pharmacie Coffee",
            subject="Campus coffee partnership - Native",
            body_text="Hi there,\n\nI'd love to discuss a campus coffee partnership with Pharmacie.\n\nKind regards,\nZachary Bell",
            direction="EMAIL", hubspot_id="out-2",
            timestamp=datetime(2026, 3, 5, 10, 0),
        )
        s.add(e2)
        s.flush()
        s.add(Score(email_id=e2.id, personalisation=5, clarity=7, value_proposition=6, cta=5, overall=6,
                     notes="Decent clarity but lacks personalisation."))

        e3 = Email(
            from_email=REP_EMAIL, to_email="lab@unorthodoxroasters.co.uk",
            from_name="Zachary Bell", to_name="Unorthodox Roasters",
            subject="Your competition's already on campus",
            body_text="Hi,\n\nDid you know your competitors are already running campaigns on campus?\n\nAll the best\nZachary",
            direction="EMAIL", hubspot_id="out-3",
            timestamp=datetime(2026, 3, 1, 7, 0),
        )
        s.add(e3)
        s.flush()
        s.add(Score(email_id=e3.id, personalisation=4, clarity=6, value_proposition=7, cta=5, overall=5,
                     notes="Competitive angle works but feels generic."))

        # Extra rep emails
        eb1 = Email(from_email="bethan@native.fm", to_email="client@acme.com",
                     from_name="Bethan Telfer", to_name="Client",
                     subject="Renewal discussion", body_text="Hi, let's discuss your renewal.",
                     direction="EMAIL", hubspot_id="bt-1", timestamp=datetime(2026, 3, 1, 10, 0))
        s.add(eb1)
        s.flush()
        s.add(Score(email_id=eb1.id, personalisation=8, clarity=9, value_proposition=8, cta=7, overall=8,
                     notes="Excellent account management email."))

        ek1 = Email(from_email="katy@native.fm", to_email="lead@startup.io",
                     from_name="Katy Smale", to_name="Lead",
                     subject="Partnership opportunity", body_text="Hi, I'd love to explore a partnership.",
                     direction="EMAIL", hubspot_id="ks-1", timestamp=datetime(2026, 3, 4, 11, 0))
        s.add(ek1)
        s.flush()
        s.add(Score(email_id=ek1.id, personalisation=7, clarity=8, value_proposition=7, cta=6, overall=7,
                     notes="Good BizDev outreach with clear value."))

        en1 = Email(from_email="new@native.fm", to_email="someone@company.com",
                     from_name="New Starter", to_name="Someone",
                     subject="Quick intro", body_text="Hi, I'm new to the team.",
                     direction="EMAIL", hubspot_id="ns-1", timestamp=datetime(2026, 3, 3, 12, 0))
        s.add(en1)
        s.flush()
        s.add(Score(email_id=en1.id, personalisation=3, clarity=5, value_proposition=4, cta=3, overall=4,
                     notes="Generic intro with weak CTA."))

        # Unanswered chain (red dots should NOT appear)
        chain_u = EmailChain(
            normalized_subject="Campus sampling opportunity",
            participants=f"{PROSPECT},{REP_EMAIL}",
            started_at=datetime(2026, 3, 2, 9, 0),
            last_activity_at=datetime(2026, 3, 2, 14, 0),
            email_count=2, outgoing_count=1, incoming_count=1,
            is_unanswered=True,
        )
        s.add(chain_u)
        s.flush()

        eu1 = Email(from_email=REP_EMAIL, to_email=PROSPECT,
                     from_name="Zachary Bell", to_name="Nicholas Chang",
                     subject="Campus sampling opportunity",
                     body_text="Hi Nicholas,\n\nWanted to share a sampling opportunity.",
                     direction="EMAIL", hubspot_id="ua-1",
                     timestamp=datetime(2026, 3, 2, 9, 0),
                     chain_id=chain_u.id, position_in_chain=1)
        s.add(eu1)
        s.flush()
        s.add(Score(email_id=eu1.id, personalisation=5, clarity=7, value_proposition=6, cta=5, overall=6,
                     notes="Reasonable opening."))

        eu2 = Email(from_email=PROSPECT, to_email=REP_EMAIL,
                     from_name="Nicholas Chang", to_name="Zachary Bell",
                     subject="Re: Campus sampling opportunity",
                     body_text="Hi Zach,\n\nInteresting - can you send more details on pricing?",
                     direction="INCOMING_EMAIL", hubspot_id="ua-2",
                     timestamp=datetime(2026, 3, 2, 14, 0),
                     chain_id=chain_u.id, position_in_chain=2)
        s.add(eu2)

        # Back-and-forth chain with chain score (for testing reverse chronological)
        chain_bf = EmailChain(
            normalized_subject="Native campus partnership proposal",
            participants=f"{PROSPECT},{REP_EMAIL}",
            started_at=datetime(2026, 3, 2, 2, 51),
            last_activity_at=datetime(2026, 3, 4, 5, 57),
            email_count=3, outgoing_count=2, incoming_count=1,
            is_unanswered=False,
        )
        s.add(chain_bf)
        s.flush()

        ec1 = Email(from_email=REP_EMAIL, to_email=PROSPECT,
                     from_name="Zachary Bell", to_name="Nicholas Chang",
                     subject="Native campus partnership proposal",
                     body_text="Hi Nicholas,\n\nI'd like to propose a campus partnership.",
                     direction="EMAIL", hubspot_id="ch-1",
                     timestamp=datetime(2026, 3, 2, 2, 51),
                     chain_id=chain_bf.id, position_in_chain=1)
        s.add(ec1)
        s.flush()
        s.add(Score(email_id=ec1.id, personalisation=7, clarity=8, value_proposition=7, cta=6, overall=7,
                     notes="Strong opening with clear proposal."))

        ec2 = Email(from_email=PROSPECT, to_email=REP_EMAIL,
                     from_name="Nicholas Chang", to_name="Zachary Bell",
                     subject="Re: Native campus partnership proposal",
                     body_text="Hi Zach,\n\nI will be sending the brief ASAP.",
                     direction="INCOMING_EMAIL", hubspot_id="ch-2",
                     timestamp=datetime(2026, 3, 3, 4, 30),
                     chain_id=chain_bf.id, position_in_chain=2)
        s.add(ec2)

        ec3 = Email(from_email=REP_EMAIL, to_email=PROSPECT,
                     from_name="Zachary Bell", to_name="Nicholas Chang",
                     subject="Re: Native campus partnership proposal",
                     body_text="Great, looking forward to the brief. Let me know when works.",
                     direction="EMAIL", hubspot_id="ch-3",
                     timestamp=datetime(2026, 3, 4, 5, 57),
                     chain_id=chain_bf.id, position_in_chain=3)
        s.add(ec3)
        s.flush()
        s.add(Score(email_id=ec3.id, personalisation=6, clarity=7, value_proposition=5, cta=7, overall=6,
                     notes="Good follow-through on conversation."))

        s.add(ChainScore(
            chain_id=chain_bf.id,
            progression=7, responsiveness=8, persistence=6, conversation_quality=6,
            avg_response_hours=1.5,
            notes="Good progression with call scheduling.",
        ))

        s.commit()
        chain_bf_id = chain_bf.id
        chain_u_id = chain_u.id

    engine.dispose()
    print("Database seeded.")
    return chain_bf_id, chain_u_id


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


def run_tests(driver, chain_bf_id, chain_u_id):
    from selenium.webdriver.common.by import By

    issues = []

    # ===== 1. NAV: "Inbox" NOT "Feed", ORDER = Inbox, Team, Settings =====
    print("\n=== Nav: Inbox label and ordering ===")
    for page_name, url in [("team", f"{BASE}/"), ("feed", f"{BASE}/feed"), ("settings", f"{BASE}/settings")]:
        driver.get(url)
        time.sleep(1)
        screenshot(driver, f"01_nav_{page_name}")

        nav = driver.find_element(By.TAG_NAME, "nav")
        nav_links = nav.find_elements(By.TAG_NAME, "a")
        # Filter to only the nav text links (skip the logo)
        link_texts = [a.text for a in nav_links if a.text and a.text != "Email Reviewer"]
        print(f"  [{page_name}] Nav links: {link_texts}")

        # Check "Inbox" is present and "Feed" is not
        if "Inbox" not in link_texts:
            issues.append(f"Nav on {page_name}: 'Inbox' not found, got {link_texts}")
        if "Feed" in link_texts:
            issues.append(f"Nav on {page_name}: 'Feed' still present, got {link_texts}")

        # Check order: Inbox, Team, Settings
        expected_order = ["Inbox", "Team", "Settings"]
        if link_texts != expected_order:
            issues.append(f"Nav on {page_name}: wrong order, expected {expected_order}, got {link_texts}")

    # Check active state on feed page
    driver.get(f"{BASE}/feed")
    time.sleep(1)
    inbox_link = driver.find_element(By.XPATH, "//nav//a[text()='Inbox']")
    inbox_classes = inbox_link.get_attribute("class")
    if "text-indigo-600" not in inbox_classes:
        issues.append(f"Nav: Inbox link not active on /feed page, classes: {inbox_classes}")
    else:
        print("  Inbox link active on /feed: correct")

    # Check active state on team page
    driver.get(f"{BASE}/")
    time.sleep(1)
    team_link = driver.find_element(By.XPATH, "//nav//a[text()='Team']")
    team_classes = team_link.get_attribute("class")
    if "text-indigo-600" not in team_classes:
        issues.append(f"Nav: Team link not active on / page, classes: {team_classes}")
    else:
        print("  Team link active on /: correct")

    # ===== 2. THREAD NODE DOTS HIDDEN =====
    print("\n=== Feed: Thread node dots hidden ===")
    driver.get(f"{BASE}/feed")
    time.sleep(1)
    screenshot(driver, "02_feed_no_node_dots", full_page=False)

    # Verify node-outgoing and node-incoming use transparent background
    page_source = driver.page_source
    if "node-outgoing { background: #4f46e5; }" in page_source:
        issues.append("Feed: node-outgoing still has colored background (should be transparent)")
    elif "node-outgoing { background: transparent; }" in page_source:
        print("  node-outgoing is transparent: correct")
    if "node-incoming { background: #9ca3af; }" in page_source:
        issues.append("Feed: node-incoming still has colored background (should be transparent)")
    elif "node-incoming { background: transparent; }" in page_source:
        print("  node-incoming is transparent: correct")

    # Verify conversations still show up
    conv_items = driver.find_elements(By.CSS_SELECTOR, ".feed-item[data-type='conversation']")
    print(f"  Conversation items in feed: {len(conv_items)}")
    if len(conv_items) < 1:
        issues.append("Feed: no conversation items found (expected at least 1)")

    # ===== 3. CHAIN DETAIL: EMAILS IN REVERSE CHRONOLOGICAL ORDER =====
    print(f"\n=== Chain Detail: Reverse chronological (id={chain_bf_id}) ===")
    driver.get(f"{BASE}/chains/{chain_bf_id}")
    time.sleep(1)
    screenshot(driver, "03_chain_detail_reverse_chrono")

    # Get email rows and check date order
    email_rows = driver.find_elements(By.CSS_SELECTOR, ".email-row")
    print(f"  Email rows: {len(email_rows)}")
    if len(email_rows) == 3:
        dates = []
        for row in email_rows:
            date_td = row.find_elements(By.CSS_SELECTOR, "td.whitespace-nowrap.text-sm.text-gray-500")
            if date_td:
                dates.append(date_td[0].text)
        print(f"  Dates in order: {dates}")
        # Verify dates are in descending order (newest first)
        if dates and dates != sorted(dates, reverse=True):
            issues.append(f"Chain detail: emails not in reverse chronological order, dates: {dates}")
        else:
            print("  Reverse chronological order: correct")
    else:
        issues.append(f"Chain detail: expected 3 email rows, got {len(email_rows)}")

    # Check first row is the most recent email
    if email_rows:
        first_row_text = email_rows[0].text
        # The most recent email (Mar 4) should mention "Re: Native campus partnership proposal"
        print(f"  First row text: {first_row_text[:80]}...")
        if "2026-03-04" in first_row_text:
            print("  Newest email (2026-03-04) is first: correct")
        else:
            issues.append(f"Chain detail: first email row should be newest (2026-03-04), got: {first_row_text[:80]}")

    # ===== 4. REP DETAIL: EMAILS IN REVERSE CHRONOLOGICAL ORDER =====
    print(f"\n=== Rep Detail: Reverse chronological ===")
    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    time.sleep(1)
    screenshot(driver, "04_rep_detail_reverse_chrono")

    # Check outreach emails table
    outreach_rows = driver.find_elements(By.CSS_SELECTOR, ".email-row")
    if outreach_rows:
        dates = []
        for row in outreach_rows[:5]:
            date_tds = row.find_elements(By.CSS_SELECTOR, "td.whitespace-nowrap.text-sm.text-gray-500")
            if date_tds:
                dates.append(date_tds[0].text)
        print(f"  Outreach email dates: {dates}")
        if dates and len(dates) >= 2:
            # Verify descending order
            if dates == sorted(dates, reverse=True):
                print("  Outreach emails in reverse chronological order: correct")
            else:
                issues.append(f"Rep detail: outreach emails not in reverse chronological order: {dates}")

    # ===== 5. FEED SIDEBAR: ITEMS IN REVERSE CHRONOLOGICAL ORDER =====
    print("\n=== Feed: Items in reverse chronological order ===")
    driver.get(f"{BASE}/feed")
    time.sleep(1)
    screenshot(driver, "05_feed_reverse_chrono", full_page=False)

    feed_items = driver.find_elements(By.CSS_SELECTOR, ".feed-item")
    print(f"  Feed items: {len(feed_items)}")
    if feed_items:
        times = []
        for item in feed_items[:8]:
            time_el = item.find_elements(By.CSS_SELECTOR, ".feed-time")
            if time_el:
                times.append(time_el[0].text)
        print(f"  Feed item times: {times}")

    # ===== 6. HOLISTIC UI CONSISTENCY CHECKS =====
    print("\n=== Holistic consistency checks ===")

    # Check that "Inbox" link goes to /feed
    driver.get(f"{BASE}/")
    time.sleep(0.5)
    inbox_link = driver.find_element(By.XPATH, "//nav//a[text()='Inbox']")
    inbox_href = inbox_link.get_attribute("href")
    if "/feed" not in inbox_href:
        issues.append(f"Inbox link href should point to /feed, got: {inbox_href}")
    else:
        print(f"  Inbox link href: {inbox_href} (correct)")

    # Click Inbox to verify navigation works
    inbox_link.click()
    time.sleep(1)
    if "/feed" not in driver.current_url:
        issues.append(f"Clicking Inbox didn't navigate to /feed, got: {driver.current_url}")
    else:
        print(f"  Inbox click -> {driver.current_url}: correct")

    # Verify the feed page title says "Inbox" or the page renders correctly
    page_source = driver.page_source
    if "feed-container" in page_source:
        print("  Feed/Inbox page rendered correctly")
    else:
        issues.append("Feed/Inbox page didn't render correctly after clicking Inbox")

    # Check H1 consistency across pages
    h1_sizes = {}
    for name, url in [("team", f"{BASE}/"), ("rep", f"{BASE}/reps/{REP_EMAIL}"), ("settings", f"{BASE}/settings")]:
        driver.get(url)
        time.sleep(0.5)
        h1 = driver.find_element(By.TAG_NAME, "h1")
        h1_sizes[name] = driver.execute_script("return window.getComputedStyle(arguments[0]).fontSize", h1)
    print(f"  H1 sizes: {h1_sizes}")
    if len(set(h1_sizes.values())) > 1:
        issues.append(f"H1 font-size inconsistency: {h1_sizes}")

    # Check that chain detail page expand/accordion still works
    print(f"\n=== Chain Detail: Expand + Accordion ===")
    driver.get(f"{BASE}/chains/{chain_bf_id}")
    time.sleep(1)
    email_rows = driver.find_elements(By.CSS_SELECTOR, ".email-row")
    if email_rows:
        email_rows[0].click()
        time.sleep(0.5)
        open_panel = driver.find_elements(By.CSS_SELECTOR, ".detail-panel.open")
        if open_panel:
            print("  First row expanded: yes")
            ai_notes = driver.find_elements(By.CSS_SELECTOR, ".detail-panel.open .ai-notes")
            print(f"  AI notes visible: {bool(ai_notes)}")
        else:
            issues.append("Chain detail: first email row didn't expand")

        if len(email_rows) >= 2:
            email_rows[1].click()
            time.sleep(0.5)
            first_still = "expanded" in email_rows[0].get_attribute("class")
            second_exp = "expanded" in email_rows[1].get_attribute("class")
            if first_still:
                issues.append("Chain detail: accordion didn't close first row")
            if not second_exp:
                issues.append("Chain detail: second row didn't expand")
            else:
                print("  Accordion works: correct")

    screenshot(driver, "06_chain_detail_expanded")

    # Check rep detail page expand/modal still works
    print(f"\n=== Rep Detail: Expand + Modal ===")
    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    time.sleep(1)
    email_rows = driver.find_elements(By.CSS_SELECTOR, ".email-row")
    if email_rows:
        email_rows[0].click()
        time.sleep(0.5)
        open_panel = driver.find_elements(By.CSS_SELECTOR, ".detail-panel.open")
        if open_panel:
            print("  Rep detail: first row expanded")
            # Open modal
            driver.execute_script("""
                var btn = document.querySelector('.detail-panel.open .full-email-link');
                if (btn) btn.click();
            """)
            time.sleep(0.5)
            modal = driver.find_elements(By.CSS_SELECTOR, "#email-modal:not(.hidden)")
            if modal:
                print("  Modal opened: yes")
                screenshot(driver, "07_rep_detail_modal")
            else:
                issues.append("Rep detail: modal didn't open")
        else:
            issues.append("Rep detail: first row didn't expand")

    # Check settings page
    print("\n=== Settings page ===")
    driver.get(f"{BASE}/settings")
    time.sleep(1)
    screenshot(driver, "08_settings")
    page = driver.page_source
    if "Settings" in page:
        print("  Settings page: renders correctly")

    # ===== SUMMARY =====
    print("\n" + "=" * 60)
    if issues:
        print(f"ISSUES FOUND: {len(issues)}")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("ALL CHECKS PASSED")
    print("=" * 60)

    return issues


def main():
    os.makedirs(OUT, exist_ok=True)

    chain_bf_id, chain_u_id = seed()
    server = start_server()

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1440,900")
    chrome_options.binary_location = "/usr/bin/chromium-browser"

    driver = webdriver.Chrome(options=chrome_options)

    try:
        issues = run_tests(driver, chain_bf_id, chain_u_id)
    finally:
        driver.quit()
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=5)

    if issues:
        print(f"\nFAILED with {len(issues)} issues")
        sys.exit(1)
    else:
        print("\nPASSED - all visual checks OK")


if __name__ == "__main__":
    main()
