import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.application import Application, ApplicationStatusEnum
from app.models.job import Job
from app.schemas.application import ApplicationOut, ApplicationStatusUpdate, ApplicationStats

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationOut])
async def list_applications(
    status: ApplicationStatusEnum | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Application).where(Application.user_id == current_user.id)
    if status:
        q = q.where(Application.status == status)
    q = q.order_by(Application.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/stats", response_model=ApplicationStats)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.user_id == current_user.id)
    )
    apps = result.scalars().all()

    total = len(apps)
    submitted = sum(1 for a in apps if a.status != ApplicationStatusEnum.PENDING)
    viewed = sum(1 for a in apps if a.status == ApplicationStatusEnum.VIEWED)
    interviews = sum(1 for a in apps if a.status == ApplicationStatusEnum.INTERVIEW_SCHEDULED)
    offers = sum(1 for a in apps if a.status == ApplicationStatusEnum.OFFER_RECEIVED)
    rejected = sum(1 for a in apps if a.status == ApplicationStatusEnum.REJECTED)

    responses = viewed + interviews + offers + rejected
    response_rate = (responses / submitted * 100) if submitted > 0 else 0.0

    # Get avg match score from related jobs
    job_ids = [a.job_id for a in apps]
    avg_score = None
    if job_ids:
        score_result = await db.execute(
            select(func.avg(Job.match_score)).where(Job.id.in_(job_ids))
        )
        avg_score = score_result.scalar()

    return ApplicationStats(
        total=total,
        submitted=submitted,
        viewed=viewed,
        interview_scheduled=interviews,
        offer_received=offers,
        rejected=rejected,
        response_rate=round(response_rate, 1),
        avg_match_score=round(float(avg_score), 1) if avg_score else None,
    )


@router.get("/{app_id}", response_model=ApplicationOut)
async def get_application(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.id == app_id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/{app_id}", response_model=ApplicationOut)
async def update_application(
    app_id: uuid.UUID,
    data: ApplicationStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.id == app_id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    old_status = app.status
    app.status = data.status
    if data.notes:
        app.notes = data.notes

    # Append to timeline
    timeline = app.timeline or []
    timeline.append({
        "event": f"Status changed: {old_status} → {data.status}",
        "timestamp": datetime.utcnow().isoformat(),
        "details": {"notes": data.notes},
    })
    app.timeline = timeline

    await db.commit()
    await db.refresh(app)
    return app
