"""
Maintenance tasks: schedule refresh, data cleanup, stats rollup.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from celery import shared_task
from sqlalchemy import select, delete

from app.database import AsyncSessionLocal
from app.models.user import User, UserPreferences
from app.models.agent_run import PipelineRun, AgentRun
from app.models.job import Job

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(name="worker.tasks.maintenance_tasks.refresh_user_beat_schedules")
def refresh_user_beat_schedules():
    """
    Refresh the dynamic per-user pipeline schedule.
    For each active user with pipeline_enabled=True, ensure their daily task is registered.
    """
    return run_async(_refresh_schedules_async())


async def _refresh_schedules_async():
    async with AsyncSessionLocal() as db:
        # Get all active users with pipeline enabled
        result = await db.execute(
            select(User, UserPreferences)
            .join(UserPreferences, UserPreferences.user_id == User.id, isouter=True)
            .where(User.is_active == True)
        )
        rows = result.all()

        from worker.celery_app import celery_app
        from celery.schedules import crontab

        current_schedule = celery_app.conf.beat_schedule or {}
        updated = False

        for user, prefs in rows:
            pipeline_enabled = prefs.pipeline_enabled if prefs else True
            if not pipeline_enabled:
                continue

            pipeline_hour = (prefs.pipeline_hour if prefs else 8) - 1  # Convert Paris → UTC
            if pipeline_hour < 0:
                pipeline_hour = 23

            task_key = f"daily-pipeline-user-{user.id}"
            expected = {
                "task": "worker.tasks.pipeline_tasks.trigger_user_pipeline",
                "schedule": crontab(hour=pipeline_hour, minute=0),
                "args": [str(user.id)],
            }

            if task_key not in current_schedule:
                current_schedule[task_key] = expected
                updated = True
                logger.info(f"Registered pipeline schedule for user {user.id} at {pipeline_hour}:00 UTC")

        if updated:
            celery_app.conf.beat_schedule = current_schedule
            logger.info(f"Beat schedule updated: {len(current_schedule)} entries")


@shared_task(name="worker.tasks.maintenance_tasks.cleanup_old_data")
def cleanup_old_data():
    """Weekly cleanup: remove data older than 90 days."""
    return run_async(_cleanup_async())


async def _cleanup_async():
    async with AsyncSessionLocal() as db:
        cutoff = datetime.utcnow() - timedelta(days=90)

        # Delete old pipeline runs with their agent runs (cascade)
        result = await db.execute(
            select(PipelineRun.id).where(PipelineRun.started_at < cutoff)
        )
        old_run_ids = [row[0] for row in result.all()]

        if old_run_ids:
            await db.execute(delete(AgentRun).where(AgentRun.pipeline_run_id.in_(old_run_ids)))
            await db.execute(delete(PipelineRun).where(PipelineRun.id.in_(old_run_ids)))
            await db.commit()
            logger.info(f"Cleaned up {len(old_run_ids)} old pipeline runs")

        # Clean up below-threshold jobs older than 30 days
        from app.models.job import JobStatusEnum
        cutoff_jobs = datetime.utcnow() - timedelta(days=30)
        await db.execute(
            delete(Job).where(
                Job.status == JobStatusEnum.BELOW_THRESHOLD,
                Job.scraped_at < cutoff_jobs,
            )
        )
        await db.commit()
        logger.info("Cleanup complete")
