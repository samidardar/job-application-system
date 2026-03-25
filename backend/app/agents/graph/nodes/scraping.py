"""
Scraping node — fetches jobs from all sources in parallel:
  1. Scrapling (LinkedIn + Indeed) — anti-detection stealthy scraping
  2. France Travail API
  3. La Bonne Alternance API
Deduplicates and saves to DB.
"""
import asyncio
import logging
import uuid
from datetime import datetime

from sqlalchemy import select

from app.agents.graph.state import PipelineState
from app.database import AsyncSessionLocal
from app.models.job import Job, JobPlatformEnum, JobTypeEnum, JobStatusEnum
from app.services.france_travail_api import get_france_travail_api
from app.services.bonne_alternance_api import get_bonne_alternance_api
from app.services.scrapling_scraper import get_scrapling_scraper

logger = logging.getLogger(__name__)

PLATFORM_MAP: dict[str, JobPlatformEnum] = {
    "linkedin": JobPlatformEnum.LINKEDIN,
    "indeed": JobPlatformEnum.INDEED,
    "glassdoor": JobPlatformEnum.INDEED,
    "welcometothejungle": JobPlatformEnum.WTTJ,
    "francetravail": JobPlatformEnum.FRANCE_TRAVAIL,
    "bonne_alternance": JobPlatformEnum.BONNE_ALTERNANCE,
}

CONTRACT_MAP: dict[str, JobTypeEnum] = {
    "alternance": JobTypeEnum.ALTERNANCE,
    "stage": JobTypeEnum.STAGE,
    "cdi": JobTypeEnum.CDI,
    "cdd": JobTypeEnum.CDD,
    "freelance": JobTypeEnum.FREELANCE,
    "internship": JobTypeEnum.STAGE,
    "full-time": JobTypeEnum.CDI,
    "apprentissage": JobTypeEnum.ALTERNANCE,
    "professionnalisation": JobTypeEnum.ALTERNANCE,
}


async def _scrape_scrapling(
    roles: list[str],
    locations: list[str],
    contract_types: list[str],
) -> list[dict]:
    """Scrape LinkedIn + Indeed via Scrapling (anti-detection, stealthy)."""
    try:
        scraper = get_scrapling_scraper()
        jobs = await scraper.search_jobs(roles, locations, contract_types)
        # Normalise job_type field using contract detection
        for job in jobs:
            if not job.get("job_type"):
                job["job_type"] = _detect_contract(
                    job.get("title", ""),
                    job.get("description_raw", "")[:500],
                    contract_types,
                )
        return jobs
    except Exception as e:
        logger.error(f"[scrapling] scraper failed: {e}", exc_info=True)
        return []


def _detect_contract(title: str, description: str, preferred: list[str]) -> str | None:
    text = (title + " " + description).lower()
    for c in preferred:
        if c.lower() in text:
            return c.lower()
    if "alternance" in text or "apprentissage" in text or "professionnalisation" in text:
        return "alternance"
    if "stage" in text or "internship" in text:
        return "stage"
    if "cdi" in text or "full-time" in text:
        return "cdi"
    if "cdd" in text:
        return "cdd"
    return None


async def _save_jobs_to_db(
    raw_jobs: list[dict],
    user_id: uuid.UUID,
) -> list[dict]:
    """Dedup against DB and save new jobs. Returns saved job dicts with DB id."""
    saved: list[dict] = []
    async with AsyncSessionLocal() as db:
        for raw in raw_jobs:
            ext_id = raw.get("external_id", "")
            platform_str = raw.get("platform", "linkedin")
            if not ext_id:
                continue
            platform = PLATFORM_MAP.get(platform_str, JobPlatformEnum.LINKEDIN)

            # Dedup check
            existing = await db.execute(
                select(Job).where(
                    Job.user_id == user_id,
                    Job.external_id == ext_id,
                    Job.platform == platform,
                )
            )
            if existing.scalar_one_or_none():
                continue

            job_type_str = raw.get("job_type")
            job_type = CONTRACT_MAP.get(job_type_str or "", None) if job_type_str else None

            posted_at = None
            if raw.get("posted_at"):
                try:
                    posted_at = datetime.fromisoformat(str(raw["posted_at"]).replace("Z", "+00:00"))
                    posted_at = posted_at.replace(tzinfo=None)
                except Exception:
                    pass

            job = Job(
                user_id=user_id,
                external_id=ext_id,
                platform=platform,
                title=raw.get("title", ""),
                company=raw.get("company", ""),
                company_size=raw.get("company_size"),
                location=raw.get("location", ""),
                remote_type=raw.get("remote_type"),
                job_type=job_type,
                salary_range=raw.get("salary_range"),
                description_raw=raw.get("description_raw", "")[:10000],
                application_url=raw.get("application_url", ""),
                posted_at=posted_at,
                status=JobStatusEnum.SCRAPED,
            )
            db.add(job)
            try:
                await db.flush()
                await db.refresh(job)
                raw_copy = dict(raw)
                raw_copy["id"] = str(job.id)
                saved.append(raw_copy)
            except Exception as e:
                logger.warning(f"Failed to save job {ext_id}: {e}")
                await db.rollback()
                continue
        await db.commit()
    return saved


async def node_scrape(state: PipelineState) -> dict:
    """Fetch jobs from LinkedIn/Indeed (Scrapling) + France Travail + La Bonne Alternance."""
    prefs = state.get("user_preferences", {})
    user_id = uuid.UUID(state["user_id"])

    roles: list[str] = prefs.get("target_roles") or ["Développeur Python", "Data Engineer"]
    contract_types: list[str] = prefs.get("contract_types") or ["alternance"]
    locations: list[str] = prefs.get("preferred_locations") or ["Paris, France"]

    logger.info(f"[scrape] roles={roles} contracts={contract_types} locations={locations}")

    # Determine if alternance/stage is included → use specialised sources
    wants_alternance = any(c in ("alternance", "stage") for c in [ct.lower() for ct in contract_types])

    # Run all scrapers in parallel
    tasks = [_scrape_scrapling(roles, locations, contract_types)]
    ft_api = get_france_travail_api()
    tasks.append(ft_api.search_all(roles, locations, contract_types, hours_back=168))  # 7 days

    if wants_alternance:
        lba_api = get_bonne_alternance_api()
        tasks.append(lba_api.search_jobs(roles, locations))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    combined: list[dict] = []
    source_names = ["scrapling", "france_travail", "bonne_alternance"]
    for name, result in zip(source_names, results):
        if isinstance(result, list):
            logger.info(f"[scrape] {name}: {len(result)} offres")
            combined.extend(result)
        elif isinstance(result, Exception):
            logger.error(f"[scrape] {name} error: {result}")

    # Save to DB and dedup
    saved = await _save_jobs_to_db(combined, user_id)
    logger.info(f"[scrape] {len(saved)} nouvelles offres sauvegardées (sur {len(combined)} scrappées)")

    return {
        "scraped_jobs": saved,
        "jobs_scraped": len(saved),
        "errors": [],
    }
