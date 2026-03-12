"""Tests for the feed page: service function and route."""

from datetime import datetime, timedelta

import pytest

from app.enums import EmailDirection


def _recent(days_ago=5):
    return datetime.utcnow() - timedelta(days=days_ago)


def _ts(days_ago=5):
    """Return a recent timestamp for test data."""
    return datetime.utcnow() - timedelta(days=days_ago)


# ── Service tests ──────────────────────────────────────────────


class TestGetFeedEmpty:
    async def test_empty_database_returns_zero_items(self, db):
        from app.services.feed import get_feed

        result = await get_feed(db)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1


class TestGetFeedStandaloneEmails:
    async def test_standalone_outgoing_email_appears(
        self, db, make_rep, make_email, make_score
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep One", rep_type="SDR")
        e = await make_email(
            from_email="rep@co.com",
            from_name="Rep One",
            to_email="client@test.com",
            to_name="Client",
            subject="Hello",
            body_text="Body text here",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e.id, overall=7, notes="Good email", scored_at=_ts(2))

        result = await get_feed(db)
        assert result["total"] == 1
        item = result["items"][0]
        assert item["type"] == "email"
        assert item["subject"] == "Hello"
        assert item["from_name"] == "Rep One"
        assert item["score"] == 7

    async def test_incoming_emails_excluded(
        self, db, make_rep, make_email, make_score
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep One", rep_type="SDR")
        e = await make_email(
            from_email="rep@co.com",
            direction=EmailDirection.INCOMING_EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e.id, overall=5, scored_at=_ts(2))

        result = await get_feed(db)
        assert result["total"] == 0

    async def test_email_in_chain_excluded_from_standalone(
        self, db, make_rep, make_email, make_score, make_chain
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep One", rep_type="SDR")
        chain = await make_chain(normalized_subject="Thread")
        e = await make_email(
            from_email="rep@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
            chain_id=chain.id,
        )
        await make_score(email_id=e.id, overall=7, scored_at=_ts(2))

        result = await get_feed(db)
        # Should appear as conversation, not standalone email
        standalone_items = [i for i in result["items"] if i["type"] == "email"]
        assert len(standalone_items) == 0


class TestGetFeedConversations:
    async def test_chain_appears_as_conversation(
        self, db, make_rep, make_email, make_score, make_chain
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep One", rep_type="SDR")
        chain = await make_chain(
            normalized_subject="Exclusive Partners",
            last_activity_at=_ts(1),
            email_count=2,
            is_unanswered=True,
        )
        e1 = await make_email(
            from_email="rep@co.com",
            from_name="Rep One",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(3),
            chain_id=chain.id,
            position_in_chain=1,
        )
        await make_score(email_id=e1.id, overall=7, scored_at=_ts(3))
        await make_email(
            from_email="prospect@test.com",
            from_name="Prospect",
            direction=EmailDirection.INCOMING_EMAIL.value,
            timestamp=_ts(1),
            chain_id=chain.id,
            position_in_chain=2,
        )

        result = await get_feed(db)
        convos = [i for i in result["items"] if i["type"] == "conversation"]
        assert len(convos) == 1
        c = convos[0]
        assert c["subject"] == "Exclusive Partners"
        assert c["is_unanswered"] is True
        assert c["email_count"] == 2

    async def test_conversation_score_from_latest_scored_email(
        self, db, make_rep, make_email, make_score, make_chain
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep One", rep_type="SDR")
        chain = await make_chain(
            normalized_subject="Thread",
            last_activity_at=_ts(1),
            email_count=2,
        )
        e1 = await make_email(
            from_email="rep@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(5),
            chain_id=chain.id,
            position_in_chain=1,
        )
        await make_score(email_id=e1.id, overall=5, scored_at=_ts(5))
        e2 = await make_email(
            from_email="rep@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(1),
            chain_id=chain.id,
            position_in_chain=2,
        )
        await make_score(email_id=e2.id, overall=9, scored_at=_ts(1))

        result = await get_feed(db)
        convos = [i for i in result["items"] if i["type"] == "conversation"]
        assert len(convos) == 1
        assert convos[0]["score"] == 9


class TestGetFeedOrdering:
    async def test_items_ordered_by_most_recent_activity(
        self, db, make_rep, make_email, make_score, make_chain
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")

        # Older standalone email
        e1 = await make_email(
            from_email="rep@co.com",
            from_name="Rep",
            subject="Old email",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(5),
        )
        await make_score(email_id=e1.id, overall=6, scored_at=_ts(5))

        # Newer chain
        chain = await make_chain(
            normalized_subject="Recent thread",
            last_activity_at=_ts(1),
            email_count=2,
        )
        e2 = await make_email(
            from_email="rep@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(3),
            chain_id=chain.id,
        )
        await make_score(email_id=e2.id, overall=8, scored_at=_ts(3))

        result = await get_feed(db)
        assert result["total"] == 2
        assert result["items"][0]["type"] == "conversation"
        assert result["items"][1]["type"] == "email"


class TestGetFeedFilters:
    async def test_filter_by_rep(
        self, db, make_rep, make_email, make_score
    ):
        from app.services.feed import get_feed

        await make_rep(email="alice@co.com", display_name="Alice", rep_type="SDR")
        await make_rep(email="bob@co.com", display_name="Bob", rep_type="SDR")
        e1 = await make_email(
            from_email="alice@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e1.id, overall=7, scored_at=_ts(2))
        e2 = await make_email(
            from_email="bob@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(1),
        )
        await make_score(email_id=e2.id, overall=6, scored_at=_ts(1))

        result = await get_feed(db, rep_email="alice@co.com")
        assert result["total"] == 1
        assert result["items"][0]["from_email"] == "alice@co.com"

    async def test_filter_by_search(
        self, db, make_rep, make_email, make_score
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        e1 = await make_email(
            from_email="rep@co.com",
            subject="Campus Advertising",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e1.id, overall=7, scored_at=_ts(2))
        e2 = await make_email(
            from_email="rep@co.com",
            subject="Unrelated",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(1),
        )
        await make_score(email_id=e2.id, overall=6, scored_at=_ts(1))

        result = await get_feed(db, search="Campus")
        assert result["total"] == 1
        assert result["items"][0]["subject"] == "Campus Advertising"

    async def test_filter_unanswered_only(
        self, db, make_rep, make_email, make_score, make_chain
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")

        # Standalone email - excluded from unanswered view
        e1 = await make_email(
            from_email="rep@co.com",
            subject="Standalone",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e1.id, overall=7, scored_at=_ts(2))

        # Unanswered chain
        chain_u = await make_chain(
            normalized_subject="Unanswered",
            last_activity_at=_ts(1),
            is_unanswered=True,
            email_count=1,
        )
        e2 = await make_email(
            from_email="rep@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(1),
            chain_id=chain_u.id,
        )
        await make_score(email_id=e2.id, overall=6, scored_at=_ts(1))

        # Answered chain
        chain_a = await make_chain(
            normalized_subject="Answered",
            last_activity_at=_ts(1),
            is_unanswered=False,
            email_count=2,
        )
        e3 = await make_email(
            from_email="rep@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(3),
            chain_id=chain_a.id,
        )
        await make_score(email_id=e3.id, overall=5, scored_at=_ts(3))

        result = await get_feed(db, unanswered_only=True)
        assert result["total"] == 1
        assert result["items"][0]["subject"] == "Unanswered"

    async def test_filter_by_score_range(
        self, db, make_rep, make_email, make_score
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        e1 = await make_email(
            from_email="rep@co.com",
            subject="High",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e1.id, overall=9, scored_at=_ts(2))
        e2 = await make_email(
            from_email="rep@co.com",
            subject="Low",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(1),
        )
        await make_score(email_id=e2.id, overall=3, scored_at=_ts(1))

        result = await get_feed(db, score_min=7, score_max=10)
        assert result["total"] == 1
        assert result["items"][0]["subject"] == "High"

    async def test_filter_by_date_range(
        self, db, make_rep, make_email, make_score
    ):
        from datetime import date
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        e1 = await make_email(
            from_email="rep@co.com",
            subject="In range",
            direction=EmailDirection.EMAIL.value,
            timestamp=datetime(2026, 3, 5, 10, 0),
        )
        await make_score(email_id=e1.id, overall=7, scored_at=_ts(2))
        e2 = await make_email(
            from_email="rep@co.com",
            subject="Out of range",
            direction=EmailDirection.EMAIL.value,
            timestamp=datetime(2026, 1, 1, 10, 0),
        )
        await make_score(email_id=e2.id, overall=6, scored_at=_ts(1))

        result = await get_feed(
            db, date_from=date(2026, 3, 1), date_to=date(2026, 3, 10)
        )
        assert result["total"] == 1
        assert result["items"][0]["subject"] == "In range"


class TestGetFeedPagination:
    async def test_pagination_limits_results(
        self, db, make_rep, make_email, make_score
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        for i in range(5):
            e = await make_email(
                from_email="rep@co.com",
                subject=f"Email {i}",
                direction=EmailDirection.EMAIL.value,
                timestamp=_ts(i + 1),
                hubspot_id=f"hs_{i}",
            )
            await make_score(email_id=e.id, overall=7, scored_at=_ts(i + 1))

        result = await get_feed(db, per_page=2, page=1)
        assert result["total"] == 5
        assert len(result["items"]) == 2
        assert result["pages"] == 3

    async def test_page_two(
        self, db, make_rep, make_email, make_score
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        for i in range(5):
            e = await make_email(
                from_email="rep@co.com",
                subject=f"Email {i}",
                direction=EmailDirection.EMAIL.value,
                timestamp=_ts(i + 1),
                hubspot_id=f"hs_{i}",
            )
            await make_score(email_id=e.id, overall=7, scored_at=_ts(i + 1))

        result = await get_feed(db, per_page=2, page=2)
        assert len(result["items"]) == 2


class TestGetFeedRepFiltering:
    async def test_non_sales_reps_excluded_from_rep_list(self, db, make_rep):
        """Reps with Non-Sales type should not appear in the rep dropdown."""
        from app.services.feed import get_feed_reps

        await make_rep(email="sales@co.com", display_name="Sales Rep", rep_type="SDR")
        await make_rep(email="nonsales@co.com", display_name="Non Sales", rep_type="Non-Sales")
        await make_rep(email="untyped@co.com", display_name="Untyped")

        reps = await get_feed_reps(db)
        emails = [r.email for r in reps]
        assert "sales@co.com" in emails
        assert "nonsales@co.com" not in emails
        assert "untyped@co.com" not in emails


class TestGetFeedSearchConversation:
    async def test_search_matches_chain_normalized_subject(
        self, db, make_rep, make_email, make_score, make_chain
    ):
        from app.services.feed import get_feed

        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        chain = await make_chain(
            normalized_subject="Digital Screens Campaign",
            last_activity_at=_ts(1),
            email_count=1,
        )
        e = await make_email(
            from_email="rep@co.com",
            subject="Re: Digital Screens Campaign",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(1),
            chain_id=chain.id,
        )
        await make_score(email_id=e.id, overall=7, scored_at=_ts(1))

        result = await get_feed(db, search="Digital Screens")
        assert result["total"] == 1
        assert result["items"][0]["type"] == "conversation"


class TestGetFeedConversationRepFilter:
    async def test_chain_filtered_by_rep_with_outgoing_email(
        self, db, make_rep, make_email, make_score, make_chain
    ):
        from app.services.feed import get_feed

        await make_rep(email="alice@co.com", display_name="Alice", rep_type="SDR")
        await make_rep(email="bob@co.com", display_name="Bob", rep_type="SDR")
        chain = await make_chain(
            normalized_subject="Alice Thread",
            last_activity_at=_ts(1),
            email_count=2,
        )
        e = await make_email(
            from_email="alice@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
            chain_id=chain.id,
        )
        await make_score(email_id=e.id, overall=7, scored_at=_ts(2))
        await make_email(
            from_email="prospect@test.com",
            direction=EmailDirection.INCOMING_EMAIL.value,
            timestamp=_ts(1),
            chain_id=chain.id,
        )

        result = await get_feed(db, rep_email="bob@co.com")
        assert result["total"] == 0

        result = await get_feed(db, rep_email="alice@co.com")
        assert result["total"] == 1


# ── Route tests ─────────────────────────────────────────────────


class TestFeedRoute:
    async def test_feed_page_returns_200(self, client):
        resp = await client.get("/feed")
        assert resp.status_code == 200

    async def test_feed_page_has_nav_link(self, client):
        resp = await client.get("/feed")
        assert 'href="/"' in resp.text

    async def test_feed_page_contains_filter_controls(self, client):
        resp = await client.get("/feed")
        assert "Search" in resp.text or "search" in resp.text
        assert "All reps" in resp.text or "all reps" in resp.text.lower()

    async def test_feed_page_renders_standalone_email(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@co.com", display_name="Rep One", rep_type="SDR")
        e = await make_email(
            from_email="rep@co.com",
            from_name="Rep One",
            to_name="Client Person",
            subject="Campus Advertising Opportunity",
            body_text="Hi there, this is the body of the email.",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e.id, overall=8, notes="Strong opener", scored_at=_ts(2))

        resp = await client.get("/feed")
        assert resp.status_code == 200
        assert "Campus Advertising Opportunity" in resp.text
        assert "Rep One" in resp.text

    async def test_feed_page_renders_conversation(
        self, client, make_rep, make_email, make_score, make_chain
    ):
        await make_rep(email="rep@co.com", display_name="Rep One", rep_type="SDR")
        chain = await make_chain(
            normalized_subject="Partnership Discussion",
            last_activity_at=_ts(1),
            email_count=3,
            is_unanswered=True,
        )
        e = await make_email(
            from_email="rep@co.com",
            from_name="Rep One",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
            chain_id=chain.id,
        )
        await make_score(email_id=e.id, overall=7, scored_at=_ts(2))

        resp = await client.get("/feed")
        assert "Partnership Discussion" in resp.text

    async def test_feed_page_search_filter(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        e = await make_email(
            from_email="rep@co.com",
            subject="Unique Subject XYZ",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e.id, overall=7, scored_at=_ts(2))

        resp = await client.get("/feed?search=XYZ")
        assert "Unique Subject XYZ" in resp.text

        resp = await client.get("/feed?search=NOMATCH999")
        assert "Unique Subject XYZ" not in resp.text

    async def test_feed_page_rep_filter(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@co.com", display_name="Alice", rep_type="SDR")
        await make_rep(email="bob@co.com", display_name="Bob", rep_type="SDR")
        e1 = await make_email(
            from_email="alice@co.com",
            from_name="Alice",
            subject="Alice Email",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e1.id, overall=7, scored_at=_ts(2))
        e2 = await make_email(
            from_email="bob@co.com",
            from_name="Bob",
            subject="Bob Email",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(1),
        )
        await make_score(email_id=e2.id, overall=6, scored_at=_ts(1))

        resp = await client.get("/feed?rep_email=alice@co.com")
        assert "Alice Email" in resp.text
        assert "Bob Email" not in resp.text

    async def test_feed_page_unanswered_filter(
        self, client, make_rep, make_email, make_score, make_chain
    ):
        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        chain = await make_chain(
            normalized_subject="Unanswered Thread",
            last_activity_at=_ts(1),
            is_unanswered=True,
            email_count=1,
        )
        e = await make_email(
            from_email="rep@co.com",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(1),
            chain_id=chain.id,
        )
        await make_score(email_id=e.id, overall=5, scored_at=_ts(1))

        e2 = await make_email(
            from_email="rep@co.com",
            subject="Standalone",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
            hubspot_id="standalone_1",
        )
        await make_score(email_id=e2.id, overall=7, scored_at=_ts(2))

        resp = await client.get("/feed?unanswered=1")
        assert "Unanswered Thread" in resp.text
        assert "Standalone" not in resp.text

    async def test_feed_page_pagination_controls(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        for i in range(25):
            e = await make_email(
                from_email="rep@co.com",
                subject=f"Email {i}",
                direction=EmailDirection.EMAIL.value,
                timestamp=_ts(i + 1),
                hubspot_id=f"hs_{i}",
            )
            await make_score(email_id=e.id, overall=7, scored_at=_ts(i + 1))

        resp = await client.get("/feed?per_page=20")
        assert "Showing" in resp.text
        assert "25" in resp.text

    async def test_feed_page_score_color_classes(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        e = await make_email(
            from_email="rep@co.com",
            subject="High Score Email",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(email_id=e.id, overall=9, scored_at=_ts(2))

        resp = await client.get("/feed")
        assert "score-high" in resp.text

    async def test_feed_nav_active_state(self, client):
        resp = await client.get("/feed")
        # Inbox nav link should have active indicator
        assert "Inbox" in resp.text

    async def test_feed_page_nav_shows_inbox_not_feed(self, client):
        resp = await client.get("/feed")
        nav_html = resp.text.split("<nav")[1].split("</nav>")[0]
        assert "Inbox" in nav_html
        assert ">Feed<" not in nav_html

    async def test_feed_page_nav_order_inbox_team_settings(self, client):
        resp = await client.get("/feed")
        nav_html = resp.text.split("<nav")[1].split("</nav>")[0]
        inbox_pos = nav_html.index("Inbox")
        team_pos = nav_html.index("Team")
        settings_pos = nav_html.index("Settings")
        assert inbox_pos < team_pos < settings_pos

    async def test_feed_page_thread_node_dots_hidden(
        self, client, make_rep, make_email, make_score, make_chain
    ):
        """Thread node dots (node-outgoing/node-incoming) should be transparent."""
        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")

        resp = await client.get("/feed")
        assert resp.status_code == 200
        assert "node-outgoing { background: transparent; }" in resp.text
        assert "node-incoming { background: transparent; }" in resp.text


class TestFeedNavigation:
    async def test_team_page_has_inbox_link(self, client):
        resp = await client.get("/team")
        assert 'href="/"' in resp.text

    async def test_settings_page_has_inbox_link(self, client):
        resp = await client.get("/settings")
        assert 'href="/"' in resp.text

    async def test_team_page_nav_shows_inbox_not_feed(self, client):
        resp = await client.get("/team")
        nav_html = resp.text.split("<nav")[1].split("</nav>")[0]
        assert "Inbox" in nav_html
        assert ">Feed<" not in nav_html

    async def test_nav_order_inbox_team_settings(self, client):
        resp = await client.get("/team")
        nav_html = resp.text.split("<nav")[1].split("</nav>")[0]
        inbox_pos = nav_html.index("Inbox")
        team_pos = nav_html.index("Team")
        settings_pos = nav_html.index("Settings")
        assert inbox_pos < team_pos < settings_pos


class TestFeedMasterDetail:
    async def test_feed_page_has_detail_panel(self, client):
        resp = await client.get("/feed")
        assert resp.status_code == 200
        assert "feed-detail-panel" in resp.text

    async def test_feed_page_has_split_layout(self, client):
        resp = await client.get("/feed")
        assert "feed-split" in resp.text

    async def test_standalone_email_has_score_tiles_data(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@co.com", display_name="Rep One", rep_type="SDR")
        e = await make_email(
            from_email="rep@co.com",
            from_name="Rep One",
            to_email="client@test.com",
            subject="Detail Test",
            body_text="Body text for detail panel.",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
        )
        await make_score(
            email_id=e.id, overall=8, personalisation=7, clarity=9,
            value_proposition=6, cta=8, notes="Strong opener", scored_at=_ts(2),
        )

        resp = await client.get("/feed")
        assert resp.status_code == 200
        # Score data available via data attributes for JS detail panel
        assert "Detail Test" in resp.text
        assert "data-score" in resp.text

    async def test_conversation_has_chain_id_data(
        self, client, make_rep, make_email, make_score, make_chain
    ):
        await make_rep(email="rep@co.com", display_name="Rep One", rep_type="SDR")
        chain = await make_chain(
            normalized_subject="Thread for Detail",
            last_activity_at=_ts(1),
            email_count=2,
            is_unanswered=True,
        )
        e = await make_email(
            from_email="rep@co.com",
            from_name="Rep One",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(2),
            chain_id=chain.id,
        )
        await make_score(email_id=e.id, overall=7, scored_at=_ts(2))

        resp = await client.get("/feed")
        assert "data-chain-id" in resp.text


class TestFeedThreadDetail:
    async def test_chain_detail_api_returns_emails(
        self, client, make_rep, make_email, make_score, make_chain
    ):
        await make_rep(email="rep@co.com", display_name="Rep", rep_type="SDR")
        chain = await make_chain(
            normalized_subject="Thread Detail",
            last_activity_at=_ts(1),
            email_count=2,
        )
        e1 = await make_email(
            from_email="rep@co.com",
            from_name="Rep",
            direction=EmailDirection.EMAIL.value,
            timestamp=_ts(3),
            chain_id=chain.id,
            position_in_chain=1,
        )
        await make_score(email_id=e1.id, overall=7, scored_at=_ts(3))
        await make_email(
            from_email="prospect@test.com",
            from_name="Prospect",
            direction=EmailDirection.INCOMING_EMAIL.value,
            timestamp=_ts(1),
            chain_id=chain.id,
            position_in_chain=2,
        )

        resp = await client.get(f"/api/chains/{chain.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["normalized_subject"] == "Thread Detail"
        assert len(data["emails"]) == 2
