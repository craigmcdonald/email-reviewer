"""Visual test: take screenshots of dashboard pages.

Seeds PostgreSQL via sync psycopg2, starts uvicorn as a subprocess,
takes screenshots with Selenium.
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

# Set env before importing app models
os.environ["AUTH_ENABLED"] = "FALSE"
os.environ["CURRENT_USER"] = "test"
os.environ["DATABASE_URL"] = DB_URL

from app.models import ChainScore, Email, EmailChain, Job, Rep, Score, Settings  # noqa: F401
from app.models.base import Base
from scripts.seeds.settings import SETTINGS_SEED

REP_EMAIL = "zacharybell@native.fm"
PROSPECT_EMAIL = "nicholas.c@hoyoverse.com"
PROSPECT2_EMAIL = "lab@unorthodoxroasters.co.uk"

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
        initial_email_prompt_blocks=SETTINGS_SEED["initial_email_prompt_blocks"].copy(),
        chain_email_prompt_blocks=SETTINGS_SEED["chain_email_prompt_blocks"].copy(),
        chain_evaluation_prompt_blocks=SETTINGS_SEED["chain_evaluation_prompt_blocks"].copy(),
    ))

    # Reps with different types
    session.add(Rep(email=REP_EMAIL, display_name="Zachary Bell", rep_type="SDR"))
    session.add(Rep(email="bethan@native.fm", display_name="Bethan Telfer", rep_type="AM"))
    session.add(Rep(email="katy@native.fm", display_name="Katy Smale", rep_type="BizDev"))
    session.add(Rep(email="new@native.fm", display_name="New Starter"))  # Unassigned
    session.flush()

    # --- 1. Outreach: standalone emails (no chain_id) ---
    e1 = Email(
        from_email=REP_EMAIL, to_email=PROSPECT_EMAIL,
        from_name="Zachary Bell", to_name="Nicholas Chang",
        subject="Native & HoYoverse - 2026 Student Opportunities",
        body_text="Hi Nicholas,\n\nI wanted to reach out about campus marketing opportunities for HoYoverse in 2026.\n\nWe currently work with gaming and entertainment brands across 80+ UK universities, helping them reach students through digital screens, sampling events, and branded activations.\n\nGiven Genshin Impact's popularity with the student demographic, I think there's a great opportunity to run targeted campaigns during Freshers' Week and throughout the academic year.\n\nI'd love to set up a quick call to walk you through what we offer and share some case studies from similar campaigns.\n\nBest regards,\nZachary Bell\nBusiness Development Manager\nNative Campus Advertising\nzacharybell@native.fm\n+44 7700 900123",
        direction="EMAIL", hubspot_id="out-1",
        timestamp=datetime(2026, 3, 2, 9, 0),
    )
    session.add(e1)
    session.flush()
    session.add(Score(
        email_id=e1.id, personalisation=6, clarity=8, value_proposition=7, cta=6, overall=7,
        notes="Good opening with clear value proposition for campus marketing.",
    ))

    e2 = Email(
        from_email=REP_EMAIL, to_email="pharmacie@pharmacie.coffee",
        from_name="Zachary Bell", to_name="Pharmacie Coffee",
        subject="Campus coffee partnership - Native",
        body_text="Hi there,\n\nI'd love to discuss a campus coffee partnership with Pharmacie. We work with over 50 universities across the UK and have helped brands like yours connect with students through sampling, digital screens, and event sponsorship.\n\nWould you be open to a quick call next week to explore this?\n\nKind regards,\nZachary Bell\nBusiness Development Manager\nNative Campus Advertising\n+44 7700 900123",
        direction="EMAIL", hubspot_id="out-2",
        timestamp=datetime(2026, 3, 3, 10, 0),
    )
    session.add(e2)
    session.flush()
    session.add(Score(
        email_id=e2.id, personalisation=5, clarity=7, value_proposition=6, cta=5, overall=6,
        notes="Decent clarity but lacks personalisation.",
    ))

    e3 = Email(
        from_email=REP_EMAIL, to_email=PROSPECT2_EMAIL,
        from_name="Zachary Bell", to_name="Unorthodox Roasters",
        subject="Your competition's already on campus",
        body_text="Hi,\n\nDid you know your competitors are already running campaigns on campus? We've seen a 40% increase in brand recall when students encounter products in their Students' Union.\n\nI'd love to share some data on what's working in the specialty coffee space right now.\n\nAll the best\nZachary\n\n--\n\nZachary Bell\nBusiness Development Manager\nNative Campus Advertising",
        direction="EMAIL", hubspot_id="out-3",
        timestamp=datetime(2026, 3, 2, 7, 0),
    )
    session.add(e3)
    session.flush()
    session.add(Score(
        email_id=e3.id, personalisation=4, clarity=6, value_proposition=7, cta=5, overall=5,
        notes="Competitive angle works but feels generic.",
    ))

    # Extra rep emails for team page variety
    eb1 = Email(
        from_email="bethan@native.fm", to_email="client@acme.com",
        from_name="Bethan Telfer", to_name="Client",
        subject="Renewal discussion",
        body_text="Hi, let's discuss your renewal options for next quarter.",
        direction="EMAIL", hubspot_id="bt-1",
        timestamp=datetime(2026, 3, 1, 10, 0),
    )
    session.add(eb1)
    session.flush()
    session.add(Score(
        email_id=eb1.id, personalisation=8, clarity=9, value_proposition=8, cta=7, overall=8,
        notes="Excellent account management email.",
    ))

    ek1 = Email(
        from_email="katy@native.fm", to_email="lead@startup.io",
        from_name="Katy Smale", to_name="Lead",
        subject="Partnership opportunity",
        body_text="Hi, I'd love to explore a partnership with your team.",
        direction="EMAIL", hubspot_id="ks-1",
        timestamp=datetime(2026, 3, 1, 11, 0),
    )
    session.add(ek1)
    session.flush()
    session.add(Score(
        email_id=ek1.id, personalisation=7, clarity=8, value_proposition=7, cta=6, overall=7,
        notes="Good BizDev outreach with clear value.",
    ))

    en1 = Email(
        from_email="new@native.fm", to_email="someone@company.com",
        from_name="New Starter", to_name="Someone",
        subject="Quick intro",
        body_text="Hi, I'm new to the team and wanted to introduce myself.",
        direction="EMAIL", hubspot_id="ns-1",
        timestamp=datetime(2026, 3, 1, 12, 0),
    )
    session.add(en1)
    session.flush()
    session.add(Score(
        email_id=en1.id, personalisation=3, clarity=5, value_proposition=4, cta=3, overall=4,
        notes="Generic intro with weak CTA.",
    ))

    # --- 2. Follow-up sequence: same rep, same prospect, same subject ---
    e4 = Email(
        from_email=REP_EMAIL, to_email="drew.watson@damgroupuk.com",
        from_name="Zachary Bell", to_name="Drew Watson",
        subject="Final nudge - promise I'll stop after this",
        body_text="Hi Drew,\n\nJust a quick follow-up on my previous email about campus advertising.",
        direction="EMAIL", hubspot_id="fu-1",
        timestamp=datetime(2026, 3, 2, 7, 3),
    )
    session.add(e4)
    session.flush()
    session.add(Score(
        email_id=e4.id, personalisation=3, clarity=6, value_proposition=5, cta=4, overall=4,
        notes="First touch in sequence - decent but generic.",
    ))

    e5 = Email(
        from_email=REP_EMAIL, to_email="drew.watson@damgroupuk.com",
        from_name="Zachary Bell", to_name="Drew Watson",
        subject="Re: Final nudge - promise I'll stop after this",
        body_text="Hi Drew,\n\nFollowing up on my last message. Would love to connect.",
        direction="EMAIL", hubspot_id="fu-2",
        timestamp=datetime(2026, 3, 4, 9, 0),
    )
    session.add(e5)
    session.flush()
    session.add(Score(
        email_id=e5.id, personalisation=2, clarity=5, value_proposition=4, cta=3, overall=3,
        notes="Follow-up lacks new value.",
    ))

    e6 = Email(
        from_email=REP_EMAIL, to_email="drew.watson@damgroupuk.com",
        from_name="Zachary Bell", to_name="Drew Watson",
        subject="Final nudge - promise I'll stop after this",
        body_text="Drew, last attempt. Let me know if campus ads are on your radar for 2026.",
        direction="EMAIL", hubspot_id="fu-3",
        timestamp=datetime(2026, 3, 6, 8, 0),
    )
    session.add(e6)
    session.flush()
    session.add(Score(
        email_id=e6.id, personalisation=2, clarity=5, value_proposition=3, cta=4, overall=3,
        notes="Third attempt with diminishing returns.",
    ))

    # --- 3. Unanswered reply: rep sends, prospect replies, rep silent ---
    chain_u = EmailChain(
        normalized_subject="Native & HoYoverse - 2026 Student Opportunities",
        participants=f"{PROSPECT_EMAIL},{REP_EMAIL}",
        started_at=datetime(2026, 3, 2, 9, 0),
        last_activity_at=datetime(2026, 3, 2, 14, 0),
        email_count=2, outgoing_count=1, incoming_count=1,
        is_unanswered=True,
    )
    session.add(chain_u)
    session.flush()

    eu1 = Email(
        from_email=REP_EMAIL, to_email=PROSPECT_EMAIL,
        from_name="Zachary Bell", to_name="Nicholas Chang",
        subject="Campus sampling opportunity",
        body_text="Hi Nicholas,\n\nWanted to share a sampling opportunity on campus.",
        direction="EMAIL", hubspot_id="ua-1",
        timestamp=datetime(2026, 3, 2, 9, 0),
        chain_id=chain_u.id, position_in_chain=1,
    )
    session.add(eu1)
    session.flush()
    session.add(Score(
        email_id=eu1.id, personalisation=5, clarity=7, value_proposition=6, cta=5, overall=6,
        notes="Reasonable opening.",
    ))

    eu2 = Email(
        from_email=PROSPECT_EMAIL, to_email=REP_EMAIL,
        from_name="Nicholas Chang", to_name="Zachary Bell",
        subject="Re: Campus sampling opportunity",
        body_text="Hi Zach,\n\nInteresting - can you send more details on pricing?",
        direction="INCOMING_EMAIL", hubspot_id="ua-2",
        timestamp=datetime(2026, 3, 2, 14, 0),
        chain_id=chain_u.id, position_in_chain=2,
    )
    session.add(eu2)
    # No chain score for unanswered

    # --- 4. Back-and-forth chain with chain score ---
    chain_bf = EmailChain(
        normalized_subject="Native & HoYoverse - 2026 Student Opportunities",
        participants=f"{PROSPECT_EMAIL},{REP_EMAIL}",
        started_at=datetime(2026, 3, 2, 2, 51),
        last_activity_at=datetime(2026, 3, 2, 5, 57),
        email_count=3, outgoing_count=2, incoming_count=1,
        is_unanswered=False,
    )
    session.add(chain_bf)
    session.flush()

    ec1 = Email(
        from_email=REP_EMAIL, to_email=PROSPECT_EMAIL,
        from_name="Zachary Bell", to_name="Nicholas Chang",
        subject="Native campus partnership proposal",
        body_text="Hi Nicholas,\n\nI'd like to propose a campus partnership for HoYoverse.",
        direction="EMAIL", hubspot_id="ch-1",
        timestamp=datetime(2026, 3, 2, 2, 51),
        chain_id=chain_bf.id, position_in_chain=1,
    )
    session.add(ec1)
    session.flush()
    session.add(Score(
        email_id=ec1.id, personalisation=7, clarity=8, value_proposition=7, cta=6, overall=7,
        notes="Strong opening with clear proposal.",
    ))

    ec2 = Email(
        from_email=PROSPECT_EMAIL, to_email=REP_EMAIL,
        from_name="Nicholas Chang", to_name="Zachary Bell",
        subject="Re: Native campus partnership proposal",
        body_text="Hi Zach,\n\nI will be sending out the brief ASAP, then we can have the call.",
        direction="INCOMING_EMAIL", hubspot_id="ch-2",
        timestamp=datetime(2026, 3, 2, 4, 30),
        chain_id=chain_bf.id, position_in_chain=2,
    )
    session.add(ec2)

    ec3 = Email(
        from_email=REP_EMAIL, to_email=PROSPECT_EMAIL,
        from_name="Zachary Bell", to_name="Nicholas Chang",
        subject="Re: Native campus partnership proposal",
        body_text="Great, looking forward to the brief. Let me know when works for the call.",
        direction="EMAIL", hubspot_id="ch-3",
        timestamp=datetime(2026, 3, 2, 5, 57),
        chain_id=chain_bf.id, position_in_chain=3,
    )
    session.add(ec3)
    session.flush()
    session.add(Score(
        email_id=ec3.id, personalisation=6, clarity=7, value_proposition=5, cta=7, overall=6,
        notes="Good follow-through on conversation.",
    ))

    session.add(ChainScore(
        chain_id=chain_bf.id,
        progression=7, responsiveness=8, persistence=6, conversation_quality=6,
        avg_response_hours=1.5,
        notes="Good progression with call scheduling. Responsive follow-up.",
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
    "team_filtered_sdr": f"http://127.0.0.1:{PORT}/?rep_type=SDR",
    "team_filtered_unassigned": f"http://127.0.0.1:{PORT}/?rep_type=Unassigned",
    "rep_detail": f"http://127.0.0.1:{PORT}/reps/{REP_EMAIL}",
    "feed": f"http://127.0.0.1:{PORT}/feed",
    "feed_unanswered": f"http://127.0.0.1:{PORT}/feed?unanswered=1",
    "settings_general": f"http://127.0.0.1:{PORT}/settings?tab=general",
    "settings_evaluation": f"http://127.0.0.1:{PORT}/settings?tab=evaluation",
}

for name, url in urls.items():
    driver.get(url)
    time.sleep(1)
    total_height = driver.execute_script("return document.body.scrollHeight")
    driver.set_window_size(1440, max(900, total_height + 200))
    time.sleep(0.5)
    driver.save_screenshot(f"/tmp/{name}.png")
    print(f"Saved /tmp/{name}.png")

# Feed detail panel screenshot
driver.get(f"http://127.0.0.1:{PORT}/feed")
time.sleep(1)
driver.execute_script("var row = document.querySelector('.feed-row'); if (row) row.click();")
time.sleep(1)
total_height = driver.execute_script("return document.body.scrollHeight")
driver.set_window_size(1440, max(900, total_height + 200))
time.sleep(0.5)
driver.save_screenshot("/tmp/feed_detail_panel.png")
print("Saved /tmp/feed_detail_panel.png")

# Expanded email row + modal screenshots
driver.get(f"http://127.0.0.1:{PORT}/reps/{REP_EMAIL}")
time.sleep(1)

# Click first email row to expand
driver.execute_script("document.querySelector('.email-row').click()")
time.sleep(0.5)
total_height = driver.execute_script("return document.body.scrollHeight")
driver.set_window_size(1440, max(900, total_height + 200))
time.sleep(0.5)
driver.save_screenshot("/tmp/rep_detail_expanded.png")
print("Saved /tmp/rep_detail_expanded.png")

# Click "View full email with signature" to open modal
driver.execute_script("""
    var btn = document.querySelector('.detail-panel.open .full-email-link');
    if (btn) btn.click();
""")
time.sleep(0.5)
driver.save_screenshot("/tmp/rep_detail_modal.png")
print("Saved /tmp/rep_detail_modal.png")

driver.quit()

# Cleanup
server.send_signal(signal.SIGTERM)
server.wait(timeout=5)
