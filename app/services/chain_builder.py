"""Groups emails into conversation chains using message headers, thread IDs, and subject matching."""

import re
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import EmailDirection
from app.models.chain import EmailChain
from app.models.email import Email

_PREFIX_PATTERN = re.compile(r"^(Re|RE|Fwd|FW|Fw):\s*")


def normalize_subject(subject: str | None) -> str:
    if subject is None:
        return ""
    result = subject
    while True:
        new_result = _PREFIX_PATTERN.sub("", result)
        if new_result == result:
            break
        result = new_result
    return result.strip()


def _email_participants(email: Email) -> set[str]:
    participants = set()
    if email.from_email:
        participants.add(email.from_email.lower())
    if email.to_email:
        participants.add(email.to_email.lower())
    return participants


def _is_outgoing(email: Email) -> bool:
    return email.direction == EmailDirection.EMAIL


async def build_chains(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Email).order_by(Email.timestamp.asc().nullslast(), Email.id.asc())
    )
    emails = list(result.scalars().all())

    if not emails:
        return {"chains_created": 0, "chains_updated": 0, "emails_linked": 0}

    # Union-Find to group emails
    # email.id -> group leader email.id
    parent: dict[int, int] = {e.id: e.id for e in emails}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    email_by_id = {e.id: e for e in emails}
    msg_id_to_email: dict[str, Email] = {}
    for e in emails:
        if e.message_id:
            msg_id_to_email[e.message_id] = e

    # Track which emails got linked by message_id threading
    message_id_linked: set[int] = set()

    # Pass 1: in_reply_to / message_id matching
    for e in emails:
        if e.in_reply_to and e.in_reply_to in msg_id_to_email:
            parent_email = msg_id_to_email[e.in_reply_to]
            union(parent_email.id, e.id)
            message_id_linked.add(e.id)
            message_id_linked.add(parent_email.id)

    # Pass 2: thread_id matching (only for emails not already chained by message_id)
    thread_groups: dict[str, list[Email]] = defaultdict(list)
    for e in emails:
        if e.id not in message_id_linked and e.thread_id:
            thread_groups[e.thread_id].append(e)

    # Also add message_id-linked emails' thread_ids to prevent merging
    # across existing chains via thread_id
    for tid, group in thread_groups.items():
        if len(group) >= 2:
            first = group[0]
            for other in group[1:]:
                union(first.id, other.id)

    # Pass 3: subject normalization + participant overlap + time proximity
    # Only for emails still in singleton groups
    def is_unchained(e: Email) -> bool:
        eid = e.id
        root = find(eid)
        # Check if this email is alone in its group
        for other in emails:
            if other.id != eid and find(other.id) == root:
                return False
        return True

    unchained = [e for e in emails if is_unchained(e)]

    # Group unchained emails by normalized subject
    subject_groups: dict[str, list[Email]] = defaultdict(list)
    for e in unchained:
        ns = normalize_subject(e.subject)
        if ns:
            subject_groups[ns].append(e)

    for ns, group in subject_groups.items():
        if len(group) < 2:
            continue
        # Sort by timestamp
        group.sort(key=lambda e: (e.timestamp or datetime.min, e.id))
        for i, e in enumerate(group):
            e_participants = _email_participants(e)
            for j in range(i + 1, len(group)):
                other = group[j]
                # Already in same group?
                if find(e.id) == find(other.id):
                    continue
                other_participants = _email_participants(other)
                # Check participant overlap
                if not e_participants & other_participants:
                    continue
                # Check time proximity (30 days)
                if e.timestamp and other.timestamp:
                    if abs((other.timestamp - e.timestamp).total_seconds()) > 30 * 86400:
                        continue
                union(e.id, other.id)

    # Build final groups
    groups: dict[int, list[Email]] = defaultdict(list)
    for e in emails:
        groups[find(e.id)].append(e)

    # Filter to groups with 2+ emails
    chain_groups = {k: v for k, v in groups.items() if len(v) >= 2}

    # Clear existing chain assignments for all emails (idempotency)
    # First, collect all existing chain_ids
    existing_chain_ids = set()
    for e in emails:
        if e.chain_id is not None:
            existing_chain_ids.add(e.chain_id)
        e.chain_id = None
        e.position_in_chain = None

    chains_created = 0
    chains_updated = 0
    emails_linked = 0

    # Load existing chains for potential reuse
    existing_chains: dict[int, EmailChain] = {}
    if existing_chain_ids:
        chain_result = await session.execute(
            select(EmailChain).where(EmailChain.id.in_(existing_chain_ids))
        )
        for c in chain_result.scalars().all():
            existing_chains[c.id] = c

    # Delete existing chains and recreate (simpler for idempotency)
    for chain in existing_chains.values():
        await session.delete(chain)
    await session.flush()

    for group_emails in chain_groups.values():
        group_emails.sort(key=lambda e: (e.timestamp or datetime.min, e.id))

        all_participants: set[str] = set()
        outgoing = 0
        incoming = 0
        for e in group_emails:
            all_participants |= _email_participants(e)
            if _is_outgoing(e):
                outgoing += 1
            else:
                incoming += 1

        first_email = group_emails[0]
        chain = EmailChain(
            normalized_subject=normalize_subject(first_email.subject),
            participants=",".join(sorted(all_participants)),
            started_at=group_emails[0].timestamp,
            last_activity_at=group_emails[-1].timestamp,
            email_count=len(group_emails),
            outgoing_count=outgoing,
            incoming_count=incoming,
        )
        session.add(chain)
        await session.flush()

        chains_created += 1

        for pos, e in enumerate(group_emails, start=1):
            e.chain_id = chain.id
            e.position_in_chain = pos
            emails_linked += 1

    await session.flush()

    return {
        "chains_created": chains_created,
        "chains_updated": chains_updated,
        "emails_linked": emails_linked,
    }
