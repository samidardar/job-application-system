"""
Document Generation node — VOUS-MOI-NOUS framework.

For each matched job, generates in parallel:
  1. CV tailored — ATS-optimized, VOUS-MOI-NOUS analysis guides tailoring
  2. LDM (lettre de motivation) — 280-320 words, VOUS-MOI-NOUS structure,
     zero clichés, concrete proof points, France market style

VOUS-MOI-NOUS:
  VOUS = Ce que l'entreprise cherche (analyse de l'offre)
  MOI  = Ce que le candidat apporte (profil réel, jamais inventé)
  NOUS = La synergie → angle d'attaque unique de la candidature
"""
import asyncio
import logging
import uuid
from pathlib import Path
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select

from app.agents.graph.state import PipelineState, JobDict
from app.database import AsyncSessionLocal
from app.models.job import Job, JobStatusEnum
from app.models.document import Document, DocumentTypeEnum
from app.models.user import UserProfile, User
from app.services.claude_service import get_claude_service
from app.services.pdf_generator import generate_pdf
from app.config import settings

logger = logging.getLogger(__name__)

# ─── Pydantic output schemas ────────────────────────────────────────────────

class CVOutput(BaseModel):
    cv_html: str                   # Full HTML document, WeasyPrint-ready
    keywords_injected: list[str]   # ATS keywords naturally integrated
    changes_summary: list[str]     # What was tailored (max 4 bullet points)
    ats_score_estimate: int        # Estimated ATS score 0-100


class LDMOutput(BaseModel):
    lettre_html: str               # HTML with <p> tags
    lettre_text: str               # Plain text version
    word_count: int                # Must be 280-320
    keywords_used: list[str]       # ATS keywords used in the letter
    hook_sentence: str             # First sentence (the accroche)


# ─── CV Generation ──────────────────────────────────────────────────────────

CV_SYSTEM = """Tu es un expert ATS et CV coach spécialisé dans le marché tech français (alternance, stage, CDI).
Tu utilises le framework VOUS-MOI-NOUS pour créer des CVs parfaitement ciblés.

VOUS-MOI-NOUS:
• VOUS  = Analyse de ce que l'entreprise cherche réellement (mots-clés ATS, missions, stack)
• MOI   = Ce que le candidat apporte (profil réel uniquement, jamais d'invention)
• NOUS  = La synergie → les éléments du profil qui répondent exactement aux besoins

RÈGLES ABSOLUES:
1. Ne jamais inventer compétence, expérience, diplôme ou certification absents du profil
2. Réordonner les compétences: les plus pertinentes pour CE poste en premier
3. Reformuler 2-3 bullets d'expérience avec la terminologie exacte de l'offre
4. La section Résumé/Profil (3-4 phrases) doit être 100% tailored pour cette entreprise et ce poste
5. Injecter les mots-clés ATS critiques naturellement (pas de keyword stuffing)
6. HTML propre compatible WeasyPrint: pas de tables pour la mise en page, utiliser divs/flex
7. Quantifier les résultats quand c'est possible (chiffres, %, durées)"""


