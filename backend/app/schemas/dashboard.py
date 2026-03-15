from pydantic import BaseModel


class DailyStats(BaseModel):
    date: str
    scraped: int
    matched: int
    applied: int


class PlatformBreakdown(BaseModel):
    platform: str
    count: int


class DashboardMetrics(BaseModel):
    # Summary cards
    total_applications: int
    applications_this_month: int
    response_rate: float
    interviews_count: int
    avg_match_score: float | None
    pipeline_today: dict  # {scraped, matched, applied, status}

    # Charts data
    daily_stats_7d: list[DailyStats]
    platform_breakdown: list[PlatformBreakdown]
    match_score_distribution: list[dict]  # [{range, count}]

    # Last pipeline run
    last_pipeline_run: dict | None

    # Top opportunities
    top_opportunities: list[dict]

    # Activity feed
    recent_activity: list[dict]
