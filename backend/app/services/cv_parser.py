import io
import logging
import re
from typing import Any
import pdfplumber
from app.services.claude_service import get_claude_service
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ParsedCVSchema(BaseModel):
    raw_text: str
    full_name: str | None
    email: str | None
    phone: str | None
    linkedin_url: str | None
    github_url: str | None
    ville: str | None
    skills_technical: list[str]
    skills_soft: list[str]
    education: list[dict]
    experience: list[dict]
    languages: list[dict]
    certifications: list[str]
    summary: str | None


class CVParser:
    async def parse(self, pdf_bytes: bytes) -> dict[str, Any]:
        """Extract structured data from a PDF CV."""
        # Step 1: Extract raw text with pdfplumber
        raw_text = self._extract_text(pdf_bytes)

        if not raw_text.strip():
            return {"raw_text": "", "error": "Could not extract text from PDF"}

        # Step 2: Use Claude to structure the extracted text
        claude = get_claude_service()
        system = """Tu es un expert en analyse de CV. Extrais les informations structurées du texte de CV fourni.
Sois précis et exhaustif. Si une information n'est pas présente, utilise null ou une liste vide.
Pour l'expérience professionnelle, extrais: title, company, location, start_date, end_date, duration, bullets (liste de réalisations).
Pour l'éducation, extrais: degree, school, location, year_start, year_end, gpa (si mentionné).
Pour les langues: lang, level (ex: "Français - Natif", "Anglais - C1")."""

        user = f"""Voici le texte extrait d'un CV. Extrais toutes les informations structurées.

TEXTE DU CV:
{raw_text[:6000]}"""

        try:
            parsed, _, _ = await claude.complete_structured(
                system=system,
                user=user,
                output_schema=ParsedCVSchema,
                max_tokens=3000,
            )
            result = parsed.model_dump()
            result["raw_text"] = raw_text
            return result
        except Exception as e:
            logger.error(f"Claude CV parsing failed: {e}")
            # Fallback to basic extraction
            return self._basic_extract(raw_text)

    def _extract_text(self, pdf_bytes: bytes) -> str:
        """Extract raw text from PDF using pdfplumber."""
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
                return "\n\n".join(pages_text)
        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
            return ""

    def _basic_extract(self, raw_text: str) -> dict[str, Any]:
        """Basic regex-based fallback extraction."""
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', raw_text)
        phone_match = re.search(r'(?:\+33|0)[1-9](?:[\s.-]?\d{2}){4}', raw_text)
        linkedin_match = re.search(r'linkedin\.com/in/[\w-]+', raw_text)
        github_match = re.search(r'github\.com/[\w-]+', raw_text)

        return {
            "raw_text": raw_text,
            "email": email_match.group(0) if email_match else None,
            "phone": phone_match.group(0) if phone_match else None,
            "linkedin_url": f"https://{linkedin_match.group(0)}" if linkedin_match else None,
            "github_url": f"https://{github_match.group(0)}" if github_match else None,
            "full_name": None,
            "ville": None,
            "skills_technical": [],
            "skills_soft": [],
            "education": [],
            "experience": [],
            "languages": [],
            "certifications": [],
            "summary": None,
        }

    def generate_html_template(self, parsed_data: dict, user: Any) -> str:
        """Generate an HTML CV template from parsed data."""
        first_name = getattr(user, "first_name", "")
        last_name = getattr(user, "last_name", "")
        full_name = parsed_data.get("full_name") or f"{first_name} {last_name}"
        email = parsed_data.get("email", "")
        phone = parsed_data.get("phone", "")
        linkedin = parsed_data.get("linkedin_url", "")
        github = parsed_data.get("github_url", "")
        ville = parsed_data.get("ville", "")
        summary = parsed_data.get("summary", "")

        skills_technical = parsed_data.get("skills_technical", [])
        skills_soft = parsed_data.get("skills_soft", [])
        education = parsed_data.get("education", [])
        experience = parsed_data.get("experience", [])
        languages = parsed_data.get("languages", [])
        certifications = parsed_data.get("certifications", [])

        skills_html = ", ".join(skills_technical) if skills_technical else ""
        soft_html = ", ".join(skills_soft) if skills_soft else ""

        exp_html = ""
        for exp in experience:
            bullets = exp.get("bullets", [])
            bullets_html = "".join(f"<li>{b}</li>" for b in bullets)
            exp_html += f"""
            <div class="experience-item">
                <div class="exp-header">
                    <strong>{exp.get('title', '')}</strong> — {exp.get('company', '')}
                    <span class="date">{exp.get('start_date', '')} – {exp.get('end_date', 'Présent')}</span>
                </div>
                <ul>{bullets_html}</ul>
            </div>"""

        edu_html = ""
        for edu in education:
            edu_html += f"""
            <div class="education-item">
                <strong>{edu.get('degree', '')}</strong> — {edu.get('school', '')}
                <span class="date">{edu.get('year_start', '')} – {edu.get('year_end', '')}</span>
            </div>"""

        lang_html = " | ".join(
            f"{l.get('lang', '')} ({l.get('level', '')})" for l in languages
        ) if languages else ""

        cert_html = ", ".join(certifications) if certifications else ""

        contact_parts = [p for p in [email, phone, ville, linkedin, github] if p]
        contact_html = " | ".join(contact_parts)

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 20px 40px; color: #1a1a1a; font-size: 10pt; line-height: 1.4; }}
  h1 {{ font-size: 22pt; font-weight: 700; margin: 0 0 4px; color: #0f172a; }}
  .contact {{ color: #475569; font-size: 9pt; margin-bottom: 16px; }}
  h2 {{ font-size: 12pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1.5px solid #0f172a; margin: 16px 0 8px; padding-bottom: 2px; color: #0f172a; }}
  .summary {{ color: #374151; margin-bottom: 8px; }}
  .skills {{ color: #1e293b; }}
  .experience-item, .education-item {{ margin-bottom: 10px; }}
  .exp-header {{ display: flex; justify-content: space-between; }}
  .date {{ color: #64748b; font-size: 9pt; }}
  ul {{ margin: 4px 0 0 0; padding-left: 18px; }}
  li {{ margin-bottom: 2px; }}
</style>
</head>
<body>
  <h1>{full_name}</h1>
  <div class="contact">{contact_html}</div>
  {'<h2>Profil</h2><p class="summary">' + summary + '</p>' if summary else ''}
  {'<h2>Compétences techniques</h2><p class="skills">' + skills_html + '</p>' if skills_html else ''}
  {'<h2>Compétences transversales</h2><p>' + soft_html + '</p>' if soft_html else ''}
  {'<h2>Expérience professionnelle</h2>' + exp_html if exp_html else ''}
  {'<h2>Formation</h2>' + edu_html if edu_html else ''}
  {'<h2>Langues</h2><p>' + lang_html + '</p>' if lang_html else ''}
  {'<h2>Certifications</h2><p>' + cert_html + '</p>' if cert_html else ''}
</body>
</html>"""
