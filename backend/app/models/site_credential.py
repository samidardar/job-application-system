import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class SiteCredential(Base):
    """Stores Playwright session state per user per domain.

    Allows the agent to reuse browser sessions across pipeline runs
    so users only need to log in once per platform (LinkedIn, Indeed, etc.).
    The session_state_path points to a JSON file containing cookies +
    localStorage exported via Playwright's storage_state().
    """
    __tablename__ = "site_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "linkedin.com", "jobs.lever.co"
    login_email: Mapped[str] = mapped_column(String(255), nullable=False)
    session_state_path: Mapped[str | None] = mapped_column(Text)  # path to Playwright storage_state JSON
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="site_credentials")
