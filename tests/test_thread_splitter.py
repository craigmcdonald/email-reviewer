import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.email import Email
from app.services.thread_splitter import (
    _find_duplicate,
    _matches_any_indicator,
    split_email_threads,
)


class TestMatchesAnyIndicator:
    def test_matches_from_colon(self):
        assert _matches_any_indicator("blah From: someone", ["From:"]) is True

    def test_matches_wrote_colon(self):
        assert _matches_any_indicator("On Mon Bob wrote:", ["wrote:"]) is True

    def test_no_match(self):
        assert _matches_any_indicator("plain email body", ["From:", "wrote:"]) is False

    def test_empty_body(self):
        assert _matches_any_indicator("", ["From:"]) is False

    def test_empty_indicators(self):
        assert _matches_any_indicator("From: someone", []) is False

    def test_case_sensitive(self):
        assert _matches_any_indicator("from: someone", ["From:"]) is False


class TestFindDuplicate:
    def test_matches_by_email_subject_and_body(self):
        candidates = [
            {
                "from_email": "alice@example.com",
                "subject": "Hello",
                "body_text": "Hi Bob, I wanted to follow up on our discussion.",
                "timestamp": datetime(2026, 2, 24, 14, 27),
            },
        ]
        result = _find_duplicate(
            from_email="alice@example.com",
            subject="Re: Hello",
            body_snippet="Hi Bob, I wanted to follow up",
            timestamp=None,
            candidates=candidates,
        )
        assert result is not None

    def test_no_match_different_sender(self):
        candidates = [
            {
                "from_email": "bob@example.com",
                "subject": "Hello",
                "body_text": "Hi Bob, I wanted to follow up on our discussion.",
                "timestamp": datetime(2026, 2, 24, 14, 27),
            },
        ]
        result = _find_duplicate(
            from_email="alice@example.com",
            subject="Hello",
            body_snippet="Hi Bob, I wanted to follow up",
            timestamp=None,
            candidates=candidates,
        )
        assert result is None

    def test_no_match_different_subject(self):
        candidates = [
            {
                "from_email": "alice@example.com",
                "subject": "Goodbye",
                "body_text": "Hi Bob, I wanted to follow up on our discussion.",
                "timestamp": datetime(2026, 2, 24, 14, 27),
            },
        ]
        result = _find_duplicate(
            from_email="alice@example.com",
            subject="Hello",
            body_snippet="Hi Bob, I wanted to follow up",
            timestamp=None,
            candidates=candidates,
        )
        assert result is None

    def test_no_match_different_body(self):
        candidates = [
            {
                "from_email": "alice@example.com",
                "subject": "Hello",
                "body_text": "Something completely different here.",
                "timestamp": datetime(2026, 2, 24, 14, 27),
            },
        ]
        result = _find_duplicate(
            from_email="alice@example.com",
            subject="Hello",
            body_snippet="Hi Bob, I wanted to follow up",
            timestamp=None,
            candidates=candidates,
        )
        assert result is None

    def test_case_insensitive_email(self):
        candidates = [
            {
                "from_email": "Alice@Example.COM",
                "subject": "Hello",
                "body_text": "Hi Bob, I wanted to follow up on our discussion.",
                "timestamp": None,
            },
        ]
        result = _find_duplicate(
            from_email="alice@example.com",
            subject="Hello",
            body_snippet="Hi Bob, I wanted to follow up",
            timestamp=None,
            candidates=candidates,
        )
        assert result is not None

    def test_body_match_works_without_timestamp(self):
        candidates = [
            {
                "from_email": "alice@example.com",
                "subject": "Hello",
                "body_text": "Hi Bob, I wanted to follow up on our discussion.",
                "timestamp": None,
            },
        ]
        result = _find_duplicate(
            from_email="alice@example.com",
            subject="Hello",
            body_snippet="Hi Bob, I wanted to follow up",
            timestamp=None,
            candidates=candidates,
        )
        assert result is not None

    def test_empty_candidates(self):
        result = _find_duplicate(
            from_email="alice@example.com",
            subject="Hello",
            body_snippet="Hi Bob",
            timestamp=None,
            candidates=[],
        )
        assert result is None


