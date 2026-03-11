"""Tests for the 30-day windowed team queries and trend card data."""

from datetime import datetime, timedelta

import pytest

from app.services.rep import get_team, get_team_trends


def _recent(days_ago=5):
    return datetime.utcnow() - timedelta(days=days_ago)


def _old(days_ago=60):
    return datetime.utcnow() - timedelta(days=days_ago)


class TestGetTeamWindowedQueries:
    """Integration tests for get_team's rolling 30-day metrics."""

    async def test_emails_per_day_counts_outgoing_in_window(
        self, db, make_rep, make_email
    ):
        await make_rep(email="rep@x.com", display_name="Rep")
        # 3 outgoing emails in window
        for _ in range(3):
            await make_email(
                from_email="rep@x.com",
                direction="EMAIL",
                timestamp=_recent(),
            )
        # 1 outgoing email outside window
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            timestamp=_old(),
        )
        # 1 incoming email in window (should not count)
        await make_email(
            from_email="rep@x.com",
            direction="INCOMING_EMAIL",
            timestamp=_recent(),
        )

        result = await get_team(db)
        row = result["items"][0]
        # 3 outgoing / 30 days = 0.1
        assert row.emails_per_day == pytest.approx(3 / 30, abs=0.01)

    async def test_emails_per_day_null_when_no_outgoing(
        self, db, make_rep
    ):
        await make_rep(email="rep@x.com", display_name="Rep")
        result = await get_team(db)
        assert result["items"][0].emails_per_day is None

    async def test_reply_rate_counts_emails_in_replied_chains(
        self, db, make_rep, make_email, make_chain
    ):
        await make_rep(email="rep@x.com", display_name="Rep")

        # Chain with reply (incoming_count > 0)
        replied_chain = await make_chain(
            normalized_subject="Replied", incoming_count=2
        )
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            timestamp=_recent(),
            chain_id=replied_chain.id,
        )

        # Chain with no reply
        no_reply_chain = await make_chain(
            normalized_subject="No reply", incoming_count=0
        )
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            timestamp=_recent(),
            chain_id=no_reply_chain.id,
        )

        # Email not in any chain
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            timestamp=_recent(),
        )

        result = await get_team(db)
        row = result["items"][0]
        # 1 replied / 3 total outgoing = 0.333
        assert row.reply_rate == pytest.approx(1 / 3, abs=0.01)

    async def test_reply_rate_excludes_old_emails(
        self, db, make_rep, make_email, make_chain
    ):
        await make_rep(email="rep@x.com", display_name="Rep")
        chain = await make_chain(
            normalized_subject="Old thread", incoming_count=1
        )
        # Old email outside window
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            timestamp=_old(),
            chain_id=chain.id,
        )

        result = await get_team(db)
        row = result["items"][0]
        assert row.reply_rate is None

    async def test_outreach_score_uses_scored_at_window(
        self, db, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@x.com", display_name="Rep")

        # Score in window
        e1 = await make_email(from_email="rep@x.com")
        await make_score(email_id=e1.id, overall=8, scored_at=_recent())

        # Score outside window
        e2 = await make_email(from_email="rep@x.com")
        await make_score(email_id=e2.id, overall=2, scored_at=_old())

        result = await get_team(db)
        row = result["items"][0]
        # Only the recent score (8) should be included
        assert row.avg_overall == pytest.approx(8.0, abs=0.1)

    async def test_outreach_score_null_when_no_recent_scores(
        self, db, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@x.com", display_name="Rep")
        e = await make_email(from_email="rep@x.com")
        await make_score(email_id=e.id, overall=8, scored_at=_old())

        result = await get_team(db)
        assert result["items"][0].avg_overall is None

    async def test_unanswered_count_not_windowed(
        self, db, make_rep, make_email, make_chain
    ):
        """Unanswered count reflects current state, not windowed."""
        await make_rep(email="rep@x.com", display_name="Rep")

        chain1 = await make_chain(
            normalized_subject="Urgent", is_unanswered=True
        )
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            chain_id=chain1.id,
        )

        chain2 = await make_chain(
            normalized_subject="Done", is_unanswered=False
        )
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            chain_id=chain2.id,
        )

        result = await get_team(db)
        assert result["items"][0].unanswered_count == 1

    async def test_unanswered_count_zero_when_all_answered(
        self, db, make_rep, make_email, make_chain
    ):
        await make_rep(email="rep@x.com", display_name="Rep")
        chain = await make_chain(
            normalized_subject="Done", is_unanswered=False
        )
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            chain_id=chain.id,
        )

        result = await get_team(db)
        assert result["items"][0].unanswered_count is None

    async def test_avg_response_hours_uses_scored_at_window(
        self, db, make_rep, make_email, make_chain, make_chain_score
    ):
        await make_rep(email="rep@x.com", display_name="Rep")

        chain1 = await make_chain(normalized_subject="Fast")
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            chain_id=chain1.id,
        )
        await make_chain_score(
            chain_id=chain1.id,
            avg_response_hours=4.0,
            scored_at=_recent(),
        )

        # Old chain score outside window
        chain2 = await make_chain(normalized_subject="Old")
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            chain_id=chain2.id,
        )
        await make_chain_score(
            chain_id=chain2.id,
            avg_response_hours=48.0,
            scored_at=_old(),
        )

        result = await get_team(db)
        row = result["items"][0]
        assert row.avg_response_hours == pytest.approx(4.0, abs=0.1)

    async def test_conv_score_uses_scored_at_window(
        self, db, make_rep, make_email, make_chain, make_chain_score
    ):
        await make_rep(email="rep@x.com", display_name="Rep")

        chain = await make_chain(normalized_subject="Recent")
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            chain_id=chain.id,
        )
        await make_chain_score(
            chain_id=chain.id,
            conversation_quality=9,
            scored_at=_recent(),
        )

        result = await get_team(db)
        assert result["items"][0].avg_conv_score == pytest.approx(9.0, abs=0.1)

    async def test_sorted_by_outreach_score_descending(
        self, db, make_rep, make_email, make_score
    ):
        await make_rep(email="low@x.com", display_name="Low")
        e_low = await make_email(from_email="low@x.com")
        await make_score(email_id=e_low.id, overall=3, scored_at=_recent())

        await make_rep(email="high@x.com", display_name="High")
        e_high = await make_email(from_email="high@x.com")
        await make_score(email_id=e_high.id, overall=9, scored_at=_recent())

        result = await get_team(db)
        assert result["items"][0].email == "high@x.com"
        assert result["items"][1].email == "low@x.com"

    async def test_unscored_rep_appears_last(
        self, db, make_rep, make_email, make_score
    ):
        await make_rep(email="scored@x.com", display_name="Scored")
        e = await make_email(from_email="scored@x.com")
        await make_score(email_id=e.id, overall=5, scored_at=_recent())

        await make_rep(email="unscored@x.com", display_name="Unscored")

        result = await get_team(db)
        assert result["items"][0].email == "scored@x.com"
        assert result["items"][1].email == "unscored@x.com"

    async def test_rep_type_filter_works_with_windowed_queries(
        self, db, make_rep, make_email, make_score
    ):
        await make_rep(email="sdr@x.com", display_name="SDR Rep", rep_type="SDR")
        e = await make_email(from_email="sdr@x.com")
        await make_score(email_id=e.id, overall=8, scored_at=_recent())

        await make_rep(email="am@x.com", display_name="AM Rep", rep_type="AM")
        e2 = await make_email(from_email="am@x.com")
        await make_score(email_id=e2.id, overall=6, scored_at=_recent())

        result = await get_team(db, rep_type="SDR")
        assert result["total"] == 1
        assert result["items"][0].email == "sdr@x.com"


