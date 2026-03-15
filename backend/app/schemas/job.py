import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.job import JobPlatformEnum, JobTypeEnum, JobStatusEnum


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

    model_config = {"from_attributes": True}


class JobStatusUpdate(BaseModel):
    status: JobStatusEnum
