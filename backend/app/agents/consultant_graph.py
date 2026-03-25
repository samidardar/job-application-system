"""
Dr. Rousseau — AI Career Consultant for the French job market.

LangGraph ReAct agent powered by Gemini 2.5 Flash with real tool-calling.

Tools available to Dr. Rousseau:
  1. scrape_job_url         — fetch and analyse any job posting URL
  2. get_user_profile       — load the authenticated user's complete profile
  3. get_career_recommendations — generate live cert/project recs from profile
  4. generate_cv_and_ldm    — trigger CV + cover letter generation for a job

Tool args marked with InjectedToolArg are injected server-side from
RunnableConfig.configurable["user_id"] — the LLM never sees or guesses them.

Graph topology:  START → agent (ReAct loop) → END
"""
import json
import logging
import uuid
from typing import Annotated

from langchain_core.messages import SystemMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.prebuilt import InjectedToolArg

from app.config import settings

logger = logging.getLogger(__name__)


# ─── Dr. Rousseau System Prompt ─────────────────────────────────────────────

DR_ROUSSEAU_SYSTEM_PROMPT = """Vous êtes le Dr. Rousseau, consultant en carrière de niveau PhD avec 15 ans d'expérience sur le marché de l'emploi français. Vous avez personnellement accompagné plus de 2 000 étudiants et jeunes actifs vers des alternances, stages et CDI dans des entreprises telles que Thales, Capgemini, BNP Paribas, Decathlon, Renault, LVMH et des start-ups deeptech. Vous connaissez intimement les processus RH français, les ATS utilisés, et les attentes non-dites des recruteurs.

═══════════════════════════════════════════════════════
OUTILS À VOTRE DISPOSITION
═══════════════════════════════════════════════════════

Vous avez accès à des outils puissants. Utilisez-les de manière proactive :

• **get_user_profile** — Toujours appeler EN PREMIER pour personnaliser chaque réponse avec le vrai profil de l'utilisateur (formation, expériences, compétences, projets, certifications). Ne supposez JAMAIS le profil de quelqu'un.

• **scrape_job_url** — Quand l'utilisateur partage une URL d'offre d'emploi, utilisez cet outil pour en extraire le contenu complet avant d'analyser ou de conseiller.

• **get_career_recommendations** — Pour générer des recommandations de certifications et projets RÉELLES et PERSONNALISÉES selon le profil et domaine de l'utilisateur. Appelez cet outil quand l'utilisateur demande quoi améliorer, quels projets faire, ou quelles certifications obtenir. NE JAMAIS donner des recommandations génériques sans cet outil.

• **generate_cv_and_ldm** — Quand l'utilisateur veut postuler à un poste spécifique (via URL ou description), utilisez cet outil pour générer automatiquement un CV ATS-optimisé + lettre de motivation VOUS-MOI-NOUS personnalisée.

═══════════════════════════════════════════════════════
DOMAINES D'EXPERTISE PRÉCIS
═══════════════════════════════════════════════════════

ALTERNANCE (contrat d'apprentissage & contrat de professionnalisation)
• Différences légales : contrat d'apprentissage (via CFA, rémunération par âge selon barème légal) vs contrat de professionnalisation (plus flexible, ouvert aux demandeurs d'emploi)
• Calendrier stratégique : pic des recrutements janvier–avril pour la rentrée de septembre ; ne jamais attendre juin pour commencer
• Rythme école/entreprise : 1 semaine école / 3 semaines entreprise, 2j/3j, etc.
• OPCO et financement : l'employeur ne "perd pas d'argent" avec un alternant
• Plateformes dédiées : La Bonne Alternance, Alternance.emploi.gouv.fr, ANASUP, Indeed, LinkedIn
• Rémunération 2024 : barème officiel par tranche d'âge (18 ans: 27% SMIC, 21 ans: 53%, 26 ans+: 100%)

STAGE (convention obligatoire)
• Gratification légale 2024 : 4,35 €/h — obligatoire au-delà de 2 mois
• Durée maximale : 6 mois (même entreprise, même année académique)
• Droits du stagiaire : tickets-restaurant, remboursement 50% transport, congés proportionnels
• Convention de stage : tripartite (étudiant + école + entreprise) — à anticiper 3–4 semaines

CDI / CDD
• Période d'essai : 2 mois employé, 4 mois cadre/ingénieur
• Négociation salariale : jamais le premier à donner un chiffre, fourchette +10–15%

OPTIMISATION ATS
• Mots-clés exacts de l'offre (8–12 max), jamais de synonymes
• Format PDF une colonne, police standard (Calibri, Arial)
• Sections : Expériences professionnelles, Compétences, Formation, Langues

LETTRE DE MOTIVATION — structure VOUS-MOI-NOUS
• VOUS : Ce que l'entreprise cherche (3–4 éléments précis)
• MOI : Ce que le candidat apporte (preuve, chiffre, réalisation)
• NOUS : La synergie — pourquoi cette entreprise spécifiquement
• 280–320 mots maximum
• Mots INTERDITS : dynamique, motivé, passionné par, je me permets de

═══════════════════════════════════════════════════════
STYLE DE COMMUNICATION
═══════════════════════════════════════════════════════

• Autoritaire mais empathique — ultra-concret, immédiatement actionnable
• Direct : pas de remplissage générique, des faits, des chiffres, des exemples
• Terminez TOUJOURS par "**Prochaine étape concrète**" avec UNE action précise dans les 24–48h
• Si vous donnez une note (CV, LDM) : note sur 10 + 2 points d'amélioration les plus impactants
• Adaptez la langue à celle de l'utilisateur (français si en français, anglais si en anglais)

═══════════════════════════════════════════════════════
ÉTHIQUE ET LIMITES
═══════════════════════════════════════════════════════
• Jamais conseiller de mentir sur un CV ou une expérience
• Si vous ne connaissez pas une grille salariale précise, orientez vers APEC, Glassdoor, LinkedIn Salary
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def scrape_job_url(url: str) -> str:
    """
    Fetch and analyse the content of any job posting URL.
    Use this when the user shares a job URL so you can read the full offer
    before giving tailored advice or generating documents.

    Args:
        url: The job posting URL to fetch (LinkedIn, Indeed, WTTJ, company site, etc.)

    Returns:
        JSON string with: title, company, location, description, application_url
    """
    try:
        from app.services.scrapling_scraper import scrape_job_page
        result = await scrape_job_page(url)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[tool:scrape_job_url] error: {e}")
        return json.dumps({"error": str(e), "url": url})


@tool
async def get_user_profile(
    user_id: Annotated[str, InjectedToolArg],
) -> str:
    """
    Load the authenticated user's complete career profile from the database.
    Always call this first to personalise your advice with real data.

    Returns:
        JSON string with: full_name, education, experience, skills, certifications,
        projects, languages, target_roles, contract_types
    """
    try:
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.user import User, UserProfile, UserPreferences

        uid = uuid.UUID(user_id)
        async with AsyncSessionLocal() as db:
            user_result = await db.execute(select(User).where(User.id == uid))
            user = user_result.scalar_one_or_none()
            if not user:
                return json.dumps({"error": "User not found"})

            profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == uid))
            profile = profile_result.scalar_one_or_none()

            prefs_result = await db.execute(select(UserPreferences).where(UserPreferences.user_id == uid))
            prefs = prefs_result.scalar_one_or_none()

            data: dict = {
                "full_name": user.full_name,
                "email": user.email,
                "education": profile.education if profile else [],
                "experience": profile.experience if profile else [],
                "skills_technical": profile.skills_technical if profile else [],
                "skills_soft": profile.skills_soft if profile else [],
                "certifications": profile.certifications if profile else [],
                "projects": profile.projects if profile else [],
                "languages": profile.languages if profile else [],
                "ville": profile.ville if profile else None,
                "linkedin_url": profile.linkedin_url if profile else None,
                "github_url": profile.github_url if profile else None,
                "portfolio_url": profile.portfolio_url if profile else None,
                "target_roles": prefs.target_roles if prefs else [],
                "contract_types": prefs.contract_types if prefs else [],
                "preferred_locations": prefs.preferred_locations if prefs else [],
                "cv_summary": (profile.cv_text_content or "")[:1000] if profile else "",
            }
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.error(f"[tool:get_user_profile] error: {e}")
        return json.dumps({"error": str(e)})


@tool
async def get_career_recommendations(
    domain: str,
    contract_type: str,
    current_skills: str,
    user_id: Annotated[str, InjectedToolArg],
) -> str:
    """
    Generate personalised career recommendations: certifications to obtain and
    projects to build, based on the user's actual profile and target domain.
    Uses Claude to generate REAL, up-to-date recommendations — no mock data.

    Args:
        domain: Target career domain (e.g. "Data Science", "DevOps", "Finance", "RH")
        contract_type: "alternance", "stage", or "cdi"
        current_skills: Comma-separated list of skills the user already has

    Returns:
        JSON with: certifications (list), projects (list), reasoning
    """
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        prompt = f"""Tu es un expert en développement de carrière pour le marché français.

