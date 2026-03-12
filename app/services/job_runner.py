"""Job runners for fetch, score, rescore, export, and chain build operations."""

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_config
from app.models.base import _utcnow
from app.database import worker_session
from app.enums import JobStatus, JobType
from app.models.chain_score import ChainScore
from app.models.email import Email
from app.models.job import Job
from app.models.rep import Rep
from app.models.score import Score
from app.services.chain_builder import rebuild_all_chains, update_chains_for_emails
from app.services.classifier import classify_emails
from app.services.export import export_to_excel
from app.services.fetcher import fetch_and_store
from app.services.scorer import score_unscored_emails
from app.services.settings import get_settings
from app.services.thread_splitter import split_email_threads

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _session_scope(session: Optional[AsyncSession] = None):
    """Yield the provided session or create a new one, committing on exit.

    When session is None (RQ worker), creates a fresh engine and session via
    worker_session() to avoid event loop mismatch with the module-level engine.
    """
    if session is not None:
        yield session
        await session.commit()
    else:
        async with worker_session() as new_session:
            yield new_session
            await new_session.commit()


def _set_running(job: Job) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = _utcnow()


def _set_completed(job: Job, result_summary: dict) -> None:
    job.status = JobStatus.COMPLETED
    job.completed_at = _utcnow()
    job.result_summary = result_summary


def _set_failed(job: Job, error: str) -> None:
    job.status = JobStatus.FAILED
    job.completed_at = _utcnow()
    job.error_message = error


async def _fail_job(session: AsyncSession, job_id: int, exc: Exception) -> None:
    """Record a job failure, handling cases where the session may be dirty.

    Rolls back any pending changes, then loads the job fresh and sets FAILED.
    If even the failure recording fails (e.g. DB unreachable), logs the error
    so it's visible in worker output.
    """
    error_msg = str(exc)
    try:
        await session.rollback()
        result = await session.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        _set_failed(job, error_msg)
        await session.flush()
    except Exception as inner:
        logger.error(
            "Job %d failed with: %s. Additionally failed to record error: %s",
            job_id, error_msg, inner,
        )


async def run_fetch_job(
    session: Optional[AsyncSession],
    job_id: int,
    *,
    fetch_start_date: Optional[date] = None,
    fetch_end_date: Optional[date] = None,
    max_count: Optional[int] = None,
    auto_score: Optional[bool] = None,
) -> None:
    async with _session_scope(session) as s:
        try:
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_running(job)
            await s.commit()

            settings = await get_settings(s)
            company_domains = [
                d.strip() for d in settings.company_domains.split(",") if d.strip()
            ]

            # Compute effective start date
            if fetch_start_date:
                effective_start = datetime.combine(
                    fetch_start_date, datetime.min.time()
                )
            else:
                max_ts_result = await s.execute(
                    select(func.max(Email.timestamp))
                )
                max_timestamp = max_ts_result.scalar_one_or_none()

                global_start = datetime.combine(
                    settings.global_start_date, datetime.min.time()
                )
                if max_timestamp and max_timestamp > global_start:
                    # Overlap by 1 hour to catch emails created between cycles.
                    # The upsert deduplicates on hubspot_id, so re-fetching is safe.
                    effective_start = max_timestamp - timedelta(hours=1)
                else:
                    effective_start = global_start

            fetch_kwargs: dict = {
                "start_date": effective_start,
            }
            if fetch_end_date:
                fetch_kwargs["end_date"] = datetime.combine(
                    fetch_end_date, datetime.min.time()
                )
            if max_count is not None:
                fetch_kwargs["max_count"] = max_count

            # Stage 1: Fetch emails from HubSpot
            reps_before_result = await s.execute(
                select(func.count()).select_from(Rep)
            )
            reps_before = reps_before_result.scalar_one()

            # Snapshot existing email IDs so we can identify new ones after fetch
            existing_ids_result = await s.execute(select(Email.id))
            existing_email_ids = {row[0] for row in existing_ids_result.all()}

            fetched_count = await fetch_and_store(
                s,
                access_token=app_config.HUBSPOT_ACCESS_TOKEN,
                company_domains=company_domains,
                **fetch_kwargs,
            )

            reps_after_result = await s.execute(
                select(func.count()).select_from(Rep)
            )
            new_reps_count = reps_after_result.scalar_one() - reps_before

            # Identify newly created email IDs via set difference. Updated
            # emails (same hubspot_id, changed subject/body) are upserted in
            # place and won't appear here, so they don't trigger chain
            # reassignment — an email update shouldn't change chain membership.
            all_ids_result = await s.execute(select(Email.id))
            all_email_ids = {row[0] for row in all_ids_result.all()}
            new_email_ids = all_email_ids - existing_email_ids

            await s.commit()

            summary: dict = {"fetched": fetched_count, "new_reps": new_reps_count}
            stage_errors: list[str] = []

            # Stage 2: Classify incoming emails (commits per batch internally)
            try:
                classify_result = await classify_emails(s)
                summary["auto_replies"] = classify_result.get("auto_replies_found", 0)
            except Exception as exc:
                logger.exception("Fetch job %d: classify stage failed", job_id)
                stage_errors.append(f"classify: {exc}")

            # Stage 3: Incrementally update conversation chains for new emails
            try:
                if new_email_ids:
                    await update_chains_for_emails(s, new_email_ids)
                await s.commit()
            except Exception as exc:
                logger.exception("Fetch job %d: chain build stage failed", job_id)
                await s.rollback()
                stage_errors.append(f"chain_build: {exc}")

            # Stage 4: Score (commits per batch internally)
            should_score = auto_score if auto_score is not None else settings.auto_score_after_fetch
            if should_score:
                try:
                    score_result = await score_unscored_emails(
                        s, batch_size=settings.scoring_batch_size
                    )
                    summary["scored"] = score_result.get("scored", 0)
                    summary["errors"] = score_result.get("errors", 0)
                    summary["tokens"] = score_result.get(
                        "total_input_tokens", 0
                    ) + score_result.get("total_output_tokens", 0)
                except Exception as exc:
                    logger.exception("Fetch job %d: score stage failed", job_id)
                    stage_errors.append(f"score: {exc}")

            if stage_errors:
                summary["stage_errors"] = stage_errors

            # Re-fetch job to avoid stale ORM state after intermediate commits
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_completed(job, summary)
            await s.commit()

        except Exception as exc:
            await _fail_job(s, job_id, exc)


