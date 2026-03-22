"""
Matching node — Claude scores each job against the user profile (0-100).
Jobs scoring >= min_match_score move on; others are marked BELOW_THRESHOLD.
Uses asyncio.gather for parallel scoring of all valid jobs.
"""
import asyncio
import logging
import uuid

from pydantic import BaseModel, field_validator
from sqlalchemy import select

from app.agents.graph.state import PipelineState, JobDict
from app.database import AsyncSessionLocal
from app.models.job import Job, JobStatusEnum
from app.services.claude_service import get_claude_service

logger = logging.getLogger(__name__)

# Contract type labels for the prompt
CONTRACT_LABELS = {
    "alternance": "Alternance (contrat d'apprentissage ou professionnalisation)",
    "stage": "Stage conventionné",
    "cdi": "CDI — Contrat à durée indéterminée",
    "cdd": "CDD — Contrat à durée déterminée",
    "freelance": "Freelance / mission",
}


class MatchingOutput(BaseModel):
    score: int                        # 0-100
    verdict: str                      # "apply" | "skip"
    top_match_reasons: list[str]      # Max 3 bullet points
    skill_gaps: list[str]             # Skills missing, be honest
    ats_keywords_critical: list[str]  # Keywords that MUST appear in CV/LDM
    tailoring_hints: str              # 1-2 sentences for content generation
    contract_type_match: bool         # Does contract type match user preferences?

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: int) -> int:
        return max(0, min(100, v))

    @field_validator("verdict")
    @classmethod
    def normalise_verdict(cls, v: str) -> str:
        v = v.lower().strip()
        return v if v in ("apply", "skip") else "skip"


