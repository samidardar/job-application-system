"""
SOTA Playwright-based scraper for LinkedIn, Indeed France, and Welcome to the Jungle.
Uses stealth configuration to avoid bot detection.
"""
import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncGenerator

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

# Stealth JS — overrides navigator.webdriver and related fingerprints
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR', 'fr', 'en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'permissions', {
  get: () => ({ query: () => Promise.resolve({ state: 'granted' }) }),
});
"""

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


@dataclass
class ScrapedJob:
    external_id: str
    platform: str
    title: str
    company: str
    location: str = ""
    job_type: str | None = None
    description: str = ""
    application_url: str = ""
    posted_at: datetime | None = None
    salary: str | None = None
    remote: str | None = None


async def _delay(min_ms: int = 800, max_ms: int = 2200) -> None:
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def _create_context(browser: Browser) -> BrowserContext:
    ua = random.choice(USER_AGENTS)
    context = await browser.new_context(
        user_agent=ua,
        viewport={"width": random.randint(1280, 1920), "height": random.randint(800, 1080)},
        locale="fr-FR",
        timezone_id="Europe/Paris",
        extra_http_headers={
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
    )
    await context.add_init_script(STEALTH_INIT_SCRIPT)
    return context


class PlaywrightScraper:
    """Scrapes LinkedIn, Indeed, and WTTJ using Playwright."""

    def __init__(self):
        self._browser: Browser | None = None
        self._playwright = None

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certifcate-errors",
                "--ignore-certifcate-errors-spki-list",
            ],
        )
        logger.info("Playwright browser started")

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Playwright browser stopped")

    async def scrape_all(
        self,
        job_title: str,
        location: str,
        max_per_platform: int = 25,
    ) -> list[ScrapedJob]:
        """Scrape all three platforms concurrently."""
        if not self._browser:
            await self.start()

        results = await asyncio.gather(
            self._scrape_linkedin(job_title, location, max_per_platform),
            self._scrape_indeed(job_title, location, max_per_platform),
            self._scrape_wttj(job_title, location, max_per_platform),
            return_exceptions=True,
        )

        jobs: list[ScrapedJob] = []
        platform_names = ["LinkedIn", "Indeed", "WTTJ"]
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"{platform_names[i]} scraping failed: {result}")
            else:
                logger.info(f"{platform_names[i]}: {len(result)} jobs scraped")
                jobs.extend(result)

        # Deduplicate by title+company
        seen = set()
        unique = []
        for j in jobs:
            key = f"{j.title.lower().strip()}|{j.company.lower().strip()}"
            if key not in seen:
                seen.add(key)
                unique.append(j)

        logger.info(f"Total unique jobs after dedup: {len(unique)}")
        return unique

    # ─── LinkedIn ────────────────────────────────────────────────────────────

    async def _scrape_linkedin(
        self, job_title: str, location: str, max_results: int
    ) -> list[ScrapedJob]:
        context = await _create_context(self._browser)
        page = await context.new_page()
        jobs: list[ScrapedJob] = []

        try:
            title_enc = job_title.replace(" ", "%20")
            loc_enc = location.replace(" ", "%20")
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={title_enc}&location={loc_enc}&f_TPR=r86400&position=1&pageNum=0"
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _delay(2000, 4000)

            # Scroll to load more jobs
            for _ in range(3):
                await page.keyboard.press("End")
                await _delay(1000, 2000)

            # Extract job cards
            cards = await page.query_selector_all(".base-card")
            if not cards:
                cards = await page.query_selector_all("[data-entity-urn]")

            logger.info(f"LinkedIn: found {len(cards)} job cards")

            for card in cards[:max_results]:
                try:
                    job = await self._parse_linkedin_card(card, page)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"LinkedIn card parse error: {e}")

        except Exception as e:
            logger.error(f"LinkedIn scraping error: {e}")
        finally:
            await context.close()

        return jobs

    async def _parse_linkedin_card(self, card, page: Page) -> ScrapedJob | None:
        try:
            title_el = await card.query_selector(".base-search-card__title, h3.base-search-card__title")
            company_el = await card.query_selector(".base-search-card__subtitle, h4.base-search-card__subtitle")
            location_el = await card.query_selector(".job-search-card__location")
            link_el = await card.query_selector("a.base-card__full-link, a[href*='/jobs/view/']")
            time_el = await card.query_selector("time")

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            location = (await location_el.inner_text()).strip() if location_el else ""
            url = await link_el.get_attribute("href") if link_el else ""
            if url and "?" in url:
                url = url.split("?")[0]

            posted_str = await time_el.get_attribute("datetime") if time_el else None
            posted_at = None
            if posted_str:
                try:
                    posted_at = datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            # Extract job ID from URL
            id_match = re.search(r"/jobs/view/(\d+)", url or "")
            external_id = f"li_{id_match.group(1)}" if id_match else f"li_{hash(title + company)}"

            if not title or not company:
                return None

            # Fetch description from job page
            description = ""
            if url:
                description = await self._fetch_linkedin_description(url, page)

            # Detect job type
            job_type = _detect_contract_type(title + " " + description)

            return ScrapedJob(
                external_id=external_id,
                platform="linkedin",
                title=title,
                company=company,
                location=location,
                job_type=job_type,
                description=description[:8000],
                application_url=url or "",
                posted_at=posted_at,
            )
        except Exception as e:
            logger.debug(f"LinkedIn card parse: {e}")
            return None

    async def _fetch_linkedin_description(self, url: str, page: Page) -> str:
        """Fetch job description from LinkedIn job page."""
        try:
            ctx = await _create_context(self._browser)
            detail_page = await ctx.new_page()
            await detail_page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await _delay(1500, 2500)

            # Try to expand "see more"
            see_more = await detail_page.query_selector("button.show-more-less-html__button")
            if see_more:
                await see_more.click()
                await _delay(500, 1000)

            desc_el = await detail_page.query_selector(".description__text, .show-more-less-html__markup")
            description = ""
            if desc_el:
                description = await desc_el.inner_text()

            await ctx.close()
            return description.strip()
        except Exception:
            return ""

    # ─── Indeed France ───────────────────────────────────────────────────────

    async def _scrape_indeed(
        self, job_title: str, location: str, max_results: int
    ) -> list[ScrapedJob]:
        context = await _create_context(self._browser)
        page = await context.new_page()
        jobs: list[ScrapedJob] = []

        try:
            title_enc = job_title.replace(" ", "+")
            loc_enc = location.replace(" ", "+")
            url = f"https://fr.indeed.com/jobs?q={title_enc}&l={loc_enc}&fromage=1&sort=date"

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _delay(2000, 3500)

            # Handle cookie consent
            try:
                consent_btn = await page.query_selector("button#onetrust-accept-btn-handler")
                if consent_btn:
                    await consent_btn.click()
                    await _delay(500, 1000)
            except Exception:
                pass

            cards = await page.query_selector_all(".job_seen_beacon, .tapItem")
            logger.info(f"Indeed: found {len(cards)} job cards")

            for card in cards[:max_results]:
                try:
                    job = await self._parse_indeed_card(card)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"Indeed card parse error: {e}")

        except Exception as e:
            logger.error(f"Indeed scraping error: {e}")
        finally:
            await context.close()

        return jobs

    async def _parse_indeed_card(self, card) -> ScrapedJob | None:
        try:
            title_el = await card.query_selector("h2.jobTitle span[title], h2.jobTitle a")
            company_el = await card.query_selector("[data-testid='company-name'], .companyName")
            location_el = await card.query_selector("[data-testid='text-location'], .companyLocation")
            salary_el = await card.query_selector(".salary-snippet, [data-testid='attribute_snippet_testid']")
            link_el = await card.query_selector("h2.jobTitle a, a.jcs-JobTitle")

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            location = (await location_el.inner_text()).strip() if location_el else ""
            salary = (await salary_el.inner_text()).strip() if salary_el else None
            href = await link_el.get_attribute("href") if link_el else ""

            if not title or not company:
                return None

            job_id = await card.get_attribute("data-jk") or f"in_{hash(title + company)}"
            url = f"https://fr.indeed.com/viewjob?jk={job_id}" if not href.startswith("http") else href

            # Fetch description
            description = await self._fetch_indeed_description(url)
            job_type = _detect_contract_type(title + " " + description)

            return ScrapedJob(
                external_id=f"in_{job_id}",
                platform="indeed",
                title=title,
                company=company,
                location=location,
                job_type=job_type,
                description=description[:8000],
                application_url=url,
                salary=salary,
            )
        except Exception as e:
            logger.debug(f"Indeed parse: {e}")
            return None

    async def _fetch_indeed_description(self, url: str) -> str:
        try:
            ctx = await _create_context(self._browser)
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await _delay(1200, 2200)

            desc_el = await page.query_selector("#jobDescriptionText, .jobsearch-jobDescriptionText")
            description = ""
            if desc_el:
                description = await desc_el.inner_text()

            await ctx.close()
            return description.strip()
        except Exception:
            return ""

    # ─── Welcome to the Jungle ───────────────────────────────────────────────

    async def _scrape_wttj(
        self, job_title: str, location: str, max_results: int
    ) -> list[ScrapedJob]:
        context = await _create_context(self._browser)
        page = await context.new_page()
        jobs: list[ScrapedJob] = []

        try:
            title_enc = job_title.replace(" ", "%20")
            url = (
                f"https://www.welcometothejungle.com/fr/jobs"
                f"?query={title_enc}&refinementList%5Boffice.country_code%5D%5B0%5D=FR"
            )
            await page.goto(url, wait_until="networkidle", timeout=35000)
            await _delay(2000, 3500)

            # Scroll to trigger lazy load
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await _delay(800, 1500)

            # Job cards: WTTJ uses article elements
            cards = await page.query_selector_all("li[data-testid='search-results-list-item-wrapper']")
            if not cards:
                cards = await page.query_selector_all("article")

            logger.info(f"WTTJ: found {len(cards)} job cards")

            for card in cards[:max_results]:
                try:
                    job = await self._parse_wttj_card(card, page)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"WTTJ card parse error: {e}")

        except Exception as e:
            logger.error(f"WTTJ scraping error: {e}")
        finally:
            await context.close()

        return jobs

    async def _parse_wttj_card(self, card, page: Page) -> ScrapedJob | None:
        try:
            title_el = await card.query_selector("h2, [data-testid='job-title']")
            company_el = await card.query_selector("[data-testid='company-name'], h3")
            location_el = await card.query_selector("[data-testid='job-location'], [aria-label*='Lieu']")
            link_el = await card.query_selector("a[href*='/jobs/']")

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            location = (await location_el.inner_text()).strip() if location_el else ""
            href = await link_el.get_attribute("href") if link_el else ""

            if not title or not company:
                return None

            url = f"https://www.welcometothejungle.com{href}" if href and not href.startswith("http") else href

            # Extract ID from URL
            id_match = re.search(r"/jobs/([^?#]+)", href or "")
            external_id = f"wttj_{id_match.group(1).replace('/', '_')}" if id_match else f"wttj_{hash(title + company)}"

            description = await self._fetch_wttj_description(url) if url else ""
            job_type = _detect_contract_type(title + " " + description)

            return ScrapedJob(
                external_id=external_id,
                platform="welcometothejungle",
                title=title,
                company=company,
                location=location,
                job_type=job_type,
                description=description[:8000],
                application_url=url,
            )
        except Exception as e:
            logger.debug(f"WTTJ parse: {e}")
            return None

    async def _fetch_wttj_description(self, url: str) -> str:
        try:
            ctx = await _create_context(self._browser)
            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=25000)
            await _delay(1000, 2000)

            desc_el = await page.query_selector(
                "[data-testid='job-section-description'], .sc-bXCLTC"
            )
            description = ""
            if desc_el:
                description = await desc_el.inner_text()
            else:
                # Fallback: get main content
                main = await page.query_selector("main")
                if main:
                    description = await main.inner_text()

            await ctx.close()
            return description.strip()
        except Exception:
            return ""


# ─── Helpers ─────────────────────────────────────────────────────────────────

_CONTRACT_KEYWORDS = {
    "alternance": "alternance",
    "apprentissage": "alternance",
    "stage": "stage",
    "internship": "stage",
    "cdi": "cdi",
    "full-time": "cdi",
    "cdd": "cdd",
    "freelance": "freelance",
    "indépendant": "freelance",
}


def _detect_contract_type(text: str) -> str | None:
    lower = text.lower()
    for keyword, contract in _CONTRACT_KEYWORDS.items():
        if keyword in lower:
            return contract
    return None


# Singleton scraper instance (reused across requests for browser reuse)
_scraper_instance: PlaywrightScraper | None = None


async def get_scraper() -> PlaywrightScraper:
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = PlaywrightScraper()
        await _scraper_instance.start()
    return _scraper_instance
