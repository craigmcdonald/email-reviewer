"""Comprehensive visual UI test.

Seeds PostgreSQL, starts uvicorn, drives every page and interaction
with headless Selenium, screenshots each state.
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
PORT = 8769
BASE = f"http://127.0.0.1:{PORT}"
OUT = "/tmp/ui_test"

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

        # 4 reps, different types
        s.add(Rep(email=REP_EMAIL, display_name="Zachary Bell", rep_type="SDR"))
        s.add(Rep(email="bethan@native.fm", display_name="Bethan Telfer", rep_type="AM"))
        s.add(Rep(email="katy@native.fm", display_name="Katy Smale", rep_type="BizDev"))
        s.add(Rep(email="new@native.fm", display_name="New Starter"))
        s.flush()

        # Outreach emails (no chain)
        e1 = Email(
            from_email=REP_EMAIL, to_email=PROSPECT,
            from_name="Zachary Bell", to_name="Nicholas Chang",
            subject="Native & HoYoverse - 2026 Student Opportunities",
            body_text="Hi Nicholas,\n\nI wanted to reach out about campus marketing opportunities for HoYoverse in 2026.\n\nWe currently work with gaming and entertainment brands across 80+ UK universities.\n\nBest regards,\nZachary Bell\nBusiness Development Manager\nNative Campus Advertising\nzacharybell@native.fm\n+44 7700 900123",
            direction="EMAIL", hubspot_id="out-1",
            timestamp=datetime(2026, 3, 2, 9, 0),
        )
        s.add(e1)
        s.flush()
        s.add(Score(email_id=e1.id, personalisation=6, clarity=8, value_proposition=7, cta=6, overall=7,
                     notes="Good opening with clear value proposition for campus marketing."))

        e2 = Email(
            from_email=REP_EMAIL, to_email="pharmacie@pharmacie.coffee",
            from_name="Zachary Bell", to_name="Pharmacie Coffee",
            subject="Campus coffee partnership - Native",
            body_text="Hi there,\n\nI'd love to discuss a campus coffee partnership with Pharmacie.\n\nKind regards,\nZachary Bell",
            direction="EMAIL", hubspot_id="out-2",
            timestamp=datetime(2026, 3, 3, 10, 0),
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
            timestamp=datetime(2026, 3, 2, 7, 0),
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
                     direction="EMAIL", hubspot_id="ks-1", timestamp=datetime(2026, 3, 1, 11, 0))
        s.add(ek1)
        s.flush()
        s.add(Score(email_id=ek1.id, personalisation=7, clarity=8, value_proposition=7, cta=6, overall=7,
                     notes="Good BizDev outreach with clear value."))

        en1 = Email(from_email="new@native.fm", to_email="someone@company.com",
                     from_name="New Starter", to_name="Someone",
                     subject="Quick intro", body_text="Hi, I'm new to the team.",
                     direction="EMAIL", hubspot_id="ns-1", timestamp=datetime(2026, 3, 1, 12, 0))
        s.add(en1)
        s.flush()
        s.add(Score(email_id=en1.id, personalisation=3, clarity=5, value_proposition=4, cta=3, overall=4,
                     notes="Generic intro with weak CTA."))

        # Follow-up emails
        e4 = Email(from_email=REP_EMAIL, to_email="drew.watson@damgroupuk.com",
                    from_name="Zachary Bell", to_name="Drew Watson",
                    subject="Final nudge - promise I'll stop after this",
                    body_text="Hi Drew,\n\nJust a quick follow-up on my previous email about campus advertising.",
                    direction="EMAIL", hubspot_id="fu-1", timestamp=datetime(2026, 3, 2, 7, 3))
        s.add(e4)
        s.flush()
        s.add(Score(email_id=e4.id, personalisation=3, clarity=6, value_proposition=5, cta=4, overall=4,
                     notes="First touch in sequence - decent but generic."))

        e5 = Email(from_email=REP_EMAIL, to_email="drew.watson@damgroupuk.com",
                    from_name="Zachary Bell", to_name="Drew Watson",
                    subject="Re: Final nudge - promise I'll stop after this",
                    body_text="Hi Drew,\n\nFollowing up on my last message. Would love to connect.",
                    direction="EMAIL", hubspot_id="fu-2", timestamp=datetime(2026, 3, 4, 9, 0))
        s.add(e5)
        s.flush()
        s.add(Score(email_id=e5.id, personalisation=2, clarity=5, value_proposition=4, cta=3, overall=3,
                     notes="Follow-up lacks new value."))

        e6 = Email(from_email=REP_EMAIL, to_email="drew.watson@damgroupuk.com",
                    from_name="Zachary Bell", to_name="Drew Watson",
                    subject="Final nudge - promise I'll stop after this",
                    body_text="Drew, last attempt. Let me know if campus ads are on your radar for 2026.",
                    direction="EMAIL", hubspot_id="fu-3", timestamp=datetime(2026, 3, 6, 8, 0))
        s.add(e6)
        s.flush()
        s.add(Score(email_id=e6.id, personalisation=2, clarity=5, value_proposition=3, cta=4, overall=3,
                     notes="Third attempt with diminishing returns."))

        # Chain: unanswered
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
                     body_text="Hi Nicholas,\n\nWanted to share a sampling opportunity on campus.",
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

        # Chain: scored back-and-forth
        chain_bf = EmailChain(
            normalized_subject="Native campus partnership proposal",
            participants=f"{PROSPECT},{REP_EMAIL}",
            started_at=datetime(2026, 3, 2, 2, 51),
            last_activity_at=datetime(2026, 3, 2, 5, 57),
            email_count=3, outgoing_count=2, incoming_count=1,
            is_unanswered=False,
        )
        s.add(chain_bf)
        s.flush()

        ec1 = Email(from_email=REP_EMAIL, to_email=PROSPECT,
                     from_name="Zachary Bell", to_name="Nicholas Chang",
                     subject="Native campus partnership proposal",
                     body_text="Hi Nicholas,\n\nI'd like to propose a campus partnership for HoYoverse.",
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
                     body_text="Hi Zach,\n\nI will be sending out the brief ASAP, then we can have the call.",
                     direction="INCOMING_EMAIL", hubspot_id="ch-2",
                     timestamp=datetime(2026, 3, 2, 4, 30),
                     chain_id=chain_bf.id, position_in_chain=2)
        s.add(ec2)

        ec3 = Email(from_email=REP_EMAIL, to_email=PROSPECT,
                     from_name="Zachary Bell", to_name="Nicholas Chang",
                     subject="Re: Native campus partnership proposal",
                     body_text="Great, looking forward to the brief. Let me know when works for the call.",
                     direction="EMAIL", hubspot_id="ch-3",
                     timestamp=datetime(2026, 3, 2, 5, 57),
                     chain_id=chain_bf.id, position_in_chain=3)
        s.add(ec3)
        s.flush()
        s.add(Score(email_id=ec3.id, personalisation=6, clarity=7, value_proposition=5, cta=7, overall=6,
                     notes="Good follow-through on conversation."))

        s.add(ChainScore(
            chain_id=chain_bf.id,
            progression=7, responsiveness=8, persistence=6, conversation_quality=6,
            avg_response_hours=1.5,
            notes="Good progression with call scheduling. Responsive follow-up.",
        ))

        s.commit()
        # Get the chain IDs for later use
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


def screenshot(driver, name):
    """Take a full-page screenshot with dynamic height."""
    time.sleep(0.8)
    total_height = driver.execute_script("return document.body.scrollHeight")
    driver.set_window_size(1440, max(900, total_height + 200))
    time.sleep(0.3)
    path = f"{OUT}/{name}.png"
    driver.save_screenshot(path)
    print(f"  [{name}] saved")
    # Reset to standard viewport
    driver.set_window_size(1440, 900)
    return path


def run_tests(driver, chain_bf_id, chain_u_id):
    from selenium.webdriver.common.by import By

    issues = []

    # ===== 1. TEAM PAGE =====
    print("\n=== Team Page ===")
    driver.get(f"{BASE}/")
    screenshot(driver, "01_team")

    # Verify 4 reps visible
    rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
    print(f"  Reps shown: {len(rows)}")
    if len(rows) != 4:
        issues.append(f"Team: expected 4 rep rows, got {len(rows)}")

    # Check column headers
    headers = [th.text for th in driver.find_elements(By.CSS_SELECTOR, "thead th")]
    print(f"  Headers: {headers}")
    expected_headers = ["REP", "TYPE", "OVERALL", "PERSONALISATION", "CLARITY", "VALUE PROP", "CTA", "CONVERSATIONS", "CONVERSATION SCORE"]
    for eh in expected_headers:
        if eh not in headers:
            issues.append(f"Team: missing header '{eh}', got {headers}")

    # Check score colours exist
    score_high = driver.find_elements(By.CSS_SELECTOR, ".score-high")
    score_mid = driver.find_elements(By.CSS_SELECTOR, ".score-mid")
    score_low = driver.find_elements(By.CSS_SELECTOR, ".score-low")
    print(f"  Score colours: high={len(score_high)} mid={len(score_mid)} low={len(score_low)}")
    if not score_high or not score_low:
        issues.append("Team: missing score colour classes")

    # Check pagination
    showing_text = driver.find_element(By.XPATH, "//*[contains(text(),'Showing')]")
    print(f"  Pagination: {showing_text.text}")

    # Filter by SDR
    print("\n=== Team Filtered: SDR ===")
    driver.get(f"{BASE}/?rep_type=SDR")
    screenshot(driver, "02_team_filtered_sdr")
    rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
    print(f"  SDR reps shown: {len(rows)}")
    if len(rows) != 1:
        issues.append(f"Team SDR filter: expected 1 row, got {len(rows)}")

    # Filter by Unassigned
    print("\n=== Team Filtered: Unassigned ===")
    driver.get(f"{BASE}/?rep_type=Unassigned")
    screenshot(driver, "03_team_filtered_unassigned")
    rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
    print(f"  Unassigned reps shown: {len(rows)}")
    if len(rows) != 1:
        issues.append(f"Team Unassigned filter: expected 1 row, got {len(rows)}")

    # Click a rep link
    print("\n=== Team -> Rep Click ===")
    driver.get(f"{BASE}/")
    rep_link = driver.find_element(By.CSS_SELECTOR, f"a[href='/reps/{REP_EMAIL}']")
    print(f"  Clicking: {rep_link.text}")
    rep_link.click()
    time.sleep(1)
    assert "/reps/" in driver.current_url, f"Expected rep detail URL, got {driver.current_url}"

    # ===== 2. REP DETAIL PAGE =====
    print("\n=== Rep Detail Page ===")
    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    screenshot(driver, "04_rep_detail")

    # Check all 3 sections exist
    page = driver.page_source
    for section in ["Outreach", "Follow-ups", "Conversations"]:
        if section not in page:
            issues.append(f"Rep detail: missing section '{section}'")
        else:
            print(f"  Section '{section}': present")

    # Check Outreach table has all 7 column headers
    outreach_headers = driver.find_elements(By.XPATH, "(//table)[1]/thead/tr/th")
    oh_texts = [th.text for th in outreach_headers]
    print(f"  Outreach headers: {oh_texts}")
    for expected in ["SUBJECT", "DATE", "OVERALL", "PERSONALISATION", "CLARITY", "VALUE PROP", "CTA"]:
        if expected not in oh_texts:
            issues.append(f"Rep detail outreach: missing header '{expected}'")

    # Check score values are visible (not clipped)
    outreach_rows = driver.find_elements(By.CSS_SELECTOR, ".email-row")
    print(f"  Email rows: {len(outreach_rows)}")

    # Check first email row has all score cells visible
    first_row = outreach_rows[0]
    tds = first_row.find_elements(By.TAG_NAME, "td")
    visible_tds = [td for td in tds if td.is_displayed()]
    print(f"  First row visible TDs: {len(visible_tds)}")
    if len(visible_tds) < 7:
        issues.append(f"Rep detail: first email row has {len(visible_tds)} visible columns, expected 7")

    # Check Follow-ups table headers
    followup_headers = driver.find_elements(By.XPATH, "(//table)[2]/thead/tr/th")
    fh_texts = [th.text for th in followup_headers]
    print(f"  Follow-up headers: {fh_texts}")

    # Check Conversations table headers
    conv_headers = driver.find_elements(By.XPATH, "(//table)[3]/thead/tr/th")
    ch_texts = [th.text for th in conv_headers]
    print(f"  Conversations headers: {ch_texts}")

    # ===== 3. EXPAND EMAIL ROW =====
    print("\n=== Rep Detail: Expand Email ===")
    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    time.sleep(1)
    driver.execute_script("document.querySelector('.email-row').click()")
    time.sleep(0.5)
    screenshot(driver, "05_rep_detail_expanded")

    # Check expanded content
    open_panel = driver.find_elements(By.CSS_SELECTOR, ".detail-panel.open")
    if not open_panel:
        issues.append("Rep detail: email row didn't expand")
    else:
        print("  Email row expanded: yes")
        # Check AI notes visible
        ai_notes = driver.find_elements(By.CSS_SELECTOR, ".detail-panel.open .ai-notes")
        print(f"  AI notes visible: {bool(ai_notes)}")
        # Check email body visible
        body = driver.find_elements(By.CSS_SELECTOR, ".detail-panel.open .email-body-text")
        print(f"  Email body visible: {bool(body)}")
        # Check "View full email" link
        view_link = driver.find_elements(By.CSS_SELECTOR, ".detail-panel.open .full-email-link")
        print(f"  'View full email' link: {bool(view_link)}")

    # ===== 4. EMAIL MODAL =====
    print("\n=== Rep Detail: Email Modal ===")
    driver.execute_script("""
        var btn = document.querySelector('.detail-panel.open .full-email-link');
        if (btn) btn.click();
    """)
    time.sleep(0.5)
    screenshot(driver, "06_rep_detail_modal")

    modal = driver.find_elements(By.CSS_SELECTOR, "#email-modal:not(.hidden)")
    if not modal:
        issues.append("Rep detail: email modal didn't open")
    else:
        print("  Modal opened: yes")
        subject_el = driver.find_element(By.ID, "email-modal-subject")
        print(f"  Modal subject: {subject_el.text}")
        body_el = driver.find_element(By.ID, "email-modal-body")
        print(f"  Modal body length: {len(body_el.text)} chars")

    # Close modal with Escape
    from selenium.webdriver.common.keys import Keys
    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    time.sleep(0.3)
    modal_hidden = driver.find_elements(By.CSS_SELECTOR, "#email-modal.hidden")
    print(f"  Modal closed via Escape: {bool(modal_hidden)}")

    # ===== 5. EXPAND SECOND EMAIL ROW (accordion: first should close) =====
    print("\n=== Rep Detail: Accordion Behaviour ===")
    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    time.sleep(1)
    email_rows = driver.find_elements(By.CSS_SELECTOR, ".email-row")
    if len(email_rows) >= 2:
        email_rows[0].click()
        time.sleep(0.5)
        first_expanded = "expanded" in email_rows[0].get_attribute("class")
        print(f"  First row expanded: {first_expanded}")

        email_rows[1].click()
        time.sleep(0.5)
        first_still_expanded = "expanded" in email_rows[0].get_attribute("class")
        second_expanded = "expanded" in email_rows[1].get_attribute("class")
        print(f"  After clicking second: first={first_still_expanded}, second={second_expanded}")
        screenshot(driver, "07_rep_detail_accordion")

        if first_still_expanded:
            issues.append("Rep detail: accordion didn't close first row when second clicked")
        if not second_expanded:
            issues.append("Rep detail: second row didn't expand")

    # ===== 6. CHAIN DETAIL PAGE (scored) =====
    print(f"\n=== Chain Detail: Scored (id={chain_bf_id}) ===")
    driver.get(f"{BASE}/chains/{chain_bf_id}")
    screenshot(driver, "08_chain_detail_scored")

    page = driver.page_source
    # Check "Conversation Score" heading
    if "Conversation Score" not in page:
        issues.append("Chain detail: missing 'Conversation Score' heading")
    else:
        print("  'Conversation Score' heading: present")

    # Check score dimensions
    for dim in ["Quality", "Progression", "Responsiveness", "Persistence", "Avg Response"]:
        if dim not in page:
            issues.append(f"Chain detail: missing dimension '{dim}'")
        else:
            print(f"  Dimension '{dim}': present")

    # Check email thread
    thread_cards = driver.find_elements(By.CSS_SELECTOR, ".space-y-4 > div.bg-white")
    print(f"  Thread emails: {len(thread_cards)}")
    if len(thread_cards) != 3:
        issues.append(f"Chain detail: expected 3 emails in thread, got {len(thread_cards)}")

    # Check direction badges
    outgoing = driver.find_elements(By.XPATH, "//*[contains(@class,'bg-blue-100')]")
    incoming = driver.find_elements(By.XPATH, "//*[contains(@class,'bg-green-100')]")
    print(f"  Outgoing badges: {len(outgoing)}, Incoming badges: {len(incoming)}")

    # Check "Conversation Thread" heading (not "Chain Thread")
    if "Conversation Thread" not in page:
        issues.append("Chain detail: missing 'Conversation Thread' heading")
    else:
        print("  'Conversation Thread' heading: present")

    # ===== 7. CHAIN DETAIL PAGE (unscored) =====
    print(f"\n=== Chain Detail: Unscored (id={chain_u_id}) ===")
    driver.get(f"{BASE}/chains/{chain_u_id}")
    screenshot(driver, "09_chain_detail_unscored")

    page = driver.page_source
    # Should NOT have score card
    score_card = driver.find_elements(By.XPATH, "//*[contains(text(),'Conversation Score')]")
    if score_card:
        issues.append("Chain detail (unscored): should not show 'Conversation Score'")
    else:
        print("  No score card shown: correct")

    thread_cards = driver.find_elements(By.CSS_SELECTOR, ".space-y-4 > div.bg-white")
    print(f"  Thread emails: {len(thread_cards)}")
    if len(thread_cards) != 2:
        issues.append(f"Chain detail (unscored): expected 2 emails, got {len(thread_cards)}")

    # ===== 8. CHAIN DETAIL VIA REP PAGE LINK =====
    print("\n=== Rep Detail -> Chain Detail Click ===")
    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    time.sleep(1)
    chain_link = driver.find_elements(By.CSS_SELECTOR, "a[href^='/chains/']")
    if chain_link:
        link_text = chain_link[0].text
        print(f"  Clicking chain link: {link_text}")
        chain_link[0].click()
        time.sleep(1)
        screenshot(driver, "10_chain_detail_via_rep")
        assert "/chains/" in driver.current_url
        print(f"  Navigated to: {driver.current_url}")
    else:
        issues.append("Rep detail: no chain links found")

    # ===== 9. SETTINGS PAGE - ALL TABS =====
    print("\n=== Settings: General Tab ===")
    driver.get(f"{BASE}/settings?tab=general")
    screenshot(driver, "11_settings_general")

    # Check operations panel text
    page = driver.page_source
    if "Rebuild Conversations" not in page:
        issues.append("Settings: missing 'Rebuild Conversations' button text")
    else:
        print("  'Rebuild Conversations': present")

    if "Score all unscored emails and conversations" not in page:
        issues.append("Settings: missing 'Score all unscored emails and conversations'")
    else:
        print("  'Score...conversations': present")

    # Check all operation buttons exist
    for btn_text in ["Fetch", "Score", "Re-score", "Export", "Rebuild Conversations"]:
        btns = driver.find_elements(By.XPATH, f"//button[contains(text(),'{btn_text}')]")
        if not btns:
            issues.append(f"Settings: missing '{btn_text}' button")
        else:
            print(f"  Button '{btn_text}': present")

    print("\n=== Settings: Classification Tab ===")
    driver.get(f"{BASE}/settings?tab=classification")
    screenshot(driver, "12_settings_classification")
    page = driver.page_source
    if "Email Classification" not in page:
        issues.append("Settings classification: missing heading")
    else:
        print("  'Email Classification': present")

    print("\n=== Settings: Evaluation Tab ===")
    driver.get(f"{BASE}/settings?tab=evaluation")
    screenshot(driver, "13_settings_evaluation")

    page = driver.page_source
    for heading in ["Initial Email Scoring", "Follow-up Email Scoring", "Conversation Evaluation", "Scoring Weights"]:
        if heading not in page:
            issues.append(f"Settings evaluation: missing '{heading}'")
        else:
            print(f"  '{heading}': present")

    # ===== 10. NAV LINKS =====
    print("\n=== Nav Link Tests ===")
    driver.get(f"{BASE}/settings")
    # Click "Team" nav link
    team_link = driver.find_element(By.XPATH, "//nav//a[text()='Team']")
    team_link.click()
    time.sleep(0.5)
    assert driver.current_url.rstrip("/") == BASE or driver.current_url == f"{BASE}/", f"Team nav: unexpected URL {driver.current_url}"
    print(f"  Team nav link -> {driver.current_url}: OK")

    # Click "Settings" nav link
    settings_link = driver.find_element(By.XPATH, "//nav//a[text()='Settings']")
    settings_link.click()
    time.sleep(0.5)
    assert "/settings" in driver.current_url, f"Settings nav: unexpected URL {driver.current_url}"
    print(f"  Settings nav link -> {driver.current_url}: OK")

    # Click "Email Reviewer" logo
    logo = driver.find_element(By.XPATH, "//nav//a[text()='Email Reviewer']")
    logo.click()
    time.sleep(0.5)
    print(f"  Logo link -> {driver.current_url}: OK")

    # ===== 11. BACK LINKS =====
    print("\n=== Back Links ===")
    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    time.sleep(0.5)
    back_link = driver.find_element(By.XPATH, "//a[contains(text(),'Back to Team')]")
    back_link.click()
    time.sleep(0.5)
    print(f"  Rep 'Back to Team' -> {driver.current_url}: OK")
    assert driver.current_url.rstrip("/") == BASE or driver.current_url == f"{BASE}/"

    # ===== 12. CONSISTENCY CHECKS =====
    print("\n=== Font & Style Consistency ===")

    # Check team page font sizes
    driver.get(f"{BASE}/")
    time.sleep(0.5)

    h1 = driver.find_element(By.TAG_NAME, "h1")
    h1_size = driver.execute_script("return window.getComputedStyle(arguments[0]).fontSize", h1)
    print(f"  Team H1 font-size: {h1_size}")

    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    time.sleep(0.5)
    h1 = driver.find_element(By.TAG_NAME, "h1")
    h1_size_rep = driver.execute_script("return window.getComputedStyle(arguments[0]).fontSize", h1)
    print(f"  Rep Detail H1 font-size: {h1_size_rep}")

    if h1_size != h1_size_rep:
        issues.append(f"Font inconsistency: Team H1={h1_size}, Rep H1={h1_size_rep}")

    driver.get(f"{BASE}/settings")
    time.sleep(0.5)
    h1 = driver.find_element(By.TAG_NAME, "h1")
    h1_size_settings = driver.execute_script("return window.getComputedStyle(arguments[0]).fontSize", h1)
    print(f"  Settings H1 font-size: {h1_size_settings}")

    if h1_size != h1_size_settings:
        issues.append(f"Font inconsistency: Team H1={h1_size}, Settings H1={h1_size_settings}")

    # Check table header font consistency
    driver.get(f"{BASE}/")
    time.sleep(0.5)
    team_th = driver.find_element(By.CSS_SELECTOR, "thead th")
    team_th_size = driver.execute_script("return window.getComputedStyle(arguments[0]).fontSize", team_th)

    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    time.sleep(0.5)
    rep_th = driver.find_element(By.CSS_SELECTOR, "thead th")
    rep_th_size = driver.execute_script("return window.getComputedStyle(arguments[0]).fontSize", rep_th)
    print(f"  Team TH font-size: {team_th_size}, Rep TH font-size: {rep_th_size}")

    if team_th_size != rep_th_size:
        issues.append(f"Table header font inconsistency: Team={team_th_size}, Rep={rep_th_size}")

    # Check table padding consistency
    team_td_padding = driver.execute_script("""
        var td = document.querySelector('thead th');
        var s = window.getComputedStyle(td);
        return s.paddingLeft + ' ' + s.paddingRight;
    """)
    print(f"  Rep TH padding: {team_td_padding}")

    # ===== 13. EXPORT MODAL =====
    print("\n=== Export Modal ===")
    driver.get(f"{BASE}/reps/{REP_EMAIL}")
    time.sleep(1)
    # Click export button (the SVG download icon)
    export_btn = driver.find_elements(By.XPATH, "//button[@title='Export']")
    if export_btn:
        export_btn[0].click()
        time.sleep(0.5)
        screenshot(driver, "14_export_modal")
        export_modal = driver.find_elements(By.CSS_SELECTOR, "#export-modal:not(.hidden)")
        if not export_modal:
            issues.append("Export modal didn't open")
        else:
            print("  Export modal opened: yes")
            links = driver.find_elements(By.CSS_SELECTOR, "#export-modal a")
            print(f"  Export links: {[l.text for l in links]}")

        # Close with Escape
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.3)
    else:
        issues.append("No export button found")

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
    chrome_options.binary_location = "/usr/bin/google-chrome-stable"

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