async def run_score_job(
    session: Optional[AsyncSession], job_id: int
) -> None:
    async with _session_scope(session) as s:
        try:
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_running(job)
            await s.commit()

            settings = await get_settings(s)
            score_result = await score_unscored_emails(
                s, batch_size=settings.scoring_batch_size
            )
            summary = {
                "scored": score_result.get("scored", 0),
                "errors": score_result.get("errors", 0),
                "chains_scored": score_result.get("chains_scored", 0),
                "chain_errors": score_result.get("chain_errors", 0),
                "tokens": score_result.get("total_input_tokens", 0)
                + score_result.get("total_output_tokens", 0),
            }
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_completed(job, summary)
            await s.commit()

        except Exception as exc:
            await _fail_job(s, job_id, exc)


async def run_rescore_job(
    session: Optional[AsyncSession], job_id: int
) -> None:
    async with _session_scope(session) as s:
        try:
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_running(job)
            await s.commit()

            settings = await get_settings(s)

            # Delete email scores in committed batches to bound crash exposure.
            # If the process crashes, at most one batch of scores is lost rather
            # than the entire corpus.
            RESCORE_DELETE_BATCH = 100
            scored_ids_result = await s.execute(select(Score.email_id))
            all_scored_ids = [row[0] for row in scored_ids_result.all()]
            for i in range(0, len(all_scored_ids), RESCORE_DELETE_BATCH):
                batch_ids = all_scored_ids[i : i + RESCORE_DELETE_BATCH]
                await s.execute(
                    delete(Score).where(Score.email_id.in_(batch_ids))
                )
                await s.commit()

            # Delete chain scores after email scores are cleared but before
            # re-scoring. score_unscored_emails calls score_unscored_chains
            # internally, which queries for chains without a ChainScore. If
            # we deleted chain scores before email scores, a crash during
            # email score deletion would leave all chain scores permanently
            # lost. This ordering minimises the crash window.
            await s.execute(delete(ChainScore))
            await s.commit()

            score_result = await score_unscored_emails(
                s, batch_size=settings.scoring_batch_size
            )
            summary = {
                "scored": score_result.get("scored", 0),
                "errors": score_result.get("errors", 0),
                "tokens": score_result.get("total_input_tokens", 0)
                + score_result.get("total_output_tokens", 0),
                "chains_scored": score_result.get("chains_scored", 0),
                "chain_errors": score_result.get("chain_errors", 0),
            }
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_completed(job, summary)
            await s.commit()

        except Exception as exc:
            await _fail_job(s, job_id, exc)


async def run_export_job(
    session: Optional[AsyncSession],
    job_id: int,
    output_path: str | None = None,
) -> None:
    async with _session_scope(session) as s:
        try:
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_running(job)
            await s.commit()

            effective_path = output_path or f"export_{job_id}.xlsx"
            path = await export_to_excel(s, effective_path)
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_completed(job, {"output_path": path})
            await s.commit()

        except Exception as exc:
            await _fail_job(s, job_id, exc)


async def run_chain_build_job(
    session: Optional[AsyncSession], job_id: int
) -> None:
    async with _session_scope(session) as s:
        try:
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_running(job)
            await s.commit()

            summary: dict = {}
            stage_errors: list[str] = []

            # Stage 1: Classify unclassified emails so quoted_metadata is populated
            try:
                classify_result = await classify_emails(s)
                summary["classified"] = classify_result.get("classified", 0)
                summary["auto_replies"] = classify_result.get("auto_replies_found", 0)
            except Exception as exc:
                logger.exception("Chain build job %d: classify stage failed", job_id)
                stage_errors.append(f"classify: {exc}")

            # Stage 2: Split threads (requires quoted_metadata from classification)
            try:
                split_result = await split_email_threads(s)
                summary["threads_split"] = split_result.get("threads_split", 0)
                summary["messages_created"] = split_result.get("messages_created", 0)
            except Exception as exc:
                logger.exception("Chain build job %d: thread split stage failed", job_id)
                stage_errors.append(f"thread_split: {exc}")

            # Stage 3: Full rebuild of conversation chains
            chain_result = await rebuild_all_chains(s)
            summary.update(chain_result)

            if stage_errors:
                summary["stage_errors"] = stage_errors

            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_completed(job, summary)
            await s.commit()

        except Exception as exc:
            await _fail_job(s, job_id, exc)