THREAD_BODY = (
    "Hi Mark,\n\nJust following up on our earlier conversation.\n\n"
    "Best,\nPriyanka\n\n"
    "From: Mark Jones <mark@prospect.com>\n"
    "Sent: Monday, February 24, 2026 2:27 PM\n"
    "Subject: Re: Partnership Opportunity\n\n"
    "Thanks Priyanka, let me think about it.\n\n"
    "From: Priyanka Sharma <priyanka@nativecampusadvertising.com>\n"
    "Sent: Monday, February 24, 2026 10:00 AM\n"
    "Subject: Partnership Opportunity\n\n"
    "Hi Mark, I wanted to reach out about a partnership opportunity."
)

HAIKU_RESPONSE = json.dumps([
    {
        "from_name": "Priyanka Sharma",
        "from_email": "priyanka@nativecampusadvertising.com",
        "to_name": "Mark Jones",
        "to_email": "mark@prospect.com",
        "date": "2026-02-24T15:00:00",
        "subject": "Re: Partnership Opportunity",
        "body_text": "Just following up on our earlier conversation.",
    },
    {
        "from_name": "Mark Jones",
        "from_email": "mark@prospect.com",
        "to_name": "Priyanka Sharma",
        "to_email": "priyanka@nativecampusadvertising.com",
        "date": "2026-02-24T14:27:00",
        "subject": "Re: Partnership Opportunity",
        "body_text": "Thanks Priyanka, let me think about it.",
    },
    {
        "from_name": "Priyanka Sharma",
        "from_email": "priyanka@nativecampusadvertising.com",
        "to_name": "Mark Jones",
        "to_email": "mark@prospect.com",
        "date": "2026-02-24T10:00:00",
        "subject": "Partnership Opportunity",
        "body_text": "Hi Mark, I wanted to reach out about a partnership opportunity.",
    },
])


def _mock_haiku_response(text: str):
    """Build a mock Anthropic messages response."""
    msg = AsyncMock()
    msg.content = [AsyncMock(text=text)]
    return msg


