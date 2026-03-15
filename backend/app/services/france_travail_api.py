"""
France Travail API (ex Pôle Emploi) — Offres d'emploi.
OAuth2 Client Credentials. Docs: https://francetravail.io/data/api/offres-emploi

Contrats supportés:
  E1 = Apprentissage (alternance)
  PR = Professionnalisation (alternance)
  CI = Stage
  CDI, CDD, LIB (freelance)
"""
import asyncio
import logging
import time
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

CONTRACT_CODES: dict[str, list[str]] = {
    "alternance": ["E1", "PR"],
    "stage": ["CI"],
    "cdi": ["CDI"],
    "cdd": ["CDD"],
    "freelance": ["LIB"],
}

# Department codes for major French cities
DEPT_CODES: dict[str, str] = {
    "paris": "75",
    "île-de-france": "75",
    "ile-de-france": "75",
    "lyon": "69",
    "marseille": "13",
    "toulouse": "31",
    "bordeaux": "33",
    "lille": "59",
    "nantes": "44",
    "strasbourg": "67",
    "montpellier": "34",
    "rennes": "35",
    "grenoble": "38",
    "nice": "06",
    "remote": "75",  # fallback to Paris for remote
}


class FranceTravailAPI:
    def __init__(self):
        self.client_id = settings.france_travail_client_id
        self.client_secret = settings.france_travail_client_secret
        self._token: str | None = None
        self._token_expires: float = 0.0

    async def _get_token(self) -> str | None:
        if not self.client_id or not self.client_secret:
            return None
        now = time.monotonic()
        if self._token and now < self._token_expires - 60:
            return self._token
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    TOKEN_URL,
                    params={"realm": "/partenaire"},
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "scope": f"api_offresdemploiv2 application_{self.client_id}",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if resp.status_code != 200:
                logger.warning(f"France Travail auth failed: {resp.status_code} — {resp.text[:200]}")
                return None
            data = resp.json()
            self._token = data["access_token"]
            self._token_expires = now + data.get("expires_in", 1800)
            logger.info("France Travail token refreshed")
            return self._token
        except Exception as e:
            logger.error(f"France Travail auth error: {e}")
            return None

    async def search_jobs(
        self,
        keyword: str,
        location: str = "Paris",
        contract_types: list[str] | None = None,
        hours_back: int = 24,
        max_results: int = 50,
    ) -> list[dict]:
        token = await self._get_token()
        if not token:
            return []

        # Build contract codes
        codes: list[str] = []
        for ct in (contract_types or ["alternance"]):
            codes.extend(CONTRACT_CODES.get(ct.lower(), []))
        type_contrat = ",".join(dict.fromkeys(codes)) if codes else None

        # Get department code
        dept = self._get_dept(location)

        params: dict = {
            "motsCles": keyword,
            "publieeDepuis": min(max(1, hours_back // 24 + 1), 31),
            "range": f"0-{min(max_results - 1, 149)}",
        }
        if dept:
            params["departement"] = dept
        if type_contrat:
            params["typeContrat"] = type_contrat

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    SEARCH_URL,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            if resp.status_code == 204:
                return []  # No content = no results
            if resp.status_code != 200:
                logger.warning(f"France Travail search failed: {resp.status_code}")
                return []
            data = resp.json()
            results = data.get("resultats", [])
            logger.info(f"France Travail: {len(results)} offres pour '{keyword}' ({location})")
            return [self._normalize(o) for o in results]
        except Exception as e:
            logger.error(f"France Travail search error for '{keyword}': {e}")
            return []

    async def search_all(
        self,
        keywords: list[str],
        locations: list[str],
        contract_types: list[str] | None = None,
        hours_back: int = 24,
    ) -> list[dict]:
        """Search multiple keywords × locations in parallel."""
        tasks = [
            self.search_jobs(kw, loc, contract_types, hours_back)
            for kw in keywords[:3]
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
        return all_jobs

    def _get_dept(self, location: str) -> str:
        loc = location.lower().strip()
        for city, code in DEPT_CODES.items():
            if city in loc:
                return code
        return "75"  # Default Paris

    def _normalize(self, offer: dict) -> dict:
        lieu = offer.get("lieuTravail", {})
        sal = offer.get("salaire", {})
        posted_at = None
        if dt := offer.get("dateCreation"):
            try:
                from datetime import datetime, timezone
                posted_at = datetime.fromisoformat(dt.replace("Z", "+00:00")).isoformat()
            except Exception:
                pass
        return {
            "external_id": f"ft_{offer.get('id', '')}",
            "platform": "francetravail",
            "title": offer.get("intitule", ""),
            "company": offer.get("entreprise", {}).get("nom") or "Entreprise confidentielle",
            "company_size": offer.get("entreprise", {}).get("entreprisesAdaptees"),
            "location": lieu.get("libelle", ""),
            "remote_type": "remote" if offer.get("typeSalaire") == "TELETRAVAIL" else None,
            "job_type": self._map_contract(offer.get("typeContrat", "")),
            "salary_range": sal.get("libelle"),
            "description_raw": offer.get("description", "")[:8000],
            "application_url": offer.get("origineOffre", {}).get("urlOrigine", ""),
            "posted_at": posted_at,
        }

    def _map_contract(self, code: str) -> str | None:
        return {
            "E1": "alternance",
            "PR": "alternance",
            "CI": "stage",
            "CDI": "cdi",
            "CDD": "cdd",
            "LIB": "freelance",
        }.get(code)


_france_travail_instance: FranceTravailAPI | None = None


def get_france_travail_api() -> FranceTravailAPI:
    global _france_travail_instance
    if _france_travail_instance is None:
        _france_travail_instance = FranceTravailAPI()
    return _france_travail_instance
