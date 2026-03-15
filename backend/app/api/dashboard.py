from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.job import Job, JobStatusEnum
from app.models.application import Application, ApplicationStatusEnum
from app.models.agent_run import PipelineRun

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def get_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user.id
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # ── Application counts via SQL (no Python iteration over full table) ──────
    app_stats = await db.execute(
        select(
            func.count(Application.id).label("total"),
            func.count(case((Application.created_at >= month_start, Application.id))).label("this_month"),
            func.count(case((Application.status != ApplicationStatusEnum.PENDING, Application.id))).label("submitted"),
            func.count(case((Application.status == ApplicationStatusEnum.INTERVIEW_SCHEDULED, Application.id))).label("interviews"),
            func.count(case((Application.status.in_([
                ApplicationStatusEnum.VIEWED,
                ApplicationStatusEnum.REJECTED,
                ApplicationStatusEnum.INTERVIEW_SCHEDULED,
                ApplicationStatusEnum.OFFER_RECEIVED,
            ]), Application.id))).label("responses"),
        ).where(Application.user_id == user_id)
    )
    row = app_stats.one()
    total_apps = row.total
    apps_this_month = row.this_month
    submitted = row.submitted
    interviews = row.interviews
    responses = row.responses
    response_rate = round(responses / submitted * 100, 1) if submitted > 0 else 0.0

    # ── Average match score via SQL ───────────────────────────────────────────
    score_result = await db.execute(
        select(func.avg(Job.match_score), func.count(Job.id))
        .where(Job.user_id == user_id, Job.match_score.isnot(None))
    )
    avg_row = score_result.one()
    avg_score = round(float(avg_row[0]), 1) if avg_row[0] else None
    scored_jobs_count = avg_row[1]

    # ── Last pipeline run ─────────────────────────────────────────────────────
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

    # ── 7-day daily stats via SQL (one query per day would be 7 queries;
    #    fetch jobs/apps from last 7 days and aggregate in Python — bounded set) ─
    week_ago = now - timedelta(days=7)

    jobs_7d_result = await db.execute(
        select(Job.scraped_at, Job.match_score, Job.status)
        .where(Job.user_id == user_id, Job.scraped_at >= week_ago)
    )
    jobs_7d = jobs_7d_result.all()

    apps_7d_result = await db.execute(
        select(Application.submitted_at)
        .where(Application.user_id == user_id, Application.submitted_at >= week_ago)
    )
    apps_7d = apps_7d_result.scalars().all()

    daily_stats = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        scraped = sum(1 for j in jobs_7d if j.scraped_at and day_start <= j.scraped_at < day_end)
        matched = sum(1 for j in jobs_7d if j.scraped_at and j.match_score and
                      j.match_score >= 70 and day_start <= j.scraped_at < day_end)
        applied = sum(1 for a in apps_7d if a and day_start <= a < day_end)
        daily_stats.append({"date": day.strftime("%Y-%m-%d"), "scraped": scraped,
                             "matched": matched, "applied": applied})

    # ── Platform breakdown via SQL ────────────────────────────────────────────
    platform_result = await db.execute(
        select(Job.platform, func.count(Job.id).label("cnt"))
        .where(Job.user_id == user_id)
        .group_by(Job.platform)
    )
    platform_breakdown = [
        {"platform": row.platform.value, "count": row.cnt}
        for row in platform_result.all()
    ]

    # ── Score distribution via SQL ────────────────────────────────────────────
    score_dist_result = await db.execute(
        select(
            func.count(case((Job.match_score < 50, Job.id))).label("low"),
            func.count(case(((Job.match_score >= 50) & (Job.match_score < 70), Job.id))).label("mid"),
            func.count(case(((Job.match_score >= 70) & (Job.match_score < 85), Job.id))).label("good"),
            func.count(case((Job.match_score >= 85, Job.id))).label("excellent"),
        ).where(Job.user_id == user_id, Job.match_score.isnot(None))
    )
    sd = score_dist_result.one()
    score_distribution = [
        {"range": "0-49", "count": sd.low},
        {"range": "50-69", "count": sd.mid},
        {"range": "70-84", "count": sd.good},
        {"range": "85-100", "count": sd.excellent},
    ]

    # ── Top opportunities (bounded: top 10 by score, not applied) ────────────
    top_result = await db.execute(
        select(Job)
        .where(
            Job.user_id == user_id,
            Job.match_score.isnot(None),
            Job.status.notin_([JobStatusEnum.APPLIED, JobStatusEnum.BELOW_THRESHOLD]),
        )
        .order_by(Job.match_score.desc())
        .limit(10)
    )
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
        for j in top_result.scalars().all()
    ]

    # ── Recent pipeline runs (already bounded) ────────────────────────────────
    activity_result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.user_id == user_id)
        .order_by(PipelineRun.started_at.desc())
        .limit(5)
    )
    recent_activity = [
        {
            "type": "pipeline_run",
            "timestamp": r.started_at.isoformat(),
            "status": r.status,
            "scraped": r.jobs_scraped,
            "matched": r.jobs_matched,
            "applied": r.applications_submitted,
        }
        for r in activity_result.scalars().all()
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
