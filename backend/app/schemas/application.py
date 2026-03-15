import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.application import ApplicationStatusEnum


class ApplicationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    cv_document_id: uuid.UUID | None
    cover_letter_document_id: uuid.UUID | None
    status: ApplicationStatusEnum
    submitted_at: datetime | None
    submission_method: str | None
    follow_up_due_at: datetime | None
    follow_up_sent_at: datetime | None
    response_received_at: datetime | None
    notes: str | None
    timeline: list | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatusEnum
    notes: str | None = None


class ApplicationStats(BaseModel):
    total: int
    submitted: int
    viewed: int
    interview_scheduled: int
    offer_received: int
    rejected: int
    response_rate: float
    avg_match_score: float | None
