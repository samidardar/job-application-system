"""
QA Gate node — Grades each CV+LDM pair and retries if below threshold.

Grades:
  A+  (90-100) → Submit immediately, exceptional quality
  A   (75-89)  → Submit, very good quality
  B+  (60-74)  → Retry once with explicit feedback
  B   (40-59)  → Retry once, significant issues
  F   (<40)    → Skip job, too much risk

Max 1 retry per job to avoid infinite loops.
After retry, submit if ≥ B+ (60), skip if still below.
"""
import asyncio
import logging
import re
import uuid

from pydantic import BaseModel
from sqlalchemy import select

from app.agents.graph.state import PipelineState, JobDict
from app.database import AsyncSessionLocal
from app.models.job import Job, JobStatusEnum
from app.services.claude_service import get_claude_service

logger = logging.getLogger(__name__)

# Words forbidden in LDM
FORBIDDEN_WORDS = [
    "dynamique", "motivé", "motivée", "motivés", "motivées",
    "passionné par", "passionnée par", "je me permets",
    "dans l'attente", "cordiales salutations",
    "force de proposition", "rigoureux", "rigoureuse",
    "curieux", "curieuse", "sérieux", "sérieuse",
    "autonome", "polyvalent", "polyvalente", "proactif",
    "bonne communication", "madame, monsieur",
]

TARGET_WORD_COUNT_MIN = 275
TARGET_WORD_COUNT_MAX = 325


class QAOutput(BaseModel):
    score: int                # 0-100
    grade: str                # A+, A, B+, B, F
    ats_coverage: int         # % of critical keywords found in docs
    ldm_word_count: int       # Actual word count
    forbidden_words_found: list[str]
    issues: list[str]         # Specific problems found
    strengths: list[str]      # What's working well
    retry_instructions: str   # Precise feedback for regeneration if needed


def _count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _check_forbidden(text: str) -> list[str]:
    text_lower = text.lower()
    return [w for w in FORBIDDEN_WORDS if w in text_lower]


def _grade_from_score(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 60:
        return "B+"
    if score >= 40:
        return "B"
    return "F"


async def _grade_documents(job: JobDict) -> QAOutput:
    """Use Claude to grade the CV + LDM pair."""
    cv_html = job.get("cv_html") or ""
    ldm_text = job.get("ldm_text") or ""
    ats_keywords = job.get("ats_keywords") or []

    word_count = _count_words(ldm_text)
    forbidden_found = _check_forbidden(ldm_text)

    # Quick local checks before calling Claude
    local_issues: list[str] = []
    if word_count < TARGET_WORD_COUNT_MIN:
        local_issues.append(f"LDM trop courte: {word_count} mots (min {TARGET_WORD_COUNT_MIN})")
    elif word_count > TARGET_WORD_COUNT_MAX:
        local_issues.append(f"LDM trop longue: {word_count} mots (max {TARGET_WORD_COUNT_MAX})")
    if forbidden_found:
        local_issues.append(f"Mots interdits dans LDM: {', '.join(forbidden_found)}")

    # ATS coverage check
    cv_text_lower = re.sub(r"<[^>]+>", " ", cv_html).lower()
    ldm_lower = ldm_text.lower()
    keywords_found = [k for k in ats_keywords if k.lower() in cv_text_lower or k.lower() in ldm_lower]
    ats_pct = int(len(keywords_found) / max(len(ats_keywords), 1) * 100)

    system = """Tu es un expert QA en recrutement tech français. Tu évalues la qualité d'un CV tailored + LDM.
Score 0-100 basé sur:
- Personnalisation pour l'offre (30%): La lettre/CV semblent écrits pour CETTE entreprise et CE poste?
- Qualité LDM (30%): Structure VOUS-MOI-NOUS? Preuves concrètes et chiffrées? Accroche forte?
- Optimisation ATS (20%): Mots-clés critiques intégrés naturellement dans CV et LDM?
- Authenticité (10%): Pas de clichés, style direct, professionnel?
- Format (10%): Longueur correcte, HTML propre, lisible?

Sois strict. Un score A+ (90+) = candidature irréprochable, prête à envoyer sans aucune modification."""

    user_msg = f"""## OFFRE CIBLÉE
Poste: {job.get('title')} chez {job.get('company')}
Contrat: {job.get('job_type') or 'non précisé'}
ATS keywords critiques: {', '.join(ats_keywords)}

## CV GÉNÉRÉ (extrait HTML)
{cv_html[:3000]}

## LETTRE DE MOTIVATION
{ldm_text[:2000]}

## DONNÉES LOCALES
Nombre de mots LDM: {word_count} (cible: {TARGET_WORD_COUNT_MIN}-{TARGET_WORD_COUNT_MAX})
Mots interdits détectés: {', '.join(forbidden_found) if forbidden_found else 'aucun ✓'}
Couverture ATS: {ats_pct}% ({len(keywords_found)}/{max(len(ats_keywords), 1)} keywords trouvés)
Problèmes locaux: {'; '.join(local_issues) if local_issues else 'aucun ✓'}

## CONSIGNE
Grade cette paire CV+LDM. Dans retry_instructions: donne des instructions très précises et actionnables
pour corriger les problèmes (si grade < A). Exemple: "Paragraphe 2: remplacer 'motivé par' par..."""

    try:
        claude = get_claude_service()
        result, _, _ = await claude.complete_structured(
            system=system,
            user=user_msg,
            output_schema=QAOutput,
            max_tokens=1500,
        )
        # Override with local checks
        result.ldm_word_count = word_count
        result.forbidden_words_found = forbidden_found
        result.issues = list(set(result.issues + local_issues))
        result.ats_coverage = ats_pct
        result.grade = _grade_from_score(result.score)
        return result
    except Exception as e:
        logger.error(f"[qa] Grading error: {e}")
        # Fallback score based on local checks
        score = 70
        if local_issues:
            score -= 10 * len(local_issues)
        if ats_pct < 50:
            score -= 15
        score = max(0, min(100, score))
        return QAOutput(
            score=score,
            grade=_grade_from_score(score),
            ats_coverage=ats_pct,
            ldm_word_count=word_count,
            forbidden_words_found=forbidden_found,
            issues=local_issues + [f"QA Claude error: {e}"],
            strengths=[],
            retry_instructions="Corriger les problèmes de longueur et mots interdits.",
        )


async def _retry_documents(job: JobDict) -> JobDict | None:
    """Re-generate documents with QA feedback."""
    try:
        from app.agents.graph.nodes.generate_docs import (
            _generate_for_job,
        )
        from app.database import AsyncSessionLocal
        from app.models.user import UserProfile, User
        from sqlalchemy import select

        user_id = uuid.UUID(job.get("user_id_hint", job.get("id", "")[:36]))
        async with AsyncSessionLocal() as db:
            profile_result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = profile_result.scalar_one_or_none()
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()

        if not profile or not user:
            return None

        profile_dict = {
            "cv_html_template": profile.cv_html_template,
            "cv_text_content": profile.cv_text_content,
            "skills_technical": profile.skills_technical,
            "skills_soft": profile.skills_soft,
            "education": profile.education,
            "experience": profile.experience,
            "languages": profile.languages,
            "certifications": profile.certifications,
            "projects": getattr(profile, "projects", None),
            "ville": profile.ville,
            "phone": profile.phone,
            "linkedin_url": profile.linkedin_url,
            "github_url": getattr(profile, "github_url", None),
            "portfolio_url": getattr(profile, "portfolio_url", None),
        }
        user_info = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        }
        return await _generate_for_job(job, profile_dict, user_info, user_id)
    except Exception as e:
        logger.error(f"[qa] Retry generation failed: {e}")
        return None