Profil de l'utilisateur :
- Domaine cible : {domain}
- Type de contrat recherché : {contract_type}
- Compétences actuelles : {current_skills}

Génère des recommandations CONCRÈTES et RÉELLES pour maximiser les chances de l'utilisateur :

1. **Certifications** (5 max) : certifications reconnues par les recruteurs en 2024-2025 dans ce domaine.
   Pour chaque certification : nom exact, organisme, durée approximative, coût indicatif, lien officiel si connu.

2. **Projets à réaliser** (5 max) : projets concrets que l'utilisateur devrait construire et mettre sur GitHub.
   Pour chaque projet : titre, description courte, technologies à utiliser, impact sur le profil, difficulté (débutant/intermédiaire/avancé).

3. **Raisonnement** : Pourquoi ces recommandations pour CE profil spécifique ?

Réponds en JSON valide avec cette structure exacte :
{{
  "certifications": [
    {{
      "name": "...",
      "organisme": "...",
      "duration": "...",
      "cost": "...",
      "url": "...",
      "priority": "haute|moyenne|faible",
      "why": "..."
    }}
  ],
  "projects": [
    {{
      "title": "...",
      "description": "...",
      "technologies": ["..."],
      "impact": "...",
      "difficulty": "débutant|intermédiaire|avancé",
      "why": "..."
    }}
  ],
  "reasoning": "..."
}}"""

        message = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text if message.content else "{}"

        # Validate JSON
        try:
            parsed = json.loads(content)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            # Extract JSON block if wrapped in markdown
            import re
            match = re.search(r"\{[\s\S]+\}", content)
            if match:
                return match.group(0)
            return content

    except Exception as e:
        logger.error(f"[tool:get_career_recommendations] error: {e}")
        return json.dumps({"error": str(e), "certifications": [], "projects": []})


@tool
async def generate_cv_and_ldm(
    job_url: str,
    job_title: str,
    company_name: str,
    job_description: str,
    user_id: Annotated[str, InjectedToolArg],
) -> str:
    """
    Generate a tailored CV (ATS-optimized) and cover letter (VOUS-MOI-NOUS)
    for a specific job offer using the user's real profile data.

    Args:
        job_url: URL of the job posting (used to track the application)
        job_title: Title of the position
        company_name: Name of the hiring company
        job_description: Full text of the job description

    Returns:
        JSON with: cv_download_url, ldm_download_url, ats_score_estimate,
        keywords_injected, changes_summary
    """
    try:
        import anthropic
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.user import User, UserProfile

        uid = uuid.UUID(user_id)
        async with AsyncSessionLocal() as db:
            user_result = await db.execute(select(User).where(User.id == uid))
            user = user_result.scalar_one_or_none()
            profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == uid))
            profile = profile_result.scalar_one_or_none()

        if not user or not profile:
            return json.dumps({"error": "User profile not found. Please upload your CV first."})

        cv_text = profile.cv_text_content or ""
        if not cv_text:
            return json.dumps({
                "error": "No CV found in your profile. Please upload your CV first via /cv/upload.",
                "cv_download_url": None,
                "ldm_download_url": None,
            })

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        prompt = f"""Tu es un expert en optimisation de candidatures pour le marché français.

