"""
La Bonne Alternance API — Offres d'alternance (apprentissage + professionnalisation).
API publique, sans authentification.
Docs: https://labonnealternance.apprentissage.beta.gouv.fr/api/v1
"""
import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.labonnealternance.apprentissage.beta.gouv.fr/api/v1"

# ROME codes for tech roles (v3 nomenclature)
ROME_BY_KEYWORD: dict[str, list[str]] = {
    "développeur": ["M1805", "M1802"],
    "developpeur": ["M1805", "M1802"],
    "developer": ["M1805", "M1802"],
    "python": ["M1805"],
    "javascript": ["M1805"],
    "typescript": ["M1805"],
    "react": ["M1805"],
    "fullstack": ["M1805"],
    "full stack": ["M1805"],
    "frontend": ["M1805"],
    "front-end": ["M1805"],
    "backend": ["M1805"],
    "back-end": ["M1805"],
    "devops": ["M1810"],
    "cloud": ["M1810"],
    "sre": ["M1810"],
    "data scientist": ["M1811"],
    "data science": ["M1811"],
    "machine learning": ["M1811"],
    "deep learning": ["M1811"],
    "ia ": ["M1811"],
    "intelligence artificielle": ["M1811"],
    "data engineer": ["M1811"],
    "mlops": ["M1811"],
    "data analyst": ["M1402", "M1811"],
    "analyste": ["M1402"],
    "ingénieur": ["M1805"],
    "ingenieur": ["M1805"],
    "cybersécurité": ["M1810"],
    "cybersecurite": ["M1810"],
    "sécurité": ["M1810"],
    "réseau": ["M1810"],
    "reseau": ["M1810"],
    "administrateur": ["M1801"],
    "système": ["M1801"],
    "systeme": ["M1801"],
    "java": ["M1805"],
    "c++": ["M1805"],
    "golang": ["M1805"],
    "rust": ["M1805"],
    "informatique": ["M1805"],
    "logiciel": ["M1802"],
    "mobile": ["M1805"],
    "android": ["M1805"],
    "ios": ["M1805"],
}

CITY_COORDS: dict[str, tuple[float, float]] = {
    "paris": (48.8566, 2.3522),
    "lyon": (45.7640, 4.8357),
    "marseille": (43.2965, 5.3698),
    "toulouse": (43.6047, 1.4442),
    "bordeaux": (44.8378, -0.5792),
    "lille": (50.6292, 3.0573),
    "nantes": (47.2184, -1.5536),
    "strasbourg": (48.5734, 7.7521),
    "montpellier": (43.6108, 3.8767),
    "rennes": (48.1173, -1.6778),
    "grenoble": (45.1885, 5.7245),
    "nice": (43.7102, 7.2620),
    "remote": (48.8566, 2.3522),
    "île-de-france": (48.8566, 2.3522),
    "ile-de-france": (48.8566, 2.3522),
}


class BonneAlternanceAPI:
    async def search_jobs(
        self,
        keywords: list[str],
        locations: list[str],
        radius_km: int = 30,
    ) -> list[dict]:
        if not keywords or not locations:
            return []

        romes = self._get_romes(keywords)
        if not romes:
            romes = ["M1805"]  # Default: software development

        tasks = [
            self._search_location(romes, loc, radius_km)
            for loc in locations[:2]
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_jobs: list[dict] = []
        seen: set[str] = set()
        for batch in results:
            if isinstance(batch, list):
                for job in batch:
                    key = job.get("external_id", "")
                    if key and key not in seen:
                        seen.add(key)
                        all_jobs.append(job)
        logger.info(f"La Bonne Alternance: {len(all_jobs)} offres trouvées")
        return all_jobs

    async def _search_location(
        self, romes: list[str], location: str, radius_km: int
    ) -> list[dict]:
        coords = self._get_coords(location)
        lat, lon = coords
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"{BASE_URL}/jobs/min",
                    params={
                        "romes": ",".join(romes[:5]),
                        "latitude": lat,
                        "longitude": lon,
                        "radius": radius_km,
                        "sources": "offres,lba,matcha",
                        "caller": "postulio-app",
                    },
                )
            if resp.status_code != 200:
                logger.warning(f"Bonne Alternance {location}: HTTP {resp.status_code}")
                return []
            data = resp.json()
            return self._extract_all(data)
        except Exception as e:
            logger.error(f"Bonne Alternance error for {location}: {e}")
            return []

    def _extract_all(self, data: dict) -> list[dict]:
        jobs: list[dict] = []
        # PE jobs (France Travail via LBA aggregation)
        for item in data.get("peJobs", {}).get("results", []):
            if j := self._normalize_pe(item):
                jobs.append(j)
        # Matcha jobs (companies looking for apprentices)
        for item in data.get("matchas", {}).get("results", []):
            if j := self._normalize_matcha(item):
                jobs.append(j)
        # LBA company recommendations
        for item in data.get("lbaCompanies", {}).get("results", []):
            if j := self._normalize_lba(item):
                jobs.append(j)
        return jobs

    def _normalize_pe(self, item: dict) -> dict | None:
        job = item.get("job", {})
        company = item.get("company", {})
        place = item.get("place", {})
        ext_id = job.get("id") or item.get("id", "")
        if not ext_id or not job.get("title"):
            return None
        return {
            "external_id": f"lba_pe_{ext_id}",
            "platform": "bonne_alternance",
            "title": job.get("title", ""),
            "company": company.get("name", "Entreprise"),
            "company_size": None,
            "location": place.get("city") or place.get("fullAddress", ""),
            "remote_type": None,
            "job_type": "alternance",
            "salary_range": None,
            "description_raw": (job.get("description") or "")[:8000],
            "application_url": job.get("url") or item.get("url", ""),
            "posted_at": job.get("creationDate"),
        }

    def _normalize_matcha(self, item: dict) -> dict | None:
        ext_id = item.get("id") or item.get("_id", "")
        title = item.get("title") or item.get("offer", {}).get("title", "")
        if not ext_id or not title:
            return None
        company = item.get("company", {})
        place = item.get("place", {})
        return {
            "external_id": f"lba_matcha_{ext_id}",
            "platform": "bonne_alternance",
            "title": title,
            "company": company.get("name", "Entreprise"),
            "company_size": company.get("size"),
            "location": place.get("city") or place.get("fullAddress", ""),
            "remote_type": None,
            "job_type": "alternance",
            "salary_range": None,
            "description_raw": (item.get("description") or "")[:8000],
            "application_url": item.get("url", ""),
            "posted_at": item.get("createdAt"),
        }

    def _normalize_lba(self, item: dict) -> dict | None:
        """LBA companies are recommendations, not postings — skip."""
        return None  # These are headhunting recommendations, not actual job offers

    def _get_romes(self, keywords: list[str]) -> list[str]:
        romes: set[str] = set()
        for kw in keywords:
            kw_lower = kw.lower()
            for key, codes in ROME_BY_KEYWORD.items():
                if key in kw_lower:
                    romes.update(codes)
        return list(romes)

    def _get_coords(self, location: str) -> tuple[float, float]:
        loc = location.lower().strip()
        for city, coords in CITY_COORDS.items():
            if city in loc:
                return coords
        return (48.8566, 2.3522)  # Default: Paris


_instance: BonneAlternanceAPI | None = None


def get_bonne_alternance_api() -> BonneAlternanceAPI:
    global _instance
    if _instance is None:
        _instance = BonneAlternanceAPI()
    return _instance
