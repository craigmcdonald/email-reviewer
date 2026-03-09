from datetime import datetime

import pytest


class TestTeamPage:
    async def test_get_root_returns_200(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_get_root_contains_team(self, client):
        resp = await client.get("/")
        assert "Team" in resp.text

    async def test_get_root_accepts_pagination_params(
        self, client, make_rep, make_email, make_score
    ):
        for i in range(25):
            rep = await make_rep(email=f"r{i:03d}@x.com", display_name=f"Rep {i:03d}")
            em = await make_email(from_email=rep.email, subject=f"Subj {i}")
            await make_score(email_id=em.id, overall=7)
        resp = await client.get("/", params={"page": 2, "per_page": 20})
        assert resp.status_code == 200
        # Page 2 should show 5 reps (25 total, 20 per page)
        assert "Page 2 of 2" in resp.text

    async def test_get_root_default_pagination(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_team_page_flags_unassigned_rep(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="unassigned@example.com", display_name="Unassigned Rep")
        em = await make_email(from_email="unassigned@example.com", subject="Test")
        await make_score(email_id=em.id, overall=7)

        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Unassigned" in resp.text
        assert "unassigned-rep" in resp.text

    async def test_team_page_shows_rep_type(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="typed@example.com", display_name="Typed Rep", rep_type="SDR")
        em = await make_email(from_email="typed@example.com", subject="Test")
        await make_score(email_id=em.id, overall=7)

        resp = await client.get("/")
        assert resp.status_code == 200
        assert "SDR" in resp.text


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

    async def test_get_rep_detail_accepts_pagination_params(
        self, client, make_rep, make_email, make_score
    ):
        rep = await make_rep(email="alice@example.com", display_name="Alice")
        for i in range(5):
            em = await make_email(from_email="alice@example.com", subject=f"Subj {i}")
            await make_score(email_id=em.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com", params={"page": 1, "per_page": 20}
        )
        assert resp.status_code == 200

    async def test_search_filter_returns_200(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Hello world")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com", params={"search": "hello"}
        )
        assert resp.status_code == 200

    async def test_date_and_score_filters_return_200(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Test")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com",
            params={"date_from": "2024-01-01", "score_min": "5"},
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
                "search": "",
                "date_from": "",
                "date_to": "",
                "score_min": "",
                "score_max": "",
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

    async def test_rep_detail_shows_follow_up_section(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e1 = await make_email(
            from_email="alice@example.com", to_email="p@y.com",
            subject="Hello", timestamp=datetime(2024, 1, 1),
        )
        await make_score(email_id=e1.id, overall=7)
        e2 = await make_email(
            from_email="alice@example.com", to_email="p@y.com",
            subject="Hello", timestamp=datetime(2024, 1, 5),
        )
        await make_score(email_id=e2.id, overall=6)
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Follow-up" in resp.text

    async def test_rep_detail_shows_unanswered_section(
        self, client, make_rep, make_email, make_score, make_chain
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        chain = await make_chain(
            normalized_subject="Prospect reply",
            is_unanswered=True,
            incoming_count=1,
            outgoing_count=1,
        )
        await make_email(
            from_email="alice@example.com", subject="Prospect reply",
            chain_id=chain.id, position_in_chain=1,
        )
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Unanswered Replies" in resp.text

    async def test_rep_detail_shows_chains_section(
        self, client, make_rep, make_email, make_score, make_chain
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        chain = await make_chain(
            normalized_subject="Sales pitch",
            is_unanswered=False,
            incoming_count=1,
            outgoing_count=2,
        )
        await make_email(
            from_email="alice@example.com", subject="Sales pitch",
            chain_id=chain.id, position_in_chain=1,
        )
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Chains" in resp.text

    async def test_rep_detail_hides_follow_up_when_none(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Unique topic")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Follow-up" not in resp.text

    async def test_rep_detail_hides_unanswered_when_none(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Test")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Unanswered Replies" not in resp.text

    async def test_rep_detail_hides_chains_when_none(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Test")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200
        assert "Chains" not in resp.text


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

    async def test_rep_detail_contains_chains_section(
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
        assert "Chains" in resp.text


class TestRepExport:
    async def test_export_filtered_returns_xlsx(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Hello world")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com/export",
            params={"export_all": "false", "search": "hello"},
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
            params={"export_all": "true"},
        )
        assert resp.status_code == 200
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
