from datetime import datetime, timedelta

import pytest


def _recent():
    """Timestamp within the 30-day window."""
    return datetime.utcnow() - timedelta(days=5)


class TestGetReps:
    async def test_returns_200_with_empty_list(self, client):
        resp = await client.get("/api/reps")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_rep_objects_with_windowed_fields(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep One")
        email = await make_email(
            from_email="rep@example.com",
            direction="EMAIL",
            timestamp=_recent(),
        )
        await make_score(
            email_id=email.id, overall=8, clarity=9, scored_at=_recent()
        )

        resp = await client.get("/api/reps")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        row = data[0]
        assert row["email"] == "rep@example.com"
        assert row["avg_overall"] is not None
        assert row["emails_per_day"] is not None

    async def test_unanswered_count_returned(
        self, client, make_rep, make_email, make_chain
    ):
        await make_rep(email="rep@example.com", display_name="Rep One")
        chain = await make_chain(
            normalized_subject="Thread", is_unanswered=True
        )
        await make_email(
            from_email="rep@example.com",
            chain_id=chain.id,
            direction="EMAIL",
        )

        resp = await client.get("/api/reps")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["unanswered_count"] == 1

    async def test_conv_score_returned(
        self, client, make_rep, make_email, make_chain, make_chain_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep One")
        chain = await make_chain(normalized_subject="Thread")
        await make_email(
            from_email="rep@example.com",
            chain_id=chain.id,
            direction="EMAIL",
        )
        await make_chain_score(
            chain_id=chain.id,
            conversation_quality=9,
            scored_at=_recent(),
        )

        resp = await client.get("/api/reps")
        data = resp.json()
        assert data[0]["avg_conv_score"] == 9.0

    async def test_conv_score_null_when_no_chains(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep One")
        email = await make_email(
            from_email="rep@example.com",
            direction="EMAIL",
            timestamp=_recent(),
        )
        await make_score(email_id=email.id, overall=8, scored_at=_recent())

        resp = await client.get("/api/reps")
        data = resp.json()
        assert data[0]["avg_conv_score"] is None

    async def test_results_sorted_by_overall_avg_descending(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="low@example.com", display_name="Low Rep")
        email_low = await make_email(
            from_email="low@example.com",
            direction="EMAIL",
            timestamp=_recent(),
        )
        await make_score(
            email_id=email_low.id, overall=3, scored_at=_recent()
        )

        await make_rep(email="high@example.com", display_name="High Rep")
        email_high = await make_email(
            from_email="high@example.com",
            direction="EMAIL",
            timestamp=_recent(),
        )
        await make_score(
            email_id=email_high.id, overall=9, scored_at=_recent()
        )

        resp = await client.get("/api/reps")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["email"] == "high@example.com"
        assert data[1]["email"] == "low@example.com"


class TestSetRepType:
    async def test_set_rep_type(self, client, make_rep):
        await make_rep(email="rep@example.com", display_name="Rep One")
        resp = await client.patch(
            "/api/reps/rep@example.com",
            json={"rep_type": "SDR"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rep_type"] == "SDR"

    async def test_set_rep_type_invalid_value_rejected(self, client, make_rep):
        await make_rep(email="rep@example.com", display_name="Rep One")
        resp = await client.patch(
            "/api/reps/rep@example.com",
            json={"rep_type": "INVALID"},
        )
        assert resp.status_code == 422

    async def test_set_rep_type_non_sales(self, client, make_rep):
        await make_rep(email="rep@example.com", display_name="Rep One")
        resp = await client.patch(
            "/api/reps/rep@example.com",
            json={"rep_type": "Non-Sales"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rep_type"] == "Non-Sales"

    async def test_set_rep_type_returns_404_for_unknown_rep(self, client):
        resp = await client.patch(
            "/api/reps/nobody@example.com",
            json={"rep_type": "AM"},
        )
        assert resp.status_code == 404


class TestGetRepEmails:
    async def test_returns_scored_emails_for_rep(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep")
        email = await make_email(
            from_email="rep@example.com", subject="Follow up"
        )
        await make_score(email_id=email.id, overall=7)

        resp = await client.get("/api/reps/rep@example.com/emails")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["subject"] == "Follow up"

    async def test_returns_empty_list_for_unknown_rep(self, client):
        resp = await client.get("/api/reps/nobody@example.com/emails")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetEmailDetail:
    async def test_returns_email_with_score(
        self, client, make_email, make_score
    ):
        email = await make_email(
            from_email="rep@example.com", subject="Hello"
        )
        await make_score(email_id=email.id, overall=8)

        resp = await client.get(f"/api/emails/{email.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == email.id
        assert data["subject"] == "Hello"
        assert data["score"]["overall"] == 8

    async def test_returns_404_for_nonexistent_id(self, client):
        resp = await client.get("/api/emails/99999")
        assert resp.status_code == 404


class TestGetStats:
    async def test_returns_correct_totals(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep")
        e1 = await make_email(from_email="rep@example.com")
        e2 = await make_email(from_email="rep@example.com")
        await make_score(email_id=e1.id, overall=6)
        # e2 has no score

        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_emails"] == 2
        assert data["total_scored"] == 1
        assert data["total_reps"] == 1

    async def test_returns_zeros_when_empty(self, client):
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_emails"] == 0
        assert data["total_scored"] == 0
        assert data["total_reps"] == 0


class TestGetRepEmailsType:
    async def test_type_outreach_filters_correctly(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep")
        e1 = await make_email(
            from_email="rep@example.com", to_email="p@y.com",
            subject="Hello", timestamp=datetime(2024, 1, 1),
        )
        await make_score(email_id=e1.id, overall=7)
        # Follow-up (same subject, same recipient)
        e2 = await make_email(
            from_email="rep@example.com", to_email="p@y.com",
            subject="Hello", timestamp=datetime(2024, 1, 5),
        )
        await make_score(email_id=e2.id, overall=6)

        resp = await client.get("/api/reps/rep@example.com/emails", params={"type": "outreach"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == e1.id

    async def test_type_follow_up_filters_correctly(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep")
        e1 = await make_email(
            from_email="rep@example.com", to_email="p@y.com",
            subject="Hello", timestamp=datetime(2024, 1, 1),
        )
        await make_score(email_id=e1.id, overall=7)
        e2 = await make_email(
            from_email="rep@example.com", to_email="p@y.com",
            subject="Hello", timestamp=datetime(2024, 1, 5),
        )
        await make_score(email_id=e2.id, overall=6)

        resp = await client.get("/api/reps/rep@example.com/emails", params={"type": "follow_up"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == e2.id

    async def test_type_unanswered_filters_correctly(
        self, client, make_rep, make_email, make_score, make_chain
    ):
        await make_rep(email="rep@example.com", display_name="Rep")
        # Unanswered chain
        chain = await make_chain(
            normalized_subject="Thread",
            is_unanswered=True,
            incoming_count=1,
            outgoing_count=1,
        )
        await make_email(
            from_email="rep@example.com", subject="Thread",
            chain_id=chain.id, position_in_chain=1,
        )
        # Back-and-forth chain
        chain2 = await make_chain(
            normalized_subject="Chat",
            is_unanswered=False,
            incoming_count=1,
            outgoing_count=2,
        )
        await make_email(
            from_email="rep@example.com", subject="Chat",
            chain_id=chain2.id, position_in_chain=1,
        )

        resp = await client.get("/api/reps/rep@example.com/emails", params={"type": "unanswered"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == chain.id

    async def test_type_chain_filters_correctly(
        self, client, make_rep, make_email, make_score, make_chain, make_chain_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep")
        # Unanswered chain
        chain_u = await make_chain(
            normalized_subject="Unanswered",
            is_unanswered=True,
            incoming_count=1,
            outgoing_count=1,
        )
        await make_email(
            from_email="rep@example.com", subject="Unanswered",
            chain_id=chain_u.id, position_in_chain=1,
        )
        # Back-and-forth chain
        chain_bf = await make_chain(
            normalized_subject="Back and forth",
            is_unanswered=False,
            incoming_count=1,
            outgoing_count=2,
        )
        await make_email(
            from_email="rep@example.com", subject="Back and forth",
            chain_id=chain_bf.id, position_in_chain=1,
        )
        await make_chain_score(chain_id=chain_bf.id, conversation_quality=8)

        resp = await client.get("/api/reps/rep@example.com/emails", params={"type": "chain"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == chain_bf.id
