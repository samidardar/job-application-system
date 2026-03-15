import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.agents.base_agent import BaseAgent
from app.models.job import Job, JobStatusEnum
from app.models.agent_run import AgentStatusEnum
from app.models.user import UserProfile, UserPreferences
from app.services.claude_service import get_claude_service

logger = logging.getLogger(__name__)


class MatchingOutput(BaseModel):
    score: int
    verdict: str  # "apply" | "skip"
    top_match_reasons: list[str]
    skill_gaps: list[str]
    ats_keywords_critical: list[str]
    tailoring_hints: str


class MatchingAgent(BaseAgent):
    name = "matching"

    async def run(self, job_id: uuid.UUID) -> bool:
        """Score a job against user profile. Returns True if matched (score >= threshold)."""
        await self._start_run(job_id=job_id, input_data={"job_id": str(job_id)})

        try:
            # Load job, profile, preferences
            job_result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if not job:
                await self._finish_run(AgentStatusEnum.FAILED, error_message="Job not found")
                return False

            profile_result = await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == self.user_id)
            )
            profile = profile_result.scalar_one_or_none()

            prefs_result = await self.db.execute(
                select(UserPreferences).where(UserPreferences.user_id == self.user_id)
            )
            prefs = prefs_result.scalar_one_or_none()

            if not profile or not profile.cv_text_content:
                await self._finish_run(AgentStatusEnum.SKIPPED, error_message="No CV uploaded")
                return False

            threshold = prefs.min_match_score if prefs else 70

            # Build Claude prompt
            system, user_msg = self._build_prompt(job, profile, prefs)

            claude = get_claude_service()
            result, pt, ct = await claude.complete_structured(
                system=system,
                user=user_msg,
                output_schema=MatchingOutput,
                max_tokens=2000,
            )

            # Update job with matching results
            job.match_score = result.score
            job.match_rationale = {
                "top_match_reasons": result.top_match_reasons,
                "skill_gaps": result.skill_gaps,
                "verdict": result.verdict,
            }
            job.match_highlights = result.top_match_reasons
            job.ats_keywords_critical = result.ats_keywords_critical
            job.tailoring_hints = result.tailoring_hints

            is_match = result.score >= threshold

            if is_match:
                job.status = JobStatusEnum.MATCHED
            else:
                job.status = JobStatusEnum.BELOW_THRESHOLD

            await self.db.flush()

            await self._finish_run(
                AgentStatusEnum.SUCCESS,
                output_data={
                    "score": result.score,
                    "verdict": result.verdict,
                    "is_match": is_match,
                },
                claude_tokens_used=pt + ct,
            )

            return is_match

        except Exception as e:
            logger.error(f"Matching failed for job {job_id}: {e}", exc_info=True)
            if job:
                job.status = JobStatusEnum.FAILED
                await self.db.flush()
            await self._finish_run(AgentStatusEnum.FAILED, error_message=str(e))
            return False

    def _build_prompt(self, job: Job, profile: UserProfile, prefs: UserPreferences | None) -> tuple[str, str]:
        system = """You are an expert French job market recruiter specializing in tech, data science, and AI roles.
You evaluate job-candidate fit with surgical precision. Score from 0 to 100 where 70+ means apply.
Be ruthlessly honest. A score of 70+ means this candidate has a realistic chance of getting an interview.
Consider ATS keyword matching, skills alignment, contract type match, location, and experience level."""

        skills = ", ".join(profile.skills_technical or [])
        education = str(profile.education or [])[:500]
        experience = str(profile.experience or [])[:800]
        target_roles = ", ".join(prefs.target_roles or []) if prefs else ""
        contract_types = ", ".join(prefs.contract_types or []) if prefs else ""
        locations = ", ".join(prefs.preferred_locations or []) if prefs else ""

        user_msg = f"""## CANDIDATE PROFILE
Target roles: {target_roles}
Contract types sought: {contract_types}
Preferred locations: {locations}
Technical skills: {skills}
Education: {education}
Experience: {experience}

## JOB OFFER
Title: {job.title}
Company: {job.company} ({job.company_size or 'unknown size'})
Location: {job.location} — {job.remote_type or 'on-site'}
Contract: {job.job_type.value if job.job_type else 'not specified'}
Description: {(job.description_raw or '')[:3000]}

## TASK
Score this job-candidate fit and provide actionable tailoring hints."""

        return system, user_msg
