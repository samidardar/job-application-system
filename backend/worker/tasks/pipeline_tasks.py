"""
Daily pipeline orchestration tasks.

Flow per user:
1. scrape_jobs       → list of new job_ids (24h)
2. match_jobs        → filter by score >= threshold (parallel per job)
3. generate_docs     → CV + cover letter per matched job (parallel)
4. submit_apps       → Playwright form submission (parallel)
5. schedule_followups→ set follow_up_due_at
6. finalize          → update PipelineRun, emit SSE, send summary email
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from celery import shared_task
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.agent_run import PipelineRun, AgentStatusEnum
from app.models.application import Application
from app.models.document import Document, DocumentTypeEnum
from app.models.job import Job, JobStatusEnum
from app.models.user import User, UserPreferences
from app.agents.scraping_agent import ScrapingAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.cv_optimizer_agent import CVOptimizerAgent
from app.agents.cover_letter_agent import CoverLetterAgent
from app.agents.application_agent import ApplicationAgent
from app.agents.followup_agent import FollowUpAgent

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine in a sync Celery task."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(name="worker.tasks.pipeline_tasks.run_daily_pipeline", bind=True, max_retries=1)
def run_daily_pipeline(self, user_id: str, pipeline_run_id: str):
    """Legacy daily pipeline (kept for Celery Beat compatibility)."""
    return run_async(_run_pipeline_async(user_id, pipeline_run_id, "Data Scientist", "Paris, France"))


@shared_task(name="worker.tasks.pipeline_tasks.run_search_pipeline", bind=True, max_retries=1)
def run_search_pipeline(self, user_id: str, pipeline_run_id: str, job_title: str, location: str, min_match_score: int = 70):
    """On-demand pipeline triggered by user with specific job title + location."""
    return run_async(_run_pipeline_async(user_id, pipeline_run_id, job_title, location, min_match_score))


async def _run_pipeline_async(user_id: str, pipeline_run_id: str, job_title: str, location: str, min_match_score: int = 70):
    async with AsyncSessionLocal() as db:
        uid = uuid.UUID(user_id)
        run_id = uuid.UUID(pipeline_run_id)

        # Mark pipeline as running
        result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
        pipeline_run = result.scalar_one_or_none()
        if not pipeline_run:
            logger.error(f"PipelineRun {run_id} not found")
            return

        pipeline_run.status = AgentStatusEnum.RUNNING
        await db.commit()

        try:
            # Get user preferences
            prefs_result = await db.execute(
                select(UserPreferences).where(UserPreferences.user_id == uid)
            )
            prefs = prefs_result.scalar_one_or_none()
            daily_limit = prefs.daily_application_limit if prefs else 20
            auto_apply = prefs.auto_apply_enabled if prefs else False

            # === STEP 1: SCRAPING ===
            logger.info(f"[Pipeline {run_id}] Step 1: Scraping")
            scraper = ScrapingAgent(db, run_id, uid)
            new_job_ids = await scraper.run(job_title=job_title, location=location)
            await db.commit()

            pipeline_run.jobs_scraped = len(new_job_ids)
            await db.commit()

            if not new_job_ids:
                logger.info(f"[Pipeline {run_id}] No new jobs scraped")
                pipeline_run.status = AgentStatusEnum.SUCCESS
                pipeline_run.completed_at = datetime.utcnow()
                await db.commit()
                return

            # === STEP 2: MATCHING (parallel per job) ===
            logger.info(f"[Pipeline {run_id}] Step 2: Matching {len(new_job_ids)} jobs")
            matched_ids = []
            for job_id in new_job_ids:
                matcher = MatchingAgent(db, run_id, uid)
                is_match = await matcher.run(job_id)
                await db.commit()
                if is_match:
                    matched_ids.append(job_id)

            pipeline_run.jobs_matched = len(matched_ids)
            await db.commit()

            if not matched_ids:
                logger.info(f"[Pipeline {run_id}] No jobs matched threshold")
                pipeline_run.status = AgentStatusEnum.SUCCESS
                pipeline_run.completed_at = datetime.utcnow()
                await db.commit()
                return

            # Apply daily limit
            apply_ids = matched_ids[:daily_limit]

            # === STEP 3: DOCUMENT GENERATION (parallel per job) ===
            logger.info(f"[Pipeline {run_id}] Step 3: Generating documents for {len(apply_ids)} jobs")
            job_docs: dict[str, dict] = {}  # job_id → {cv_doc_id, letter_doc_id}

            for job_id in apply_ids:
                cv_agent = CVOptimizerAgent(db, run_id, uid)
                letter_agent = CoverLetterAgent(db, run_id, uid)

                cv_doc_id = await cv_agent.run(job_id)
                await db.commit()

                letter_doc_id = await letter_agent.run(job_id)
                await db.commit()

                if cv_doc_id:
                    pipeline_run.cvs_generated += 1
                if letter_doc_id:
                    pipeline_run.letters_generated += 1
                await db.commit()

                job_docs[str(job_id)] = {
                    "cv_doc_id": cv_doc_id,
                    "letter_doc_id": letter_doc_id,
                }

                # Update job status to ready
                job_result = await db.execute(select(Job).where(Job.id == job_id))
                job = job_result.scalar_one_or_none()
                if job:
                    job.status = JobStatusEnum.READY_TO_APPLY
                    await db.commit()

            # === STEP 4: APPLICATION SUBMISSION ===
            if auto_apply:
                logger.info(f"[Pipeline {run_id}] Step 4: Submitting {len(apply_ids)} applications")
                for job_id in apply_ids:
                    docs = job_docs.get(str(job_id), {})
                    app_agent = ApplicationAgent(db, run_id, uid)
                    success = await app_agent.run(
                        job_id=job_id,
                        cv_doc_id=docs.get("cv_doc_id"),
                        letter_doc_id=docs.get("letter_doc_id"),
                    )
                    await db.commit()
                    if success:
                        pipeline_run.applications_submitted += 1
                        await db.commit()
            else:
                logger.info(f"[Pipeline {run_id}] Step 4: auto_apply disabled, marking as ready")
                pipeline_run.applications_submitted = 0
                await db.commit()

            # === STEP 5: FINALIZE ===
            pipeline_run.status = AgentStatusEnum.SUCCESS
            pipeline_run.completed_at = datetime.utcnow()
            await db.commit()

            logger.info(
                f"[Pipeline {run_id}] Complete: scraped={pipeline_run.jobs_scraped} "
                f"matched={pipeline_run.jobs_matched} "
                f"applied={pipeline_run.applications_submitted}"
            )

        except Exception as e:
            logger.error(f"[Pipeline {run_id}] Error: {e}", exc_info=True)
            pipeline_run.status = AgentStatusEnum.FAILED
            pipeline_run.errors_count += 1
            pipeline_run.completed_at = datetime.utcnow()
            await db.commit()
            raise


@shared_task(name="worker.tasks.pipeline_tasks.process_all_followups")
def process_all_followups():
    """Daily task: send follow-up emails for all due applications."""
    return run_async(_process_followups_async())


async def _process_followups_async():
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        result = await db.execute(
            select(Application).where(
                Application.follow_up_due_at <= now,
                Application.follow_up_sent_at.is_(None),
            )
        )
        due_apps = result.scalars().all()
        logger.info(f"Processing {len(due_apps)} follow-up emails")

        for app in due_apps:
            # Create a dummy pipeline run for logging
            followup_run = PipelineRun(
                user_id=app.user_id,
                triggered_by="followup_scheduler",
                status=AgentStatusEnum.RUNNING,
            )
            db.add(followup_run)
            await db.flush()

            agent = FollowUpAgent(db, followup_run.id, app.user_id)
            await agent.run(app.id)
            await db.commit()


@shared_task(name="worker.tasks.pipeline_tasks.trigger_user_pipeline")
def trigger_user_pipeline(user_id: str):
    """Triggered by Celery Beat for scheduled daily runs."""
    async def create_and_run():
        async with AsyncSessionLocal() as db:
            uid = uuid.UUID(user_id)
            pipeline_run = PipelineRun(
                user_id=uid,
                triggered_by="schedule",
                status=AgentStatusEnum.PENDING,
            )
            db.add(pipeline_run)
            await db.commit()
            await db.refresh(pipeline_run)
            return str(pipeline_run.id)

    pipeline_run_id = run_async(create_and_run())
    run_daily_pipeline.delay(user_id, pipeline_run_id)
    logger.info(f"Triggered scheduled pipeline for user {user_id}, run {pipeline_run_id}")
