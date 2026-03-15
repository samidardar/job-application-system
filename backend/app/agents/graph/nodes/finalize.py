"""
Finalize node — Updates PipelineRun counters and fires SSE events.
"""
import logging
import uuid
from datetime import datetime

from sqlalchemy import select

from app.agents.graph.state import PipelineState
from app.database import AsyncSessionLocal
from app.models.agent_run import PipelineRun, AgentStatusEnum

logger = logging.getLogger(__name__)


async def node_finalize(state: PipelineState) -> dict:
    """Update PipelineRun with final counters and push SSE summary event."""
    pipeline_run_id = state.get("pipeline_run_id")
    errors = state.get("errors") or []

    summary = {
        "jobs_scraped": state.get("jobs_scraped") or 0,
        "jobs_matched": state.get("jobs_matched") or 0,
        "docs_generated": state.get("docs_generated") or 0,
        "applications_submitted": state.get("applications_submitted") or 0,
        "jobs_ready_for_review": len(state.get("jobs_ready") or []) - (state.get("applications_submitted") or 0),
        "errors_count": len(errors),
    }

    if pipeline_run_id:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(PipelineRun).where(PipelineRun.id == uuid.UUID(pipeline_run_id))
                )
                run = result.scalar_one_or_none()
                if run:
                    run.status = AgentStatusEnum.FAILED if errors and not state.get("jobs_ready") else AgentStatusEnum.SUCCESS
                    run.completed_at = datetime.utcnow()
                    run.jobs_scraped = summary["jobs_scraped"]
                    run.jobs_matched = summary["jobs_matched"]
                    run.applications_submitted = summary["applications_submitted"]
                    if hasattr(run, "errors_count"):
                        run.errors_count = summary["errors_count"]
                    await db.commit()
        except Exception as e:
            logger.error(f"[finalize] DB update error: {e}")

    # SSE event (best-effort)
    try:
        from app.api.pipeline import publish_sse_event
        await publish_sse_event(state["user_id"], {
            "event": "pipeline_complete",
            "pipeline_run_id": pipeline_run_id,
            **summary,
        })
    except Exception:
        pass

    logger.info(
        f"[finalize] Pipeline terminé — "
        f"scrappées={summary['jobs_scraped']} matchées={summary['jobs_matched']} "
        f"docs={summary['docs_generated']} soumises={summary['applications_submitted']} "
        f"en_revue={summary['jobs_ready_for_review']}"
    )
    return {}
