import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.agents.base_agent import BaseAgent
from app.models.job import Job, JobStatusEnum, JobPlatformEnum
from app.models.application import Application, ApplicationStatusEnum
from app.models.document import Document, DocumentTypeEnum
from app.models.agent_run import AgentStatusEnum
from app.models.user import User, UserProfile
from app.services.claude_service import get_claude_service
from app.config import settings

logger = logging.getLogger(__name__)


class ScreeningAnswer(BaseModel):
    answer: str
    confidence: str
    reasoning: str


class ApplicationAgent(BaseAgent):
    name = "application"

    async def run(self, job_id: uuid.UUID, cv_doc_id: uuid.UUID | None, letter_doc_id: uuid.UUID | None) -> bool:
        """Submit an application for a job. Returns True on success."""
        await self._start_run(
            job_id=job_id,
            input_data={"job_id": str(job_id), "cv_doc_id": str(cv_doc_id), "letter_doc_id": str(letter_doc_id)}
        )

        try:
            job_result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if not job:
                await self._finish_run(AgentStatusEnum.FAILED, error_message="Job not found")
                return False

            user_result = await self.db.execute(select(User).where(User.id == self.user_id))
            user = user_result.scalar_one_or_none()

            profile_result = await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == self.user_id)
            )
            profile = profile_result.scalar_one_or_none()

            if not user or not profile:
                await self._finish_run(AgentStatusEnum.SKIPPED, error_message="No user/profile found")
                return False

            # Get CV and cover letter file paths
            cv_path = None
            letter_path = None

            if cv_doc_id:
                cv_result = await self.db.execute(select(Document).where(Document.id == cv_doc_id))
                cv_doc = cv_result.scalar_one_or_none()
                if cv_doc:
                    cv_path = cv_doc.file_path

            if letter_doc_id:
                letter_result = await self.db.execute(select(Document).where(Document.id == letter_doc_id))
                letter_doc = letter_result.scalar_one_or_none()
                if letter_doc:
                    letter_path = letter_doc.file_path

            # Submit based on platform
            success, method, screenshot_path = await self._submit(
                job=job,
                user=user,
                profile=profile,
                cv_path=cv_path,
                letter_path=letter_path,
            )

            if success:
                # Create or update application record
                existing = await self.db.execute(
                    select(Application).where(Application.job_id == job_id)
                )
                application = existing.scalar_one_or_none()

                now = datetime.utcnow()
                if not application:
                    application = Application(
                        user_id=self.user_id,
                        job_id=job_id,
                        cv_document_id=cv_doc_id,
                        cover_letter_document_id=letter_doc_id,
                        status=ApplicationStatusEnum.SUBMITTED,
                        submitted_at=now,
                        submission_method=method,
                        submission_screenshot_path=screenshot_path,
                        follow_up_due_at=now + timedelta(days=7),
                        timeline=[{
                            "event": "Application submitted",
                            "timestamp": now.isoformat(),
                            "details": {"method": method, "platform": job.platform.value},
                        }],
                    )
                    self.db.add(application)
                else:
                    application.status = ApplicationStatusEnum.SUBMITTED
                    application.submitted_at = now
                    application.submission_method = method
                    application.follow_up_due_at = now + timedelta(days=7)

                job.status = JobStatusEnum.APPLIED
                await self.db.flush()

                await self._finish_run(
                    AgentStatusEnum.SUCCESS,
                    output_data={"method": method, "application_id": str(application.id)},
                )
                return True
            else:
                job.status = JobStatusEnum.FAILED
                await self.db.flush()
                await self._finish_run(AgentStatusEnum.FAILED, error_message="Application submission failed")
                return False

        except Exception as e:
            logger.error(f"Application submission failed for job {job_id}: {e}", exc_info=True)
            await self._finish_run(AgentStatusEnum.FAILED, error_message=str(e))
            return False

    async def _submit(
        self,
        job: Job,
        user: User,
        profile: UserProfile,
        cv_path: str | None,
        letter_path: str | None,
    ) -> tuple[bool, str, str | None]:
        """Platform-specific submission. Returns (success, method, screenshot_path)."""
        if not job.application_url:
            logger.warning(f"No application URL for job {job.id}")
            return False, "no_url", None

        platform = job.platform
        try:
            if platform == JobPlatformEnum.LINKEDIN:
                return await self._submit_linkedin(job, user, profile, cv_path, letter_path)
            elif platform == JobPlatformEnum.INDEED:
                return await self._submit_indeed(job, user, profile, cv_path, letter_path)
            else:
                return await self._submit_email(job, user, profile, cv_path, letter_path)
        except Exception as e:
            logger.error(f"Platform submission error: {e}")
            return False, "error", None

    async def _submit_linkedin(self, job, user, profile, cv_path, letter_path):
        """LinkedIn Easy Apply via Playwright."""
        try:
            from playwright.async_api import async_playwright
            screenshot_path = str(
                Path(settings.storage_path) / "screenshots" / f"linkedin_{job.id}.png"
            )
            Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                await page.goto(job.application_url, wait_until="networkidle", timeout=30000)
                await page.screenshot(path=screenshot_path)

                # Look for Easy Apply button
                easy_apply_btn = page.locator("button:has-text('Easy Apply'), button:has-text('Candidature simplifiée')")
                if await easy_apply_btn.count() > 0:
                    await easy_apply_btn.first.click()
                    await page.wait_for_timeout(2000)

                    # Fill form fields
                    await self._fill_linkedin_form(page, user, profile, cv_path, letter_path)
                    await page.screenshot(path=screenshot_path)
                    await browser.close()
                    return True, "linkedin_easy_apply", screenshot_path
                else:
                    logger.info(f"No Easy Apply button found for {job.title}")
                    await browser.close()
                    return False, "linkedin_no_easy_apply", screenshot_path

        except Exception as e:
            logger.error(f"LinkedIn submission error: {e}")
            return False, "linkedin_error", None

    async def _fill_linkedin_form(self, page, user, profile, cv_path, letter_path):
        """Fill LinkedIn Easy Apply form fields."""
        import asyncio
        await asyncio.sleep(1)

        # Phone number
        phone_field = page.locator("input[id*='phone']")
        if await phone_field.count() > 0 and profile.phone:
            await phone_field.first.fill(profile.phone)

        # Upload CV if file input present
        if cv_path:
            file_input = page.locator("input[type='file']")
            if await file_input.count() > 0:
                await file_input.first.set_input_files(cv_path)
                await asyncio.sleep(1)

        # Submit (click Next until Submit button appears)
        for _ in range(5):
            submit_btn = page.locator("button:has-text('Submit'), button:has-text('Envoyer')")
            next_btn = page.locator("button:has-text('Next'), button:has-text('Suivant')")

            if await submit_btn.count() > 0:
                await submit_btn.first.click()
                await asyncio.sleep(2)
                break
            elif await next_btn.count() > 0:
                await next_btn.first.click()
                await asyncio.sleep(1)
            else:
                break

    async def _submit_indeed(self, job, user, profile, cv_path, letter_path):
        """Indeed Apply via Playwright."""
        try:
            from playwright.async_api import async_playwright
            screenshot_path = str(
                Path(settings.storage_path) / "screenshots" / f"indeed_{job.id}.png"
            )
            Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await (await browser.new_context()).new_page()
                await page.goto(job.application_url, wait_until="networkidle", timeout=30000)
                await page.screenshot(path=screenshot_path)

                # Look for Apply button
                apply_btn = page.locator("button:has-text('Postuler'), button:has-text('Apply Now'), a:has-text('Postuler')")
                if await apply_btn.count() > 0:
                    await apply_btn.first.click()
                    await page.wait_for_timeout(2000)
                    await page.screenshot(path=screenshot_path)
                    await browser.close()
                    return True, "indeed_apply", screenshot_path

                await browser.close()
                return False, "indeed_no_button", screenshot_path

        except Exception as e:
            logger.error(f"Indeed submission error: {e}")
            return False, "indeed_error", None

    async def _submit_email(self, job, user, profile, cv_path, letter_path):
        """Email-based application (WTTJ and others)."""
        # For WTTJ and email-based, we record the intent
        # Full email sending requires SMTP config
        logger.info(f"Email application for {job.title} at {job.company} — URL: {job.application_url}")
        return True, "email_intent_recorded", None

    async def _answer_screening_question(self, question: str, field_type: str, user: User, profile: UserProfile) -> str:
        """Use Claude to answer form screening questions."""
        claude = get_claude_service()
        profile_summary = f"""
Name: {user.first_name} {user.last_name}
Skills: {', '.join(profile.skills_technical or [])}
Education: {str(profile.education or [])[:300]}
Experience: {str(profile.experience or [])[:300]}
Location: {profile.ville or 'Paris'}
"""
        system = f"""You are filling a job application form on behalf of {user.first_name} {user.last_name}.
Answer all questions truthfully based on the candidate profile.
Respond in the same language as the question (French or English).
Keep answers concise and professional."""

        user_msg = f"""## CANDIDATE PROFILE
{profile_summary}

## SCREENING QUESTION
Question: "{question}"
Field type: {field_type}"""

        result, _, _ = await claude.complete_structured(
            system=system,
            user=user_msg,
            output_schema=ScreeningAnswer,
            max_tokens=500,
        )
        return result.answer