async def _score_job(
    job: dict,
    profile: dict,
    prefs: dict,
    threshold: int,
) -> JobDict | None:
    """Score one job with Claude. Returns enriched JobDict or None if below threshold."""
    job_id = job.get("id", "")

    # Build contract label
    job_contract = job.get("job_type") or "non précisé"
    contract_label = CONTRACT_LABELS.get(job_contract, job_contract)
    preferred_contracts = prefs.get("contract_types") or []
    preferred_contract_labels = [CONTRACT_LABELS.get(c, c) for c in preferred_contracts]

    # Profile data
    skills = ", ".join(profile.get("skills_technical") or [])
    education_raw = profile.get("education") or []
    experience_raw = profile.get("experience") or []
    education_str = "; ".join(
        f"{e.get('degree', '')} @ {e.get('school', '')} ({e.get('year', '')})"
        for e in (education_raw[:2] if isinstance(education_raw, list) else [])
    )
    experience_str = "; ".join(
        f"{e.get('title', '')} @ {e.get('company', '')} ({e.get('duration', '')})"
        for e in (experience_raw[:3] if isinstance(experience_raw, list) else [])
    )

    system = """Tu es un expert RH / recruteur tech spécialisé dans le marché français (alternance, stage, CDI).
Tu évalues l'adéquation candidat-offre avec précision chirurgicale.

Score 0-100:
- 85-100 : Excellente adéquation, candidature prioritaire
- 70-84  : Bonne adéquation, postuler sans hésiter
- 55-69  : Adéquation partielle, postuler si peu d'autres options
- <55    : Mauvaise adéquation, passer

Sois honnête. Un score ≥70 signifie que le candidat a une chance réaliste d'obtenir un entretien.
Pénalise fortement si le type de contrat ne correspond pas aux préférences du candidat."""

    user_msg = f"""## PROFIL CANDIDAT
Postes recherchés: {', '.join(prefs.get('target_roles') or [])}
Contrats souhaités: {', '.join(preferred_contract_labels)}
Localisations: {', '.join(prefs.get('preferred_locations') or [])}
Compétences techniques: {skills}
Formation: {education_str or 'Non précisée'}
Expérience: {experience_str or 'Aucune expérience pro'}

## OFFRE D'EMPLOI
Titre: {job.get('title', '')}
Entreprise: {job.get('company', '')} — {job.get('company_size') or 'taille inconnue'}
Lieu: {job.get('location', '')} ({job.get('remote_type') or 'présentiel'})
Contrat proposé: {contract_label}
Salaire: {job.get('salary_range') or 'Non précisé'}
Description (extrait): {(job.get('description_raw') or '')[:2500]}

## CONSIGNE
Score cette offre pour ce candidat. Si le contrat ne correspond pas aux préférences → verdict "skip" automatique."""

    try:
        claude = get_claude_service()
        result, pt, ct = await claude.complete_structured(
            system=system,
            user=user_msg,
            output_schema=MatchingOutput,
            max_tokens=1500,
        )

        # Force skip if contract type doesn't match
        if not result.contract_type_match and preferred_contracts:
            result.score = min(result.score, 45)
            result.verdict = "skip"

        # Save to DB
        if job_id:
            async with AsyncSessionLocal() as db:
                db_result = await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
                db_job = db_result.scalar_one_or_none()
                if db_job:
                    db_job.match_score = result.score
                    db_job.match_rationale = {
                        "top_match_reasons": result.top_match_reasons,
                        "skill_gaps": result.skill_gaps,
                        "verdict": result.verdict,
                        "contract_type_match": result.contract_type_match,
                    }
                    db_job.match_highlights = result.top_match_reasons
                    db_job.ats_keywords_critical = result.ats_keywords_critical
                    db_job.tailoring_hints = result.tailoring_hints
                    db_job.status = (
                        JobStatusEnum.MATCHED
                        if result.score >= threshold
                        else JobStatusEnum.BELOW_THRESHOLD
                    )
                    await db.commit()

        if result.score < threshold:
            logger.debug(f"[match] SKIP {job.get('title')} @ {job.get('company')} → {result.score}")
            return None

        logger.info(f"[match] MATCH {job.get('title')} @ {job.get('company')} → {result.score}/100")
        enriched: JobDict = dict(job)  # type: ignore
        enriched["match_score"] = result.score
        enriched["ats_keywords"] = result.ats_keywords_critical
        enriched["tailoring_hints"] = result.tailoring_hints
        enriched["match_reasons"] = result.top_match_reasons
        enriched["skill_gaps"] = result.skill_gaps
        return enriched

    except Exception as e:
        logger.error(f"[match] Error for {job.get('title')}: {e}")
        return None


async def node_match(state: PipelineState) -> dict:
    """Score all valid jobs in parallel, keep those >= threshold."""
    valid_jobs = state.get("valid_jobs", [])
    profile = state.get("user_profile", {})
    prefs = state.get("user_preferences", {})
    threshold = prefs.get("min_match_score") or 70

    if not valid_jobs:
        return {"matched_jobs": [], "errors": []}

    logger.info(f"[match] Scoring {len(valid_jobs)} offres (seuil={threshold})")

    # Parallel scoring (max 8 concurrent to avoid rate limits)
    semaphore = asyncio.Semaphore(8)

    async def score_with_sem(job: dict) -> JobDict | None:
        async with semaphore:
            return await _score_job(job, profile, prefs, threshold)

    results = await asyncio.gather(
        *[score_with_sem(j) for j in valid_jobs],
        return_exceptions=True,
    )

    matched: list[JobDict] = []
    errors: list[str] = []
    for r in results:
        if isinstance(r, dict) and r:
            matched.append(r)  # type: ignore
        elif isinstance(r, Exception):
            errors.append(str(r))

    # Respect daily_application_limit
    limit = prefs.get("daily_application_limit") or 20
    if len(matched) > limit:
        matched = sorted(matched, key=lambda j: j.get("match_score", 0), reverse=True)[:limit]

    logger.info(f"[match] {len(matched)} offres matchées sur {len(valid_jobs)} valides")
    return {
        "matched_jobs": matched,
        "jobs_matched": len(matched),
        "errors": errors,
    }
