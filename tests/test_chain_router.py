from datetime import datetime


class TestGetChainDetail:
    async def test_returns_200_with_chain_and_emails(
        self, client, make_chain, make_email, make_chain_score
    ):
        chain = await make_chain(
            normalized_subject="Project update",
            email_count=2,
            started_at=datetime(2025, 1, 1),
            last_activity_at=datetime(2025, 1, 3),
        )
        await make_email(
            from_email="alice@example.com",
            subject="Re: Project update",
            chain_id=chain.id,
            position_in_chain=1,
            timestamp=datetime(2025, 1, 1),
        )
        await make_email(
            from_email="bob@example.com",
            subject="Re: Project update",
            chain_id=chain.id,
            position_in_chain=2,
            timestamp=datetime(2025, 1, 3),
        )
        await make_chain_score(chain_id=chain.id, conversation_quality=7)

        resp = await client.get(f"/api/chains/{chain.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["normalized_subject"] == "Project update"
        assert len(data["emails"]) == 2
        # Emails in reverse chronological order (newest first)
        assert data["emails"][0]["from_email"] == "bob@example.com"
        assert data["emails"][1]["from_email"] == "alice@example.com"
        assert data["chain_score"]["conversation_quality"] == 7

    async def test_emails_ordered_reverse_chronological(
        self, client, make_chain, make_email, make_chain_score
    ):
        chain = await make_chain(
            normalized_subject="Thread order test",
            email_count=3,
            started_at=datetime(2025, 2, 1),
            last_activity_at=datetime(2025, 2, 5),
        )
        await make_email(
            from_email="first@example.com",
            subject="Thread order test",
            chain_id=chain.id,
            position_in_chain=1,
            timestamp=datetime(2025, 2, 1),
        )
        await make_email(
            from_email="second@example.com",
            subject="Re: Thread order test",
            chain_id=chain.id,
            position_in_chain=2,
            timestamp=datetime(2025, 2, 3),
        )
        await make_email(
            from_email="third@example.com",
            subject="Re: Thread order test",
            chain_id=chain.id,
            position_in_chain=3,
            timestamp=datetime(2025, 2, 5),
        )
        await make_chain_score(chain_id=chain.id)

        resp = await client.get(f"/api/chains/{chain.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["emails"]) == 3
        assert data["emails"][0]["from_email"] == "third@example.com"
        assert data["emails"][1]["from_email"] == "second@example.com"
        assert data["emails"][2]["from_email"] == "first@example.com"

    async def test_returns_404_for_nonexistent_chain(self, client):
        resp = await client.get("/api/chains/99999")
        assert resp.status_code == 404


class TestGetRepChains:
    async def test_returns_chains_for_rep(
        self, client, make_chain, make_email
    ):
        chain = await make_chain(
            normalized_subject="Sales pitch",
            email_count=2,
        )
        await make_email(
            from_email="rep@example.com",
            subject="Sales pitch",
            chain_id=chain.id,
            position_in_chain=1,
        )

        resp = await client.get("/api/reps/rep@example.com/chains")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["normalized_subject"] == "Sales pitch"

    async def test_returns_empty_list_for_unknown_rep(self, client):
        resp = await client.get("/api/reps/nobody@example.com/chains")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_excludes_chains_with_score_error(
        self, db, make_chain, make_email, make_chain_score
    ):
        """Chains with score_error=True on their ChainScore should be excluded
        from the score-filtered view."""
        from app.services.chain import get_rep_chains

        chain_good = await make_chain(
            normalized_subject="Good chain", email_count=2,
        )
        await make_email(
            from_email="rep@example.com", subject="Good chain",
            chain_id=chain_good.id, position_in_chain=1,
        )
        await make_chain_score(chain_id=chain_good.id, conversation_quality=8)

        chain_err = await make_chain(
            normalized_subject="Error chain", email_count=2,
        )
        await make_email(
            from_email="rep@example.com", subject="Error chain",
            chain_id=chain_err.id, position_in_chain=1,
        )
        await make_chain_score(chain_id=chain_err.id, score_error=True, conversation_quality=None)

        result = await get_rep_chains(db, "rep@example.com", score_min=1)
        subjects = [item["normalized_subject"] for item in result["items"]]
        assert "Good chain" in subjects
        assert "Error chain" not in subjects