def _build_cv_prompt(job: JobDict, profile: dict, user_info: dict) -> str:
    research = job.get("company_research") or {}
    education = profile.get("education") or []
    experience = profile.get("experience") or []
    skills_tech = profile.get("skills_technical") or []
    skills_soft = profile.get("skills_soft") or []
    languages = profile.get("languages") or []
    certifications = profile.get("certifications") or []
    projects = profile.get("projects") or []

    edu_str = "\n".join(
        f"  - {e.get('degree', '')} — {e.get('school', '')} ({e.get('year', '') or e.get('end_year', '')})"
        for e in (education[:3] if isinstance(education, list) else [])
    )
    exp_str = "\n".join(
        f"  - {e.get('title', '')} @ {e.get('company', '')} ({e.get('duration', '') or e.get('period', '')}): {e.get('description', '')[:200]}"
        for e in (experience[:4] if isinstance(experience, list) else [])
    )
    proj_str = "\n".join(
        f"  - {p.get('name', '')}: {p.get('description', '')[:150]} [{p.get('tech', '')}]"
        for p in (projects[:3] if isinstance(projects, list) else [])
    )

    cv_template = profile.get("cv_html_template") or ""
    if cv_template and len(cv_template) > 200:
        base_section = f"""## CV DE BASE (HTML — modifier, ne pas copier tel quel)
{cv_template[:6000]}"""
    else:
        base_section = f"""## DONNÉES PROFIL (générer un CV complet depuis ces données)
Prénom: {user_info.get('first_name', '')}
Nom: {user_info.get('last_name', '')}
Email: {user_info.get('email', '')}
Ville: {profile.get('ville', 'Paris')}
Téléphone: {profile.get('phone', '')}
LinkedIn: {profile.get('linkedin_url', '')}
GitHub: {profile.get('github_url', '')}
Portfolio: {profile.get('portfolio_url', '')}

Formation:
{edu_str or '  (non précisée)'}

Expériences:
{exp_str or '  (aucune)'}

Compétences techniques: {', '.join(skills_tech)}
Compétences soft: {', '.join(skills_soft[:5])}
Langages: {', '.join(str(l) for l in languages)}
Certifications: {', '.join(str(c) for c in certifications)}
Projets:
{proj_str or '  (aucun)'}"""

    return f"""## ANALYSE VOUS-MOI-NOUS

### VOUS — Ce que {job.get('company', '')} cherche
Poste: {job.get('title', '')} | Contrat: {job.get('job_type') or 'non précisé'} | Lieu: {job.get('location', '')}
Type entreprise: {research.get('company_type', 'unknown')} | Secteur: {research.get('sector', '')}
Stack technique mentionnée: {', '.join(research.get('tech_stack', []))}
Culture / valeurs: {', '.join(research.get('culture_signals', []))}
Mots-clés ATS critiques: {', '.join(job.get('ats_keywords', []))}
Missions clés: {', '.join(research.get('key_projects', []))}

### MOI — Ce que {user_info.get('first_name', 'le candidat')} apporte
{base_section}

### NOUS — La synergie
Points de match: {', '.join(job.get('match_reasons', []))}
Hints de tailoring: {job.get('tailoring_hints', '')}
Lacunes à minimiser: {', '.join(job.get('skill_gaps', []))}

---

## MISSION
Génère un CV HTML complet, professionnel, ATS-optimisé pour cette candidature spécifique.

## TEMPLATE HTML OBLIGATOIRE
Le CV doit utiliser exactement cette structure CSS professionnelle:
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
  @page {{ margin: 12mm 14mm; size: A4; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Arial', 'Helvetica', sans-serif; font-size: 10.5pt; color: #1a1a2e; line-height: 1.45; }}
  .header {{ background: #0f2c4a; color: white; padding: 16px 20px 14px; }}
  .header h1 {{ font-size: 20pt; font-weight: 700; letter-spacing: 0.03em; margin-bottom: 3px; }}
  .header .job-title {{ font-size: 11pt; color: #93c5fd; margin-bottom: 10px; font-style: italic; }}
  .contact-bar {{ display: flex; flex-wrap: wrap; gap: 14px; font-size: 9pt; color: #cbd5e1; }}
  .contact-bar span::before {{ margin-right: 4px; }}
  .body {{ display: flex; gap: 0; }}
  .left-col {{ width: 32%; background: #f8fafc; padding: 14px 12px; border-right: 1px solid #e2e8f0; }}
  .right-col {{ flex: 1; padding: 14px 16px; }}
  h2 {{ font-size: 9.5pt; text-transform: uppercase; letter-spacing: 0.09em; color: #0f2c4a; margin-bottom: 7px; padding-bottom: 3px; border-bottom: 2px solid #2563eb; font-weight: 700; }}
  .section {{ margin-bottom: 13px; }}
  .skill-group {{ margin-bottom: 6px; }}
  .skill-group .label {{ font-weight: 600; font-size: 9pt; color: #374151; margin-bottom: 3px; }}
  .skill-tags {{ display: flex; flex-wrap: wrap; gap: 3px; }}
  .tag {{ background: #dbeafe; color: #1e40af; padding: 1px 6px; border-radius: 3px; font-size: 8.5pt; font-weight: 500; }}
  .tag.primary {{ background: #1e40af; color: white; }}
  .exp-item {{ margin-bottom: 10px; }}
  .exp-header {{ margin-bottom: 3px; }}
  .exp-title {{ font-weight: 700; font-size: 10.5pt; }}
  .exp-company {{ color: #2563eb; font-weight: 600; font-size: 10pt; }}
  .exp-meta {{ color: #6b7280; font-size: 9pt; margin-bottom: 4px; }}
  .exp-bullets {{ padding-left: 12px; }}
  .exp-bullets li {{ font-size: 10pt; color: #374151; margin-bottom: 2px; list-style: disc; }}
  .summary {{ font-size: 10.5pt; color: #334155; line-height: 1.55; font-style: italic; margin-bottom: 13px; padding: 8px 10px; background: #eff6ff; border-left: 3px solid #2563eb; border-radius: 2px; }}
  .edu-item {{ margin-bottom: 7px; }}
  .edu-degree {{ font-weight: 700; font-size: 10pt; }}
  .edu-school {{ color: #2563eb; font-size: 9.5pt; }}
  .edu-date {{ color: #6b7280; font-size: 9pt; }}
  .lang-item {{ font-size: 10pt; margin-bottom: 3px; }}
  .proj-item {{ margin-bottom: 6px; }}
  .proj-name {{ font-weight: 600; font-size: 10pt; }}
  .proj-desc {{ font-size: 9.5pt; color: #374151; }}
</style>
</head>
<body>
[REMPLIR ICI avec les données du candidat, tailored pour ce poste]
</body>
</html>"""


