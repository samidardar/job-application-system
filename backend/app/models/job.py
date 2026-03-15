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
    from app.models.application import Application
    from app.models.document import Document


class JobPlatformEnum(str, Enum):
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    WTTJ = "welcometothejungle"


class JobTypeEnum(str, Enum):
    ALTERNANCE = "alternance"
    STAGE = "stage"
    CDI = "cdi"
    CDD = "cdd"
    FREELANCE = "freelance"


class JobStatusEnum(str, Enum):
    SCRAPED = "scraped"
    BELOW_THRESHOLD = "below_threshold"
    MATCHED = "matched"
    CV_GENERATED = "cv_generated"
    LETTER_GENERATED = "letter_generated"
    READY_TO_APPLY = "ready_to_apply"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    SKIPPED = "skipped"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Scraped data
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    platform: Mapped[JobPlatformEnum] = mapped_column(SAEnum(JobPlatformEnum), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(500), nullable=False)
    company_size: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(200))
    remote_type: Mapped[str | None] = mapped_column(String(50))
    job_type: Mapped[JobTypeEnum | None] = mapped_column(SAEnum(JobTypeEnum))
    salary_range: Mapped[str | None] = mapped_column(String(200))
    description_raw: Mapped[str | None] = mapped_column(Text)
    description_clean: Mapped[str | None] = mapped_column(Text)
    requirements_extracted: Mapped[dict | None] = mapped_column(JSONB)
    application_url: Mapped[str | None] = mapped_column(String(1000))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Matching
    match_score: Mapped[int | None] = mapped_column(Integer)
    match_rationale: Mapped[dict | None] = mapped_column(JSONB)
    match_highlights: Mapped[list | None] = mapped_column(JSONB)
    ats_keywords_critical: Mapped[list | None] = mapped_column(JSONB)
    tailoring_hints: Mapped[str | None] = mapped_column(Text)

    # State machine
    status: Mapped[JobStatusEnum] = mapped_column(SAEnum(JobStatusEnum), default=JobStatusEnum.SCRAPED, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="jobs")
    application: Mapped["Application | None"] = relationship("Application", back_populates="job", uselist=False)
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="job", cascade="all, delete-orphan")
