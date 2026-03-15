"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ENUMs first
    job_platform_enum = postgresql.ENUM(
        'linkedin', 'indeed', 'welcometothejungle',
        name='jobplatformenum', create_type=False
    )
    job_type_enum = postgresql.ENUM(
        'alternance', 'stage', 'cdi', 'cdd', 'freelance',
        name='jobtypeenum', create_type=False
    )
    job_status_enum = postgresql.ENUM(
        'scraped', 'below_threshold', 'matched', 'cv_generated',
        'letter_generated', 'ready_to_apply', 'applying', 'applied', 'failed', 'skipped',
        name='jobstatusenum', create_type=False
    )
    app_status_enum = postgresql.ENUM(
        'pending', 'submitted', 'viewed', 'rejected',
        'interview_scheduled', 'offer_received',
        name='applicationstatusenum', create_type=False
    )
    doc_type_enum = postgresql.ENUM(
        'cv_original', 'cv_tailored', 'cover_letter',
        name='documenttypeenum', create_type=False
    )
    agent_status_enum = postgresql.ENUM(
        'pending', 'running', 'success', 'failed', 'skipped',
        name='agentstatusenum', create_type=False
    )

    for enum in [job_platform_enum, job_type_enum, job_status_enum,
                 app_status_enum, doc_type_enum, agent_status_enum]:
        enum.create(op.get_bind(), checkfirst=True)

    # users
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # user_profiles
    op.create_table('user_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('phone', sa.String(50)),
        sa.Column('ville', sa.String(100)),
        sa.Column('linkedin_url', sa.String(500)),
        sa.Column('github_url', sa.String(500)),
        sa.Column('portfolio_url', sa.String(500)),
        sa.Column('cv_original_path', sa.String(500)),
        sa.Column('cv_parsed_data', postgresql.JSONB()),
        sa.Column('cv_text_content', sa.Text()),
        sa.Column('cv_html_template', sa.Text()),
        sa.Column('skills_technical', postgresql.JSONB()),
        sa.Column('skills_soft', postgresql.JSONB()),
        sa.Column('education', postgresql.JSONB()),
        sa.Column('experience', postgresql.JSONB()),
        sa.Column('languages', postgresql.JSONB()),
        sa.Column('certifications', postgresql.JSONB()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )

    # user_preferences
    op.create_table('user_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_roles', postgresql.JSONB()),
        sa.Column('contract_types', postgresql.JSONB()),
        sa.Column('preferred_locations', postgresql.JSONB()),
        sa.Column('salary_min', sa.Integer()),
        sa.Column('exclude_keywords', postgresql.JSONB()),
        sa.Column('min_match_score', sa.Integer(), nullable=False, server_default='70'),
        sa.Column('daily_application_limit', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('auto_apply_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('pipeline_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('pipeline_hour', sa.Integer(), nullable=False, server_default='8'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )

    # jobs
    op.create_table('jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_id', sa.String(500), nullable=False),
        sa.Column('platform', sa.Enum('linkedin', 'indeed', 'welcometothejungle', name='jobplatformenum'), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('company', sa.String(500), nullable=False),
        sa.Column('company_size', sa.String(100)),
        sa.Column('location', sa.String(200)),
        sa.Column('remote_type', sa.String(50)),
        sa.Column('job_type', sa.Enum('alternance', 'stage', 'cdi', 'cdd', 'freelance', name='jobtypeenum')),
        sa.Column('salary_range', sa.String(200)),
        sa.Column('description_raw', sa.Text()),
        sa.Column('description_clean', sa.Text()),
        sa.Column('requirements_extracted', postgresql.JSONB()),
        sa.Column('application_url', sa.String(1000)),
        sa.Column('posted_at', sa.DateTime()),
        sa.Column('scraped_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('match_score', sa.Integer()),
        sa.Column('match_rationale', postgresql.JSONB()),
        sa.Column('match_highlights', postgresql.JSONB()),
        sa.Column('ats_keywords_critical', postgresql.JSONB()),
        sa.Column('tailoring_hints', sa.Text()),
        sa.Column('status', sa.Enum('scraped', 'below_threshold', 'matched', 'cv_generated',
                                    'letter_generated', 'ready_to_apply', 'applying', 'applied',
                                    'failed', 'skipped', name='jobstatusenum'),
                  nullable=False, server_default='scraped'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_jobs_user_id', 'jobs', ['user_id'])
    op.create_index('ix_jobs_status', 'jobs', ['status'])
    op.create_index('ix_jobs_user_external', 'jobs', ['user_id', 'external_id', 'platform'], unique=True)

    # documents
    op.create_table('documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True)),
        sa.Column('document_type', sa.Enum('cv_original', 'cv_tailored', 'cover_letter', name='documenttypeenum'), nullable=False),
        sa.Column('content_html', sa.Text()),
        sa.Column('content_text', sa.Text()),
        sa.Column('ats_keywords_injected', postgresql.JSONB()),
        sa.Column('file_path', sa.String(500)),
        sa.Column('file_name', sa.String(255)),
        sa.Column('file_size_bytes', sa.Integer()),
        sa.Column('language', sa.String(10), nullable=False, server_default='fr'),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('generation_prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('generation_completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_user_id', 'documents', ['user_id'])

    # applications
    op.create_table('applications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cv_document_id', postgresql.UUID(as_uuid=True)),
        sa.Column('cover_letter_document_id', postgresql.UUID(as_uuid=True)),
        sa.Column('status', sa.Enum('pending', 'submitted', 'viewed', 'rejected',
                                    'interview_scheduled', 'offer_received',
                                    name='applicationstatusenum'),
                  nullable=False, server_default='pending'),
        sa.Column('submitted_at', sa.DateTime()),
        sa.Column('submission_method', sa.String(100)),
        sa.Column('submission_screenshot_path', sa.String(500)),
        sa.Column('last_status_check', sa.DateTime()),
        sa.Column('follow_up_due_at', sa.DateTime()),
        sa.Column('follow_up_sent_at', sa.DateTime()),
        sa.Column('response_received_at', sa.DateTime()),
        sa.Column('notes', sa.Text()),
        sa.Column('timeline', postgresql.JSONB(), server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['cv_document_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['cover_letter_document_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id'),
    )
    op.create_index('ix_applications_user_id', 'applications', ['user_id'])
    op.create_index('ix_applications_status', 'applications', ['status'])

    # pipeline_runs
    op.create_table('pipeline_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('celery_task_id', sa.String(255)),
        sa.Column('triggered_by', sa.String(50), nullable=False, server_default='schedule'),
        sa.Column('status', sa.Enum('pending', 'running', 'success', 'failed', 'skipped', name='agentstatusenum'),
                  nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('jobs_scraped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('jobs_matched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cvs_generated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('letters_generated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('applications_submitted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('errors_count', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pipeline_runs_user_id', 'pipeline_runs', ['user_id'])

    # agent_runs
    op.create_table('agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pipeline_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True)),
        sa.Column('agent_name', sa.String(100), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'success', 'failed', 'skipped', name='agentstatusenum'),
                  nullable=False, server_default='pending'),
        sa.Column('input_data', postgresql.JSONB()),
        sa.Column('output_data', postgresql.JSONB()),
        sa.Column('error_message', sa.Text()),
        sa.Column('claude_tokens_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_seconds', sa.Float(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['pipeline_run_id'], ['pipeline_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_runs_pipeline_run_id', 'agent_runs', ['pipeline_run_id'])


def downgrade() -> None:
    op.drop_table('agent_runs')
    op.drop_table('pipeline_runs')
    op.drop_table('applications')
    op.drop_table('documents')
    op.drop_table('jobs')
    op.drop_table('user_preferences')
    op.drop_table('user_profiles')
    op.drop_table('users')

    for enum_name in ['jobplatformenum', 'jobtypeenum', 'jobstatusenum',
                      'applicationstatusenum', 'documenttypeenum', 'agentstatusenum']:
        op.execute(f'DROP TYPE IF EXISTS {enum_name}')
