"""
Daily pipeline orchestration — powered by LangGraph StateGraph.

Flow (LangGraph nodes):
  scrape → detect_ghosts → match → research →
  generate_docs → qa_gate → submit → finalize

Each node is async; the graph is run via asyncio in a Celery worker thread.
"""
import asyncio
import logging
import uuid
from datetime import datetime

from celery import shared_task
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.agent_run import PipelineRun, AgentStatusEnum
from app.models.application import Application
from app.models.user import User, UserProfile, UserPreferences

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
    """Main pipeline orchestrator — runs the LangGraph for one user."""
    return run_async(_run_pipeline_async(user_id, pipeline_run_id))


async def _run_pipeline_async(user_id: str, pipeline_run_id: str):
    from app.agents.graph.pipeline import pipeline  # import here to avoid circular at startup

    uid = uuid.UUID(user_id)
    run_id = uuid.UUID(pipeline_run_id)

    # ── Mark pipeline RUNNING and load user data ──────────────────────────────
    async with AsyncSessionLocal() as db:
        run_result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
        pipeline_run = run_result.scalar_one_or_none()
        if not pipeline_run:
            logger.error(f"PipelineRun {run_id} not found")
            return

        pipeline_run.status = AgentStatusEnum.RUNNING
        await db.commit()

        # Load user + profile + preferences
        user_result = await db.execute(select(User).where(User.id == uid))
        user = user_result.scalar_one_or_none()

        profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == uid))
        profile = profile_result.scalar_one_or_none()

        prefs_result = await db.execute(select(UserPreferences).where(UserPreferences.user_id == uid))
        prefs = prefs_result.scalar_one_or_none()

        if not user or not prefs:
            logger.error(f"User or preferences not found for {uid}")
            pipeline_run.status = AgentStatusEnum.FAILED
            pipeline_run.completed_at = datetime.utcnow()
            await db.commit()
            return

        if not profile or not profile.cv_text_content:
            logger.warning(f"[Pipeline {run_id}] Profil incomplet pour {user.email} — pipeline annulé")
            pipeline_run.status = AgentStatusEnum.FAILED
            pipeline_run.completed_at = datetime.utcnow()
            await db.commit()
            # SSE notification
            try:
                from app.api.pipeline import publish_sse_event
                await publish_sse_event(user_id, {
                    "event": "pipeline_error",
                    "message": "Profil incomplet: uploadez votre CV pour lancer le pipeline.",
                })
            except Exception:
                pass
            return

        # Serialize model data for state (avoid SQLAlchemy lazy-load issues)
        user_info = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        }
        profile_dict = {
            "cv_html_template": profile.cv_html_template,
            "cv_text_content": profile.cv_text_content,
            "skills_technical": profile.skills_technical or [],
            "skills_soft": profile.skills_soft or [],
            "education": profile.education or [],
            "experience": profile.experience or [],
            "languages": profile.languages or [],
            "certifications": profile.certifications or [],
            "projects": getattr(profile, "projects", None) or [],
            "ville": profile.ville or "Paris",
            "phone": profile.phone or "",
            "linkedin_url": profile.linkedin_url or "",
            "github_url": getattr(profile, "github_url", "") or "",
            "portfolio_url": getattr(profile, "portfolio_url", "") or "",
        }
        prefs_dict = {
            "target_roles": prefs.target_roles or [],
            "contract_types": prefs.contract_types or ["alternance"],
            "preferred_locations": prefs.preferred_locations or ["Paris"],
            "min_match_score": prefs.min_match_score or 70,
            "daily_application_limit": prefs.daily_application_limit or 20,
            "auto_apply_enabled": prefs.auto_apply_enabled or False,
            "salary_min": prefs.salary_min,
            "exclude_keywords": prefs.exclude_keywords or [],
        }

    # ── Emit start SSE ────────────────────────────────────────────────────────
    try:
        from app.api.pipeline import publish_sse_event
        await publish_sse_event(user_id, {
            "event": "pipeline_start",
            "pipeline_run_id": pipeline_run_id,
            "message": f"Pipeline démarré pour {user_info['first_name']}",
        })
    except Exception:
        pass

    # ── Build initial state ───────────────────────────────────────────────────
    initial_state = {
        "user_id": user_id,
        "pipeline_run_id": pipeline_run_id,
        "user_profile": profile_dict,
        "user_preferences": prefs_dict,
        "user_info": user_info,
        "scraped_jobs": [],
        "valid_jobs": [],
        "matched_jobs": [],
        "jobs_ready": [],
        "errors": [],
        "jobs_scraped": 0,
        "jobs_matched": 0,
        "docs_generated": 0,
        "applications_submitted": 0,
    }

    # ── Run LangGraph ─────────────────────────────────────────────────────────
    try:
        logger.info(f"[Pipeline {run_id}] Starting LangGraph for {user.email}")
        final_state = await pipeline.ainvoke(initial_state)

        logger.info(
            f"[Pipeline {run_id}] Completed: "
            f"scraped={final_state.get('jobs_scraped')} "
            f"matched={final_state.get('jobs_matched')} "
            f"docs={final_state.get('docs_generated')} "
            f"submitted={final_state.get('applications_submitted')} "
            f"errors={len(final_state.get('errors', []))}"
        )
    except Exception as e:
        logger.error(f"[Pipeline {run_id}] LangGraph error: {e}", exc_info=True)
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
            run = result.scalar_one_or_none()
            if run:
                run.status = AgentStatusEnum.FAILED
                run.completed_at = datetime.utcnow()
                await db.commit()
        try:
            from app.api.pipeline import publish_sse_event
            await publish_sse_event(user_id, {"event": "pipeline_error", "message": str(e)})
        except Exception:
            pass
        raise


@shared_task(name="worker.tasks.pipeline_tasks.process_all_followups")
def process_all_followups():
    """Daily task: send follow-up emails for all due applications."""
    return run_async(_process_followups_async())


async def _process_followups_async():
    from app.agents.followup_agent import FollowUpAgent
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        result = await db.execute(
            select(Application).where(
                Application.follow_up_due_at <= now,
                Application.follow_up_sent_at.is_(None),
            )
        )
        due_apps = result.scalars().all()
        logger.info(f"[followups] {len(due_apps)} relances à envoyer")
        for app in due_apps:
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
    """Triggered by Celery Beat for scheduled daily runs at 07:00 UTC (08:00 Paris)."""
    async def _create_and_dispatch():
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

    pipeline_run_id = run_async(_create_and_dispatch())
    run_daily_pipeline.delay(user_id, pipeline_run_id)
    logger.info(f"[beat] Pipeline schedulé pour user={user_id} run={pipeline_run_id}")
