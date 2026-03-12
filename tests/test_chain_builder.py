from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.chain import EmailChain
from app.models.chain_score import ChainScore
from app.models.email import Email
from app.services.chain_builder import build_chains, normalize_subject, update_chains_for_emails


class TestNormalizeSubject:
    def test_strips_re_prefix(self):
        assert normalize_subject("Re: Hello") == "Hello"

    def test_strips_uppercase_re_prefix(self):
        assert normalize_subject("RE: Hello") == "Hello"

    def test_strips_fwd_prefix(self):
        assert normalize_subject("Fwd: Hello") == "Hello"

    def test_strips_fw_uppercase_prefix(self):
        assert normalize_subject("FW: Hello") == "Hello"

    def test_strips_fw_mixed_case_prefix(self):
        assert normalize_subject("Fw: Hello") == "Hello"

    def test_strips_multiple_nested_prefixes(self):
        assert normalize_subject("Re: Fwd: Re: Hello") == "Hello"

    def test_trims_whitespace_after_stripping(self):
        assert normalize_subject("Re:   Hello  ") == "Hello"

    def test_returns_original_when_no_prefixes(self):
        assert normalize_subject("Hello World") == "Hello World"

    def test_handles_empty_string(self):
        assert normalize_subject("") == ""

    def test_handles_none(self):
        assert normalize_subject(None) == ""

    def test_strips_email_arrow_prefix(self):
        assert normalize_subject("Email: >> Hello") == "Hello"

    def test_strips_email_arrow_with_extra_spaces(self):
        assert normalize_subject("Email: >>  Hello") == "Hello"

    def test_strips_nested_email_arrow_and_re(self):
        assert normalize_subject("Re: Email: >> Hello") == "Hello"


class TestBuildChainsMessageIdMatching:
    async def test_links_two_emails_via_in_reply_to(self, db, make_email):
        e1 = await make_email(
            message_id="<msg1@example.com>",
            subject="Hello",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<msg2@example.com>",
            in_reply_to="<msg1@example.com>",
            subject="Re: Hello",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        result = await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id is not None
        assert e1.chain_id == e2.chain_id
        assert result["emails_linked"] == 2

    async def test_builds_three_email_chain_via_successive_message_id(
        self, db, make_email
    ):
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Topic",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        e3 = await make_email(
            message_id="<c@x.com>",
            in_reply_to="<b@x.com>",
            subject="Re: Re: Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 12, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        await db.refresh(e3)
        assert e1.chain_id == e2.chain_id == e3.chain_id

    async def test_position_in_chain_set_correctly(self, db, make_email):
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Topic",
            from_email="alice@test.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Topic",
            from_email="bob@other.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        e3 = await make_email(
            message_id="<c@x.com>",
            in_reply_to="<b@x.com>",
            subject="Re: Re: Topic",
            from_email="alice@test.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 12, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        await db.refresh(e3)
        assert e1.position_in_chain == 1
        assert e2.position_in_chain == 2
        assert e3.position_in_chain == 3

    async def test_chain_aggregate_fields(self, db, make_email):
        await make_email(
            message_id="<a@x.com>",
            subject="Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Topic",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 2, 10, 0),
        )
        await make_email(
            message_id="<c@x.com>",
            in_reply_to="<b@x.com>",
            subject="Re: Re: Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 3, 10, 0),
        )
        await db.commit()

        await build_chains(db)

        result = await db.execute(select(EmailChain))
        chain = result.scalar_one()
        assert chain.email_count == 3
        assert chain.outgoing_count == 2
        assert chain.incoming_count == 1
        assert chain.started_at == datetime(2025, 1, 1, 10, 0)
        assert chain.last_activity_at == datetime(2025, 1, 3, 10, 0)


