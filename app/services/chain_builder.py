"""Groups emails into conversation chains using message headers, thread IDs, and subject matching."""

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from app.enums import EmailDirection
from app.models.chain import EmailChain
from app.models.chain_score import ChainScore
from app.models.email import Email

_EMAIL_LOAD_COLS = load_only(
    Email.id, Email.message_id, Email.in_reply_to, Email.thread_id,
    Email.from_email, Email.from_name, Email.to_email, Email.to_name,
    Email.subject, Email.timestamp, Email.direction, Email.is_auto_reply,
    Email.chain_id, Email.position_in_chain, Email.quoted_metadata,
)
_THIRTY_DAYS = 30 * 86400

_PREFIX_PATTERN = re.compile(r"^(?:(Re|RE|Fwd|FW|Fw):\s*|Email:\s*>>\s*)")


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
    """Full rebuild of all chains. Alias for rebuild_all_chains."""
    return await rebuild_all_chains(session)


async def rebuild_all_chains(session: AsyncSession) -> dict:
    """Destructive full rebuild: deletes all chains and recreates from scratch.

    Used by the standalone CHAIN_BUILD job. For incremental updates during
    fetch, use update_chains_for_emails() instead.
    """
    result = await session.execute(
        select(Email)
        .options(_EMAIL_LOAD_COLS)
        .order_by(Email.timestamp.asc().nullslast(), Email.id.asc())
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
    root_counts: Counter[int] = Counter(find(e.id) for e in emails)
    unchained = [e for e in emails if root_counts[find(e.id)] == 1]

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
                # Exclude each email's from_email to prevent mass-send chaining
                # where the rep's address is the sole overlap
                e_from = (e.from_email or "").lower()
                other_from = (other.from_email or "").lower()
                e_recipients = e_participants - {e_from}
                other_recipients = other_participants - {other_from}
                # Overlap must exist on the recipient side of at least one email
                if not (e_recipients & other_participants or other_recipients & e_participants):
                    continue
                # Check time proximity (30 days)
                if e.timestamp and other.timestamp:
                    if abs((other.timestamp - e.timestamp).total_seconds()) > _THIRTY_DAYS:
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

    # Load existing chains (with their scores) for potential reuse
    existing_chains: dict[int, EmailChain] = {}
    if existing_chain_ids:
        chain_result = await session.execute(
            select(EmailChain)
            .options(joinedload(EmailChain.chain_score))
            .where(EmailChain.id.in_(existing_chain_ids))
        )
        for c in chain_result.unique().scalars().all():
            existing_chains[c.id] = c

    # Preserve chain score data so it survives the chain delete-and-recreate
    # cycle. Stored as plain dicts keyed by (normalized_subject, participants),
    # with a secondary index by normalized_subject alone as a fallback when
    # participants change (e.g. a new person joins the thread).
    saved_scores: dict[tuple[str, str], dict] = {}
    saved_scores_by_subject: dict[str, dict | None] = {}
    for chain in existing_chains.values():
        if chain.chain_score is not None:
            score = chain.chain_score
            key = (chain.normalized_subject or "", chain.participants or "")
            ns = chain.normalized_subject or ""
            score_data = {
                "progression": score.progression,
                "responsiveness": score.responsiveness,
                "persistence": score.persistence,
                "conversation_quality": score.conversation_quality,
                "avg_response_hours": score.avg_response_hours,
                "notes": score.notes,
                "score_error": score.score_error,
                "scored_at": score.scored_at,
            }
            saved_scores[key] = score_data
            if ns not in saved_scores_by_subject:
                saved_scores_by_subject[ns] = score_data
            else:
                # Multiple chains share the same subject - fallback is ambiguous
                saved_scores_by_subject[ns] = None

    # Delete existing chains (cascade removes chain_scores too)
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
            elif not e.is_auto_reply:
                incoming += 1

        # Follow-up sequence: all outgoing, no replies. Skip chain creation.
        if incoming == 0:
            continue

        # Determine if this is an unanswered reply (no outgoing after last incoming)
        # Ignore auto-reply timestamps when determining unanswered status
        last_incoming_ts = None
        for e in reversed(group_emails):
            if not _is_outgoing(e) and not e.is_auto_reply:
                last_incoming_ts = e.timestamp
                break
        has_outgoing_after_incoming = any(
            _is_outgoing(e) and e.timestamp and last_incoming_ts and e.timestamp > last_incoming_ts
            for e in group_emails
        )

        first_email = group_emails[0]
        chain = EmailChain(
            normalized_subject=normalize_subject(first_email.subject),
            participants=",".join(sorted(all_participants)),
            started_at=group_emails[0].timestamp,
            last_activity_at=group_emails[-1].timestamp,
            email_count=len(group_emails),
            outgoing_count=outgoing,
            incoming_count=incoming,
            is_unanswered=not has_outgoing_after_incoming,
        )
        session.add(chain)
        await session.flush()

        # Re-create a chain score from saved data if one matches. Try exact
        # key first, then fall back to normalized_subject alone to handle
        # participant changes.
        score_key = (chain.normalized_subject or "", chain.participants or "")
        ns = chain.normalized_subject or ""
        score_data = saved_scores.pop(score_key, None)
        if score_data is None and ns in saved_scores_by_subject:
            candidate = saved_scores_by_subject.pop(ns, None)
            if candidate is not None:
                score_data = candidate
                # Remove from the primary dict so it's not left over
                for k, v in list(saved_scores.items()):
                    if v is score_data:
                        saved_scores.pop(k)
                        break
        if score_data is not None:
            restored_score = ChainScore(chain_id=chain.id, **score_data)
            session.add(restored_score)

        chains_created += 1

        for pos, e in enumerate(group_emails, start=1):
            e.chain_id = chain.id
            e.position_in_chain = pos
            emails_linked += 1

    # Unlink auto-reply emails from chains
    for e in emails:
        if e.is_auto_reply and e.chain_id is not None:
            e.chain_id = None
            e.position_in_chain = None

    await session.flush()

    # Pass 4: quoted-content matching for unchained emails with quoted_metadata
    # Track which chains were modified so we can update their metadata
    modified_chain_ids: set[int] = set()
    unchained_with_quotes = [
        e for e in emails
        if e.chain_id is None and e.quoted_metadata
    ]
    for e in unchained_with_quotes:
        quoted = e.quoted_metadata
        if not isinstance(quoted, list):
            continue
        for q in quoted:
            q_from = q.get("from_email", "")
            q_subject = q.get("subject", "")
            if not q_from or not q_subject:
                continue
            q_norm = normalize_subject(q_subject)
            for other in emails:
                if other.id == e.id:
                    continue
                if (other.from_email and other.from_email.lower() == q_from.lower()
                        and normalize_subject(other.subject) == q_norm):
                    if other.chain_id is not None:
                        e.chain_id = other.chain_id
                        max_pos = max(
                            (x.position_in_chain or 0)
                            for x in emails if x.chain_id == other.chain_id
                        )
                        e.position_in_chain = max_pos + 1
                        modified_chain_ids.add(other.chain_id)
                        chains_updated += 1
                        break
            if e.chain_id is not None:
                break

    # Recalculate metadata for chains modified by Pass 4
    if modified_chain_ids:
        chain_result = await session.execute(
            select(EmailChain).where(EmailChain.id.in_(modified_chain_ids))
        )
        for chain in chain_result.scalars().all():
            chain_emails_list = [
                x for x in emails if x.chain_id == chain.id
            ]
            chain_emails_list.sort(key=lambda x: (x.timestamp or datetime.min, x.id))
            outgoing = sum(1 for x in chain_emails_list if _is_outgoing(x))
            incoming = sum(1 for x in chain_emails_list if not _is_outgoing(x) and not x.is_auto_reply)
            chain.email_count = len(chain_emails_list)
            chain.outgoing_count = outgoing
            chain.incoming_count = incoming
            chain.last_activity_at = chain_emails_list[-1].timestamp if chain_emails_list else chain.last_activity_at
            last_incoming_ts = None
            for x in reversed(chain_emails_list):
                if not _is_outgoing(x) and not x.is_auto_reply:
                    last_incoming_ts = x.timestamp
                    break
            chain.is_unanswered = not any(
                _is_outgoing(x) and x.timestamp and last_incoming_ts and x.timestamp > last_incoming_ts
                for x in chain_emails_list
            )

    await session.flush()

    return {
        "chains_created": chains_created,
        "chains_updated": chains_updated,
        "emails_linked": emails_linked,
    }


def _compute_chain_metadata(group_emails: list[Email]) -> dict | None:
    """Compute chain metadata from a list of emails. Returns None if no chain should be created."""
    group_emails.sort(key=lambda e: (e.timestamp or datetime.min, e.id))

    all_participants: set[str] = set()
    outgoing = 0
    incoming = 0
    for e in group_emails:
        all_participants |= _email_participants(e)
        if _is_outgoing(e):
            outgoing += 1
        elif not e.is_auto_reply:
            incoming += 1

    if incoming == 0:
        return None

    last_incoming_ts = None
    for e in reversed(group_emails):
        if not _is_outgoing(e) and not e.is_auto_reply:
            last_incoming_ts = e.timestamp
            break
    has_outgoing_after_incoming = any(
        _is_outgoing(e) and e.timestamp and last_incoming_ts and e.timestamp > last_incoming_ts
        for e in group_emails
    )

    first_email = group_emails[0]
    return {
        "normalized_subject": normalize_subject(first_email.subject),
        "participants": ",".join(sorted(all_participants)),
        "started_at": group_emails[0].timestamp,
        "last_activity_at": group_emails[-1].timestamp,
        "email_count": len(group_emails),
        "outgoing_count": outgoing,
        "incoming_count": incoming,
        "is_unanswered": not has_outgoing_after_incoming,
    }


def _run_union_find(emails: list[Email]) -> dict[int, list[Email]]:
    """Run the 3-pass union-find algorithm on a list of emails.

    Returns groups (leader_id -> [emails]).
    """
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

    msg_id_to_email: dict[str, Email] = {}
    for e in emails:
        if e.message_id:
            msg_id_to_email[e.message_id] = e

    message_id_linked: set[int] = set()

    # Pass 1: in_reply_to / message_id matching
    for e in emails:
        if e.in_reply_to and e.in_reply_to in msg_id_to_email:
            parent_email = msg_id_to_email[e.in_reply_to]
            union(parent_email.id, e.id)
            message_id_linked.add(e.id)
            message_id_linked.add(parent_email.id)

    # Pass 2: thread_id matching
    thread_groups: dict[str, list[Email]] = defaultdict(list)
    for e in emails:
        if e.id not in message_id_linked and e.thread_id:
            thread_groups[e.thread_id].append(e)

    for tid, group in thread_groups.items():
        if len(group) >= 2:
            first = group[0]
            for other in group[1:]:
                union(first.id, other.id)

    # Pass 3: subject normalization + participant overlap + time proximity
    root_counts: Counter[int] = Counter(find(e.id) for e in emails)
    unchained = [e for e in emails if root_counts[find(e.id)] == 1]

    subject_groups: dict[str, list[Email]] = defaultdict(list)
    for e in unchained:
        ns = normalize_subject(e.subject)
        if ns:
            subject_groups[ns].append(e)

    for ns, group in subject_groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda e: (e.timestamp or datetime.min, e.id))
        for i, e in enumerate(group):
            e_participants = _email_participants(e)
            for j in range(i + 1, len(group)):
                other = group[j]
                if find(e.id) == find(other.id):
                    continue
                other_participants = _email_participants(other)
                e_from = (e.from_email or "").lower()
                other_from = (other.from_email or "").lower()
                e_recipients = e_participants - {e_from}
                other_recipients = other_participants - {other_from}
                if not (e_recipients & other_participants or other_recipients & e_participants):
                    continue
                if e.timestamp and other.timestamp:
                    if abs((other.timestamp - e.timestamp).total_seconds()) > _THIRTY_DAYS:
                        continue
                union(e.id, other.id)

    # Build final groups
    groups: dict[int, list[Email]] = defaultdict(list)
    for e in emails:
        groups[find(e.id)].append(e)

    return groups


