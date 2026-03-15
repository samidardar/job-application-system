import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.job import Job, JobStatusEnum, JobPlatformEnum
from app.schemas.job import JobOut, JobListOut, JobStatusUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobListOut])
async def list_jobs(
    status: JobStatusEnum | None = Query(None),
    platform: JobPlatformEnum | None = Query(None),
    score_min: int | None = Query(None, ge=0, le=100),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Job).where(Job.user_id == current_user.id)
    if status:
        q = q.where(Job.status == status)
    if platform:
        q = q.where(Job.platform == platform)
    if score_min is not None:
        q = q.where(Job.match_score >= score_min)
    q = q.order_by(Job.scraped_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}/status", response_model=JobOut)
async def update_job_status(
    job_id: uuid.UUID,
    data: JobStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = data.status
    await db.commit()
    await db.refresh(job)
    return job
