"""
LangGraph pipeline state for Postulio.
All data flows through PipelineState between nodes.
"""
from typing import TypedDict, Annotated
import operator


class JobDict(TypedDict, total=False):
    """A job as it moves through the pipeline (DB id + enriched data)."""
    id: str                      # UUID from DB
    external_id: str
    platform: str
    title: str
    company: str
    company_size: str | None
    location: str
    remote_type: str | None
    job_type: str | None         # alternance | stage | cdi | cdd | freelance
    salary_range: str | None
    description_raw: str
    application_url: str
    posted_at: str | None

    # After matching
    match_score: int
    ats_keywords: list[str]
    tailoring_hints: str
    match_reasons: list[str]
    skill_gaps: list[str]

    # After research
    company_research: dict       # {type, culture, tech_stack, context, hook_idea}

    # After document generation
    cv_doc_id: str | None
    ldm_doc_id: str | None
    cv_html: str                 # For QA grading
    ldm_text: str                # For QA grading

    # After QA gate
    qa_grade: str                # A+, A, B+, B, F
    qa_score: int                # 0-100
    qa_feedback: str             # Feedback for retry
    retry_count: int             # Max 1 retry

    # Final
    ready_to_apply: bool
    application_id: str | None


class PipelineState(TypedDict, total=False):
    """Full pipeline state flowing through LangGraph nodes."""

    # Input (set by worker before running graph)
    user_id: str
    pipeline_run_id: str
    user_profile: dict           # UserProfile fields as dict
    user_preferences: dict       # UserPreferences fields as dict
    user_info: dict              # {first_name, last_name, email}

    # Stage: scraping
    scraped_jobs: list[dict]     # Raw dicts from all sources

    # Stage: ghost detection
    valid_jobs: list[dict]       # Non-ghost jobs

    # Stage: matching (score >= threshold → matched)
    matched_jobs: list[JobDict]

    # Stage: document generation + QA
    jobs_ready: list[JobDict]    # qa_grade A or A+, ready_to_apply=True

    # Errors (auto-merged with operator.add)
    errors: Annotated[list[str], operator.add]

    # Counters (updated by finalize node)
    jobs_scraped: int
    jobs_matched: int
    docs_generated: int
    applications_submitted: int
