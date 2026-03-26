"""
LangChain tools for Dr. Rousseau — all created via make_tools() factory
so that `db` and `user_id` are captured in the closure.

Tools deliberately return rich string summaries (not raw dicts) so the LLM
can relay them directly to the user without extra formatting work.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime

import httpx
from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.cv_optimizer_agent import CVOptimizerAgent
from app.agents.cover_letter_agent import CoverLetterAgent
from app.agents.matching_agent import MatchingAgent
from app.models.agent_run import AgentStatusEnum, PipelineRun
from app.models.application import Application, ApplicationStatusEnum
from app.models.document import Document, DocumentTypeEnum
from app.models.job import Job, JobPlatformEnum, JobStatusEnum
from app.models.user import UserProfile, UserPreferences
from app.services.claude_service import get_claude_service
from app.config import settings

logger = logging.getLogger(__name__)

# Human-readable status messages shown to the user during tool execution
TOOL_STATUS = {
    "analyze_job_url": "🔍 Analyse de l'offre en cours...",
    "generate_application_docs": "📄 Génération du CV ciblé et de la lettre de motivation...",
    "get_dashboard_stats": "📊 Récupération de tes statistiques...",
    "search_new_jobs": "🚀 Lancement de la recherche d'offres...",
}

# Regex to strip HTML tags for plain-text extraction
_RE_HTML_TAGS = re.compile(r"<[^>]+>")
_RE_WHITESPACE = re.compile(r"\s{3,}")

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


async def _fetch_url_text(url: str, max_chars: int = 12_000) -> str:
    """Fetch a URL and return stripped plain text (best-effort, no JS rendering)."""
    try:
        async with httpx.AsyncClient(
            headers=FETCH_HEADERS,
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw = resp.text
    except httpx.HTTPStatusError as e:
        return f"[HTTP {e.response.status_code} lors du chargement de {url}]"
    except Exception as e:
        return f"[Impossible de charger {url}: {e}]"

    # Strip scripts, styles, and then all tags
    raw = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    text = _RE_HTML_TAGS.sub(" ", raw)
    text = _RE_WHITESPACE.sub("\n", text).strip()
    return text[:max_chars]


def _stable_external_id(url: str) -> str:
    """Deterministic external_id derived from URL so we can detect duplicates."""
    return "chat_" + hashlib.sha256(url.encode()).hexdigest()[:16]


def make_tools(db: AsyncSession, user_id: uuid.UUID) -> list:
    """
    Factory: creates all Dr. Rousseau tools with `db` and `user_id`
    bound via closure. Call once per request.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # TOOL 1 — analyze_job_url
    # ─────────────────────────────────────────────────────────────────────────

    @tool
    async def analyze_job_url(url: str) -> str:
        """
        Fetch a job posting URL, extract structured job data using AI,
        save it to the database, and compute a match score against the
        user's profile. Use this whenever the user shares a job URL.

        Args:
            url: Full URL of the job posting (LinkedIn, Indeed, WTTJ, etc.)

        Returns:
            A summary with job title, company, match score, key ATS keywords,
            and the job_id needed to generate application documents.
        """
        try:
            external_id = _stable_external_id(url)

            # Duplicate check — skip scraping if we already have this URL
            existing = await db.execute(
                select(Job).where(
                    Job.user_id == user_id,
                    Job.external_id == external_id,
                )
            )
            job = existing.scalar_one_or_none()

            if not job:
                # Fetch & parse
                raw_text = await _fetch_url_text(url)
                if raw_text.startswith("["):
                    return f"❌ Impossible de charger l'offre: {raw_text}"

                # Use Claude to extract structured job data
                claude = get_claude_service()
                from pydantic import BaseModel

                class JobExtract(BaseModel):
                    title: str
                    company: str
                    location: str
                    job_type: str  # alternance|stage|cdi|cdd|freelance|unknown
                    description: str  # 1500 chars max
                    requirements: list[str]  # hard skills only

                extract_prompt = (
                    "Extrais les informations clés de cette offre d'emploi en JSON strict.\n"
                    "Pour job_type, déduis parmi: alternance, stage, cdi, cdd, freelance, unknown.\n"
                    "Pour requirements, liste uniquement les compétences techniques (frameworks, langages, outils).\n\n"
                    f"TEXTE DE L'OFFRE:\n{raw_text[:8000]}"
                )

                result, _, _ = await claude.complete_structured(
                    system="Tu es un expert RH. Extrais les données d'une offre d'emploi en JSON.",
                    user=extract_prompt,
                    output_schema=JobExtract,
                    max_tokens=1500,
                )

                from app.models.job import JobTypeEnum
                type_map = {
                    "alternance": JobTypeEnum.ALTERNANCE,
                    "stage": JobTypeEnum.STAGE,
                    "cdi": JobTypeEnum.CDI,
                    "cdd": JobTypeEnum.CDD,
                    "freelance": JobTypeEnum.FREELANCE,
                }

                job = Job(
                    user_id=user_id,
                    external_id=external_id,
                    platform=JobPlatformEnum.LINKEDIN,  # best guess for generic URL
                    title=result.title[:500],
                    company=result.company[:500],
                    location=result.location[:200],
                    job_type=type_map.get(result.job_type),
                    description_raw=raw_text[:8000],
                    description_clean=result.description[:5000],
                    requirements_extracted={"skills": result.requirements},
                    application_url=url[:1000],
                    status=JobStatusEnum.SCRAPED,
                )
                db.add(job)
                await db.flush()
                await db.refresh(job)
                logger.info(f"[DrRousseauTool] Saved job {job.id}: {job.title} @ {job.company}")

            # Run matching agent
            matcher = MatchingAgent(db=db, pipeline_run_id=None, user_id=user_id)
            is_match = await matcher.run(job.id)
            await db.flush()

            await db.refresh(job)
            score = job.match_score or 0
            keywords = ", ".join((job.ats_keywords_critical or [])[:8])
            match_verdict = "✅ Bonne correspondance" if is_match else "⚠️ En dessous du seuil"

            gaps = []
            if job.match_rationale and isinstance(job.match_rationale, dict):
                gaps = job.match_rationale.get("skill_gaps", [])[:3]

            gaps_str = f"\n  Gaps: {', '.join(gaps)}" if gaps else ""
            hints = job.tailoring_hints or ""
            hints_str = f"\n  Conseil: {hints[:200]}" if hints else ""

            return (
                f"**{job.title}** chez **{job.company}** ({job.location or 'France'})\n"
                f"Score de match: **{score}/100** — {match_verdict}{gaps_str}\n"
                f"Mots-clés ATS: {keywords or 'non disponibles'}{hints_str}\n"
                f"job_id: `{job.id}`\n"
                f"_(Utilise generate_application_docs avec ce job_id pour générer les documents)_"
            )

        except Exception as e:
            logger.error(f"[DrRousseauTool] analyze_job_url error: {e}", exc_info=True)
            return f"❌ Erreur lors de l'analyse: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # TOOL 2 — generate_application_docs
    # ─────────────────────────────────────────────────────────────────────────

    @tool
    async def generate_application_docs(job_id: str) -> str:
        """
        Generate a tailored ATS-optimized CV and a French cover letter for a
        specific job, then create an Application record in the dashboard.
        Requires the user to have uploaded a CV template first.

        Args:
            job_id: UUID of the job (returned by analyze_job_url)

        Returns:
            Confirmation with document names and a link to the dashboard.
        """
        try:
            jid = uuid.UUID(job_id)
        except ValueError:
            return "❌ job_id invalide. Utilise d'abord analyze_job_url pour obtenir un job_id valide."

        try:
            job_result = await db.execute(select(Job).where(Job.id == jid, Job.user_id == user_id))
            job = job_result.scalar_one_or_none()
            if not job:
                return f"❌ Offre `{job_id}` introuvable. Vérifie le job_id."

            # Check CV template exists
            profile_result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = profile_result.scalar_one_or_none()
            if not profile or not profile.cv_html_template:
                return (
                    "❌ Aucun CV template trouvé. Va dans **Paramètres > CV** pour uploader "
                    "ton CV original avant de générer des documents ciblés."
                )

            # Generate CV
            cv_agent = CVOptimizerAgent(db=db, pipeline_run_id=None, user_id=user_id)
            cv_doc_id = await cv_agent.run(jid)
            await db.flush()

            # Generate cover letter
            letter_agent = CoverLetterAgent(db=db, pipeline_run_id=None, user_id=user_id)
            letter_doc_id = await letter_agent.run(jid)
            await db.flush()

            if not cv_doc_id and not letter_doc_id:
                return "❌ Échec de la génération des documents. Consulte les logs pour plus de détails."

            # Upsert Application record
            app_result = await db.execute(
                select(Application).where(Application.job_id == jid, Application.user_id == user_id)
            )
            application = app_result.scalar_one_or_none()

            if not application:
                application = Application(
                    user_id=user_id,
                    job_id=jid,
                    cv_document_id=cv_doc_id,
                    cover_letter_document_id=letter_doc_id,
                    status=ApplicationStatusEnum.PENDING,
                    timeline=[
                        {
                            "event": "documents_generated",
                            "timestamp": datetime.utcnow().isoformat(),
                            "details": "Documents générés via Dr. Rousseau",
                        }
                    ],
                )
                db.add(application)
            else:
                application.cv_document_id = cv_doc_id or application.cv_document_id
                application.cover_letter_document_id = letter_doc_id or application.cover_letter_document_id

            # Update job status
            job.status = JobStatusEnum.READY_TO_APPLY
            await db.flush()

            parts = []
            if cv_doc_id:
                parts.append("✅ CV ciblé ATS généré")
            if letter_doc_id:
                parts.append("✅ Lettre de motivation rédigée")

            return (
                f"Documents créés pour **{job.title}** chez **{job.company}** :\n"
                + "\n".join(parts)
                + "\n\nTout est visible dans ton **dashboard > Documents**. "
                "Tu peux maintenant postuler manuellement ou activer l'auto-apply dans les paramètres."
            )

        except Exception as e:
            logger.error(f"[DrRousseauTool] generate_application_docs error: {e}", exc_info=True)
            return f"❌ Erreur lors de la génération: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # TOOL 3 — get_dashboard_stats
    # ─────────────────────────────────────────────────────────────────────────

    @tool
    async def get_dashboard_stats() -> str:
        """
        Return a real-time summary of the user's job search activity:
        number of applications by status, recent matched jobs, and
        pipeline run history. Use when the user asks about their progress
        or current situation.

        Returns:
            Formatted text summary of the user's dashboard.
        """
        try:
            from app.models.application import ApplicationStatusEnum
            from sqlalchemy import case

            # Count applications by status
            app_counts = await db.execute(
                select(
                    func.count(Application.id).label("total"),
                    func.count(
                        case((Application.status == ApplicationStatusEnum.SUBMITTED, 1))
                    ).label("submitted"),
                    func.count(
                        case((Application.status == ApplicationStatusEnum.INTERVIEW_SCHEDULED, 1))
                    ).label("interviews"),
                    func.count(
                        case((Application.status == ApplicationStatusEnum.OFFER_RECEIVED, 1))
                    ).label("offers"),
                    func.count(
                        case((Application.status == ApplicationStatusEnum.REJECTED, 1))
                    ).label("rejected"),
                    func.count(
                        case((Application.status == ApplicationStatusEnum.PENDING, 1))
                    ).label("pending"),
                ).where(Application.user_id == user_id)
            )
            stats = app_counts.one()

            # Recent matched jobs not yet applied
            recent_jobs_result = await db.execute(
                select(Job)
                .where(
                    Job.user_id == user_id,
                    Job.status == JobStatusEnum.MATCHED,
                    Job.match_score >= 70,
                )
                .order_by(Job.scraped_at.desc())
                .limit(5)
            )
            recent_jobs = recent_jobs_result.scalars().all()

            # Last pipeline run
            pipeline_result = await db.execute(
                select(PipelineRun)
                .where(PipelineRun.user_id == user_id)
                .order_by(PipelineRun.started_at.desc())
                .limit(1)
            )
            last_run = pipeline_result.scalar_one_or_none()

            # Build response
            lines = [
                "## 📊 Tableau de bord Postulio",
                "",
                "**Candidatures :**",
                f"  • Total : {stats.total}",
                f"  • En attente : {stats.pending}",
                f"  • Soumises : {stats.submitted}",
                f"  • Entretiens : {stats.interviews}",
                f"  • Offres reçues : {stats.offers}",
                f"  • Refus : {stats.rejected}",
            ]

            if stats.submitted > 0:
                interview_rate = round(stats.interviews / stats.submitted * 100, 1)
                lines.append(f"  • Taux d'entretien : {interview_rate}%")

            if recent_jobs:
                lines += ["", "**Offres matchées en attente de candidature :**"]
                for j in recent_jobs:
                    lines.append(f"  • {j.title} @ {j.company} — Score: {j.match_score}/100 (job_id: `{j.id}`)")

            if last_run:
                elapsed = ""
                if last_run.completed_at:
                    delta = last_run.completed_at - last_run.started_at
                    elapsed = f" ({int(delta.total_seconds())}s)"
                lines += [
                    "",
                    f"**Dernier pipeline :** {last_run.status.value}{elapsed}",
                    f"  • Offres scrappées : {last_run.jobs_scraped}",
                    f"  • Offres matchées : {last_run.jobs_matched}",
                    f"  • Candidatures soumises : {last_run.applications_submitted}",
                ]

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"[DrRousseauTool] get_dashboard_stats error: {e}", exc_info=True)
            return f"❌ Erreur lors de la récupération des stats: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # TOOL 4 — search_new_jobs
    # ─────────────────────────────────────────────────────────────────────────

    @tool
    async def search_new_jobs(role: str, location: str) -> str:
        """
        Trigger a background job search pipeline for the given role and location.
        The pipeline will scrape LinkedIn, Indeed, and Welcome to the Jungle,
        score each job against the user's profile, and populate the dashboard
        with matched results. This runs asynchronously — results appear in
        the dashboard within 2-5 minutes.

        Args:
            role: Job title to search (e.g. "Data Scientist", "ML Engineer")
            location: City or region (e.g. "Paris", "Lyon", "Remote France")

        Returns:
            Confirmation that the pipeline was launched.
        """
        try:
            prefs_result = await db.execute(
                select(UserPreferences).where(UserPreferences.user_id == user_id)
            )
            prefs = prefs_result.scalar_one_or_none()
            min_score = prefs.min_match_score if prefs else settings.default_min_match_score

            # Create PipelineRun record
            pipeline_run = PipelineRun(
                user_id=user_id,
                triggered_by="chat_agent",
                status=AgentStatusEnum.PENDING,
            )
            db.add(pipeline_run)
            await db.flush()
            await db.refresh(pipeline_run)

            # Dispatch Celery task (fire-and-forget)
            from worker.tasks.pipeline_tasks import run_search_pipeline
            run_search_pipeline.delay(
                str(user_id),
                str(pipeline_run.id),
                role,
                location,
                min_score,
            )

            logger.info(
                f"[DrRousseauTool] Launched pipeline {pipeline_run.id} "
                f"for user {user_id}: role={role!r}, location={location!r}"
            )

            return (
                f"🚀 Pipeline lancé pour **{role}** à **{location}**.\n"
                f"Pipeline ID : `{pipeline_run.id}`\n\n"
                "La recherche tourne en arrière-plan (LinkedIn + Indeed + WTTJ). "
                "Les résultats apparaîtront dans ton dashboard dans 2 à 5 minutes. "
                "Utilise `get_dashboard_stats` pour suivre la progression."
            )

        except Exception as e:
            logger.error(f"[DrRousseauTool] search_new_jobs error: {e}", exc_info=True)
            return f"❌ Erreur lors du lancement du pipeline: {e}"

    return [analyze_job_url, generate_application_docs, get_dashboard_stats, search_new_jobs]
