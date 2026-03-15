import uuid
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.agent_run import PipelineRun, AgentStatusEnum
from app.schemas.agent import PipelineRunOut, PipelineTriggerResponse

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# In-memory SSE event store per user (pipeline_run_id → list of events)
_sse_queues: dict[str, asyncio.Queue] = {}


def get_sse_queue(user_id: str) -> asyncio.Queue:
    if user_id not in _sse_queues:
        _sse_queues[user_id] = asyncio.Queue(maxsize=100)
    return _sse_queues[user_id]


async def publish_sse_event(user_id: str, event: dict) -> None:
    queue = get_sse_queue(user_id)
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        pass


@router.post("/trigger", response_model=PipelineTriggerResponse)
async def trigger_pipeline(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Import here to avoid circular imports
    from worker.tasks.pipeline_tasks import run_daily_pipeline

    # Create pipeline run record
    pipeline_run = PipelineRun(
        user_id=current_user.id,
        triggered_by="manual",
        status=AgentStatusEnum.PENDING,
    )
    db.add(pipeline_run)
    await db.commit()
    await db.refresh(pipeline_run)

    # Dispatch Celery task
    task = run_daily_pipeline.delay(
        str(current_user.id),
        str(pipeline_run.id),
    )

    # Update with celery task id
    pipeline_run.celery_task_id = task.id
    await db.commit()

    return PipelineTriggerResponse(
        pipeline_run_id=pipeline_run.id,
        celery_task_id=task.id,
        message="Pipeline started. Use /pipeline/stream for live updates.",
    )


@router.get("/status")
async def get_pipeline_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.user_id == current_user.id)
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        return {"status": "no_runs", "message": "No pipeline runs yet"}
    return {
        "pipeline_run_id": str(run.id),
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "jobs_scraped": run.jobs_scraped,
        "jobs_matched": run.jobs_matched,
        "applications_submitted": run.applications_submitted,
    }


@router.get("/runs", response_model=list[PipelineRunOut])
async def list_pipeline_runs(
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.user_id == current_user.id)
        .order_by(PipelineRun.started_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=PipelineRunOut)
async def get_pipeline_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(PipelineRun)
        .options(selectinload(PipelineRun.agent_runs))
        .where(PipelineRun.id == run_id, PipelineRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run


@router.get("/stream")
async def stream_pipeline(current_user: User = Depends(get_current_user)):
    """Server-Sent Events endpoint for live pipeline status."""
    user_id = str(current_user.id)
    queue = get_sse_queue(user_id)

    async def event_generator():
        # Send initial connected event
        yield f"data: {json.dumps({'event': 'connected', 'user_id': user_id})}\n\n"

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