# ─── LDM Generation ─────────────────────────────────────────────────────────

LDM_SYSTEM = """Tu es un expert en rédaction de lettres de motivation pour le marché tech français.
Tu maîtrises le framework VOUS-MOI-NOUS et le style direct, professionnel, sans clichés.

STRUCTURE OBLIGATOIRE (4 paragraphes, 280-320 mots TOTAL):

§1 — ACCROCHE (≈50 mots)
Commence par un fait concret, précis sur {company} ou son secteur qui prouve que tu les connais.
Relie-le naturellement à ta trajectoire. Frappe fort dès la première phrase.

§2 — VOUS (≈80 mots)
Montre que tu as compris ce qu'ils cherchent vraiment. Reprends les termes exacts de leur offre.
Démontre ta compréhension des enjeux métier / tech de l'entreprise.

§3 — MOI (≈120 mots)
2-3 preuves concrètes et chiffrées de tes compétences directement pertinentes pour CE poste.
Chaque preuve = action + résultat mesurable. Intègre naturellement les mots-clés ATS.
Exemple: "J'ai développé [X] qui a permis [Y] (+Z%)" ou "En [contexte], j'ai [action], ce qui a [résultat]"

§4 — NOUS + CTA (≈70 mots)
La valeur unique que TU apportes à EUX. Pourquoi cette candidature a du sens pour les deux parties.
Appel à l'action direct et professionnel.

INTERDITS ABSOLUS (zéro tolérance):
"dynamique", "motivé(e)", "passionné(e) par", "je me permets de", "dans l'attente de votre retour",
"avec mes cordiales salutations", "force de proposition", "rigoureux(se)", "curieux(se)",
"sérieux(se)", "autonome", "polyvalent(e)", "proactif", "bonne communication"

COMMENCER PAR: Le corps de la lettre directement (PAS "Madame, Monsieur")
FORMAT: <p> pour chaque paragraphe, <strong> sur les termes techniques clés
LONGUEUR: 280-320 mots EXACTEMENT (compter soigneusement)"""


def _build_ldm_prompt(job: JobDict, profile: dict, user_info: dict) -> str:
    research = job.get("company_research") or {}
    education = profile.get("education") or []
    experience = profile.get("experience") or []
    skills = profile.get("skills_technical") or []

    current_edu = (education[0] if isinstance(education, list) and education else {})
    recent_exp = (experience[0] if isinstance(experience, list) and experience else {})

    relevant_skills = [s for s in skills if any(
        k.lower() in s.lower() for k in job.get("ats_keywords", [])
    )][:6]
    if not relevant_skills:
        relevant_skills = skills[:6]

    contract_ctx = {
        "alternance": f"alternance (rythme école/entreprise) au sein de {job.get('company', '')}",
        "stage": f"stage de {job.get('company', '')}",
        "cdi": f"poste en CDI chez {job.get('company', '')}",
        "cdd": f"poste en CDD chez {job.get('company', '')}",
    }.get(job.get("job_type") or "", f"poste chez {job.get('company', '')}")

    return f"""## DONNÉES CANDIDAT
Prénom: {user_info.get('first_name', '')}
Nom: {user_info.get('last_name', '')}
Formation: {current_edu.get('degree', '')} — {current_edu.get('school', '')} ({current_edu.get('year', '')})
Expérience récente: {recent_exp.get('title', '')} @ {recent_exp.get('company', '')} — {recent_exp.get('description', '')[:300]}
Compétences clés pour ce poste: {', '.join(relevant_skills)}
Tous les projets: {', '.join(str(p.get('name', '')) for p in (profile.get('projects') or [])[:3])}

## POSTE CIBLÉ
Entreprise: {job.get('company', '')}
Poste: {job.get('title', '')}
Contrat: {contract_ctx}
Lieu: {job.get('location', '')}
Mots-clés ATS à intégrer: {', '.join(job.get('ats_keywords', [])[:10])}
Ce qu'ils cherchent vraiment: {job.get('tailoring_hints', '')}
Points de match forts: {', '.join(job.get('match_reasons', []))}

## INTELLIGENCE ENTREPRISE
Type: {research.get('company_type', 'unknown')} | Stage: {research.get('company_stage', 'unknown')}
Secteur: {research.get('sector', '')}
Stack: {', '.join(research.get('tech_stack', []))}
Culture: {', '.join(research.get('culture_signals', []))}
Idée d'accroche: {research.get('hook_idea', '')}
Projets/missions mentionnés: {', '.join(research.get('key_projects', []))}
Contexte alternance/stage: {research.get('contract_context', '')}

## CONSIGNE
Rédige la lettre de motivation. Suis EXACTEMENT le framework VOUS-MOI-NOUS décrit en système.
Compte les mots soigneusement: 280-320 mots dans lettre_text.
Pour lettre_html: chaque paragraphe dans <p>...</p>, termes techniques en <strong>."""


