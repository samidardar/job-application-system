import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.application import Application
    from app.models.agent_run import PipelineRun
    from app.models.site_credential import SiteCredential


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    profile: Mapped["UserProfile"] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    preferences: Mapped["UserPreferences"] = relationship("UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="user", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship("PipelineRun", back_populates="user", cascade="all, delete-orphan")
    site_credentials: Mapped[list["SiteCredential"]] = relationship("SiteCredential", back_populates="user", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    # Contact & personal info
    phone: Mapped[str | None] = mapped_column(String(50))
    ville: Mapped[str | None] = mapped_column(String(100))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    github_url: Mapped[str | None] = mapped_column(String(500))
    portfolio_url: Mapped[str | None] = mapped_column(String(500))

    # CV storage
    cv_original_path: Mapped[str | None] = mapped_column(String(500))
    cv_parsed_data: Mapped[dict | None] = mapped_column(JSONB)
    cv_text_content: Mapped[str | None] = mapped_column(Text)
    cv_html_template: Mapped[str | None] = mapped_column(Text)

    # Structured profile data (from CV parsing)
    skills_technical: Mapped[list | None] = mapped_column(JSONB)
    skills_soft: Mapped[list | None] = mapped_column(JSONB)
    education: Mapped[list | None] = mapped_column(JSONB)
    experience: Mapped[list | None] = mapped_column(JSONB)
    languages: Mapped[list | None] = mapped_column(JSONB)
    certifications: Mapped[list | None] = mapped_column(JSONB)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    # Job search preferences
    target_roles: Mapped[list | None] = mapped_column(JSONB)
    contract_types: Mapped[list | None] = mapped_column(JSONB)
    preferred_locations: Mapped[list | None] = mapped_column(JSONB)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    exclude_keywords: Mapped[list | None] = mapped_column(JSONB)

    # Pipeline config
    min_match_score: Mapped[int] = mapped_column(Integer, default=70)
    daily_application_limit: Mapped[int] = mapped_column(Integer, default=20)
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    pipeline_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    pipeline_hour: Mapped[int] = mapped_column(Integer, default=8)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="preferences")
