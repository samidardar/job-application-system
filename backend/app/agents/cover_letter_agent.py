import logging
import uuid
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.agents.base_agent import BaseAgent
from app.models.job import Job, JobStatusEnum
from app.models.document import Document, DocumentTypeEnum
from app.models.agent_run import AgentStatusEnum
from app.models.user import UserProfile, User
from app.services.claude_service import get_claude_service
from app.services.pdf_generator import generate_pdf
from app.config import settings

logger = logging.getLogger(__name__)


class CoverLetterOutput(BaseModel):
    lettre_html: str
    lettre_text: str
    word_count: int
    keywords_used: list[str]
    hook_sentence: str


class CoverLetterAgent(BaseAgent):
    name = "cover_letter"

    async def run(self, job_id: uuid.UUID) -> uuid.UUID | None:
        """Generate a personalized French cover letter for a job. Returns document_id."""
        await self._start_run(job_id=job_id, input_data={"job_id": str(job_id)})

        try:
            job_result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if not job:
                await self._finish_run(AgentStatusEnum.FAILED, error_message="Job not found")
                return None

            user_result = await self.db.execute(select(User).where(User.id == self.user_id))
            user = user_result.scalar_one_or_none()

            profile_result = await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == self.user_id)
            )
            profile = profile_result.scalar_one_or_none()

            if not profile or not user:
                await self._finish_run(AgentStatusEnum.SKIPPED, error_message="No profile found")
                return None

            # Build top skills relevant to this job
            all_skills = profile.skills_technical or []
            keywords = job.ats_keywords_critical or []
            relevant_skills = [s for s in all_skills if any(k.lower() in s.lower() for k in keywords)][:5]
            if not relevant_skills:
                relevant_skills = all_skills[:5]

            # Most recent experience
            experience = profile.experience or []
            recent_exp = experience[0] if experience else {}

            # Current education
            education = profile.education or []
            current_edu = education[0] if education else {}

            system = """Tu es un expert en rédaction de lettres de motivation en français pour le marché de l'emploi français, spécialisé dans les profils tech, data science et IA.
Tu écris des lettres percutantes, authentiques, sans clichés, avec un style direct et professionnel.
Chaque lettre doit être unique et démontrer une compréhension réelle du poste et de l'entreprise.

INTERDITS ABSOLUS: "dynamique", "motivé(e)", "passionné(e) par", "je me permets de", "dans l'attente de votre retour", "avec mes cordiales salutations".
La lettre ne doit pas commencer par "Madame, Monsieur" mais directement par le corps.
Structure: accroche forte (1 phrase) → pourquoi ce poste + cette entreprise → compétences clés avec exemples concrets → conclusion avec appel à l'action."""

            user_msg = f"""## PROFIL CANDIDAT
Prénom: {user.first_name}
Nom: {user.last_name}
Formation actuelle: {current_edu.get('degree', '')} — {current_edu.get('school', '')}
Compétences clés pour ce poste: {', '.join(relevant_skills)}
Expérience récente: {recent_exp.get('title', '')} chez {recent_exp.get('company', '')}
Ville: {profile.ville or 'Paris'}

## OFFRE D'EMPLOI
Poste: {job.title}
Entreprise: {job.company}
Type de contrat: {job.job_type.value if job.job_type else 'non précisé'}
Description: {(job.description_raw or '')[:2000]}
Ce qu'ils cherchent vraiment: {job.tailoring_hints or 'Voir description du poste'}

## CONSIGNES
- Longueur: 280-320 mots exactement
- Intègre naturellement ces mots-clés: {', '.join(keywords[:8])}
- Termine par une formule de politesse professionnelle (ex: "Je reste disponible pour un entretien à votre convenance.")
- Le HTML doit utiliser <p> pour les paragraphes et <strong> sur les termes techniques clés"""

            claude = get_claude_service()
            result, pt, ct = await claude.complete_structured(
                system=system,
                user=user_msg,
                output_schema=CoverLetterOutput,
                max_tokens=3000,
            )

            # Wrap in full HTML document for PDF
            full_html = self._wrap_html(result.lettre_html, user, job)

            # Generate PDF
            file_name = f"lettre_{job.company.replace(' ', '_')}_{job_id}.pdf"
            file_path = str(Path(settings.storage_path) / "documents" / str(self.user_id) / file_name)
            file_size = await generate_pdf(full_html, file_path)

            # Save document
            doc = Document(
                user_id=self.user_id,
                job_id=job_id,
                document_type=DocumentTypeEnum.COVER_LETTER,
                content_html=full_html,
                content_text=result.lettre_text,
                ats_keywords_injected=result.keywords_used,
                file_path=file_path,
                file_name=file_name,
                file_size_bytes=file_size,
                generation_prompt_tokens=pt,
                generation_completion_tokens=ct,
            )
            self.db.add(doc)
            await self.db.flush()

            job.status = JobStatusEnum.LETTER_GENERATED
            await self.db.flush()

            await self._finish_run(
                AgentStatusEnum.SUCCESS,
                output_data={
                    "document_id": str(doc.id),
                    "word_count": result.word_count,
                    "hook": result.hook_sentence,
                },
                claude_tokens_used=pt + ct,
            )

            return doc.id

        except Exception as e:
            logger.error(f"Cover letter generation failed for job {job_id}: {e}", exc_info=True)
            await self._finish_run(AgentStatusEnum.FAILED, error_message=str(e))
            return None

    def _wrap_html(self, body_html: str, user: User, job: Job) -> str:
        from datetime import date
        today = date.today().strftime("%d %B %Y")
        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 40px 50px; color: #1a1a1a; font-size: 11pt; line-height: 1.6; }}
  .header {{ margin-bottom: 30px; }}
  .sender {{ font-weight: 700; font-size: 13pt; }}
  .meta {{ color: #475569; font-size: 10pt; margin-top: 4px; }}
  .date {{ text-align: right; color: #64748b; margin-bottom: 20px; }}
  .recipient {{ margin-bottom: 25px; font-weight: 600; }}
  .subject {{ font-weight: 700; margin-bottom: 20px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }}
  p {{ margin: 0 0 12px 0; }}
  strong {{ color: #1e3a5f; }}
</style>
</head>
<body>
  <div class="header">
    <div class="sender">{user.first_name} {user.last_name}</div>
  </div>
  <div class="date">{today}</div>
  <div class="recipient">Service Recrutement — {job.company}</div>
  <div class="subject">Objet : Candidature — {job.title}</div>
  {body_html}
</body>
</html>"""
