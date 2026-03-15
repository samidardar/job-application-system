"""
ClaudePageAnalyzer — reads stripped page HTML and returns structured analysis.

Given the HTML of a job application page, Claude identifies:
  - What type of page it is (login, registration, application form, captcha…)
  - Which platform it belongs to (Greenhouse, Lever, Workday…)
  - All form fields with their selector hints and pre-filled values
  - Whether the page can be auto-processed or needs human intervention

Usage:
    analyzer = ClaudePageAnalyzer()
    analysis = await analyzer.analyze(html, user_profile, user_info)
"""
import logging
import re
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class FieldInfo(BaseModel):
    label: str
    selector_hint: str     # CSS selector hint (Claude's best guess from HTML context)
    field_type: str        # text | email | password | file | select | textarea | checkbox | radio
    required: bool
    suggested_value: str   # Pre-filled value from user profile


class PageAnalysis(BaseModel):
    page_type: str         # login | registration | application_form | captcha |
                           # email_verification | success | already_applied | unknown
    platform: str          # greenhouse | lever | smartrecruiters | workday | taleo |
                           # wttj | francetravail | linkedin | indeed | custom
    fields: list[FieldInfo]
    submit_hint: str       # Text on the submit/next button
    needs_account: bool
    can_auto_proceed: bool  # False if CAPTCHA, phone verification, or enterprise SSO detected
    next_action: str       # fill_and_submit | create_account | login |
                           # mark_manual | already_done | handle_verification
    manual_reason: str     # Human-readable reason why manual intervention is needed (if any)
    is_multi_step: bool    # True if the form has multiple steps/pages