@pytest.mark.asyncio
class TestSplitEmailThreads:
    async def test_skips_email_without_indicators(self, db, make_email, make_settings):
        await make_settings(
            thread_split_indicators=["From:", "wrote:"],
            thread_splitter_prompt_blocks={"opening": "x", "messages": "y", "closing": "z"},
        )
        await make_email(
            body_text="Plain email with no thread indicators at all.",
            quoted_metadata=[{"from_email": "someone@example.com"}],
            direction="EMAIL",
            is_thread_split=False,
        )
        await db.commit()

        result = await split_email_threads(db)

        assert result["candidates"] == 0
        assert result["threads_split"] == 0

    async def test_skips_already_split_email(self, db, make_email, make_settings):
        await make_settings(
            thread_split_indicators=["From:"],
            thread_splitter_prompt_blocks={"opening": "x", "messages": "y", "closing": "z"},
        )
        await make_email(
            body_text=THREAD_BODY,
            quoted_metadata=[{"from_email": "mark@prospect.com"}],
            direction="EMAIL",
            is_thread_split=True,
        )
        await db.commit()

        result = await split_email_threads(db)

        assert result["candidates"] == 0
        assert result["threads_split"] == 0

    async def test_skips_email_without_quoted_metadata(self, db, make_email, make_settings):
        await make_settings(
            thread_split_indicators=["From:"],
            thread_splitter_prompt_blocks={"opening": "x", "messages": "y", "closing": "z"},
        )
        await make_email(
            body_text=THREAD_BODY,
            quoted_metadata=None,
            direction="EMAIL",
            is_thread_split=False,
        )
        await db.commit()

        result = await split_email_threads(db)

        assert result["candidates"] == 0

    @patch("app.services.thread_splitter.AsyncAnthropic")
    async def test_splits_thread_creates_children(
        self, mock_anthropic_cls, db, make_email, make_settings
    ):
        await make_settings(
            thread_split_indicators=["From:"],
            thread_splitter_prompt_blocks={"opening": "x", "messages": "y", "closing": "z"},
        )
        parent = await make_email(
            from_email="priyanka@nativecampusadvertising.com",
            subject="Re: Partnership Opportunity",
            body_text=THREAD_BODY,
            quoted_metadata=[{"from_email": "mark@prospect.com"}],
            direction="EMAIL",
            is_thread_split=False,
        )
        await db.commit()

        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_haiku_response(HAIKU_RESPONSE)

        result = await split_email_threads(db)

        assert result["threads_split"] == 1
        assert result["messages_created"] == 2

        # Parent body trimmed to top-level message
        await db.refresh(parent)
        assert parent.is_thread_split is True
        assert "Just following up" in parent.body_text
        assert "From: Mark Jones" not in parent.body_text

        # Children created with correct split_from_id
        children = (await db.execute(
            select(Email).where(Email.split_from_id == parent.id)
        )).scalars().all()
        assert len(children) == 2
        child_emails = {c.from_email for c in children}
        assert "mark@prospect.com" in child_emails
        assert "priyanka@nativecampusadvertising.com" in child_emails

    @patch("app.services.thread_splitter.AsyncAnthropic")
    async def test_dedup_skips_existing_email(
        self, mock_anthropic_cls, db, make_email, make_settings
    ):
        await make_settings(
            thread_split_indicators=["From:"],
            thread_splitter_prompt_blocks={"opening": "x", "messages": "y", "closing": "z"},
        )
        # Pre-existing email that matches one of the quoted messages
        await make_email(
            from_email="mark@prospect.com",
            subject="Re: Partnership Opportunity",
            body_text="Thanks Priyanka, let me think about it.",
            direction="INCOMING_EMAIL",
        )
        parent = await make_email(
            from_email="priyanka@nativecampusadvertising.com",
            subject="Re: Partnership Opportunity",
            body_text=THREAD_BODY,
            quoted_metadata=[{"from_email": "mark@prospect.com"}],
            direction="EMAIL",
            is_thread_split=False,
        )
        await db.commit()

        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_haiku_response(HAIKU_RESPONSE)

        result = await split_email_threads(db)

        assert result["threads_split"] == 1
        assert result["duplicates_skipped"] >= 1
        # Only 1 child created (the original Priyanka email), Mark's was deduped
        children = (await db.execute(
            select(Email).where(Email.split_from_id == parent.id)
        )).scalars().all()
        assert len(children) == 1

    @patch("app.services.thread_splitter.AsyncAnthropic")
    async def test_idempotent_second_run(
        self, mock_anthropic_cls, db, make_email, make_settings
    ):
        await make_settings(
            thread_split_indicators=["From:"],
            thread_splitter_prompt_blocks={"opening": "x", "messages": "y", "closing": "z"},
        )
        await make_email(
            from_email="priyanka@nativecampusadvertising.com",
            subject="Re: Partnership Opportunity",
            body_text=THREAD_BODY,
            quoted_metadata=[{"from_email": "mark@prospect.com"}],
            direction="EMAIL",
            is_thread_split=False,
        )
        await db.commit()

        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_haiku_response(HAIKU_RESPONSE)

        # First run
        await split_email_threads(db)
        # Second run - should find nothing to do
        result = await split_email_threads(db)

        assert result["candidates"] == 0
        assert result["threads_split"] == 0

    @patch("app.services.thread_splitter.AsyncAnthropic")
    async def test_infers_direction_from_company_domains(
        self, mock_anthropic_cls, db, make_email, make_settings
    ):
        await make_settings(
            thread_split_indicators=["From:"],
            thread_splitter_prompt_blocks={"opening": "x", "messages": "y", "closing": "z"},
        )
        parent = await make_email(
            from_email="priyanka@nativecampusadvertising.com",
            subject="Re: Partnership Opportunity",
            body_text=THREAD_BODY,
            quoted_metadata=[{"from_email": "mark@prospect.com"}],
            direction="EMAIL",
            is_thread_split=False,
        )
        await db.commit()

        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_haiku_response(HAIKU_RESPONSE)

        await split_email_threads(db)

        children = (await db.execute(
            select(Email).where(Email.split_from_id == parent.id)
        )).scalars().all()
        for child in children:
            domain = child.from_email.split("@")[1]
            if domain == "nativecampusadvertising.com":
                assert child.direction == "EMAIL"
            else:
                assert child.direction == "INCOMING_EMAIL"

    async def test_no_prompt_blocks_returns_early(self, db, make_email, make_settings):
        await make_settings(
            thread_split_indicators=["From:"],
            thread_splitter_prompt_blocks=None,
        )
        await make_email(
            body_text=THREAD_BODY,
            quoted_metadata=[{"from_email": "mark@prospect.com"}],
            direction="EMAIL",
            is_thread_split=False,
        )
        await db.commit()

        result = await split_email_threads(db)

        assert result["candidates"] == 0
