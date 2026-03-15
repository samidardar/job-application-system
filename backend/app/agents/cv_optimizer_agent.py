import logging
import uuid
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.agents.base_agent import BaseAgent
from app.models.job import Job, JobStatusEnum
from app.models.document import Document, DocumentTypeEnum
from app.models.agent_run import AgentStatusEnum
from app.models.user import UserProfile
from app.services.claude_service import get_claude_service
from app.services.pdf_generator import generate_pdf
from app.config import settings

logger = logging.getLogger(__name__)


class CVOptimizerOutput(BaseModel):
    cv_html: str
    keywords_injected: list[str]
    changes_made: list[str]
    ats_score_estimate: int


class CVOptimizerAgent(BaseAgent):
    name = "cv_optimizer"

    async def run(self, job_id: uuid.UUID) -> uuid.UUID | None:
        """Generate a tailored CV for a job. Returns document_id."""
        await self._start_run(job_id=job_id, input_data={"job_id": str(job_id)})

        try:
            job_result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if not job:
                await self._finish_run(AgentStatusEnum.FAILED, error_message="Job not found")
                return None

            profile_result = await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == self.user_id)
            )
            profile = profile_result.scalar_one_or_none()

            if not profile or not profile.cv_html_template:
                await self._finish_run(AgentStatusEnum.SKIPPED, error_message="No CV template")
                return None

            system = """You are an expert ATS-optimization specialist and senior technical recruiter.
You rewrite CV content to maximally match a specific job description WITHOUT fabricating experience.
Every bullet point must be truthful, quantified where possible, and keyword-rich.
Keep the same HTML structure — only modify text content.
Do NOT invent skills, certifications, or experience the candidate doesn't have."""

            user_msg = f"""## BASE CV (HTML)
{profile.cv_html_template}

## TARGET JOB
Title: {job.title} at {job.company}
Must-have keywords: {', '.join(job.ats_keywords_critical or [])}
Tailoring hints: {job.tailoring_hints or 'Focus on matching the job requirements'}
Job description: {(job.description_raw or '')[:2000]}

## RULES
- Reorder skills to lead with the most relevant ones for this job
- Rewrite 2-3 experience bullets to mirror job description language
- Inject ATS keywords naturally (no keyword stuffing)
- Keep same HTML structure, only change text content
- Output must be valid HTML"""

            claude = get_claude_service()
            result, pt, ct = await claude.complete_structured(
                system=system,
                user=user_msg,
                output_schema=CVOptimizerOutput,
                max_tokens=6000,
            )

            # Generate PDF
            file_name = f"cv_{job.company.replace(' ', '_')}_{job_id}.pdf"
            file_path = str(Path(settings.storage_path) / "documents" / str(self.user_id) / file_name)

            file_size = await generate_pdf(result.cv_html, file_path)

            # Save document
            doc = Document(
                user_id=self.user_id,
                job_id=job_id,
                document_type=DocumentTypeEnum.CV_TAILORED,
                content_html=result.cv_html,
                content_text="",
                ats_keywords_injected=result.keywords_injected,
                file_path=file_path,
                file_name=file_name,
                file_size_bytes=file_size,
                generation_prompt_tokens=pt,
                generation_completion_tokens=ct,
            )
            self.db.add(doc)
            await self.db.flush()

            job.status = JobStatusEnum.CV_GENERATED
            await self.db.flush()

            await self._finish_run(
                AgentStatusEnum.SUCCESS,
                output_data={
                    "document_id": str(doc.id),
                    "ats_score": result.ats_score_estimate,
                    "keywords_count": len(result.keywords_injected),
                },
                claude_tokens_used=pt + ct,
            )

            return doc.id

        except Exception as e:
            logger.error(f"CV optimization failed for job {job_id}: {e}", exc_info=True)
            await self._finish_run(AgentStatusEnum.FAILED, error_message=str(e))
            return None
