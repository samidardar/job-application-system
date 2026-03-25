"""Add projects JSONB column to user_profiles

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-23 00:00:00.000000

Changes:
- Add projects JSONB column to user_profiles table
  (stores personal/academic projects parsed from CV or added manually)
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("projects", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "projects")
