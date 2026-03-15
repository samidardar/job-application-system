"""
Research node — Company intelligence extraction via Claude.
For each matched job, Claude reads the job description and extracts
structured company insights used to personalize the CV and LDM.

No external web search — Claude extracts from what's in the job description,
which is the most reliable signal available.
"""
import asyncio
import logging

from pydantic import BaseModel

from app.agents.graph.state import PipelineState, JobDict
from app.services.claude_service import get_claude_service

logger = logging.getLogger(__name__)


class CompanyResearch(BaseModel):
    company_type: str           # startup | scaleup | pme | grand_groupe | cabinet | public
    sector: str                 # e.g. "fintech", "santé numérique", "e-commerce"
    tech_stack: list[str]       # Technologies explicitly mentioned
    culture_signals: list[str]  # Values/culture clues from JD
    contract_context: str       # Why this company takes alternants/stagiaires/CDI
    hook_idea: str              # 1-sentence accroche idea for the LDM
    key_projects: list[str]     # Projects/missions mentioned in JD
    company_stage: str          # early | growth | mature | unknown


async def _research_one(job: JobDict) -> dict:
    system = """Tu es un expert en intelligence économique et en marché tech français.
Tu analyses des offres d'emploi pour en extraire des insights stratégiques sur l'entreprise.
Ces insights servent à personnaliser un CV et une lettre de motivation."""

    user_msg = f"""Analyse cette offre d'emploi et extrais des informations clés sur l'entreprise.

## OFFRE
Titre: {job.get('title', '')}
Entreprise: {job.get('company', '')} ({job.get('company_size') or 'taille inconnue'})
Lieu: {job.get('location', '')} — {job.get('remote_type') or 'présentiel'}
Contrat: {job.get('job_type') or 'non précisé'}
Description: {(job.get('description_raw') or '')[:3000]}

## CONSIGNE
Extrais uniquement ce qui est EXPLICITEMENT mentionné ou clairement implicite dans l'offre.
Ne devine pas, ne fabrique pas. Si une information n'est pas disponible, mets "unknown" ou une liste vide.
Pour hook_idea: une phrase d'accroche originale et factuelle pour une lettre de motivation, qui montre
qu'on connaît vraiment l'entreprise (basée sur des éléments réels de l'offre)."""

    try:
        claude = get_claude_service()
        result, _, _ = await claude.complete_structured(
            system=system,
            user=user_msg,
            output_schema=CompanyResearch,
            max_tokens=1000,
        )
        return {
            "company_type": result.company_type,
            "sector": result.sector,
            "tech_stack": result.tech_stack,
            "culture_signals": result.culture_signals,
            "contract_context": result.contract_context,
            "hook_idea": result.hook_idea,
            "key_projects": result.key_projects,
            "company_stage": result.company_stage,
        }
    except Exception as e:
        logger.warning(f"[research] Error for {job.get('company')}: {e}")
        return {
            "company_type": "unknown",
            "sector": "tech",
            "tech_stack": [],
            "culture_signals": [],
            "contract_context": "",
            "hook_idea": "",
            "key_projects": [],
            "company_stage": "unknown",
        }


async def node_research(state: PipelineState) -> dict:
    """Enrich matched jobs with company research (parallel)."""
    matched = state.get("matched_jobs", [])
    if not matched:
        return {"matched_jobs": [], "errors": []}

    logger.info(f"[research] Researching {len(matched)} entreprises")

    semaphore = asyncio.Semaphore(6)

    async def research_with_sem(job: JobDict) -> JobDict:
        async with semaphore:
            research = await _research_one(job)
            enriched = dict(job)
            enriched["company_research"] = research
            return enriched  # type: ignore

    results = await asyncio.gather(
        *[research_with_sem(j) for j in matched],
        return_exceptions=True,
    )

    enriched_jobs: list[JobDict] = []
    errors: list[str] = []
    for r in results:
        if isinstance(r, dict):
            enriched_jobs.append(r)  # type: ignore
        elif isinstance(r, Exception):
            errors.append(str(r))

    return {"matched_jobs": enriched_jobs, "errors": errors}
