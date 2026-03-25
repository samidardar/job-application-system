"""
ScraplingJobScraper — anti-detection job scraping using Scrapling.

Tier 1: StealthyFetcher (HTTP with Cloudflare bypass headers)
Tier 2: PlayWrightFetcher (real Chromium for heavy JS-gated pages)

Why Scrapling over jobspy:
- Fingerprint-based anti-bot evasion (JA3/TLS spoofing)
- Playwright fallback for JS-heavy pages (LinkedIn, modern Indeed)
- No dependency on brittle CSS selectors tied to a specific DOM version
- Auto-selects fastest working strategy per domain
"""
import asyncio
import hashlib
import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)

# LinkedIn search URL template
_LINKEDIN_SEARCH = (
    "https://www.linkedin.com/jobs/search/?keywords={query}&location={location}"
    "&f_TPR=r604800&sortBy=DD"
)
# Indeed search URL template (French locale)
_INDEED_SEARCH = (
    "https://fr.indeed.com/jobs?q={query}&l={location}&fromage=7&sort=date"
)


def _hash_url(url: str) -> str:
    """Stable external_id derived from a job URL (no UUID — survives re-scrapes)."""
    return hashlib.sha256(url.encode()).hexdigest()[:24]


async def _stealthy_fetch(url: str) -> "Adaptor | None":  # type: ignore[name-defined]
    """Tier-1 fetch: fast HTTP with anti-bot headers. Returns Scrapling Adaptor or None."""
    try:
        from scrapling.fetchers import StealthyFetcher  # type: ignore[import]

        loop = asyncio.get_running_loop()
        page = await loop.run_in_executor(
            None,
            lambda: StealthyFetcher.fetch(
                url,
                headless=True,
                network_idle=True,
                block_images=True,
                disable_resources=True,
                timeout=30,
            ),
        )
        if page and page.status == 200:
            return page
        return None
    except Exception as e:
        logger.debug(f"[scrapling] StealthyFetcher failed for {url}: {e}")
        return None


async def _playwright_fetch(url: str) -> "Adaptor | None":  # type: ignore[name-defined]
    """Tier-2 fetch: real Chromium browser. Slower but bypasses heavy JS gates."""
    try:
        from scrapling.fetchers import PlayWrightFetcher  # type: ignore[import]

        loop = asyncio.get_running_loop()
        page = await loop.run_in_executor(
            None,
            lambda: PlayWrightFetcher.fetch(
                url,
                headless=True,
                network_idle=True,
                block_images=True,
                timeout=45,
            ),
        )
        if page and page.status == 200:
            return page
        return None
    except Exception as e:
        logger.debug(f"[scrapling] PlayWrightFetcher failed for {url}: {e}")
        return None


async def _fetch_with_fallback(url: str) -> "Adaptor | None":  # type: ignore[name-defined]
    """Try StealthyFetcher first; fall back to PlayWrightFetcher if blocked."""
    page = await _stealthy_fetch(url)
    if page is None:
        logger.debug(f"[scrapling] Falling back to Playwright for {url}")
        page = await _playwright_fetch(url)
    return page


def _text(el) -> str:
    """Safe text extraction from a Scrapling element (or None)."""
    if el is None:
        return ""
    try:
        return el.text.strip()
    except Exception:
        return ""


def _attr(el, attr: str) -> str:
    """Safe attribute extraction from a Scrapling element (or None)."""
    if el is None:
        return ""
    try:
        return el.attrib.get(attr, "") or ""
    except Exception:
        return ""


# ─── LinkedIn ─────────────────────────────────────────────────────────────────

def _parse_linkedin_page(page) -> list[dict]:
    """Extract job listings from a LinkedIn search results page."""
    jobs: list[dict] = []
    try:
        cards = page.css("ul.jobs-search__results-list li")
        if not cards:
            # Authenticated layout
            cards = page.css("li.scaffold-layout__list-item")

        for card in cards:
            title_el = card.css_first("h3.base-search-card__title") or card.css_first("a.job-card-container__link")
            company_el = card.css_first("h4.base-search-card__subtitle") or card.css_first("span.job-card-container__company-name")
            location_el = card.css_first("span.job-search-card__location") or card.css_first("li.job-card-container__metadata-item")
            link_el = card.css_first("a.base-card__full-link") or card.css_first("a.job-card-container__link")

            title = _text(title_el)
            company = _text(company_el)
            location = _text(location_el)
            url = _attr(link_el, "href").split("?")[0]

            if not title or not url:
                continue

            jobs.append({
                "external_id": _hash_url(url),
                "platform": "linkedin",
                "title": title,
                "company": company,
                "location": location,
                "application_url": url,
                "description_raw": "",
                "posted_at": None,
                "salary_range": None,
                "remote_type": None,
                "job_type": None,
            })
    except Exception as e:
        logger.warning(f"[scrapling] LinkedIn parse error: {e}")
    return jobs


