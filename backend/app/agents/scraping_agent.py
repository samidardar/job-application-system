import logging
import uuid
from sqlalchemy import select
from app.agents.base_agent import BaseAgent
from app.models.job import Job, JobPlatformEnum, JobTypeEnum, JobStatusEnum
from app.models.agent_run import AgentStatusEnum
from app.services.playwright_scraper import get_scraper, ScrapedJob

logger = logging.getLogger(__name__)

PLATFORM_MAP = {
    "linkedin": JobPlatformEnum.LINKEDIN,
    "indeed": JobPlatformEnum.INDEED,
    "welcometothejungle": JobPlatformEnum.WTTJ,
}

CONTRACT_MAP = {
    "alternance": JobTypeEnum.ALTERNANCE,
    "stage": JobTypeEnum.STAGE,
    "cdi": JobTypeEnum.CDI,
    "cdd": JobTypeEnum.CDD,
    "freelance": JobTypeEnum.FREELANCE,
}


class ScrapingAgent(BaseAgent):
    name = "scraping"

    async def run(self, job_title: str, location: str) -> list[uuid.UUID]:
        """Scrape jobs for given title and location. Returns list of new job IDs."""
        await self._start_run(input_data={"job_title": job_title, "location": location})

        try:
            scraper = await get_scraper()
            scraped_jobs = await scraper.scrape_all(
                job_title=job_title,
                location=location,
                max_per_platform=25,
            )

            new_job_ids: list[uuid.UUID] = []
            for scraped in scraped_jobs:
                job_id = await self._save_job(scraped)
                if job_id:
                    new_job_ids.append(job_id)

            await self._finish_run(
                AgentStatusEnum.SUCCESS,
                output_data={
                    "jobs_found": len(new_job_ids),
                    "job_ids": [str(i) for i in new_job_ids],
                },
            )
            return new_job_ids

        except Exception as e:
            logger.error(f"Scraping failed: {e}", exc_info=True)
            await self._finish_run(AgentStatusEnum.FAILED, error_message=str(e))
            return []

    async def _save_job(self, scraped: ScrapedJob) -> uuid.UUID | None:
        platform = PLATFORM_MAP.get(scraped.platform, JobPlatformEnum.LINKEDIN)

        # Check duplicate
        existing = await self.db.execute(
            select(Job).where(
                Job.user_id == self.user_id,
                Job.external_id == scraped.external_id,
                Job.platform == platform,
            )
        )
        if existing.scalar_one_or_none():
            return None

        job_type = CONTRACT_MAP.get(scraped.job_type or "", None)

        job = Job(
            user_id=self.user_id,
            external_id=scraped.external_id,
            platform=platform,
            title=scraped.title,
            company=scraped.company,
            location=scraped.location,
            remote_type=scraped.remote,
            job_type=job_type,
            salary_range=scraped.salary,
            description_raw=scraped.description,
            description_clean=_clean_description(scraped.description),
            application_url=scraped.application_url,
            posted_at=scraped.posted_at,
            status=JobStatusEnum.SCRAPED,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        logger.info(f"Saved: {job.title} @ {job.company} [{scraped.platform}]")
        return job.id


def _clean_description(raw: str) -> str:
    if not raw:
        return ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return "\n".join(lines)[:5000]