class TestGetTeamTrends:
    """Integration tests for get_team_trends sparkline and delta logic."""

    async def test_returns_three_metric_keys(self, db):
        result = await get_team_trends(db)
        assert set(result.keys()) == {
            "outreach_score",
            "reply_rate",
            "avg_response_time",
        }

    async def test_each_metric_has_value_delta_sparkline(self, db):
        result = await get_team_trends(db)
        for key in result:
            metric = result[key]
            assert "value" in metric
            assert "delta" in metric
            assert "sparkline" in metric
            assert len(metric["sparkline"]) == 7

    async def test_all_nulls_when_no_data(self, db):
        result = await get_team_trends(db)
        assert result["outreach_score"]["value"] is None
        assert result["reply_rate"]["value"] is None
        assert result["avg_response_time"]["value"] is None

    async def test_outreach_score_value_from_recent_scores(
        self, db, make_email, make_score
    ):
        for _ in range(3):
            e = await make_email(from_email="rep@x.com")
            await make_score(email_id=e.id, overall=6, scored_at=_recent())

        result = await get_team_trends(db)
        assert result["outreach_score"]["value"] == pytest.approx(6.0, abs=0.5)

    async def test_sparkline_has_seven_entries(
        self, db, make_email, make_score
    ):
        e = await make_email(from_email="rep@x.com")
        await make_score(email_id=e.id, overall=7, scored_at=_recent(3))

        result = await get_team_trends(db)
        assert len(result["outreach_score"]["sparkline"]) == 7

    async def test_reply_rate_value_as_percentage(
        self, db, make_email, make_chain
    ):
        # 2 outgoing emails, 1 in a replied chain
        replied_chain = await make_chain(
            normalized_subject="Replied", incoming_count=1
        )
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            timestamp=_recent(),
            chain_id=replied_chain.id,
        )
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            timestamp=_recent(),
        )

        result = await get_team_trends(db)
        # 1/2 = 50%
        assert result["reply_rate"]["value"] == pytest.approx(50.0, abs=1.0)

    async def test_avg_response_time_value(
        self, db, make_chain, make_chain_score
    ):
        chain = await make_chain(normalized_subject="Test")
        await make_chain_score(
            chain_id=chain.id,
            avg_response_hours=12.0,
            scored_at=_recent(),
        )

        result = await get_team_trends(db)
        assert result["avg_response_time"]["value"] == pytest.approx(
            12.0, abs=0.5
        )

    async def test_delta_is_none_when_insufficient_weeks(self, db):
        result = await get_team_trends(db)
        # No data = all sparkline entries are None, so delta is None
        assert result["outreach_score"]["delta"] is None
