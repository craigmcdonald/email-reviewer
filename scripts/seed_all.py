"""Populate the database with seed data.

Seeds settings (prompt blocks and scoring weights), reps, emails, and scores
in dependency order. Idempotent - updates settings to canonical values and
skips records that already exist (matched by primary key or hubspot_id).

Usage:
    python -m scripts.seed_all                        # all seeds
    python -m scripts.seed_all --only settings        # settings only
    python -m scripts.seed_all --only settings reps   # settings and reps only
"""

import argparse
import asyncio
import re
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Email, Rep, Score, Settings  # noqa: F401 - registers tables
from scripts.seeds.emails import EMAILS
from scripts.seeds.reps import REPS
from scripts.seeds.scores import SCORES
from scripts.seeds.settings import SETTINGS_SEED


def _build_engine():
    url = settings.DATABASE_URL
    url = re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", url)
    return create_async_engine(url)


async def _seed_settings(session: AsyncSession):
    existing = await session.get(Settings, 1)
    if existing:
        for key, value in SETTINGS_SEED.items():
            setattr(existing, key, value)
        action = "updated"
    else:
        session.add(Settings(id=1, **SETTINGS_SEED))
        action = "inserted"
    await session.flush()
    print(f"  settings: {action}")


async def _seed_reps(session: AsyncSession):
    inserted = 0
    for data in REPS:
        existing = await session.get(Rep, data["email"])
        if existing:
            continue
        session.add(Rep(**data))
        inserted += 1
    await session.flush()
    print(f"  reps: {inserted} inserted, {len(REPS) - inserted} already present")


async def _seed_emails(session: AsyncSession):
    inserted = 0
    for data in EMAILS:
        result = await session.execute(
            select(Email).where(Email.hubspot_id == data["hubspot_id"])
        )
        if result.scalar_one_or_none():
            continue
        session.add(Email(**data))
        inserted += 1
    await session.flush()
    print(f"  emails: {inserted} inserted, {len(EMAILS) - inserted} already present")


async def _seed_scores(session: AsyncSession):
    inserted = 0
    for data in SCORES:
        hubspot_id = data.pop("hubspot_id")
        result = await session.execute(
            select(Email).where(Email.hubspot_id == hubspot_id)
        )
        email = result.scalar_one_or_none()
        if not email:
            print(f"  scores: skipping - no email with hubspot_id {hubspot_id}")
            data["hubspot_id"] = hubspot_id
            continue

        existing = await session.execute(
            select(Score).where(Score.email_id == email.id)
        )
        if existing.scalar_one_or_none():
            data["hubspot_id"] = hubspot_id
            continue

        session.add(Score(email_id=email.id, **data))
        inserted += 1
        data["hubspot_id"] = hubspot_id
    await session.flush()
    print(f"  scores: {inserted} inserted, {len(SCORES) - inserted} already present")


ALL_SEEDS = ["settings", "reps", "emails", "scores"]


async def _run(only: set[str]):
    engine = _build_engine()
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            print("Seeding database...")
            if "settings" in only:
                await _seed_settings(session)
            if "reps" in only:
                await _seed_reps(session)
            if "emails" in only:
                await _seed_emails(session)
            if "scores" in only:
                await _seed_scores(session)
            print("Done.")

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Populate the database with seed data.")
    parser.add_argument(
        "--only",
        nargs="+",
        choices=ALL_SEEDS,
        help="Run only the specified seeds (default: all).",
    )
    args = parser.parse_args()
    only = set(args.only) if args.only else set(ALL_SEEDS)
    asyncio.run(_run(only))


if __name__ == "__main__":
    main()
