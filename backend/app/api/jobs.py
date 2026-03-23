import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.job import Job, JobStatusEnum, JobPlatformEnum
from app.models.document import Document, DocumentTypeEnum
from app.schemas.job import JobOut, JobListOut, JobStatusUpdate, JobDetailOut

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


@router.get("/{job_id}", response_model=JobDetailOut)
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.documents))
        .where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/generate", status_code=202)
async def generate_documents(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger CV ciblé + lettre de motivation generation for a specific job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    background_tasks.add_task(_generate_documents_task, str(current_user.id), job_id)
    return {"message": "Génération en cours", "job_id": str(job_id)}


async def _generate_documents_task(user_id: str, job_id: uuid.UUID):
    """Background task: run matching → CV optimizer → cover letter for one job."""
    import uuid as _uuid
    from app.database import AsyncSessionLocal
    from app.agents.matching_agent import MatchingAgent
    from app.agents.cv_optimizer_agent import CVOptimizerAgent
    from app.agents.cover_letter_agent import CoverLetterAgent

    user_uuid = _uuid.UUID(user_id)
    async with AsyncSessionLocal() as db:
        try:
            matching = MatchingAgent(db=db, pipeline_run_id=None, user_id=user_uuid)
            await matching.run(job_id)
            await db.commit()

            cv_agent = CVOptimizerAgent(db=db, pipeline_run_id=None, user_id=user_uuid)
            await cv_agent.run(job_id)
            await db.commit()

            letter_agent = CoverLetterAgent(db=db, pipeline_run_id=None, user_id=user_uuid)
            await letter_agent.run(job_id)
            await db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Document generation failed for job {job_id}: {e}")


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
