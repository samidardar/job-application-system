import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.agent_run import AgentStatusEnum


class AgentRunOut(BaseModel):
    id: uuid.UUID
    pipeline_run_id: uuid.UUID
    job_id: uuid.UUID | None
    agent_name: str
    status: AgentStatusEnum
    error_message: str | None
    claude_tokens_used: int
    duration_seconds: float
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class PipelineRunOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    celery_task_id: str | None
    triggered_by: str
    status: AgentStatusEnum
    started_at: datetime
    completed_at: datetime | None
    jobs_scraped: int
    jobs_matched: int
    cvs_generated: int
    letters_generated: int
    applications_submitted: int
    errors_count: int
    agent_runs: list[AgentRunOut] | None = None

    model_config = {"from_attributes": True}


class PipelineTriggerResponse(BaseModel):
    pipeline_run_id: uuid.UUID
    celery_task_id: str
    message: str
