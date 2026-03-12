from datetime import datetime

import pytest


class TestRootRedirectsToInbox:
    async def test_get_root_returns_200(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_get_root_returns_inbox(self, client):
        resp = await client.get("/")
        # Root should serve the inbox/feed page, not team
        assert "feed-split" in resp.text


class TestTeamPage:
    async def test_get_team_returns_200(self, client):
        resp = await client.get("/team")
        assert resp.status_code == 200

    async def test_get_team_contains_team(self, client):
        resp = await client.get("/team")
        assert "Team" in resp.text

    async def test_get_team_accepts_pagination_params(
        self, client, make_rep, make_email, make_score
    ):
        for i in range(25):
            rep = await make_rep(email=f"r{i:03d}@x.com", display_name=f"Rep {i:03d}")
            em = await make_email(from_email=rep.email, subject=f"Subj {i}")
            await make_score(email_id=em.id, overall=7)
        resp = await client.get("/team", params={"page": 2, "per_page": 20})
        assert resp.status_code == 200
        # Page 2 should show 5 reps (25 total, 20 per page)
        assert "Page 2 of 2" in resp.text

    async def test_get_team_default_pagination(self, client):
        resp = await client.get("/team")
        assert resp.status_code == 200

    async def test_team_page_flags_unassigned_rep(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="unassigned@example.com", display_name="Unassigned Rep")
        em = await make_email(from_email="unassigned@example.com", subject="Test")
        await make_score(email_id=em.id, overall=7)

        resp = await client.get("/team")
        assert resp.status_code == 200
        assert "Unassigned" in resp.text
        assert "rep-type-select" in resp.text

    async def test_team_page_shows_rep_type(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="typed@example.com", display_name="Typed Rep", rep_type="SDR")
        em = await make_email(from_email="typed@example.com", subject="Test")
        await make_score(email_id=em.id, overall=7)

        resp = await client.get("/team")
        assert resp.status_code == 200
        assert "SDR" in resp.text

    async def test_team_page_type_dropdown_hidden_when_assigned(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="typed@example.com", display_name="Typed Rep", rep_type="BizDev")
        em = await make_email(from_email="typed@example.com", subject="Test")
        await make_score(email_id=em.id, overall=7)

        resp = await client.get("/team")
        assert resp.status_code == 200
        # Dropdown should be hidden by default; only edit icon shown
        assert "rep-type-edit-btn" in resp.text
        assert 'class="rep-type-select' not in resp.text or "hidden" in resp.text

    async def test_team_page_type_dropdown_shown_when_unassigned(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="untyped@example.com", display_name="Untyped Rep")
        em = await make_email(from_email="untyped@example.com", subject="Test")
        await make_score(email_id=em.id, overall=7)

        resp = await client.get("/team")
        assert resp.status_code == 200
        # Dropdown should be visible for unassigned reps
        assert "rep-type-select" in resp.text

    async def test_team_page_filter_by_rep_type(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="sdr@example.com", display_name="SDR Rep", rep_type="SDR")
        em1 = await make_email(from_email="sdr@example.com", subject="Test SDR")
        await make_score(email_id=em1.id, overall=7)

        await make_rep(email="am@example.com", display_name="AM Rep", rep_type="AM")
        em2 = await make_email(from_email="am@example.com", subject="Test AM")
        await make_score(email_id=em2.id, overall=6)

        resp = await client.get("/team", params={"rep_type": "SDR"})
        assert resp.status_code == 200
        assert "SDR Rep" in resp.text
        assert "AM Rep" not in resp.text

    async def test_team_page_filter_by_rep_type_empty_shows_all(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="sdr@example.com", display_name="SDR Rep", rep_type="SDR")
        em1 = await make_email(from_email="sdr@example.com", subject="Test SDR")
        await make_score(email_id=em1.id, overall=7)

        await make_rep(email="am@example.com", display_name="AM Rep", rep_type="AM")
        em2 = await make_email(from_email="am@example.com", subject="Test AM")
        await make_score(email_id=em2.id, overall=6)

        resp = await client.get("/team", params={"rep_type": ""})
        assert resp.status_code == 200
        assert "SDR Rep" in resp.text
        assert "AM Rep" in resp.text

    async def test_team_page_filter_unassigned(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="sdr@example.com", display_name="SDR Rep", rep_type="SDR")
        em1 = await make_email(from_email="sdr@example.com", subject="Test SDR")
        await make_score(email_id=em1.id, overall=7)

        await make_rep(email="new@example.com", display_name="New Rep")
        em2 = await make_email(from_email="new@example.com", subject="Test New")
        await make_score(email_id=em2.id, overall=6)

        resp = await client.get("/team", params={"rep_type": "Unassigned"})
        assert resp.status_code == 200
        assert "New Rep" in resp.text
        assert "SDR Rep" not in resp.text


class TestRepDetailPage:
    async def test_get_rep_detail_returns_200_when_rep_exists(
        self, client, make_rep
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200

    async def test_get_rep_detail_returns_404_when_rep_missing(self, client):
        resp = await client.get("/reps/nobody@example.com")
        assert resp.status_code == 404

    async def test_rep_detail_ai_notes_rendered(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(
            from_email="alice@example.com", subject="Test email",
            body_text="Email body here\n--\nSignature",
        )
        await make_score(email_id=e.id, overall=8, notes="Good personalisation")
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "ai-notes" in resp.text
        assert "Good personalisation" in resp.text

    async def test_rep_detail_email_body_stripped_signature(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(
            from_email="alice@example.com", subject="Sig test",
            body_text="Main body content\n--\nSignature block here",
        )
        await make_score(email_id=e.id, overall=7)
        resp = await client.get("/reps/alice@example.com")
        assert "Main body content" in resp.text

    async def test_rep_detail_full_email_modal_link(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(
            from_email="alice@example.com", subject="Modal test",
            body_text="Body with signature\n--\nSig",
        )
        await make_score(email_id=e.id, overall=7)
        resp = await client.get("/reps/alice@example.com")
        assert "View full email with signature" in resp.text

    async def test_get_rep_detail_accepts_prefixed_pagination_params(
        self, client, make_rep, make_email, make_score
    ):
        rep = await make_rep(email="alice@example.com", display_name="Alice")
        for i in range(5):
            em = await make_email(from_email="alice@example.com", subject=f"Subj {i}")
            await make_score(email_id=em.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com", params={"o_page": 1, "o_per_page": 20}
        )
        assert resp.status_code == 200

    async def test_outreach_search_filter_returns_200(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Hello world")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com", params={"o_search": "hello"}
        )
        assert resp.status_code == 200

    async def test_prefixed_date_and_score_filters_return_200(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Test")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com",
            params={"o_date_from": "2024-01-01", "o_score_min": "5"},
        )
        assert resp.status_code == 200

    async def test_empty_filter_params_do_not_422(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Test")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com",
            params={
                "o_search": "",
                "o_date_from": "",
                "o_date_to": "",
                "o_score_min": "",
                "o_score_max": "",
            },
        )
        assert resp.status_code == 200

    async def test_rep_detail_shows_outreach_heading(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Cold intro")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Outreach" in resp.text

    async def test_rep_detail_shows_follow_ups_section(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Follow-ups" in resp.text

    async def test_rep_detail_shows_conversations_section(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Conversations" in resp.text

    async def test_rep_detail_conversations_filter_by_status(
        self, client, make_rep, make_chain, make_email
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        chain = await make_chain(
            normalized_subject="Sales pitch",
            is_unanswered=True,
            incoming_count=1,
            outgoing_count=1,
        )
        await make_email(
            from_email="alice@example.com", subject="Sales pitch",
            chain_id=chain.id, position_in_chain=1,
        )
        resp = await client.get(
            "/reps/alice@example.com", params={"c_status": "unanswered"}
        )
        assert resp.status_code == 200


class TestChainDetailPage:
    async def test_get_chain_detail_returns_200(
        self, client, make_chain, make_email
    ):
        chain = await make_chain(normalized_subject="Test chain")
        await make_email(
            from_email="rep@example.com",
            subject="Test chain",
            chain_id=chain.id,
            position_in_chain=1,
        )
        resp = await client.get(f"/chains/{chain.id}")
        assert resp.status_code == 200

    async def test_rep_detail_contains_conversations_section(
        self, client, make_rep, make_chain, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        chain = await make_chain(normalized_subject="Sales pitch")
        await make_email(
            from_email="alice@example.com",
            subject="Sales pitch",
            chain_id=chain.id,
            position_in_chain=1,
        )
        e = await make_email(from_email="alice@example.com", subject="Other")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Conversations" in resp.text


class TestRepExport:
    async def test_export_outreach_filtered_returns_xlsx(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Hello world")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com/export",
            params={"section": "outreach", "export_all": "false", "search": "hello"},
        )
        assert resp.status_code == 200
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    async def test_export_all_returns_xlsx(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Test")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com/export",
            params={"section": "outreach", "export_all": "true"},
        )
        assert resp.status_code == 200
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    async def test_export_follow_ups_returns_xlsx(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Test")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com/export",
            params={"section": "follow_ups", "export_all": "true"},
        )
        assert resp.status_code == 200
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    async def test_export_conversations_returns_xlsx(
        self, client, make_rep, make_chain, make_email
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        chain = await make_chain(normalized_subject="Test chain")
        await make_email(
            from_email="alice@example.com", subject="Test chain",
            chain_id=chain.id, position_in_chain=1,
        )
        resp = await client.get(
            "/reps/alice@example.com/export",
            params={"section": "conversations", "export_all": "true"},
        )
        assert resp.status_code == 200
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
