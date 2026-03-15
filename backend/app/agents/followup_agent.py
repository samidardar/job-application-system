import logging
import uuid
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.agents.base_agent import BaseAgent
from app.models.application import Application, ApplicationStatusEnum
from app.models.job import Job
from app.models.document import Document, DocumentTypeEnum
from app.models.agent_run import AgentStatusEnum
from app.models.user import User, UserProfile
from app.services.claude_service import get_claude_service
from app.config import settings

logger = logging.getLogger(__name__)


class FollowUpEmailOutput(BaseModel):
    subject: str
    body_html: str
    body_text: str
    word_count: int


class FollowUpAgent(BaseAgent):
    name = "followup"

    async def run(self, application_id: uuid.UUID) -> bool:
        """Send a follow-up email for an application. Returns True on success."""
        await self._start_run(input_data={"application_id": str(application_id)})

        try:
            app_result = await self.db.execute(
                select(Application).where(Application.id == application_id)
            )
            application = app_result.scalar_one_or_none()
            if not application:
                await self._finish_run(AgentStatusEnum.FAILED, error_message="Application not found")
                return False

            # Don't follow up if already responded
            if application.status in [
                ApplicationStatusEnum.INTERVIEW_SCHEDULED,
                ApplicationStatusEnum.OFFER_RECEIVED,
                ApplicationStatusEnum.REJECTED,
            ]:
                await self._finish_run(AgentStatusEnum.SKIPPED, output_data={"reason": "already_responded"})
                return False

            # Get job and user info
            job_result = await self.db.execute(select(Job).where(Job.id == application.job_id))
            job = job_result.scalar_one_or_none()

            user_result = await self.db.execute(select(User).where(User.id == self.user_id))
            user = user_result.scalar_one_or_none()

            # Get cover letter hook sentence
            cover_letter_hook = ""
            if application.cover_letter_document_id:
                letter_result = await self.db.execute(
                    select(Document).where(Document.id == application.cover_letter_document_id)
                )
                letter_doc = letter_result.scalar_one_or_none()
                if letter_doc and letter_doc.content_text:
                    cover_letter_hook = letter_doc.content_text[:200]

            # Generate follow-up email
            system = """Tu es un assistant professionnel qui rédige des emails de relance courtois et efficaces pour le marché de l'emploi français.
Le ton est professionnel, bref et sans insistance. Maximum 100 mots pour le corps du message."""

            submitted_date = application.submitted_at.strftime("%d %B %Y") if application.submitted_at else "récemment"

            user_msg = f"""## CONTEXTE
Candidature envoyée le: {submitted_date}
Poste: {job.title if job else 'Poste'}
Entreprise: {job.company if job else 'Entreprise'}
Candidat(e): {user.first_name} {user.last_name}
Lettre de motivation (extrait): {cover_letter_hook}

## TÂCHE
Rédige un email de relance de 80-100 mots maximum. Il doit:
- Rappeler la candidature de façon concise
- Manifester l'intérêt toujours présent
- Demander poliment l'état d'avancement
- Ne pas être désespéré ni agressif
- Être en français, ton professionnel"""

            claude = get_claude_service()
            result, pt, ct = await claude.complete_structured(
                system=system,
                user=user_msg,
                output_schema=FollowUpEmailOutput,
                max_tokens=1000,
            )

            # Try to send email
            email_sent = False
            if settings.smtp_user and settings.smtp_password:
                try:
                    email_sent = self._send_email(
                        to_email=f"recrutement@{job.company.lower().replace(' ', '')}.fr",  # Best guess
                        subject=result.subject,
                        body_html=result.body_html,
                        body_text=result.body_text,
                        from_name=f"{user.first_name} {user.last_name}",
                    )
                except Exception as e:
                    logger.warning(f"Email sending failed: {e}")

            # Update application
            now = datetime.utcnow()
            application.follow_up_sent_at = now
            timeline = application.timeline or []
            timeline.append({
                "event": "Follow-up sent" if email_sent else "Follow-up drafted",
                "timestamp": now.isoformat(),
                "details": {"subject": result.subject, "sent": email_sent},
            })
            application.timeline = timeline
            await self.db.flush()

            await self._finish_run(
                AgentStatusEnum.SUCCESS,
                output_data={"email_sent": email_sent, "subject": result.subject},
                claude_tokens_used=pt + ct,
            )
            return True

        except Exception as e:
            logger.error(f"Follow-up failed for application {application_id}: {e}", exc_info=True)
            await self._finish_run(AgentStatusEnum.FAILED, error_message=str(e))
            return False

    def _send_email(
        self, to_email: str, subject: str, body_html: str, body_text: str, from_name: str
    ) -> bool:
        """Send email via SMTP."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{from_name} <{settings.smtp_user}>"
            msg["To"] = to_email

            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            return False
