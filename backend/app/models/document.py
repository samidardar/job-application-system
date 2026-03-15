import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey, Integer, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import Job


class DocumentTypeEnum(str, Enum):
    CV_ORIGINAL = "cv_original"
    CV_TAILORED = "cv_tailored"
    COVER_LETTER = "cover_letter"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))

    document_type: Mapped[DocumentTypeEnum] = mapped_column(SAEnum(DocumentTypeEnum), nullable=False)

    # Content
    content_html: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    ats_keywords_injected: Mapped[list | None] = mapped_column(JSONB)

    # Storage
    file_path: Mapped[str | None] = mapped_column(String(500))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)

    # Meta
    language: Mapped[str] = mapped_column(String(10), default="fr")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    generation_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    generation_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    user: Mapped["User"] = relationship("User")
    job: Mapped["Job | None"] = relationship("Job", back_populates="documents")
