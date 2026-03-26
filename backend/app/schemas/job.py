import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.job import JobPlatformEnum, JobTypeEnum, JobStatusEnum
from typing import List


class JobOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    external_id: str
    platform: JobPlatformEnum
    title: str
    company: str
    company_size: str | None
    location: str | None
    remote_type: str | None
    job_type: JobTypeEnum | None
    salary_range: str | None
    description_clean: str | None
    requirements_extracted: dict | None
    application_url: str | None
    posted_at: datetime | None
    scraped_at: datetime
    match_score: int | None
    match_rationale: dict | None
    match_highlights: list | None
    ats_keywords_critical: list | None
    tailoring_hints: str | None
    status: JobStatusEnum

    model_config = {"from_attributes": True}


class JobListOut(BaseModel):
    id: uuid.UUID
    platform: JobPlatformEnum
    title: str
    company: str
    location: str | None
    job_type: JobTypeEnum | None
    match_score: int | None
    status: JobStatusEnum
    posted_at: datetime | None
    scraped_at: datetime
    # Frontend-friendly aliases
    application_url: str | None = None
    description_clean: str | None = None

    @property
    def url(self) -> str | None:
        return self.application_url

    @property
    def description(self) -> str | None:
        return self.description_clean

    model_config = {"from_attributes": True}


class JobStatusUpdate(BaseModel):
    status: JobStatusEnum


class JobListResponse(BaseModel):
    """Paginated job list response."""
    items: List[JobListOut]
    total: int
    page: int
    size: int
