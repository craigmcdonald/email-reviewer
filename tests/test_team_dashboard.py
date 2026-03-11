"""Tests for team page dashboard route and helper functions."""

from datetime import datetime, timedelta

import pytest

from app.routers.dashboard import reply_bar_class, resp_time_bar_class, score_class


def _recent(days_ago=5):
    return datetime.utcnow() - timedelta(days=days_ago)


class TestScoreClass:
    def test_none_returns_empty(self):
        assert score_class(None) == ""

    def test_high_score(self):
        assert score_class(7) == "score-high"
        assert score_class(10) == "score-high"

    def test_mid_score(self):
        assert score_class(4) == "score-mid"
        assert score_class(6.9) == "score-mid"

    def test_low_score(self):
        assert score_class(3.9) == "score-low"
        assert score_class(0) == "score-low"

    def test_boundary_at_seven(self):
        assert score_class(7.0) == "score-high"
        assert score_class(6.99) == "score-mid"

    def test_boundary_at_four(self):
        assert score_class(4.0) == "score-mid"
        assert score_class(3.99) == "score-low"


class TestReplyBarClass:
    def test_none_returns_empty(self):
        assert reply_bar_class(None) == ""

    def test_high_rate(self):
        assert reply_bar_class(0.25) == "bar-high"
        assert reply_bar_class(0.5) == "bar-high"

    def test_mid_rate(self):
        assert reply_bar_class(0.15) == "bar-mid"
        assert reply_bar_class(0.24) == "bar-mid"

    def test_low_rate(self):
        assert reply_bar_class(0.14) == "bar-low"
        assert reply_bar_class(0.0) == "bar-low"


class TestRespTimeBarClass:
    def test_none_returns_empty(self):
        assert resp_time_bar_class(None) == ""

    def test_fast_response(self):
        assert resp_time_bar_class(4) == "bar-high"
        assert resp_time_bar_class(8) == "bar-high"

    def test_medium_response(self):
        assert resp_time_bar_class(12) == "bar-mid"
        assert resp_time_bar_class(24) == "bar-mid"

    def test_slow_response(self):
        assert resp_time_bar_class(25) == "bar-low"
        assert resp_time_bar_class(48) == "bar-low"


class TestTeamPageRendering:
    async def test_trend_cards_present(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Outreach Score" in resp.text
        assert "Reply Rate" in resp.text
        assert "Avg Response Time" in resp.text

    async def test_rolling_30_days_label(self, client):
        resp = await client.get("/")
        assert "Rolling 30 days" in resp.text

    async def test_column_group_headers(self, client):
        resp = await client.get("/")
        assert "group-outreach" in resp.text
        assert "group-conversations" in resp.text

    async def test_rep_avatar_initials_rendered(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="john@x.com", display_name="John Smith")
        e = await make_email(
            from_email="john@x.com",
            direction="EMAIL",
            timestamp=_recent(),
        )
        await make_score(email_id=e.id, overall=7, scored_at=_recent())

        resp = await client.get("/")
        assert "rep-avatar" in resp.text
        assert "JS" in resp.text

    async def test_emails_per_day_shown(
        self, client, make_rep, make_email
    ):
        await make_rep(email="rep@x.com", display_name="Rep One")
        for _ in range(3):
            await make_email(
                from_email="rep@x.com",
                direction="EMAIL",
                timestamp=_recent(),
            )

        resp = await client.get("/")
        assert resp.status_code == 200
        # 3/30 = 0.1
        assert "0.1" in resp.text

    async def test_unanswered_highlighted_red(
        self, client, make_rep, make_email, make_chain
    ):
        await make_rep(email="rep@x.com", display_name="Rep One")
        chain = await make_chain(
            normalized_subject="Urgent", is_unanswered=True
        )
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            chain_id=chain.id,
        )

        resp = await client.get("/")
        assert "unanswered-some" in resp.text

    async def test_unanswered_zero_muted(
        self, client, make_rep
    ):
        await make_rep(email="rep@x.com", display_name="Rep One")
        resp = await client.get("/")
        assert "unanswered-zero" in resp.text

    async def test_reply_rate_bar_rendered(
        self, client, make_rep, make_email, make_chain
    ):
        await make_rep(email="rep@x.com", display_name="Rep One")
        chain = await make_chain(
            normalized_subject="Thread", incoming_count=1
        )
        await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            timestamp=_recent(),
            chain_id=chain.id,
        )

        resp = await client.get("/")
        assert "ratio-bar-fill" in resp.text

    async def test_no_reps_shows_empty_state(self, client):
        resp = await client.get("/")
        assert "No reps found" in resp.text

    async def test_score_color_classes_applied(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@x.com", display_name="High Scorer")
        e = await make_email(
            from_email="rep@x.com",
            direction="EMAIL",
            timestamp=_recent(),
        )
        await make_score(email_id=e.id, overall=9, scored_at=_recent())

        resp = await client.get("/")
        assert "score-high" in resp.text

    async def test_type_badge_class_applied(
        self, client, make_rep
    ):
        await make_rep(
            email="rep@x.com", display_name="Rep", rep_type="SDR"
        )
        resp = await client.get("/")
        assert "badge-sdr" in resp.text

    async def test_sparkline_svg_rendered(self, client):
        resp = await client.get("/")
        assert "trend-sparkline" in resp.text

    async def test_dash_shown_for_null_metrics(
        self, client, make_rep
    ):
        await make_rep(email="rep@x.com", display_name="Empty Rep")
        resp = await client.get("/")
        # Null metrics render as em-dash
        assert "\u2014" in resp.text or "—" in resp.text