async def _enrich_linkedin_description(job: dict) -> dict:
    """Fetch individual job page to get full description (best-effort)."""
    url = job.get("application_url", "")
    if not url:
        return job
    try:
        page = await _fetch_with_fallback(url)
        if page:
            desc_el = (
                page.css_first("div.description__text")
                or page.css_first("div.show-more-less-html__markup")
                or page.css_first("article.jobs-description")
            )
            if desc_el:
                job["description_raw"] = desc_el.text[:10000].strip()
    except Exception as e:
        logger.debug(f"[scrapling] LinkedIn description fetch failed for {url}: {e}")
    return job


# ─── Indeed ───────────────────────────────────────────────────────────────────

def _parse_indeed_page(page) -> list[dict]:
    """Extract job listings from an Indeed search results page."""
    jobs: list[dict] = []
    try:
        cards = page.css("div.job_seen_beacon") or page.css("li.css-1ac2h1w")
        for card in cards:
            title_el = card.css_first("h2.jobTitle span[id]") or card.css_first("h2.jobTitle a")
            company_el = card.css_first("span.companyName") or card.css_first("[data-testid='company-name']")
            location_el = card.css_first("div.companyLocation") or card.css_first("[data-testid='text-location']")
            link_el = card.css_first("a[id^='job_']") or card.css_first("a.jcs-JobTitle")

            title = _text(title_el)
            company = _text(company_el)
            location = _text(location_el)

            href = _attr(link_el, "href")
            if href and not href.startswith("http"):
                href = "https://fr.indeed.com" + href
            url = href.split("&")[0] if href else ""

            if not title:
                continue

            # Extract job key from URL for stable external_id
            key_match = re.search(r"jk=([a-f0-9]+)", href)
            external_id = key_match.group(1) if key_match else _hash_url(url or title + company)

            jobs.append({
                "external_id": external_id,
                "platform": "indeed",
                "title": title,
                "company": company,
                "location": location,
                "application_url": url,
                "description_raw": "",
                "posted_at": None,
                "salary_range": None,
                "remote_type": None,
                "job_type": None,
            })
    except Exception as e:
        logger.warning(f"[scrapling] Indeed parse error: {e}")
    return jobs


# ─── Single-URL enrichment (used by Dr. Rousseau tool) ───────────────────────

async def scrape_job_page(url: str) -> dict:
    """
    Fetch a single job posting URL and return structured data.
    Used by Dr. Rousseau's scrape_job_url tool to analyse arbitrary job URLs.

    Returns:
        {
          "title": str,
          "company": str,
          "location": str,
          "description": str,
          "application_url": str,
          "error": str | None,
        }
    """
    try:
        page = await _fetch_with_fallback(url)
        if not page:
            return {"error": f"Impossible de charger la page: {url}", "title": "", "company": "", "location": "", "description": "", "application_url": url}

        # Generic extractors — work across most job boards
        title = (
            _text(page.css_first("h1"))
            or _text(page.css_first('[class*="job-title"]'))
            or _text(page.css_first('[class*="jobtitle"]'))
            or "Titre non trouvé"
        )
        company = (
            _text(page.css_first('[class*="company"]'))
            or _text(page.css_first('[class*="employer"]'))
            or ""
        )
        location = (
            _text(page.css_first('[class*="location"]'))
            or _text(page.css_first('[class*="city"]'))
            or ""
        )
        # Try multiple common description containers
        desc_el = (
            page.css_first("div.description")
            or page.css_first('[class*="job-description"]')
            or page.css_first('[class*="jobDescription"]')
            or page.css_first("article")
            or page.css_first("main")
        )
        description = _text(desc_el)[:8000] if desc_el else ""

        return {
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "application_url": url,
            "error": None,
        }
    except Exception as e:
        logger.error(f"[scrapling] scrape_job_page failed for {url}: {e}")
        return {
            "error": str(e),
            "title": "",
            "company": "",
            "location": "",
            "description": "",
            "application_url": url,
        }


