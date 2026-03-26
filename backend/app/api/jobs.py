import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.job import Job, JobStatusEnum, JobPlatformEnum
from app.schemas.job import JobOut, JobListOut, JobStatusUpdate, JobListResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: JobStatusEnum | None = Query(None),
    platform: JobPlatformEnum | None = Query(None),
    score_min: int | None = Query(None, ge=0, le=100),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    base_q = select(Job).where(Job.user_id == current_user.id)
    if status:
        base_q = base_q.where(Job.status == status)
    if platform:
        base_q = base_q.where(Job.platform == platform)
    if score_min is not None:
        base_q = base_q.where(Job.match_score >= score_min)

    # Count total for pagination
    count_q = select(func.count()).select_from(base_q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # Fetch page
    q = base_q.order_by(Job.scraped_at.desc()).limit(size).offset(offset)
    result = await db.execute(q)
    items = result.scalars().all()

    return JobListResponse(items=list(items), total=total, page=page, size=size)


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
