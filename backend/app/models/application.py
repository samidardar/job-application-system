import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import Job
    from app.models.document import Document


class ApplicationStatusEnum(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    VIEWED = "viewed"
    REJECTED = "rejected"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    OFFER_RECEIVED = "offer_received"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    cv_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    cover_letter_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))

    # Submission
    status: Mapped[ApplicationStatusEnum] = mapped_column(
        SAEnum(ApplicationStatusEnum),
        default=ApplicationStatusEnum.PENDING,
        index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    submission_method: Mapped[str | None] = mapped_column(String(100))
    submission_screenshot_path: Mapped[str | None] = mapped_column(String(500))

    # Tracking & follow-up
    last_status_check: Mapped[datetime | None] = mapped_column(DateTime)
    follow_up_due_at: Mapped[datetime | None] = mapped_column(DateTime)
    follow_up_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    response_received_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)

    # Timeline: [{event, timestamp, details}]
    timeline: Mapped[list | None] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="applications")
    job: Mapped["Job"] = relationship("Job", back_populates="application")
    cv_document: Mapped["Document | None"] = relationship("Document", foreign_keys=[cv_document_id])
    cover_letter_document: Mapped["Document | None"] = relationship("Document", foreign_keys=[cover_letter_document_id])