# ─── Multi-platform job search ────────────────────────────────────────────────

class ScraplingJobScraper:
    """
    Async job scraper using Scrapling for anti-detection.

    Usage:
        scraper = ScraplingJobScraper()
        jobs = await scraper.search_jobs(roles, locations, contract_types)
    """

    async def search_jobs(
        self,
        roles: list[str],
        locations: list[str],
        contract_types: list[str],
        max_per_query: int = 25,
    ) -> list[dict]:
        """
        Run LinkedIn + Indeed scrapers in parallel for all (role × location) combos.
        Returns deduplicated list of job dicts.
        """
        tasks: list[asyncio.Task] = []
        for role in roles[:3]:  # Cap at 3 roles to stay under rate limits
            for location in locations[:2]:
                tasks.append(asyncio.create_task(
                    self._scrape_linkedin(role, location, contract_types, max_per_query)
                ))
                tasks.append(asyncio.create_task(
                    self._scrape_indeed(role, location, contract_types, max_per_query)
                ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined: list[dict] = []
        seen_ids: set[str] = set()
        for result in results:
            if isinstance(result, list):
                for job in result:
                    eid = job.get("external_id", "")
                    if eid and eid not in seen_ids:
                        seen_ids.add(eid)
                        combined.append(job)
            elif isinstance(result, Exception):
                logger.warning(f"[scrapling] Scraper task failed: {result}")

        logger.info(f"[scrapling] Total unique jobs scraped: {len(combined)}")
        return combined

    async def _scrape_linkedin(
        self,
        role: str,
        location: str,
        contract_types: list[str],
        max_per_query: int,
    ) -> list[dict]:
        import urllib.parse

        query = f"{role} {contract_types[0]}" if contract_types else role
        url = _LINKEDIN_SEARCH.format(
            query=urllib.parse.quote_plus(query),
            location=urllib.parse.quote_plus(location),
        )
        logger.info(f"[scrapling:linkedin] Searching: {query!r} @ {location}")

        try:
            page = await _fetch_with_fallback(url)
            if not page:
                logger.warning(f"[scrapling:linkedin] No page for {url}")
                return []

            jobs = _parse_linkedin_page(page)[:max_per_query]

            # Enrich top 10 with full descriptions (rate-limit-friendly)
            enrich_tasks = [_enrich_linkedin_description(j) for j in jobs[:10]]
            enriched = await asyncio.gather(*enrich_tasks, return_exceptions=True)
            for i, result in enumerate(enriched):
                if isinstance(result, dict):
                    jobs[i] = result

            logger.info(f"[scrapling:linkedin] {len(jobs)} jobs for {query!r} @ {location}")
            return jobs
        except Exception as e:
            logger.error(f"[scrapling:linkedin] Failed for {query!r}: {e}")
            return []

    async def _scrape_indeed(
        self,
        role: str,
        location: str,
        contract_types: list[str],
        max_per_query: int,
    ) -> list[dict]:
        import urllib.parse

        query = f"{role} {contract_types[0]}" if contract_types else role
        url = _INDEED_SEARCH.format(
            query=urllib.parse.quote_plus(query),
            location=urllib.parse.quote_plus(location),
        )
        logger.info(f"[scrapling:indeed] Searching: {query!r} @ {location}")

        try:
            page = await _fetch_with_fallback(url)
            if not page:
                logger.warning(f"[scrapling:indeed] No page for {url}")
                return []

            jobs = _parse_indeed_page(page)[:max_per_query]
            logger.info(f"[scrapling:indeed] {len(jobs)} jobs for {query!r} @ {location}")
            return jobs
        except Exception as e:
            logger.error(f"[scrapling:indeed] Failed for {query!r}: {e}")
            return []


# ── Module-level singleton ────────────────────────────────────────────────────
_scraper: ScraplingJobScraper | None = None


def get_scrapling_scraper() -> ScraplingJobScraper:
    """Lazy singleton — instantiated once per process."""
    global _scraper
    if _scraper is None:
        _scraper = ScraplingJobScraper()
    return _scraper