PROFIL DU CANDIDAT :
Nom : {user.full_name}
CV actuel :
{cv_text[:3000]}

OFFRE D'EMPLOI :
Titre : {job_title}
Entreprise : {company_name}
Description :
{job_description[:3000]}

Génère en JSON :
1. Un **CV optimisé ATS** (HTML complet, WeasyPrint-ready) — reprend le CV original, adapte les formulations pour matcher les mots-clés de l'offre, structure en une colonne.
2. Une **lettre de motivation VOUS-MOI-NOUS** de 280-320 mots (HTML + texte brut).

Structure VOUS-MOI-NOUS :
- VOUS : Ce que {company_name} cherche (3 éléments précis de l'offre)
- MOI : Ce que {user.full_name} apporte (preuves concrètes du CV)
- NOUS : La synergie unique entre le candidat et l'entreprise

JSON attendu :
{{
  "cv_html": "<!DOCTYPE html>...",
  "ldm_html": "<p>...",
  "ldm_text": "...",
  "ats_score_estimate": 0-100,
  "keywords_injected": ["..."],
  "changes_summary": ["..."]
}}"""

        message = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text if message.content else "{}"

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{[\s\S]+\}", content)
            result = json.loads(match.group(0)) if match else {}

        # Generate PDFs if we got HTML
        from app.services.pdf_generator import generate_pdf
        from app.config import settings as cfg
        import os

        output: dict = {
            "ats_score_estimate": result.get("ats_score_estimate"),
            "keywords_injected": result.get("keywords_injected", []),
            "changes_summary": result.get("changes_summary", []),
            "cv_download_url": None,
            "ldm_download_url": None,
        }

        storage = cfg.storage_path
        os.makedirs(storage, exist_ok=True)

        if result.get("cv_html"):
            cv_path = os.path.join(storage, f"cv_{uid}_{uuid.uuid4().hex[:8]}.pdf")
            await generate_pdf(result["cv_html"], cv_path)
            output["cv_download_url"] = f"/api/v1/documents/download?path={cv_path}"

        if result.get("ldm_html"):
            ldm_path = os.path.join(storage, f"ldm_{uid}_{uuid.uuid4().hex[:8]}.pdf")
            await generate_pdf(result["ldm_html"], ldm_path)
            output["ldm_download_url"] = f"/api/v1/documents/download?path={ldm_path}"

        return json.dumps(output, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"[tool:generate_cv_and_ldm] error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


# ─── Tool registry ────────────────────────────────────────────────────────────

CONSULTANT_TOOLS = [scrape_job_url, get_user_profile, get_career_recommendations, generate_cv_and_ldm]


# ─── LangGraph ReAct Agent ────────────────────────────────────────────────────

_consultant_graph = None


def _build_consultant_graph():
    """Build and compile the Dr. Rousseau ReAct LangGraph agent."""
    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Get one at https://aistudio.google.com/app/apikey and add it to .env"
        )

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-preview-04-17",
        google_api_key=settings.gemini_api_key,
        temperature=0.72,
        max_tokens=2048,
        streaming=True,
        safety_settings={
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_ONLY_HIGH",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_ONLY_HIGH",
        },
    )

    # Bind tools to the LLM
    llm_with_tools = llm.bind_tools(CONSULTANT_TOOLS)

    def agent_node(state: MessagesState, config: RunnableConfig) -> dict:
        """Core ReAct node: prepend system prompt and call Gemini with tools."""
        system = SystemMessage(content=DR_ROUSSEAU_SYSTEM_PROMPT)
        messages_with_system: list[BaseMessage] = [system] + list(state["messages"])
        response = llm_with_tools.invoke(messages_with_system, config)
        return {"messages": [response]}

    # Tool node: executes tool calls, injects user_id from config.configurable
    tool_node = ToolNode(CONSULTANT_TOOLS)

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.add_edge(START, "agent")
    # tools_condition: route to "tools" if LLM made tool calls, else END
    graph.add_conditional_edges("agent", tools_condition)
    # After tools execute, go back to agent for next reasoning step
    graph.add_edge("tools", "agent")

    return graph.compile()


def get_consultant_graph():
    """Lazy singleton — built on first call to avoid startup crash if key is missing."""
    global _consultant_graph
    if _consultant_graph is None:
        _consultant_graph = _build_consultant_graph()
    return _consultant_graph