# ─── Node ────────────────────────────────────────────────────────────────────

async def _generate_for_job(
    job: JobDict,
    profile: dict,
    user_info: dict,
    user_id: uuid.UUID,
) -> JobDict | None:
    """Generate CV + LDM for one job. Returns enriched job dict or None on failure."""
    job_id_str = job.get("id", "")
    if not job_id_str:
        return None

    job_id = uuid.UUID(job_id_str)
    company_safe = (job.get("company") or "unknown").replace(" ", "_")[:30]

    claude = get_claude_service()

    # ── CV ──
    try:
        cv_prompt = _build_cv_prompt(job, profile, user_info)
        cv_result, cv_pt, cv_ct = await claude.complete_structured(
            system=CV_SYSTEM,
            user=cv_prompt,
            output_schema=CVOutput,
            max_tokens=6000,
        )
        cv_file = f"cv_{company_safe}_{job_id}.pdf"
        cv_path = str(Path(settings.storage_path) / "documents" / str(user_id) / cv_file)
        cv_size = await generate_pdf(cv_result.cv_html, cv_path)

        cv_doc = Document(
            user_id=user_id,
            job_id=job_id,
            document_type=DocumentTypeEnum.CV_TAILORED,
            content_html=cv_result.cv_html,
            content_text="",
            ats_keywords_injected=cv_result.keywords_injected,
            file_path=cv_path,
            file_name=cv_file,
            file_size_bytes=cv_size,
            generation_prompt_tokens=cv_pt,
            generation_completion_tokens=cv_ct,
        )
    except Exception as e:
        logger.error(f"[docs] CV generation failed for {job.get('company')}: {e}")
        return None

    # ── LDM ──
    try:
        ldm_prompt = _build_ldm_prompt(job, profile, user_info)
        ldm_result, ldm_pt, ldm_ct = await claude.complete_structured(
            system=LDM_SYSTEM.replace("{company}", job.get("company", "l'entreprise")),
            user=ldm_prompt,
            output_schema=LDMOutput,
            max_tokens=3000,
        )
        full_ldm_html = _wrap_ldm_html(ldm_result.lettre_html, user_info, job)
        ldm_file = f"ldm_{company_safe}_{job_id}.pdf"
        ldm_path = str(Path(settings.storage_path) / "documents" / str(user_id) / ldm_file)
        ldm_size = await generate_pdf(full_ldm_html, ldm_path)

        ldm_doc = Document(
            user_id=user_id,
            job_id=job_id,
            document_type=DocumentTypeEnum.COVER_LETTER,
            content_html=full_ldm_html,
            content_text=ldm_result.lettre_text,
            ats_keywords_injected=ldm_result.keywords_used,
            file_path=ldm_path,
            file_name=ldm_file,
            file_size_bytes=ldm_size,
            generation_prompt_tokens=ldm_pt,
            generation_completion_tokens=ldm_ct,
        )
    except Exception as e:
        logger.error(f"[docs] LDM generation failed for {job.get('company')}: {e}")
        return None

    # ── Save to DB ──
    async with AsyncSessionLocal() as db:
        try:
            db.add(cv_doc)
            db.add(ldm_doc)
            await db.flush()
            await db.refresh(cv_doc)
            await db.refresh(ldm_doc)

            db_result = await db.execute(select(Job).where(Job.id == job_id))
            db_job = db_result.scalar_one_or_none()
            if db_job:
                db_job.status = JobStatusEnum.LETTER_GENERATED
            await db.commit()
        except Exception as db_err:
            await db.rollback()
            # Clean up orphaned PDF files so storage doesn't leak
            for path in [cv_doc.file_path, ldm_doc.file_path]:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
            logger.error(f"[docs] DB save failed for {job.get('company')}: {db_err}")
            return None

    enriched = dict(job)  # type: ignore
    enriched["cv_doc_id"] = str(cv_doc.id)
    enriched["ldm_doc_id"] = str(ldm_doc.id)
    enriched["cv_html"] = cv_result.cv_html
    enriched["ldm_text"] = ldm_result.lettre_text
    enriched["retry_count"] = 0
    logger.info(f"[docs] ✓ {job.get('title')} @ {job.get('company')} — CV+LDM générés")
    return enriched  # type: ignore


