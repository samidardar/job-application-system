"""Add site_credentials table and fix applications unique constraint

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-15 00:00:00.000000

Changes:
- Add site_credentials table (Playwright session storage per user per domain)
- Add francetravail and bonne_alternance to jobplatformenum
- Fix critical bug: applications.job_id unique constraint was global (only one
  user per job). Corrected to (user_id, job_id) unique pair.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Fix applications unique constraint ────────────────────────────────────
    # Drop the incorrect global unique constraint on job_id alone
    # (it prevented multiple users from applying to the same job)
    op.drop_constraint('applications_job_id_key', 'applications', type_='unique')
    # Add correct composite unique constraint: one application per (user, job)
    op.create_unique_constraint(
        'uq_applications_user_job', 'applications', ['user_id', 'job_id']
    )
    # Also add index on follow_up_due_at for the followup scheduler query
    op.create_index(
        'ix_applications_follow_up_due_at', 'applications', ['follow_up_due_at']
    )

    # ── Add new enum values to jobplatformenum ────────────────────────────────
    # PostgreSQL requires COMMIT before ALTER TYPE in a transaction
    op.execute("ALTER TYPE jobplatformenum ADD VALUE IF NOT EXISTS 'francetravail'")
    op.execute("ALTER TYPE jobplatformenum ADD VALUE IF NOT EXISTS 'bonne_alternance'")

    # ── Create site_credentials table ─────────────────────────────────────────
    op.create_table(
        'site_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('domain', sa.String(255), nullable=False),
        sa.Column('login_email', sa.String(255), nullable=False),
        sa.Column('session_state_path', sa.Text()),
        sa.Column('last_verified_at', sa.DateTime()),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'domain', name='uq_site_credentials_user_domain'),
    )
    op.create_index('ix_site_credentials_user_id', 'site_credentials', ['user_id'])

    # ── Performance indexes missing from 0001 ─────────────────────────────────
    # jobs: posted_at is frequently filtered/sorted
    op.create_index('ix_jobs_posted_at', 'jobs', ['posted_at'])
    # jobs: match_score is used in dashboard queries
    op.create_index('ix_jobs_match_score', 'jobs', ['match_score'])
    # pipeline_runs: started_at for ordering
    op.create_index('ix_pipeline_runs_started_at', 'pipeline_runs', ['started_at'])


def downgrade() -> None:
    op.drop_index('ix_pipeline_runs_started_at', table_name='pipeline_runs')
    op.drop_index('ix_jobs_match_score', table_name='jobs')
    op.drop_index('ix_jobs_posted_at', table_name='jobs')
    op.drop_index('ix_site_credentials_user_id', table_name='site_credentials')
    op.drop_table('site_credentials')
    op.drop_index('ix_applications_follow_up_due_at', table_name='applications')
    op.drop_constraint('uq_applications_user_job', 'applications', type_='unique')
    op.create_unique_constraint('applications_job_id_key', 'applications', ['job_id'])
