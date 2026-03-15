import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.document import DocumentTypeEnum


class DocumentOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID | None
    document_type: DocumentTypeEnum
    file_name: str | None
    file_size_bytes: int | None
    language: str
    generated_at: datetime
    generation_prompt_tokens: int
    generation_completion_tokens: int

    model_config = {"from_attributes": True}
