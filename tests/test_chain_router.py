from datetime import datetime


class TestGetChains:
    async def test_returns_200_with_empty_list(self, client):
        resp = await client.get("/api/chains")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_returns_chain_objects_with_score_fields(
        self, client, make_chain, make_chain_score
    ):
        chain = await make_chain(
            normalized_subject="Follow up",
            email_count=3,
            started_at=datetime(2025, 1, 1),
            last_activity_at=datetime(2025, 1, 5),
        )
        await make_chain_score(
            chain_id=chain.id,
            conversation_quality=8,
            progression=7,
            responsiveness=6,
            persistence=5,
        )

        resp = await client.get("/api/chains")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["normalized_subject"] == "Follow up"
        assert item["email_count"] == 3
        assert item["conversation_quality"] == 8
        assert item["progression"] == 7

    async def test_respects_pagination_params(self, client, make_chain):
        for i in range(15):
            await make_chain(
                normalized_subject=f"Subject {i}",
                participants=f"a{i}@x.com,b{i}@x.com",
            )

        resp = await client.get("/api/chains", params={"page": 2, "per_page": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["per_page"] == 10
        assert data["total"] == 15
        assert len(data["items"]) == 5


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
        # Emails in timestamp order
        assert data["emails"][0]["from_email"] == "alice@example.com"
        assert data["emails"][1]["from_email"] == "bob@example.com"
        assert data["chain_score"]["conversation_quality"] == 7

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
