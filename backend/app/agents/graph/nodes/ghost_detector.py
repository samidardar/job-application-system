"""
Ghost Offer Detector node.
Filters out fake, expired, or invalid job postings before matching.

Ghost criteria:
  - posted_at > 21 days ago (stale)
  - No application URL
  - Description < 100 chars (placeholder / bot posting)
  - Title contains obvious spam patterns
  - Duplicate title+company for same user in DB (already applied)
"""
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.agents.graph.state import PipelineState
from app.database import AsyncSessionLocal
from app.models.application import Application
from app.models.job import Job, JobStatusEnum

logger = logging.getLogger(__name__)

SPAM_TITLE_PATTERNS = [
    "urgentement", "urgent !", "recrutement massif",
    "sans expérience requise", "travail domicile", "travail à domicile",
    "revenus complémentaires", "gains rapides",
]

CUTOFF_DAYS = 21  # Jobs older than this are considered ghost


def _is_ghost(job: dict) -> tuple[bool, str]:
    """Returns (is_ghost, reason)."""
    title = (job.get("title") or "").lower()
    description = job.get("description_raw") or ""
    url = job.get("application_url") or ""
    posted_at_str = job.get("posted_at")

    # Missing application URL
    if not url.strip():
        return True, "missing_url"

    # Too short description
    if len(description.strip()) < 80:
        return True, "description_too_short"

    # Spam title patterns
    for pattern in SPAM_TITLE_PATTERNS:
        if pattern in title:
            return True, f"spam_title:{pattern}"

    # Stale posting
    if posted_at_str:
        try:
            if "Z" in posted_at_str or "+" in posted_at_str:
                posted_at = datetime.fromisoformat(posted_at_str.replace("Z", "+00:00"))
                posted_at = posted_at.replace(tzinfo=None)
            else:
                posted_at = datetime.fromisoformat(posted_at_str)
            cutoff = datetime.utcnow() - timedelta(days=CUTOFF_DAYS)
            if posted_at < cutoff:
                return True, f"stale:{posted_at.date()}"
        except Exception:
            pass  # Can't parse date, keep the job

    return False, ""


async def _already_applied(job_ids: list[str], user_id: uuid.UUID) -> set[str]:
    """Return job IDs where user already has an application."""
    if not job_ids:
        return set()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Application.job_id).where(
                Application.user_id == user_id,
                Application.job_id.in_([uuid.UUID(j) for j in job_ids]),
            )
        )
        return {str(row[0]) for row in result.fetchall()}


async def node_detect_ghosts(state: PipelineState) -> dict:
    """Filter ghost offers from scraped_jobs → valid_jobs."""
    scraped = state.get("scraped_jobs", [])
    user_id = uuid.UUID(state["user_id"])

    if not scraped:
        return {"valid_jobs": [], "errors": []}

    # Check already-applied jobs
    job_ids = [j["id"] for j in scraped if j.get("id")]
    applied_ids = await _already_applied(job_ids, user_id)

    valid: list[dict] = []
    ghost_count = 0
    errors: list[str] = []

    for job in scraped:
        job_id = job.get("id", "")

        # Skip already applied
        if job_id in applied_ids:
            ghost_count += 1
            continue

        is_ghost, reason = _is_ghost(job)
        if is_ghost:
            ghost_count += 1
            logger.debug(f"[ghost] {job.get('title')} @ {job.get('company')} → {reason}")
            # Mark as SKIPPED in DB
            if job_id:
                try:
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(
                            select(Job).where(Job.id == uuid.UUID(job_id))
                        )
                        j = result.scalar_one_or_none()
                        if j:
                            j.status = JobStatusEnum.SKIPPED
                            await db.commit()
                except Exception as e:
                    errors.append(f"ghost_db_update:{e}")
        else:
            valid.append(job)

    logger.info(f"[ghost_detector] {len(valid)} valides / {ghost_count} ghosts filtrés")
    return {"valid_jobs": valid, "errors": errors}