async def update_chains_for_emails(
    session: AsyncSession, email_ids: set[int]
) -> dict:
    """Incrementally update chains for a set of new email IDs.

    Only processes new emails and their neighbors (by message-id, thread-id,
    or subject match). Existing chains that are not affected remain untouched
    along with their chain scores.
    """
    if not email_ids:
        return {"chains_created": 0, "chains_updated": 0, "emails_linked": 0}

    # Load the new emails
    new_result = await session.execute(
        select(Email).options(_EMAIL_LOAD_COLS).where(Email.id.in_(email_ids))
    )
    new_emails = list(new_result.scalars().all())
    if not new_emails:
        return {"chains_created": 0, "chains_updated": 0, "emails_linked": 0}

    # Collect identifiers from new emails for neighbor search
    new_message_ids = {e.message_id for e in new_emails if e.message_id}
    new_in_reply_tos = {e.in_reply_to for e in new_emails if e.in_reply_to}
    new_thread_ids = {e.thread_id for e in new_emails if e.thread_id}
    new_subjects: dict[str, list[Email]] = defaultdict(list)
    for e in new_emails:
        ns = normalize_subject(e.subject)
        if ns:
            new_subjects[ns].append(e)

    # Find neighbor emails that could group with the new ones
    neighbor_conditions = []
    if new_in_reply_tos:
        neighbor_conditions.append(Email.message_id.in_(new_in_reply_tos))
    if new_message_ids:
        neighbor_conditions.append(Email.in_reply_to.in_(new_message_ids))
    if new_thread_ids:
        neighbor_conditions.append(Email.thread_id.in_(new_thread_ids))

    neighbor_ids: set[int] = set()

    if neighbor_conditions:
        neighbor_result = await session.execute(
            select(Email.id)
            .where(~Email.id.in_(email_ids), or_(*neighbor_conditions))
        )
        neighbor_ids.update(row[0] for row in neighbor_result.all())

    # Subject-based neighbor search: find emails with matching normalized
    # subjects, participant overlap, and within 30-day window
    if new_subjects:
        for ns, ns_emails in new_subjects.items():
            timestamps = [e.timestamp for e in ns_emails if e.timestamp]
            if timestamps:
                min_ts = min(timestamps) - timedelta(days=30)
                max_ts = max(timestamps) + timedelta(days=30)
                subject_neighbor_result = await session.execute(
                    select(Email.id, Email.from_email, Email.to_email, Email.timestamp)
                    .where(
                        ~Email.id.in_(email_ids),
                        Email.timestamp >= min_ts,
                        Email.timestamp <= max_ts,
                    )
                )
                for row in subject_neighbor_result.all():
                    eid, from_email, to_email, ts = row
                    if eid in neighbor_ids:
                        continue
                    candidate_participants = set()
                    if from_email:
                        candidate_participants.add(from_email.lower())
                    if to_email:
                        candidate_participants.add(to_email.lower())
                    for new_e in ns_emails:
                        new_participants = _email_participants(new_e)
                        new_from = (new_e.from_email or "").lower()
                        cand_from = (from_email or "").lower()
                        new_recipients = new_participants - {new_from}
                        cand_recipients = candidate_participants - {cand_from}
                        if new_recipients & candidate_participants or cand_recipients & new_participants:
                            neighbor_ids.add(eid)
                            break

    # Load full neighbor emails
    all_ids = email_ids | neighbor_ids
    if neighbor_ids:
        full_result = await session.execute(
            select(Email).options(_EMAIL_LOAD_COLS)
            .where(Email.id.in_(all_ids))
            .order_by(Email.timestamp.asc().nullslast(), Email.id.asc())
        )
        affected_emails = list(full_result.scalars().all())
    else:
        affected_emails = sorted(new_emails, key=lambda e: (e.timestamp or datetime.min, e.id))

    # Track which existing chains are affected
    affected_chain_ids: set[int] = set()
    for e in affected_emails:
        if e.chain_id is not None:
            affected_chain_ids.add(e.chain_id)

    # Load all emails in affected chains so we can recompute groups properly
    if affected_chain_ids:
        chain_email_result = await session.execute(
            select(Email).options(_EMAIL_LOAD_COLS)
            .where(Email.chain_id.in_(affected_chain_ids), ~Email.id.in_(all_ids))
        )
        chain_emails = list(chain_email_result.scalars().all())
        affected_emails.extend(chain_emails)
        seen = set()
        deduped = []
        for e in affected_emails:
            if e.id not in seen:
                seen.add(e.id)
                deduped.append(e)
        affected_emails = deduped

    # Save original email→chain mapping BEFORE clearing chain assignments
    original_chain_map: dict[int, int] = {}
    for e in affected_emails:
        if e.chain_id is not None:
            original_chain_map[e.id] = e.chain_id

    # Run union-find on the affected set
    groups = _run_union_find(affected_emails)

    # Load affected chains with their scores
    existing_chains: dict[int, EmailChain] = {}
    if affected_chain_ids:
        chain_result = await session.execute(
            select(EmailChain)
            .options(joinedload(EmailChain.chain_score))
            .where(EmailChain.id.in_(affected_chain_ids))
        )
        for c in chain_result.unique().scalars().all():
            existing_chains[c.id] = c

    # Clear chain assignments for affected emails
    for e in affected_emails:
        e.chain_id = None
        e.position_in_chain = None

    chains_created = 0
    chains_updated = 0
    emails_linked = 0

    # Track which existing chains have been claimed by a group
    claimed_chain_ids: set[int] = set()

    for leader_id, group_emails in groups.items():
        if len(group_emails) < 2:
            continue

        metadata = _compute_chain_metadata(group_emails)
        if metadata is None:
            continue

        # Determine which existing chain(s) this group maps to
        group_chain_ids: set[int] = set()
        for e in group_emails:
            if e.id in original_chain_map:
                group_chain_ids.add(original_chain_map[e.id])

        if group_chain_ids:
            # Group maps to one or more existing chains.
            # Pick the one with the most emails (or lowest id as tiebreaker).
            keep_chain_id = max(
                group_chain_ids,
                key=lambda cid: (
                    existing_chains[cid].email_count or 0
                    if cid in existing_chains else 0,
                    -cid,
                ),
            )
            chain = existing_chains[keep_chain_id]

            # Update chain metadata in place
            chain.normalized_subject = metadata["normalized_subject"]
            chain.participants = metadata["participants"]
            chain.started_at = metadata["started_at"]
            chain.last_activity_at = metadata["last_activity_at"]
            chain.email_count = metadata["email_count"]
            chain.outgoing_count = metadata["outgoing_count"]
            chain.incoming_count = metadata["incoming_count"]
            chain.is_unanswered = metadata["is_unanswered"]
            claimed_chain_ids.add(keep_chain_id)

            # Delete any other chains that merged into this one
            for other_cid in group_chain_ids - {keep_chain_id}:
                if other_cid in existing_chains:
                    await session.delete(existing_chains[other_cid])
                    claimed_chain_ids.add(other_cid)

            # Assign emails to the kept chain
            group_emails.sort(key=lambda e: (e.timestamp or datetime.min, e.id))
            for pos, e in enumerate(group_emails, start=1):
                e.chain_id = chain.id
                e.position_in_chain = pos
                emails_linked += 1

            chains_updated += 1
        else:
            # Entirely new chain
            chain = EmailChain(**metadata)
            session.add(chain)
            await session.flush()

            group_emails.sort(key=lambda e: (e.timestamp or datetime.min, e.id))
            for pos, e in enumerate(group_emails, start=1):
                e.chain_id = chain.id
                e.position_in_chain = pos
                emails_linked += 1

            chains_created += 1

    # Delete any affected chains that were not claimed by any group
    # (e.g. the group no longer qualifies as a chain)
    for cid in affected_chain_ids - claimed_chain_ids:
        if cid in existing_chains:
            await session.delete(existing_chains[cid])

    # Unlink auto-reply emails from chains
    for e in affected_emails:
        if e.is_auto_reply and e.chain_id is not None:
            e.chain_id = None
            e.position_in_chain = None

    await session.flush()

    return {
        "chains_created": chains_created,
        "chains_updated": chains_updated,
        "emails_linked": emails_linked,
    }