def _wrap_ldm_html(body: str, user_info: dict, job: JobDict) -> str:
    today = datetime.utcnow().strftime("%d %B %Y")
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
  @page {{ margin: 20mm 22mm; size: A4; }}
  body {{ font-family: 'Arial', 'Helvetica', sans-serif; font-size: 11pt; color: #1a1a1a; line-height: 1.6; }}
  .sender {{ font-weight: 700; font-size: 13pt; margin-bottom: 2px; }}
  .meta {{ color: #64748b; font-size: 10pt; margin-bottom: 24px; }}
  .date {{ text-align: right; color: #64748b; margin-bottom: 18px; }}
  .recipient {{ font-weight: 600; margin-bottom: 20px; }}
  .subject {{ font-weight: 700; border-bottom: 1px solid #cbd5e1; padding-bottom: 8px; margin-bottom: 22px; }}
  p {{ margin: 0 0 14px 0; text-align: justify; }}
  strong {{ color: #0f2c4a; }}
  .signature {{ margin-top: 28px; }}
</style>
</head>
<body>
  <div class="sender">{user_info.get('first_name', '')} {user_info.get('last_name', '')}</div>
  <div class="meta">{user_info.get('email', '')}</div>
  <div class="date">{today}</div>
  <div class="recipient">Service Recrutement — {job.get('company', '')}</div>
  <div class="subject">Objet&nbsp;: Candidature — {job.get('title', '')}{' (Alternance)' if job.get('job_type') == 'alternance' else ' (Stage)' if job.get('job_type') == 'stage' else ''}</div>
  {body}
  <div class="signature">
    <p>{user_info.get('first_name', '')} {user_info.get('last_name', '')}</p>
  </div>
</body>
</html>"""


async def node_generate_docs(state: PipelineState) -> dict:
    """Generate CV + LDM for all matched jobs in parallel."""
    matched = state.get("matched_jobs", [])
    profile = state.get("user_profile", {})
    user_info = state.get("user_info", {})
    user_id = uuid.UUID(state["user_id"])

    if not matched:
        return {"jobs_ready": [], "docs_generated": 0, "errors": []}

    # Check profile has enough data
    if not profile.get("skills_technical") and not profile.get("cv_html_template"):
        return {
            "jobs_ready": [],
            "docs_generated": 0,
            "errors": ["Profile incomplet: uploadez un CV ou renseignez vos compétences"],
        }

    logger.info(f"[generate_docs] Generating CV+LDM for {len(matched)} jobs")

    semaphore = asyncio.Semaphore(4)  # Conservative: WeasyPrint is CPU-heavy

    async def gen_with_sem(job: JobDict) -> JobDict | None:
        async with semaphore:
            return await _generate_for_job(job, profile, user_info, user_id)

    results = await asyncio.gather(
        *[gen_with_sem(j) for j in matched],
        return_exceptions=True,
    )

    jobs_with_docs: list[JobDict] = []
    errors: list[str] = []
    for r in results:
        if isinstance(r, dict) and r:
            jobs_with_docs.append(r)  # type: ignore
        elif isinstance(r, Exception):
            errors.append(str(r))

    logger.info(f"[generate_docs] {len(jobs_with_docs)} docs générés")
    return {
        "matched_jobs": jobs_with_docs,  # update with enriched data
        "docs_generated": len(jobs_with_docs),
        "errors": errors,
    }
