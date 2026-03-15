import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jobspy import scrape_jobs
import pandas as pd
from app.agents.base_agent import BaseAgent
from app.models.job import Job, JobPlatformEnum, JobTypeEnum, JobStatusEnum
from app.models.agent_run import AgentStatusEnum
from app.models.user import UserPreferences, UserProfile

logger = logging.getLogger(__name__)

PLATFORM_MAP = {
    "linkedin": JobPlatformEnum.LINKEDIN,
    "indeed": JobPlatformEnum.INDEED,
    "glassdoor": JobPlatformEnum.INDEED,  # fallback
}

CONTRACT_MAP = {
    "alternance": JobTypeEnum.ALTERNANCE,
    "stage": JobTypeEnum.STAGE,
    "cdi": JobTypeEnum.CDI,
    "cdd": JobTypeEnum.CDD,
    "internship": JobTypeEnum.STAGE,
    "full-time": JobTypeEnum.CDI,
}


class ScrapingAgent(BaseAgent):
    name = "scraping"

    async def run(self) -> list[uuid.UUID]:
        """Scrape jobs from the last 24h and return list of new job IDs."""
        await self._start_run(input_data={"hours_back": 24})

        try:
            # Get user preferences
            prefs_result = await self.db.execute(
                select(UserPreferences).where(UserPreferences.user_id == self.user_id)
            )
            prefs = prefs_result.scalar_one_or_none()
            profile_result = await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == self.user_id)
            )
            profile = profile_result.scalar_one_or_none()

            if not prefs:
                await self._finish_run(AgentStatusEnum.FAILED, error_message="No preferences found")
                return []

            # Build search queries from preferences
            target_roles = prefs.target_roles or ["Data Scientist", "ML Engineer", "IA"]
            contract_types = prefs.contract_types or ["Alternance"]
            locations = prefs.preferred_locations or ["Paris, France"]

            all_new_job_ids: list[uuid.UUID] = []

            for role in target_roles[:3]:  # Limit to 3 roles per run
                for location in locations[:2]:  # Limit to 2 locations
                    search_term = f"{role} {' '.join(contract_types[:1])}"
                    new_ids = await self._scrape_and_save(
                        search_term=search_term,
                        location=location,
                        contract_types=contract_types,
                    )
                    all_new_job_ids.extend(new_ids)

            unique_ids = list(set(all_new_job_ids))
            await self._finish_run(
                AgentStatusEnum.SUCCESS,
                output_data={"jobs_found": len(unique_ids), "job_ids": [str(i) for i in unique_ids]},
            )
            return unique_ids

        except Exception as e:
            logger.error(f"Scraping failed: {e}", exc_info=True)
            await self._finish_run(AgentStatusEnum.FAILED, error_message=str(e))
            return []

    async def _scrape_and_save(
        self,
        search_term: str,
        location: str,
        contract_types: list[str],
    ) -> list[uuid.UUID]:
        """Scrape jobs for a given search term and location."""
        try:
            # jobspy scrapes LinkedIn, Indeed, Glassdoor simultaneously
            jobs_df = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=search_term,
                location=location,
                results_wanted=25,
                hours_old=24,
                country_indeed="France",
                linkedin_fetch_description=True,
            )

            if jobs_df is None or jobs_df.empty:
                logger.info(f"No jobs found for '{search_term}' in {location}")
                return []

            new_job_ids = []

            for _, row in jobs_df.iterrows():
                try:
                    job_id = await self._save_job(row, contract_types)
                    if job_id:
                        new_job_ids.append(job_id)
                except Exception as e:
                    logger.warning(f"Failed to save job {row.get('id')}: {e}")

            logger.info(f"Saved {len(new_job_ids)} new jobs for '{search_term}'")
            return new_job_ids

        except Exception as e:
            logger.error(f"jobspy scraping failed for '{search_term}': {e}")
            return []

    async def _save_job(self, row: pd.Series, contract_types: list[str]) -> uuid.UUID | None:
        """Save a job row to DB if not already exists."""
        external_id = str(row.get("id", ""))
        platform_str = str(row.get("site", "linkedin")).lower()
        platform = PLATFORM_MAP.get(platform_str, JobPlatformEnum.LINKEDIN)

        if not external_id:
            return None

        # Check for duplicate
        existing = await self.db.execute(
            select(Job).where(
                Job.user_id == self.user_id,
                Job.external_id == external_id,
                Job.platform == platform,
            )
        )
        if existing.scalar_one_or_none():
            return None

        # Detect job type from title/description
        title = str(row.get("title", ""))
        description = str(row.get("description", ""))
        job_type = self._detect_job_type(title, description, contract_types)

        # Skip if exclude_keywords present in title
        posted_at = None
        if row.get("date_posted"):
            try:
                posted_at = pd.to_datetime(row["date_posted"]).to_pydatetime()
            except Exception:
                pass

        job = Job(
            user_id=self.user_id,
            external_id=external_id,
            platform=platform,
            title=title,
            company=str(row.get("company", "")),
            company_size=str(row.get("company_num_employees", "")) or None,
            location=str(row.get("location", "")),
            remote_type=str(row.get("is_remote", "")) or None,
            job_type=job_type,
            salary_range=self._format_salary(row),
            description_raw=description[:10000],
            application_url=str(row.get("job_url", "")),
            posted_at=posted_at,
            status=JobStatusEnum.SCRAPED,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job.id

    def _detect_job_type(self, title: str, description: str, preferred: list[str]) -> JobTypeEnum | None:
        text = (title + " " + description[:500]).lower()
        for contract in preferred:
            c = contract.lower()
            if c in text:
                return CONTRACT_MAP.get(c, JobTypeEnum.ALTERNANCE)
        if "alternance" in text or "apprentissage" in text:
            return JobTypeEnum.ALTERNANCE
        if "stage" in text or "internship" in text:
            return JobTypeEnum.STAGE
        if "cdi" in text or "full-time" in text:
            return JobTypeEnum.CDI
        return None

    def _format_salary(self, row: pd.Series) -> str | None:
        min_s = row.get("min_amount")
        max_s = row.get("max_amount")
        currency = row.get("currency", "EUR")
        interval = row.get("interval", "")
        if min_s and max_s:
            return f"{int(min_s)}-{int(max_s)} {currency}/{interval}"
        if min_s:
            return f"{int(min_s)}+ {currency}/{interval}"
        return None