class TestBuildChainsThreadIdMatching:
    async def test_groups_by_shared_thread_id(self, db, make_email):
        e1 = await make_email(
            thread_id="thread-abc",
            subject="Hello",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            thread_id="thread-abc",
            subject="Different Subject",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id is not None
        assert e1.chain_id == e2.chain_id

    async def test_does_not_merge_message_id_chains_by_thread_id(
        self, db, make_email
    ):
        # Chain 1: linked by message_id
        e1 = await make_email(
            message_id="<a@x.com>",
            thread_id="shared-thread",
            subject="Topic A",
            from_email="alice@test.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            in_reply_to="<a@x.com>",
            message_id="<b@x.com>",
            thread_id="shared-thread",
            subject="Re: Topic A",
            from_email="bob@other.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        # Chain 2: linked by message_id, shares thread_id with chain 1
        e3 = await make_email(
            message_id="<c@x.com>",
            thread_id="shared-thread",
            subject="Topic B",
            from_email="carol@test.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 12, 0),
        )
        e4 = await make_email(
            in_reply_to="<c@x.com>",
            message_id="<d@x.com>",
            thread_id="shared-thread",
            subject="Re: Topic B",
            from_email="dave@other.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 13, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        await db.refresh(e3)
        await db.refresh(e4)
        assert e1.chain_id == e2.chain_id
        assert e3.chain_id == e4.chain_id
        assert e1.chain_id != e3.chain_id


class TestSubjectMatchingParticipantOverlap:
    async def test_same_subject_same_sender_different_recipients_not_chained(
        self, db, make_email
    ):
        e1 = await make_email(
            subject="Campus Fair Invite",
            from_email="rep@native.fm",
            to_email="prospect1@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            subject="Campus Fair Invite",
            from_email="rep@native.fm",
            to_email="prospect2@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id is None
        assert e2.chain_id is None

    async def test_same_subject_shared_recipient_chained(
        self, db, make_email
    ):
        e1 = await make_email(
            subject="Campus Fair Invite",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            subject="Re: Campus Fair Invite",
            from_email="prospect@example.com",
            to_email="rep@native.fm",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        # Subject matching groups them because prospect appears in both
        # participant sets and is not just a sender overlap
        assert e1.chain_id is not None
        assert e1.chain_id == e2.chain_id

    async def test_reply_from_prospect_chains_correctly(
        self, db, make_email
    ):
        e1 = await make_email(
            subject="Campus Fair Invite",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            subject="Re: Campus Fair Invite",
            from_email="prospect@example.com",
            to_email="rep@native.fm",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id is not None
        assert e1.chain_id == e2.chain_id


class TestBuildChainsSubjectFallback:
    async def test_groups_by_normalized_subject_and_participant_overlap(
        self, db, make_email
    ):
        e1 = await make_email(
            subject="Meeting Follow-up",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            subject="Re: Meeting Follow-up",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 5, 10, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id is not None
        assert e1.chain_id == e2.chain_id

    async def test_does_not_group_without_participant_overlap(
        self, db, make_email
    ):
        e1 = await make_email(
            subject="Meeting Follow-up",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            subject="Re: Meeting Follow-up",
            from_email="carol@different.com",
            to_email="dave@different.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 5, 10, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        # They should not share a chain
        assert e1.chain_id is None or e2.chain_id is None or e1.chain_id != e2.chain_id

    async def test_does_not_group_beyond_30_day_window(self, db, make_email):
        e1 = await make_email(
            subject="Meeting Follow-up",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            subject="Re: Meeting Follow-up",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 3, 1, 10, 0),  # > 30 days later
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id is None or e2.chain_id is None or e1.chain_id != e2.chain_id

    async def test_leaves_unmatched_emails_unchained(self, db, make_email):
        e1 = await make_email(
            subject="Unique Subject",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        assert e1.chain_id is None


class TestChainCreationCriteria:
    async def test_all_outgoing_no_chain_record(self, db, make_email):
        e1 = await make_email(
            subject="Campus Fair Invite",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            subject="Campus Fair Invite",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 2, 10, 0),
        )
        e3 = await make_email(
            subject="Campus Fair Invite",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 3, 10, 0),
        )
        await db.commit()

        await build_chains(db)

        result = await db.execute(select(EmailChain))
        assert result.scalars().all() == []
        await db.refresh(e1)
        await db.refresh(e2)
        await db.refresh(e3)
        assert e1.chain_id is None
        assert e2.chain_id is None
        assert e3.chain_id is None

    async def test_prospect_reply_no_rep_followup_creates_unanswered_chain(
        self, db, make_email
    ):
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Hello",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Hello",
            from_email="prospect@example.com",
            to_email="rep@native.fm",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)

        result = await db.execute(select(EmailChain))
        chain = result.scalar_one()
        assert chain.is_unanswered is True
        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id == chain.id
        assert e2.chain_id == chain.id

    async def test_back_and_forth_creates_chain(self, db, make_email):
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Hello",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Hello",
            from_email="prospect@example.com",
            to_email="rep@native.fm",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        e3 = await make_email(
            message_id="<c@x.com>",
            in_reply_to="<b@x.com>",
            subject="Re: Re: Hello",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 12, 0),
        )
        await db.commit()

        await build_chains(db)

        result = await db.execute(select(EmailChain))
        chain = result.scalar_one()
        assert chain.is_unanswered is False
        await db.refresh(e1)
        await db.refresh(e2)
        await db.refresh(e3)
        assert e1.chain_id == chain.id
        assert e2.chain_id == chain.id
        assert e3.chain_id == chain.id

    async def test_chain_detection_checks_timestamp_order(self, db, make_email):
        # Outgoing before incoming doesn't count as back-and-forth on its own
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Hello",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Hello",
            from_email="prospect@example.com",
            to_email="rep@native.fm",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)

        result = await db.execute(select(EmailChain))
        chain = result.scalar_one()
        # Only outgoing before incoming, no outgoing after - this is unanswered
        assert chain.is_unanswered is True


class TestBuildChainsIdempotency:
    async def test_idempotent_same_result_on_second_run(self, db, make_email):
        await make_email(
            message_id="<a@x.com>",
            subject="Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        await make_email(
            in_reply_to="<a@x.com>",
            message_id="<b@x.com>",
            subject="Re: Topic",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        result1 = await build_chains(db)
        await db.commit()

        # Capture state after first run
        emails_result = await db.execute(
            select(Email).order_by(Email.timestamp)
        )
        emails = emails_result.scalars().all()
        positions_1 = [e.position_in_chain for e in emails]
        # Emails sharing a chain_id are in the same group
        same_chain_1 = emails[0].chain_id == emails[1].chain_id

        result2 = await build_chains(db)
        await db.commit()

        emails_result = await db.execute(
            select(Email).order_by(Email.timestamp)
        )
        emails = emails_result.scalars().all()
        positions_2 = [e.position_in_chain for e in emails]
        same_chain_2 = emails[0].chain_id == emails[1].chain_id

        assert positions_1 == positions_2
        assert same_chain_1 == same_chain_2

    async def test_incorporates_new_email_on_rerun(self, db, make_email):
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        await db.commit()

        await build_chains(db)
        await db.commit()

        # Add a reply
        e2 = await make_email(
            in_reply_to="<a@x.com>",
            message_id="<b@x.com>",
            subject="Re: Topic",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)
        await db.commit()

        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id is not None
        assert e1.chain_id == e2.chain_id


class TestChainScorePreservationAcrossParticipantChange:
    async def test_score_preserved_when_new_participant_joins(
        self, db, make_email, make_chain_score
    ):
        """When a new participant joins an existing thread, the participants
        string changes on rebuild. The chain score should still be reattached
        using normalized_subject as a fallback key."""
        # First run: two-email chain between alice and bob
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Campaign",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Campaign",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)
        await db.commit()

        # Get the chain and attach a score
        chain_result = await db.execute(select(EmailChain))
        chain = chain_result.scalar_one()
        original_chain_id = chain.id

        chain_score = ChainScore(
            chain_id=chain.id,
            progression=8,
            responsiveness=7,
            persistence=6,
            conversation_quality=9,
            scored_at=datetime(2025, 1, 2),
        )
        db.add(chain_score)
        await db.commit()

        # Now a new participant (carol) joins the thread
        e3 = await make_email(
            message_id="<c@x.com>",
            in_reply_to="<b@x.com>",
            subject="Re: Re: Campaign",
            from_email="carol@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 2, 10, 0),
        )
        await db.commit()

        # Rebuild chains - participants string now includes carol
        await build_chains(db)
        await db.commit()

        # The chain should exist and the score should be preserved
        chain_result = await db.execute(select(EmailChain))
        new_chain = chain_result.scalar_one()
        assert new_chain.email_count == 3

        score_result = await db.execute(
            select(ChainScore).where(ChainScore.chain_id == new_chain.id)
        )
        preserved_score = score_result.scalar_one_or_none()
        assert preserved_score is not None, (
            "Chain score was lost when a new participant joined the thread"
        )
        assert preserved_score.progression == 8
        assert preserved_score.conversation_quality == 9


class TestAutoReplyExclusion:
    async def test_auto_reply_not_counted_as_incoming(self, db, make_email):
        """Auto-reply emails don't count as incoming; group with only outgoing
        + auto-reply should not create a chain."""
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Hello",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Automatic reply: Hello",
            from_email="prospect@example.com",
            to_email="rep@native.fm",
            direction="INCOMING_EMAIL",
            is_auto_reply=True,
            timestamp=datetime(2025, 1, 1, 10, 5),
        )
        await db.commit()

        await build_chains(db)

        result = await db.execute(select(EmailChain))
        assert result.scalars().all() == []

    async def test_auto_reply_unlinked_from_chain(self, db, make_email):
        """Auto-reply emails are unlinked from chains after building."""
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Hello",
            from_email="rep@native.fm",
            to_email="prospect@example.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Automatic reply: Hello",
            from_email="prospect@example.com",
            to_email="rep@native.fm",
            direction="INCOMING_EMAIL",
            is_auto_reply=True,
            timestamp=datetime(2025, 1, 1, 10, 5),
        )
        e3 = await make_email(
            message_id="<c@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Hello",
            from_email="prospect@example.com",
            to_email="rep@native.fm",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 12, 0),
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        await db.refresh(e3)
        assert e1.chain_id is not None
        assert e2.chain_id is None  # auto-reply unlinked
        assert e3.chain_id == e1.chain_id


class TestQuotedContentMatching:
    async def test_links_unchained_email_via_quoted_metadata(self, db, make_email):
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Partnership",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Partnership",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        # Unchained email with quoted metadata matching e1
        e3 = await make_email(
            subject="FW: Partnership",
            from_email="bob@other.com",
            to_email="carol@other.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 2, 10, 0),
            quoted_metadata=[{"from_email": "alice@test.com", "subject": "Partnership"}],
        )
        await db.commit()

        await build_chains(db)

        await db.refresh(e1)
        await db.refresh(e2)
        await db.refresh(e3)
        assert e1.chain_id is not None
        assert e3.chain_id == e1.chain_id


class TestUpdateChainsForEmails:
    async def test_new_reply_joins_existing_chain(self, db, make_email):
        """A new incoming email via in_reply_to should join an existing chain."""
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Topic",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        # Build initial chains
        await build_chains(db)
        await db.commit()

        await db.refresh(e1)
        original_chain_id = e1.chain_id
        assert original_chain_id is not None

        # Add a new reply
        e3 = await make_email(
            message_id="<c@x.com>",
            in_reply_to="<b@x.com>",
            subject="Re: Re: Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 12, 0),
        )
        await db.commit()

        result = await update_chains_for_emails(db, {e3.id})
        await db.commit()

        await db.refresh(e1)
        await db.refresh(e2)
        await db.refresh(e3)
        # All three should be in the same chain
        assert e1.chain_id == e2.chain_id == e3.chain_id
        # The chain ID should be preserved from the original build
        assert e1.chain_id == original_chain_id

    async def test_preserves_chain_score(self, db, make_email):
        """Existing chain scores should survive incremental updates."""
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Campaign",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Campaign",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)
        await db.commit()

        # Add a chain score
        chain_result = await db.execute(select(EmailChain))
        chain = chain_result.scalar_one()
        score = ChainScore(
            chain_id=chain.id,
            progression=8, responsiveness=7,
            persistence=6, conversation_quality=9,
            scored_at=datetime(2025, 1, 2),
        )
        db.add(score)
        await db.commit()

        # Add a new email to the chain
        e3 = await make_email(
            message_id="<c@x.com>",
            in_reply_to="<b@x.com>",
            subject="Re: Re: Campaign",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 2, 10, 0),
        )
        await db.commit()

        await update_chains_for_emails(db, {e3.id})
        await db.commit()

        # Chain score should still exist
        score_result = await db.execute(
            select(ChainScore).where(ChainScore.chain_id == chain.id)
        )
        preserved = score_result.scalar_one_or_none()
        assert preserved is not None
        assert preserved.progression == 8
        assert preserved.conversation_quality == 9

    async def test_preserves_unrelated_chains(self, db, make_email):
        """Chains not touched by new emails remain unchanged."""
        # Chain 1
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Topic A",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Topic A",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)
        await db.commit()

        await db.refresh(e1)
        chain_a_id = e1.chain_id
        assert chain_a_id is not None

        # Add score to chain A
        score_a = ChainScore(
            chain_id=chain_a_id,
            progression=7, responsiveness=8,
            persistence=5, conversation_quality=6,
            scored_at=datetime(2025, 1, 2),
        )
        db.add(score_a)
        await db.commit()

        # New emails forming a completely separate chain
        e3 = await make_email(
            message_id="<x@y.com>",
            subject="Topic B",
            from_email="carol@test.com",
            to_email="dave@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 2, 1, 10, 0),
        )
        e4 = await make_email(
            message_id="<y@y.com>",
            in_reply_to="<x@y.com>",
            subject="Re: Topic B",
            from_email="dave@other.com",
            to_email="carol@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 2, 1, 11, 0),
        )
        await db.commit()

        await update_chains_for_emails(db, {e3.id, e4.id})
        await db.commit()

        # Chain A should be completely untouched
        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id == chain_a_id
        assert e2.chain_id == chain_a_id

        # Chain A score should be preserved
        score_result = await db.execute(
            select(ChainScore).where(ChainScore.chain_id == chain_a_id)
        )
        assert score_result.scalar_one_or_none() is not None

        # New chain B should be created
        await db.refresh(e3)
        await db.refresh(e4)
        assert e3.chain_id is not None
        assert e3.chain_id == e4.chain_id
        assert e3.chain_id != chain_a_id

    async def test_creates_new_chain_from_new_emails(self, db, make_email):
        """When new emails form a new group, a new chain is created."""
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Hello",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Hello",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        result = await update_chains_for_emails(db, {e1.id, e2.id})
        await db.commit()

        await db.refresh(e1)
        await db.refresh(e2)
        assert e1.chain_id is not None
        assert e1.chain_id == e2.chain_id
        assert result["chains_created"] >= 1

    async def test_updates_chain_metadata(self, db, make_email):
        """Chain metadata (email_count, last_activity_at, etc.) updated when email added."""
        e1 = await make_email(
            message_id="<a@x.com>",
            subject="Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            message_id="<b@x.com>",
            in_reply_to="<a@x.com>",
            subject="Re: Topic",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)
        await db.commit()

        chain_result = await db.execute(select(EmailChain))
        chain = chain_result.scalar_one()
        assert chain.email_count == 2
        original_chain_id = chain.id

        # Add new email to chain
        e3 = await make_email(
            message_id="<c@x.com>",
            in_reply_to="<b@x.com>",
            subject="Re: Re: Topic",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 2, 10, 0),
        )
        await db.commit()

        await update_chains_for_emails(db, {e3.id})
        await db.commit()

        # Re-fetch chain and check metadata
        chain_result = await db.execute(
            select(EmailChain).where(EmailChain.id == original_chain_id)
        )
        chain = chain_result.scalar_one()
        assert chain.email_count == 3
        assert chain.outgoing_count == 2
        assert chain.incoming_count == 1
        assert chain.last_activity_at == datetime(2025, 1, 2, 10, 0)
        assert chain.is_unanswered is False

    async def test_thread_id_matching(self, db, make_email):
        """New email matched by thread_id joins existing chain."""
        e1 = await make_email(
            thread_id="thread-abc",
            subject="Hello",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            thread_id="thread-abc",
            subject="Re: Hello",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 1, 11, 0),
        )
        await db.commit()

        await build_chains(db)
        await db.commit()

        await db.refresh(e1)
        original_chain_id = e1.chain_id

        e3 = await make_email(
            thread_id="thread-abc",
            subject="Re: Re: Hello",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 12, 0),
        )
        await db.commit()

        await update_chains_for_emails(db, {e3.id})
        await db.commit()

        await db.refresh(e3)
        assert e3.chain_id == original_chain_id

    async def test_subject_matching(self, db, make_email):
        """New email matched by subject + participant overlap joins existing chain."""
        e1 = await make_email(
            subject="Meeting Follow-up",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 1, 10, 0),
        )
        e2 = await make_email(
            subject="Re: Meeting Follow-up",
            from_email="bob@other.com",
            to_email="alice@test.com",
            direction="INCOMING_EMAIL",
            timestamp=datetime(2025, 1, 5, 10, 0),
        )
        await db.commit()

        await build_chains(db)
        await db.commit()

        await db.refresh(e1)
        original_chain_id = e1.chain_id

        e3 = await make_email(
            subject="Re: Meeting Follow-up",
            from_email="alice@test.com",
            to_email="bob@other.com",
            direction="EMAIL",
            timestamp=datetime(2025, 1, 10, 10, 0),
        )
        await db.commit()

        await update_chains_for_emails(db, {e3.id})
        await db.commit()

        await db.refresh(e3)
        assert e3.chain_id == original_chain_id

    async def test_empty_email_ids_no_op(self, db):
        """Passing empty set of IDs returns immediately."""
        result = await update_chains_for_emails(db, set())
        assert result["chains_created"] == 0
        assert result["chains_updated"] == 0
        assert result["emails_linked"] == 0
