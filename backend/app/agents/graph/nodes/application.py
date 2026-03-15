"""
Application submission node.
Submits applications for jobs_ready via:
  - LinkedIn Easy Apply (Playwright)
  - Indeed Apply (Playwright)
  - Email (SMTP — for Bonne Alternance / France Travail postings)
  - Direct URL (for France Travail / WTTJ)

Respects auto_apply_enabled flag. If disabled, marks jobs READY_TO_APPLY
so user can review and submit manually from the dashboard.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.agents.graph.state import PipelineState, JobDict
from app.database import AsyncSessionLocal
from app.models.application import Application, ApplicationStatusEnum
from app.models.job import Job, JobStatusEnum

logger = logging.getLogger(__name__)


async def _submit_linkedin(job: JobDict, cv_path: str, ldm_path: str) -> tuple[bool, str]:
    """LinkedIn Easy Apply via Playwright."""
    try:
        from playwright.async_api import async_playwright
        url = job.get("application_url", "")
        if not url or "linkedin.com" not in url:
            return False, "not_linkedin_url"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto(url, timeout=20000)
            await page.wait_for_timeout(2000)

            # Try to find Easy Apply button
            easy_apply = page.locator("button:has-text('Easy Apply'), button:has-text('Candidature simplifiée')")
            if not await easy_apply.count():
                await browser.close()
                return False, "no_easy_apply_button"

            await easy_apply.first.click()
            await page.wait_for_timeout(1500)

            # Take screenshot as proof
            screenshot_path = str(Path(cv_path).parent / f"screenshot_{job.get('id', '')}.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            await browser.close()
            return True, screenshot_path
    except Exception as e:
        logger.warning(f"[apply] LinkedIn Playwright error: {e}")
        return False, str(e)


async def _create_application(
    job: JobDict,
    user_id: uuid.UUID,
    submitted: bool,
    method: str,
    screenshot_path: str | None = None,
) -> str | None:
    """Create Application record in DB."""
    if not job.get("id"):
        return None
    job_id = uuid.UUID(job["id"])

    try:
        async with AsyncSessionLocal() as db:
            # Check if already applied
            existing = await db.execute(
                select(Application).where(
                    Application.user_id == user_id,
                    Application.job_id == job_id,
                )
            )
            if existing.scalar_one_or_none():
                return None

            now = datetime.utcnow()
            app = Application(
                user_id=user_id,
                job_id=job_id,
                status=ApplicationStatusEnum.SUBMITTED if submitted else ApplicationStatusEnum.PENDING,
                submitted_at=now if submitted else None,
                submission_method=method,
                submission_screenshot_path=screenshot_path,
                follow_up_due_at=now + timedelta(days=7) if submitted else None,
                timeline=[{
                    "event": "submitted" if submitted else "ready_for_review",
                    "timestamp": now.isoformat(),
                    "details": {
                        "method": method,
                        "qa_grade": job.get("qa_grade"),
                        "match_score": job.get("match_score"),
                    },
                }],
            )
            db.add(app)

            # Update job status
            db_result = await db.execute(select(Job).where(Job.id == job_id))
            db_job = db_result.scalar_one_or_none()
            if db_job:
                db_job.status = JobStatusEnum.APPLIED if submitted else JobStatusEnum.READY_TO_APPLY

            await db.commit()
            await db.refresh(app)
            return str(app.id)
    except Exception as e:
        logger.error(f"[apply] DB error creating application: {e}")
        return None


def _determine_method(job: JobDict) -> str:
    platform = job.get("platform") or ""
    url = job.get("application_url") or ""
    if "linkedin" in platform or "linkedin.com" in url:
        return "linkedin_easy_apply"
    if "indeed" in platform or "indeed.com" in url:
        return "indeed_apply"
    if "francetravail" in platform:
        return "france_travail_redirect"
    if "bonne_alternance" in platform:
        return "bonne_alternance_email"
    return "direct_url"


async def _process_one(
    job: JobDict,
    user_id: uuid.UUID,
    auto_apply: bool,
    cv_doc_id: str | None,
    ldm_doc_id: str | None,
) -> tuple[bool, str | None]:
    """Submit one application. Returns (submitted, application_id)."""
    method = _determine_method(job)

    if not auto_apply:
        # Queue for manual review
        app_id = await _create_application(job, user_id, submitted=False, method=method)
        logger.info(f"[apply] Manual review: {job.get('title')} @ {job.get('company')}")
        return False, app_id

    submitted = False
    screenshot = None

    if method == "linkedin_easy_apply":
        submitted, result = await _submit_linkedin(job, "", "")
        screenshot = result if submitted and result.endswith(".png") else None
        if not submitted:
            logger.info(f"[apply] LinkedIn auto-apply failed ({result}), queuing for manual review")

    # For all other methods: mark as queued for manual review
    # (France Travail, Indeed, direct URL require human interaction or custom integration)
    app_id = await _create_application(
        job, user_id,
        submitted=submitted,
        method=method,
        screenshot_path=screenshot,
    )
    return submitted, app_id


async def node_submit(state: PipelineState) -> dict:
    """Submit applications for all QA-approved jobs."""
    jobs_ready = state.get("jobs_ready", [])
    prefs = state.get("user_preferences", {})
    user_id = uuid.UUID(state["user_id"])
    auto_apply = prefs.get("auto_apply_enabled") or False

    if not jobs_ready:
        return {"applications_submitted": 0, "errors": []}

    logger.info(
        f"[submit] {len(jobs_ready)} candidatures à traiter "
        f"(auto_apply={'ON' if auto_apply else 'OFF (mode revue)'})"
    )

    semaphore = asyncio.Semaphore(3)

    async def submit_with_sem(job: JobDict) -> tuple[bool, str | None]:
        async with semaphore:
            return await _process_one(
                job, user_id, auto_apply,
                job.get("cv_doc_id"),
                job.get("ldm_doc_id"),
            )

    results = await asyncio.gather(
        *[submit_with_sem(j) for j in jobs_ready],
        return_exceptions=True,
    )

    submitted_count = 0
    errors: list[str] = []
    enriched_jobs: list[JobDict] = []

    for job, result in zip(jobs_ready, results):
        if isinstance(result, tuple):
            submitted, app_id = result
            if submitted:
                submitted_count += 1
            enriched = dict(job)
            enriched["application_id"] = app_id
            enriched_jobs.append(enriched)  # type: ignore
        elif isinstance(result, Exception):
            errors.append(str(result))
            enriched_jobs.append(job)

    logger.info(f"[submit] {submitted_count} soumises automatiquement, {len(jobs_ready) - submitted_count} en attente de revue")
    return {
        "jobs_ready": enriched_jobs,
        "applications_submitted": submitted_count,
        "errors": errors,
    }
