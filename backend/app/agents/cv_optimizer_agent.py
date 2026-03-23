"""
CV Optimizer: rewrites only text content inside existing HTML tags.
The user's original CV format, layout, and CSS are never modified.
"""
import logging
import uuid
from pathlib import Path
from sqlalchemy import select
from pydantic import BaseModel
from app.agents.base_agent import BaseAgent
from app.models.job import Job, JobStatusEnum
from app.models.document import Document, DocumentTypeEnum
from app.models.agent_run import AgentStatusEnum
from app.models.user import UserProfile
from app.services.claude_service import get_claude_service
from app.services.pdf_generator import generate_pdf
from app.config import settings

logger = logging.getLogger(__name__)


class CVOptimizerOutput(BaseModel):
    cv_html: str                        # Full HTML with ONLY text rewritten, structure intact
    keywords_injected: list[str]
    sections_modified: list[str]        # Which sections were touched
    ats_score_estimate: int


class CVOptimizerAgent(BaseAgent):
    name = "cv_optimizer"

    async def run(self, job_id: uuid.UUID) -> uuid.UUID | None:
        """Generate a tailored CV for a job preserving original format exactly."""
        await self._start_run(job_id=job_id, input_data={"job_id": str(job_id)})

        try:
            job_result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if not job:
                await self._finish_run(AgentStatusEnum.FAILED, error_message="Job not found")
                return None

            profile_result = await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == self.user_id)
            )
            profile = profile_result.scalar_one_or_none()

            if not profile or not profile.cv_html_template:
                await self._finish_run(AgentStatusEnum.SKIPPED, error_message="No CV template")
                return None

            system = """Tu es un expert ATS et recruteur senior spécialisé tech/data.
Tu reçois le HTML complet du CV original d'un candidat et une offre d'emploi.

RÈGLE ABSOLUE : Tu ne modifies QUE le texte visible. JAMAIS les balises HTML, les attributs,
les classes CSS, les styles inline, ou la structure du document.
Chaque <tag>...</tag> reste intact — seul le contenu textuel entre les balises peut changer.

Ce que tu peux faire :
- Réordonner les listes de compétences pour mettre en avant les plus pertinentes
- Réécrire les bullet points d'expérience avec les mots-clés du poste (vérité uniquement)
- Reformuler le résumé/profil pour matcher le poste
- Injecter les mots-clés ATS critiques naturellement dans le texte existant

Ce que tu ne fais JAMAIS :
- Inventer des expériences, diplômes ou compétences
- Changer le HTML/CSS/structure
- Ajouter de nouvelles sections

Retourne le HTML complet modifié."""

            user_msg = f"""## CV ORIGINAL (HTML COMPLET — préserve exactement cette structure)
{profile.cv_html_template}

## OFFRE D'EMPLOI
Titre: {job.title}
Entreprise: {job.company}
Mots-clés ATS critiques: {', '.join(job.ats_keywords_critical or [])}
Conseils de ciblage: {job.tailoring_hints or ''}
Description (extrait): {(job.description_raw or '')[:2500]}

## INSTRUCTION
Retourne le HTML du CV avec UNIQUEMENT le texte réécrit pour matcher ce poste.
Ne change aucune balise HTML, aucun style, aucune classe."""

            claude = get_claude_service()
            result, pt, ct = await claude.complete_structured(
                system=system,
                user=user_msg,
                output_schema=CVOptimizerOutput,
                max_tokens=8000,
            )

            # Generate PDF with Playwright
            safe_company = "".join(c for c in job.company if c.isalnum() or c in "_ -")[:30]
            file_name = f"cv_ciblé_{safe_company}_{job_id}.pdf"
            file_path = str(
                Path(settings.storage_path) / "documents" / str(self.user_id) / file_name
            )
            file_size = await generate_pdf(result.cv_html, file_path)

            doc = Document(
                user_id=self.user_id,
                job_id=job_id,
                document_type=DocumentTypeEnum.CV_TAILORED,
                content_html=result.cv_html,
                content_text="",
                ats_keywords_injected=result.keywords_injected,
                file_path=file_path,
                file_name=file_name,
                file_size_bytes=file_size,
                generation_prompt_tokens=pt,
                generation_completion_tokens=ct,
            )
            self.db.add(doc)
            await self.db.flush()

            job.status = JobStatusEnum.CV_GENERATED
            await self.db.flush()

            await self._finish_run(
                AgentStatusEnum.SUCCESS,
                output_data={
                    "document_id": str(doc.id),
                    "ats_score": result.ats_score_estimate,
                    "sections_modified": result.sections_modified,
                },
                claude_tokens_used=pt + ct,
            )
            return doc.id

        except Exception as e:
            logger.error(f"CV optimizer failed for job {job_id}: {e}", exc_info=True)
            await self._finish_run(AgentStatusEnum.FAILED, error_message=str(e))
            return None
