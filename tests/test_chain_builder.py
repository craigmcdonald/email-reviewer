from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.chain import EmailChain
from app.models.email import Email
from app.services.chain_builder import build_chains, normalize_subject


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
        chain_ids_1 = [(e.chain_id, e.position_in_chain) for e in emails]

        result2 = await build_chains(db)
        await db.commit()

        emails_result = await db.execute(
            select(Email).order_by(Email.timestamp)
        )
        emails = emails_result.scalars().all()
        chain_ids_2 = [(e.chain_id, e.position_in_chain) for e in emails]

        assert chain_ids_1 == chain_ids_2

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