def _strip_html(html: str) -> str:
    """Remove scripts, styles, and most tags; keep text + input attributes for analysis."""
    # Remove script and style blocks entirely
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Keep input/button/select/textarea tags (with attributes) but strip others
    cleaned = re.sub(r"<(?!/?(?:input|button|select|textarea|label|form|a\s)[^>]*>)[^>]+>", " ", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class ClaudePageAnalyzer:
    """Analyzes a job application page using Claude to determine next automation steps."""

    async def analyze(
        self,
        html: str,
        user_profile: dict,
        user_info: dict,
        job_url: str = "",
    ) -> PageAnalysis:
        """
        Analyze a page and return structured automation instructions.

        Args:
            html: Raw page HTML (will be stripped before sending to Claude)
            user_profile: User's profile dict (skills, experience, contact info)
            user_info: {first_name, last_name, email}
            job_url: The URL being analyzed (for platform detection)

        Returns:
            PageAnalysis with all fields needed to drive automation
        """
        from app.services.claude_service import get_claude_service

        stripped = _strip_html(html)[:8000]  # Claude context limit

        # Build a compact profile summary for Claude to use in field suggestions
        profile_summary = self._build_profile_summary(user_profile, user_info)

        system = """Tu es un expert en automatisation de formulaires web pour des candidatures d'emploi.
Analyse le HTML d'une page de candidature et retourne une analyse structurée JSON.

Identifie:
1. Le type de page: login | registration | application_form | captcha | email_verification | success | already_applied | unknown
2. La plateforme: greenhouse | lever | smartrecruiters | workday | taleo | wttj | francetravail | linkedin | indeed | custom
3. Tous les champs de formulaire visibles avec:
   - label: étiquette du champ
   - selector_hint: sélecteur CSS le plus précis possible (input[name=...], #id, [data-field=...])
   - field_type: text | email | password | file | select | textarea | checkbox | radio
   - required: vrai/faux
   - suggested_value: valeur pré-remplie depuis le profil candidat fourni
4. Le texte du bouton de soumission/suivant
5. Si le formulaire nécessite création de compte
6. Si l'automatisation peut continuer (False si CAPTCHA, vérification téléphone, SSO entreprise)
7. L'action suivante recommandée

Pour les mots de passe: utilise "DERIVED_PASSWORD" comme suggested_value (sera remplacé programmatiquement).
Pour les fichiers CV: utilise "CV_PDF_PATH".
Pour les lettres de motivation: utilise "LDM_PDF_PATH".

Sois précis sur les sélecteurs CSS — utilise name, id, type, placeholder quand disponibles."""

        user_msg = f"""## URL analysée
{job_url}

## HTML de la page (extrait, nettoyé)
{stripped}

## Profil candidat
{profile_summary}

## Instruction
Analyse cette page et retourne une PageAnalysis JSON structurée. Si tu vois des champs de formulaire,
pré-remplis suggested_value avec les données du profil quand possible."""

        try:
            claude = get_claude_service()
            result, _, _ = await claude.complete_structured(
                system=system,
                user=user_msg,
                output_schema=PageAnalysis,
                max_tokens=2000,
            )
            logger.info(
                f"[page_analyzer] {job_url} → type={result.page_type} "
                f"platform={result.platform} action={result.next_action} "
                f"fields={len(result.fields)}"
            )
            return result
        except Exception as e:
            logger.error(f"[page_analyzer] Analysis failed: {e}")
            # Conservative fallback: mark as needing manual review
            return PageAnalysis(
                page_type="unknown",
                platform=self._detect_platform_from_url(job_url),
                fields=[],
                submit_hint="",
                needs_account=True,
                can_auto_proceed=False,
                next_action="mark_manual",
                manual_reason=f"Page analysis failed: {e}",
                is_multi_step=False,
            )

    def _build_profile_summary(self, profile: dict, user_info: dict) -> str:
        """Build a compact profile summary for Claude's field suggestions."""
        first = user_info.get("first_name", "")
        last = user_info.get("last_name", "")
        email = user_info.get("email", "")
        phone = profile.get("phone", "")
        ville = profile.get("ville", "Paris")
        linkedin = profile.get("linkedin_url", "")
        github = profile.get("github_url", "")
        portfolio = profile.get("portfolio_url", "")

        skills_tech = profile.get("skills_technical") or []
        skills_str = ", ".join(skills_tech[:10]) if skills_tech else ""

        education = profile.get("education") or []
        edu_str = ""
        if education:
            edu = education[0] if isinstance(education[0], dict) else {}
            edu_str = f"{edu.get('degree', '')} — {edu.get('school', '')} ({edu.get('year', '')})"

        experience = profile.get("experience") or []
        exp_str = ""
        if experience:
            exp = experience[0] if isinstance(experience[0], dict) else {}
            exp_str = f"{exp.get('title', '')} @ {exp.get('company', '')} ({exp.get('duration', '')})"

        return f"""Prénom: {first}
Nom: {last}
Email: {email}
Téléphone: {phone}
Ville: {ville}
LinkedIn: {linkedin}
GitHub: {github}
Portfolio: {portfolio}
Compétences: {skills_str}
Formation: {edu_str}
Expérience récente: {exp_str}"""

    @staticmethod
    def _detect_platform_from_url(url: str) -> str:
        """Quick heuristic platform detection from URL without Claude."""
        url_lower = url.lower()
        if "greenhouse.io" in url_lower or "boards.greenhouse" in url_lower:
            return "greenhouse"
        if "lever.co" in url_lower or "jobs.lever" in url_lower:
            return "lever"
        if "smartrecruiters" in url_lower:
            return "smartrecruiters"
        if "myworkdayjobs" in url_lower or "workday.com" in url_lower:
            return "workday"
        if "taleo" in url_lower:
            return "taleo"
        if "welcometothejungle" in url_lower or "wttj" in url_lower:
            return "wttj"
        if "francetravail" in url_lower or "pole-emploi" in url_lower:
            return "francetravail"
        if "linkedin.com" in url_lower:
            return "linkedin"
        if "indeed.com" in url_lower:
            return "indeed"
        return "custom"
