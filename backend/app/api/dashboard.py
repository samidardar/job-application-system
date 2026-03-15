from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.job import Job, JobStatusEnum
from app.models.application import Application, ApplicationStatusEnum
from app.models.agent_run import PipelineRun, AgentStatusEnum

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def get_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user.id
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    # Applications
    apps_result = await db.execute(
        select(Application).where(Application.user_id == user_id)
    )
    all_apps = apps_result.scalars().all()
    total_apps = len(all_apps)
    apps_this_month = sum(1 for a in all_apps if a.created_at >= month_start)
    submitted = sum(1 for a in all_apps if a.status != ApplicationStatusEnum.PENDING)
    interviews = sum(1 for a in all_apps if a.status == ApplicationStatusEnum.INTERVIEW_SCHEDULED)
    responses = sum(1 for a in all_apps if a.status in [
        ApplicationStatusEnum.VIEWED, ApplicationStatusEnum.REJECTED,
        ApplicationStatusEnum.INTERVIEW_SCHEDULED, ApplicationStatusEnum.OFFER_RECEIVED
    ])
    response_rate = round(responses / submitted * 100, 1) if submitted > 0 else 0.0

    # Avg match score
    jobs_result = await db.execute(
        select(Job).where(Job.user_id == user_id, Job.match_score.isnot(None))
    )
    matched_jobs = jobs_result.scalars().all()
    avg_score = round(sum(j.match_score for j in matched_jobs) / len(matched_jobs), 1) if matched_jobs else None

    # Last pipeline run
    pipeline_result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.user_id == user_id)
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    last_run = pipeline_result.scalar_one_or_none()
    pipeline_today = None
    if last_run:
        pipeline_today = {
            "status": last_run.status,
            "scraped": last_run.jobs_scraped,
            "matched": last_run.jobs_matched,
            "applied": last_run.applications_submitted,
            "started_at": last_run.started_at.isoformat(),
        }

    # 7-day daily stats
    daily_stats = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        scraped = sum(1 for j in matched_jobs if day_start <= j.scraped_at < day_end)
        matched = sum(1 for j in matched_jobs if j.match_score and j.match_score >= 70
                      and day_start <= j.scraped_at < day_end)
        applied = sum(1 for a in all_apps if a.submitted_at and day_start <= a.submitted_at < day_end)

        daily_stats.append({
            "date": day.strftime("%Y-%m-%d"),
            "scraped": scraped,
            "matched": matched,
            "applied": applied,
        })

    # Platform breakdown
    all_jobs_result = await db.execute(select(Job).where(Job.user_id == user_id))
    all_jobs = all_jobs_result.scalars().all()
    platform_counts: dict[str, int] = {}
    for j in all_jobs:
        platform_counts[j.platform.value] = platform_counts.get(j.platform.value, 0) + 1
    platform_breakdown = [{"platform": k, "count": v} for k, v in platform_counts.items()]

    # Match score distribution
    score_ranges = {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0}
    for j in matched_jobs:
        s = j.match_score
        if s < 50:
            score_ranges["0-49"] += 1
        elif s < 70:
            score_ranges["50-69"] += 1
        elif s < 85:
            score_ranges["70-84"] += 1
        else:
            score_ranges["85-100"] += 1
    score_distribution = [{"range": k, "count": v} for k, v in score_ranges.items()]

    # Top opportunities (high score, not yet applied)
    top_jobs = sorted(
        [j for j in matched_jobs if j.status not in [JobStatusEnum.APPLIED, JobStatusEnum.BELOW_THRESHOLD]],
        key=lambda j: j.match_score or 0,
        reverse=True
    )[:10]
    top_opportunities = [
        {
            "id": str(j.id),
            "title": j.title,
            "company": j.company,
            "platform": j.platform.value,
            "match_score": j.match_score,
            "job_type": j.job_type.value if j.job_type else None,
            "status": j.status.value,
        }
        for j in top_jobs
    ]

    # Recent activity (last pipeline agent runs)
    activity_result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.user_id == user_id)
        .order_by(PipelineRun.started_at.desc())
        .limit(5)
    )
    recent_runs = activity_result.scalars().all()
    recent_activity = [
        {
            "type": "pipeline_run",
            "timestamp": r.started_at.isoformat(),
            "status": r.status,
            "scraped": r.jobs_scraped,
            "matched": r.jobs_matched,
            "applied": r.applications_submitted,
        }
        for r in recent_runs
    ]

    return {
        "total_applications": total_apps,
        "applications_this_month": apps_this_month,
        "response_rate": response_rate,
        "interviews_count": interviews,
        "avg_match_score": avg_score,
        "pipeline_today": pipeline_today,
        "daily_stats_7d": daily_stats,
        "platform_breakdown": platform_breakdown,
        "match_score_distribution": score_distribution,
        "last_pipeline_run": pipeline_today,
        "top_opportunities": top_opportunities,
        "recent_activity": recent_activity,
    }
