import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic import AsyncAnthropic

from app.services.classifier import (
    _matches_subject_pattern,
    classify_emails,
)


class TestMatchesSubjectPattern:
    def test_automatic_reply(self):
        assert _matches_subject_pattern("Automatic reply: Meeting") is True

    def test_out_of_office(self):
        assert _matches_subject_pattern("Out of Office: Back Monday") is True

    def test_ooo(self):
        assert _matches_subject_pattern("OOO: Vacation") is True

    def test_accepted(self):
        assert _matches_subject_pattern("Accepted: Lunch Meeting") is True

    def test_declined(self):
        assert _matches_subject_pattern("Declined: Team Standup") is True

    def test_tentative(self):
        assert _matches_subject_pattern("Tentative: Planning Session") is True

    def test_undeliverable(self):
        assert _matches_subject_pattern("Undeliverable: Hello") is True

    def test_mail_delivery_failed(self):
        assert _matches_subject_pattern("Mail Delivery Failed: Test") is True

    def test_normal_subject_no_match(self):
        assert _matches_subject_pattern("Re: Let's connect") is False

    def test_none_subject(self):
        assert _matches_subject_pattern(None) is False

    def test_empty_subject(self):
        assert _matches_subject_pattern("") is False

    def test_case_insensitive(self):
        assert _matches_subject_pattern("automatic reply: Test") is True
        assert _matches_subject_pattern("OUT OF OFFICE: Gone") is True


class TestClassifyEmails:
    async def test_pattern_match_marks_auto_reply(self, db, make_email):
        e = await make_email(
            direction="INCOMING_EMAIL",
            subject="Automatic reply: Out of Office",
            is_auto_reply=False,
            quoted_metadata=None,
        )
        await db.flush()

        summary = await classify_emails(db)

        assert summary["total"] >= 1, f"Classifier found no emails, summary: {summary}"
        assert summary["auto_replies_found"] >= 1
        await db.refresh(e)
        assert e.is_auto_reply is True

    async def test_skips_already_classified_emails(self, db, make_email):
        await make_email(
            direction="INCOMING_EMAIL",
            subject="Re: Hello",
            is_auto_reply=False,
            quoted_metadata=[{"from_email": "a@b.com", "subject": "Hello"}],
        )
        await db.commit()

        summary = await classify_emails(db)
        assert summary["total"] == 0

    async def test_includes_outgoing_emails(self, db, make_email, make_settings):
        e = await make_email(
            direction="EMAIL",
            subject="Re: SD-123 Support ticket",
            body_text="Great thanks",
            to_email="support@native-fm.atlassian.net",
            is_auto_reply=False,
            quoted_metadata=None,
        )
        await db.commit()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({"email_type": "not_sales", "quoted_emails": []})
        )]

        with patch("app.services.classifier.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock(spec=AsyncAnthropic)
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client

            summary = await classify_emails(db)

        assert summary["total"] >= 1
        assert summary["auto_replies_found"] >= 1
        await db.refresh(e)
        assert e.is_auto_reply is True

    async def test_outgoing_pattern_match_skipped(self, db, make_email):
        """Subject patterns only apply to incoming emails, not outgoing."""
        await make_email(
            direction="EMAIL",
            subject="Automatic reply: Out of Office",
            body_text="I am out of office",
            is_auto_reply=False,
            quoted_metadata=None,
        )
        await db.commit()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({"email_type": "auto_reply", "quoted_emails": []})
        )]

        with patch("app.services.classifier.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock(spec=AsyncAnthropic)
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client

            summary = await classify_emails(db)

        # Outgoing email with auto-reply subject should go through Haiku, not pattern match
        assert summary["total"] >= 1
        mock_client.messages.create.assert_called()

    async def test_returns_summary_keys(self, db, make_email):
        summary = await classify_emails(db)
        assert "total" in summary
        assert "classified" in summary
        assert "auto_replies_found" in summary
        assert "chains_extracted" in summary
        assert "errors" in summary

    async def test_haiku_classifies_remaining(self, db, make_email, make_settings):
        e = await make_email(
            direction="INCOMING_EMAIL",
            subject="Re: Let's connect",
            body_text="I'm interested in learning more.",
            is_auto_reply=False,
            quoted_metadata=None,
        )
        await db.commit()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({"email_type": "real_email", "quoted_emails": []})
        )]

        with patch("app.services.classifier.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock(spec=AsyncAnthropic)
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client

            summary = await classify_emails(db)

        assert summary["classified"] >= 1
        await db.refresh(e)
        assert e.is_auto_reply is False

    async def test_haiku_detects_auto_reply(self, db, make_email, make_settings):
        e = await make_email(
            direction="INCOMING_EMAIL",
            subject="Re: Meeting",
            body_text="I am currently out of the office with limited access to email.",
            is_auto_reply=False,
            quoted_metadata=None,
        )
        await db.commit()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({"email_type": "auto_reply", "quoted_emails": []})
        )]

        with patch("app.services.classifier.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock(spec=AsyncAnthropic)
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client

            summary = await classify_emails(db)

        await db.refresh(e)
        assert e.is_auto_reply is True
        assert summary["auto_replies_found"] >= 1

    async def test_haiku_extracts_quoted_metadata(self, db, make_email, make_settings):
        e = await make_email(
            direction="INCOMING_EMAIL",
            subject="Re: Partnership",
            body_text="Sounds good!\n\nOn Jan 1 alice wrote:\n> Let's partner up",
            is_auto_reply=False,
            quoted_metadata=None,
        )
        await db.commit()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({
                "email_type": "real_email",
                "quoted_emails": [{"from_email": "alice@x.com", "subject": "Partnership"}],
            })
        )]

        with patch("app.services.classifier.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock(spec=AsyncAnthropic)
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client

            summary = await classify_emails(db)

        await db.refresh(e)
        assert e.quoted_metadata is not None
        assert len(e.quoted_metadata) == 1
        assert summary["chains_extracted"] >= 1
