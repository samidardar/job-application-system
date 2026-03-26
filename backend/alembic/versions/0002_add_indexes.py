"""add performance indexes

Revision ID: 0002_add_indexes
Revises: 0001_initial_schema
Create Date: 2026-03-23

"""
from alembic import op

revision = "0002_add_indexes"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_jobs_user_scraped_at", "jobs", ["user_id", "scraped_at"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_agent_runs_pipeline", "agent_runs", ["pipeline_run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_pipeline", table_name="agent_runs")
    op.drop_index("ix_applications_job_id", table_name="applications")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_user_scraped_at", table_name="jobs")
