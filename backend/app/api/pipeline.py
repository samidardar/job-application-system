import uuid
import asyncio
import json
from datetime import datetime, timedelta
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

# SSE channel prefix in Redis
_SSE_CHANNEL_PREFIX = "postulio:sse:"
# Maximum concurrent SSE connections per user (prevent resource exhaustion)
_MAX_SSE_CONNECTIONS = 3
_sse_connection_counts: dict[str, int] = {}


async def _get_redis():
    """Get an async Redis client. Uses redis.asyncio (bundled with redis package)."""
    import redis.asyncio as aioredis
    from app.config import settings
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def publish_sse_event(user_id: str, event: dict) -> None:
    """Publish an SSE event to Redis pub/sub channel for this user.

    Works across multiple uvicorn workers: any worker that has a subscriber
    for this user_id will forward the event to the SSE client.
    """
    try:
        redis = await _get_redis()
        channel = f"{_SSE_CHANNEL_PREFIX}{user_id}"
        await redis.publish(channel, json.dumps(event))
        await redis.aclose()
    except Exception:
        pass  # SSE is best-effort; pipeline should not fail if SSE fails


@router.post("/trigger", response_model=PipelineTriggerResponse)
async def trigger_pipeline(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Prevent concurrent pipeline runs for the same user
    running = await db.execute(
        select(PipelineRun).where(
            PipelineRun.user_id == current_user.id,
            PipelineRun.status.in_([AgentStatusEnum.PENDING, AgentStatusEnum.RUNNING]),
        )
    )
    if running.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="A pipeline is already running for your account. Wait for it to finish.",
        )

    # Rate-limit: max 2 manual triggers per day (midnight UTC window)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_runs = await db.execute(
        select(PipelineRun).where(
            PipelineRun.user_id == current_user.id,
            PipelineRun.triggered_by == "manual",
            PipelineRun.started_at >= today_start,
        )
    )
    daily_run_count = len(daily_runs.scalars().all())
    if daily_run_count >= 2:
        raise HTTPException(
            status_code=429,
            detail="Maximum 2 déclenchements manuels par jour. Le pipeline tourne aussi automatiquement à 8h00.",
        )

    from worker.tasks.pipeline_tasks import run_daily_pipeline

    pipeline_run = PipelineRun(
        user_id=current_user.id,
        triggered_by="manual",
        status=AgentStatusEnum.PENDING,
    )
    db.add(pipeline_run)
    await db.commit()
    await db.refresh(pipeline_run)

    task = run_daily_pipeline.delay(
        str(current_user.id),
        str(pipeline_run.id),
    )

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
    limit: int = Query(20, ge=1, le=100),
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
    """Server-Sent Events endpoint for live pipeline status.

    Uses Redis pub/sub so events work correctly across multiple uvicorn workers.
    """
    user_id = str(current_user.id)

    # Limit concurrent SSE connections per user
    count = _sse_connection_counts.get(user_id, 0)
    if count >= _MAX_SSE_CONNECTIONS:
        raise HTTPException(
            status_code=429,
            detail="Too many open SSE connections. Close existing ones first.",
        )

    async def event_generator():
        _sse_connection_counts[user_id] = _sse_connection_counts.get(user_id, 0) + 1
        redis = None
        pubsub = None
        try:
            redis = await _get_redis()
            pubsub = redis.pubsub()
            channel = f"{_SSE_CHANNEL_PREFIX}{user_id}"
            await pubsub.subscribe(channel)

            yield f"data: {json.dumps({'event': 'connected', 'user_id': user_id})}\n\n"

            # Heartbeat interval (seconds) — keeps connection alive through proxies
            heartbeat_interval = 25
            last_heartbeat = asyncio.get_running_loop().time()

            while True:
                # Non-blocking check for new message
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    yield f"data: {message['data']}\n\n"
                    # Check if this is a terminal event — close the stream
                    try:
                        evt = json.loads(message["data"])
                        if evt.get("event") in ("pipeline_complete", "pipeline_error"):
                            break
                    except Exception:
                        pass

                # Send heartbeat every 25s
                now = asyncio.get_running_loop().time()
                if now - last_heartbeat >= heartbeat_interval:
                    yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"
                    last_heartbeat = now

                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass  # Client disconnected
        finally:
            _sse_connection_counts[user_id] = max(0, _sse_connection_counts.get(user_id, 1) - 1)
            if pubsub:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.aclose()
                except Exception:
                    pass
            if redis:
                try:
                    await redis.aclose()
                except Exception:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