async def _qa_one(job: JobDict) -> JobDict:
    """Grade one job's documents, retry once if needed."""
    qa = await _grade_documents(job)
    logger.info(
        f"[qa] {job.get('company')} — {job.get('title')}: "
        f"grade={qa.grade} score={qa.score} ats={qa.ats_coverage}%"
    )

    enriched = dict(job)
    enriched["qa_grade"] = qa.grade
    enriched["qa_score"] = qa.score
    enriched["qa_feedback"] = qa.retry_instructions

    # A+ or A → ready immediately
    if qa.score >= 75:
        enriched["ready_to_apply"] = True
        logger.info(f"[qa] ✓ PRÊT à soumettre: {job.get('company')} ({qa.grade})")
        return enriched  # type: ignore

    retry_count = job.get("retry_count") or 0
    if retry_count >= 1:
        # Already retried once → submit if B+, skip if below
        enriched["ready_to_apply"] = qa.score >= 60
        return enriched  # type: ignore

    # Retry once with feedback
    logger.info(f"[qa] Retry pour {job.get('company')}: {qa.retry_instructions[:100]}")
    enriched["retry_count"] = 1
    # Inject feedback into the job so generate_docs can pick it up
    enriched["qa_retry_feedback"] = qa.retry_instructions

    retried = await _retry_documents(enriched)  # type: ignore
    if retried:
        qa2 = await _grade_documents(retried)
        retried["qa_grade"] = qa2.grade
        retried["qa_score"] = qa2.score
        retried["ready_to_apply"] = qa2.score >= 60
        logger.info(f"[qa] Post-retry: {job.get('company')} → {qa2.grade} ({qa2.score})")
        return retried  # type: ignore

    enriched["ready_to_apply"] = qa.score >= 60
    return enriched  # type: ignore


async def node_qa_gate(state: PipelineState) -> dict:
    """Grade all generated document pairs and filter ready jobs."""
    matched = state.get("matched_jobs", [])
    jobs_with_docs = [j for j in matched if j.get("cv_doc_id")]

    if not jobs_with_docs:
        return {"jobs_ready": [], "errors": []}

    logger.info(f"[qa] Grading {len(jobs_with_docs)} candidatures")

    semaphore = asyncio.Semaphore(4)

    async def qa_with_sem(job: JobDict) -> JobDict:
        async with semaphore:
            return await _qa_one(job)

    results = await asyncio.gather(
        *[qa_with_sem(j) for j in jobs_with_docs],
        return_exceptions=True,
    )

    jobs_ready: list[JobDict] = []
    errors: list[str] = []
    for r in results:
        if isinstance(r, dict):
            job = r  # type: ignore
            if job.get("ready_to_apply"):
                jobs_ready.append(job)
                # Update job status in DB
                if job.get("id"):
                    try:
                        async with AsyncSessionLocal() as db:
                            db_result = await db.execute(
                                select(Job).where(Job.id == uuid.UUID(job["id"]))
                            )
                            db_job = db_result.scalar_one_or_none()
                            if db_job:
                                db_job.status = JobStatusEnum.READY_TO_APPLY
                                await db.commit()
                    except Exception as e:
                        errors.append(str(e))
        elif isinstance(r, Exception):
            errors.append(str(r))

    a_plus = sum(1 for j in jobs_ready if j.get("qa_grade") == "A+")
    a = sum(1 for j in jobs_ready if j.get("qa_grade") == "A")
    logger.info(
        f"[qa] {len(jobs_ready)}/{len(jobs_with_docs)} prêts "
        f"(A+={a_plus} A={a} B+={len(jobs_ready)-a_plus-a})"
    )
    return {"jobs_ready": jobs_ready, "errors": errors}
