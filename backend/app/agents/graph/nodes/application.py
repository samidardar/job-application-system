"""
Application submission node.

Full automated flow per job:
  1. Navigate to application URL
  2. ClaudePageAnalyzer detects page type + platform
  3. Dispatch based on page_type:
     - success / already_applied → mark APPLIED, done
     - captcha / email_verification / phone_verification → PENDING_MANUAL
     - lever / matcha (email-only apply) → send email directly
     - login → try saved session; if none → PENDING_MANUAL with login link
     - registration → fill form → save session → proceed to application
     - application_form → fill fields, upload CV+LDM → screenshot → APPLIED
     - unknown → PENDING_MANUAL
  4. Multi-step forms: loop up to 10 iterations (fill → click Next → analyze again)

Respects auto_apply_enabled flag. If disabled, marks jobs PENDING for manual review.
"""
import asyncio
import ipaddress
import logging
import re
import socket
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select

from app.agents.graph.state import PipelineState, JobDict
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.application import Application, ApplicationStatusEnum
from app.models.job import Job, JobStatusEnum
from app.services.browser_session import BrowserSessionManager

logger = logging.getLogger(__name__)

# Screenshot base directory — absolute path derived from settings to work inside Docker
_SCREENSHOT_DIR = Path(settings.storage_path) / "screenshots"

# ── SSRF Protection ───────────────────────────────────────────────────────────
_BLOCKED_DOMAINS = {
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",           # AWS/Azure metadata
}
_ALLOWED_SCHEMES = {"http", "https"}


def _is_safe_url(url: str) -> tuple[bool, str]:
    """
    Returns (True, "") if the URL is safe to navigate to.
    Returns (False, reason) if it's a potential SSRF vector.
    Blocks: non-http(s) schemes, private/loopback IPs, metadata endpoints.
    """
    if not url:
        return False, "Empty URL"
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL"

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False, f"Disallowed scheme: {parsed.scheme}"

    hostname = parsed.hostname or ""
    if not hostname:
        return False, "No hostname"

    if hostname.lower() in _BLOCKED_DOMAINS:
        return False, f"Blocked hostname: {hostname}"

    # Resolve IP and check for private/loopback ranges
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast:
            return False, f"Private/internal IP blocked: {hostname}"
    except ValueError:
        # It's a domain name — resolve it to check the IP
        # 2-second timeout prevents DoS via slow/stalling DNS servers
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(2)
        try:
            ip_str = socket.gethostbyname(hostname)
            addr = ipaddress.ip_address(ip_str)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return False, f"Domain resolves to private IP: {hostname} → {ip_str}"
        except OSError:
            pass  # DNS failure — allow (will fail at page.goto)
        finally:
            socket.setdefaulttimeout(old_timeout)

    return True, ""

# Platforms where email apply is preferred (no account needed)
_EMAIL_ONLY_PLATFORMS = {"lever", "bonne_alternance"}

# Platforms that always need manual review (enterprise SSO / complex auth)
_ALWAYS_MANUAL_PLATFORMS = {"workday", "taleo"}

# Max iterations for multi-step form navigation
_MAX_FORM_STEPS = 10


# ── Helpers ──────────────────────────────────────────────────────────────────


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


async def _screenshot(page, job_id: str) -> str | None:
    """Take a screenshot and save it. Returns the path or None on failure."""
    try:
        path = _SCREENSHOT_DIR / f"{job_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path), full_page=False)
        return str(path)
    except Exception as e:
        logger.warning(f"[apply] Screenshot failed: {e}")
        return None


async def _get_page_html(page) -> str:
    """Wait for network idle then return page HTML."""
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass  # Proceed even if timeout
    return await page.content()


async def _send_lever_email(job: JobDict, user_info: dict, cv_path: str, ldm_path: str) -> tuple[bool, str]:
    """
    Lever and some Bonne Alternance postings accept direct email applications.
    Sends via SMTP using the contact email extracted from the job listing.
    """
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        contact_email = job.get("contact_email") or job.get("application_email")
        if not contact_email:
            return False, "no_contact_email"

        msg = MIMEMultipart()
        msg["From"] = user_info.get("email", "")
        msg["To"] = contact_email
        msg["Subject"] = (
            f"Candidature — {job.get('title', 'Poste')} | "
            f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}"
        )

        body = job.get("ldm_text") or (
            f"Madame, Monsieur,\n\n"
            f"Je vous adresse ma candidature pour le poste de {job.get('title')}.\n\n"
            f"Veuillez trouver ci-joint mon CV et ma lettre de motivation.\n\n"
            f"Cordialement,\n{user_info.get('first_name', '')} {user_info.get('last_name', '')}"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Attach CV
        if cv_path and Path(cv_path).exists():
            with open(cv_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                cv_name = f"CV_{user_info.get('last_name', 'candidat').upper()}.pdf"
                part.add_header("Content-Disposition", f'attachment; filename="{cv_name}"')
                msg.attach(part)

        # Attach LDM
        if ldm_path and Path(ldm_path).exists():
            with open(ldm_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                ldm_name = f"LDM_{user_info.get('last_name', 'candidat').upper()}.pdf"
                part.add_header("Content-Disposition", f'attachment; filename="{ldm_name}"')
                msg.attach(part)

        smtp_host = getattr(settings, "smtp_host", "smtp.gmail.com")
        smtp_port = getattr(settings, "smtp_port", 587)
        smtp_user = getattr(settings, "smtp_user", "")
        smtp_pass = getattr(settings, "smtp_password", "")

        if not smtp_user:
            return False, "smtp_not_configured"

        # Run blocking SMTP in thread executor — must not block the async event loop
        raw_msg = msg.as_string()
        def _send():
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, contact_email, raw_msg)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send)

        logger.info(f"[apply] Email envoyé à {contact_email} pour {job.get('company')}")
        return True, "email_sent"
    except Exception as e:
        logger.error(f"[apply] Email send failed: {e}")
        return False, str(e)


async def _fill_application_form(page, analysis, cv_path: str, ldm_path: str) -> bool:
    """
    Fill all form fields from PageAnalysis.fields and click submit.
    Returns True if submission attempted successfully.
    """
    from app.services.page_analyzer import FieldInfo

    filled_any = False
    for field in analysis.fields:
        field: FieldInfo
        selector = field.selector_hint
        value = field.suggested_value

        if not selector or not value:
            continue

        try:
            element = page.locator(selector).first
            count = await element.count()
            if not count:
                # Try broader selectors as fallback — strip quotes to prevent CSS injection
                safe_label = re.sub(r"['\"]", "", field.label)[:20]
                safe_label_lower = re.sub(r"['\"\s]", "", field.label.lower())[:20]
                for alt in [
                    f"[placeholder*='{safe_label}']",
                    f"[aria-label*='{safe_label}']",
                    f"[name*='{safe_label_lower}']",
                ]:
                    alt_el = page.locator(alt).first
                    if await alt_el.count():
                        element = alt_el
                        break
                else:
                    logger.debug(f"[apply] Field not found: {field.label} ({selector})")
                    continue

            if field.field_type == "file":
                # CV or LDM upload
                target_path = None
                label_lower = field.label.lower()
                if value == "CV_PDF_PATH" or "cv" in label_lower or "resume" in label_lower:
                    target_path = cv_path
                elif value == "LDM_PDF_PATH" or "lettre" in label_lower or "cover" in label_lower:
                    target_path = ldm_path

                if target_path and Path(target_path).exists():
                    await element.set_input_files(target_path)
                    filled_any = True
                    logger.debug(f"[apply] File uploaded: {field.label} → {target_path}")

            elif field.field_type in ("text", "email", "textarea"):
                await element.fill(value)
                filled_any = True

            elif field.field_type == "password":
                # Password is already derived — just fill it
                await element.fill(value)
                filled_any = True

            elif field.field_type == "select":
                try:
                    await element.select_option(label=value)
                except Exception:
                    await element.select_option(value=value)
                filled_any = True

            elif field.field_type == "checkbox" and field.required:
                if not await element.is_checked():
                    await element.check()
                filled_any = True

        except Exception as e:
            logger.debug(f"[apply] Could not fill field '{field.label}': {e}")

    if not filled_any:
        return False

    # Click submit/next button
    if analysis.submit_hint:
        try:
            # Strip quotes to prevent CSS selector injection
            safe_hint = analysis.submit_hint.replace("'", "").replace('"', "")[:60]
            submit_btn = page.locator(
                f"button:has-text('{safe_hint}'), "
                f"input[value='{safe_hint}']"
            ).first
            if await submit_btn.count():
                await submit_btn.click()
                await page.wait_for_timeout(2000)
                return True
        except Exception as e:
            logger.debug(f"[apply] Submit button click failed: {e}")

    # Generic submit fallback
    for hint in ["submit", "postuler", "apply", "envoyer", "suivant", "next", "continuer"]:
        try:
            btn = page.locator(f"button:has-text('{hint}'), input[type='submit']").first
            if await btn.count():
                await btn.click()
                await page.wait_for_timeout(2000)
                return True
        except Exception:
            continue

    return False


async def _handle_registration(
    page,
    analysis,
    user_info: dict,
    user_profile: dict,
    domain: str,
    user_id: str,
    cv_path: str,
    ldm_path: str,
) -> tuple[str, str | None]:
    """
    Fill registration form, submit, then check result.
    Returns (result_action, screenshot_path):
      - ("success", screenshot) — registered and can proceed
      - ("email_verification", None) — email sent, need manual check
      - ("failed", None) — registration failed
    """
    from app.services.browser_session import BrowserSessionManager

    # Derive a deterministic password
    derived_pw = BrowserSessionManager.derive_site_password(
        user_info.get("email", ""),
        domain,
        settings.secret_key,
    )

    # Replace "DERIVED_PASSWORD" in field suggestions
    for field in analysis.fields:
        if field.field_type == "password" or field.suggested_value == "DERIVED_PASSWORD":
            field.suggested_value = derived_pw

    success = await _fill_application_form(page, analysis, cv_path, ldm_path)
    if not success:
        return "failed", None

    await page.wait_for_timeout(3000)

    # Check what happened after registration submit
    html_after = await _get_page_html(page)
    html_lower = html_after.lower()

    if any(kw in html_lower for kw in ["vérifiez", "verify your email", "check your email", "confirmation email", "email envoyé"]):
        logger.info(f"[apply] Email verification required after registration at {domain}")
        return "email_verification", None

    if any(kw in html_lower for kw in ["erreur", "error", "invalid", "already exists", "déjà utilisé"]):
        logger.warning(f"[apply] Registration error at {domain}")
        return "failed", None

    # Looks like success — save session
    await BrowserSessionManager.save_context(page.context, user_id, domain)
    return "success", None


# ── Main submission flow ──────────────────────────────────────────────────────


async def _process_one(
    job: JobDict,
    user_id: uuid.UUID,
    user_id_str: str,
    user_info: dict,
    user_profile: dict,
    auto_apply: bool,
) -> tuple[bool, str | None, str]:
    """
    Full application flow for one job.
    Returns (submitted: bool, application_id: str | None, method: str).
    """
    method = _determine_method(job)

    if not auto_apply:
        app_id = await _create_application(
            job, user_id, submitted=False, method=method,
            manual_reason="auto_apply_disabled",
        )
        logger.info(f"[apply] Manual review (auto_apply off): {job.get('title')} @ {job.get('company')}")
        return False, app_id, method

    url = job.get("application_url") or job.get("url") or ""
    if not url:
        app_id = await _create_application(
            job, user_id, submitted=False, method="no_url",
            manual_reason="No application URL found",
        )
        return False, app_id, "no_url"

    # SSRF guard: reject internal/private URLs before launching browser
    safe, ssrf_reason = _is_safe_url(url)
    if not safe:
        logger.warning(f"[apply] SSRF blocked for {job.get('company')}: {ssrf_reason}")
        app_id = await _create_application(
            job, user_id, submitted=False, method=method,
            manual_reason=f"URL rejected by security policy: {ssrf_reason}",
        )
        return False, app_id, method

    # Platform-level overrides
    platform = job.get("platform") or ""
    if any(p in platform for p in _ALWAYS_MANUAL_PLATFORMS):
        app_id = await _create_application(
            job, user_id, submitted=False, method=method,
            manual_reason=f"Platform {platform} requires enterprise SSO",
        )
        return False, app_id, method

    # Email-only platforms (Lever, Bonne Alternance with contact email)
    if any(p in platform for p in _EMAIL_ONLY_PLATFORMS) or method == "lever_email":
        sent, result = await _send_lever_email(
            job, user_info,
            job.get("cv_path") or "",
            job.get("ldm_path") or "",
        )
        if sent:
            app_id = await _create_application(job, user_id, submitted=True, method="email")
            return True, app_id, "email"
        else:
            app_id = await _create_application(
                job, user_id, submitted=False, method="email",
                manual_reason=f"Email send failed: {result}",
            )
            return False, app_id, "email"

    # Playwright-based flow
    domain = _extract_domain(url)
    cv_path = job.get("cv_path") or ""
    ldm_path = job.get("ldm_path") or ""

    try:
        from playwright.async_api import async_playwright
        from app.services.page_analyzer import ClaudePageAnalyzer

        analyzer = ClaudePageAnalyzer()

        async with async_playwright() as pw:
            browser, ctx = await BrowserSessionManager.load_context(pw, user_id_str, domain)
            try:
                page = await ctx.new_page()

                # Add stealth: override navigator.webdriver
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                await page.goto(url, timeout=25000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                screenshot_path = None

                for step in range(_MAX_FORM_STEPS):
                    html = await _get_page_html(page)
                    current_url = page.url
                    analysis = await analyzer.analyze(html, user_profile, user_info, current_url)

                    logger.info(
                        f"[apply] Step {step+1}: {analysis.page_type} / {analysis.platform} / "
                        f"{analysis.next_action} — {job.get('company')}"
                    )

                    # ── Terminal states ──────────────────────────────────────
                    if analysis.page_type in ("success", "already_applied"):
                        screenshot_path = await _screenshot(page, job.get("id", "unknown"))
                        app_id = await _create_application(
                            job, user_id, submitted=True, method=method,
                            screenshot_path=screenshot_path,
                        )
                        return True, app_id, method

                    # ── Cannot auto-proceed ──────────────────────────────────
                    if not analysis.can_auto_proceed:
                        reason = analysis.manual_reason or f"{analysis.page_type} detected"
                        app_id = await _create_application(
                            job, user_id, submitted=False, method=method,
                            manual_reason=reason, manual_url=current_url,
                        )
                        return False, app_id, method

                    if analysis.next_action == "mark_manual":
                        app_id = await _create_application(
                            job, user_id, submitted=False, method=method,
                            manual_reason=analysis.manual_reason or "Automatic analysis could not determine next step",
                            manual_url=current_url,
                        )
                        return False, app_id, method

                    # ── Login page ───────────────────────────────────────────
                    if analysis.page_type == "login" or analysis.next_action == "login":
                        has_session = BrowserSessionManager.has_session(user_id_str, domain)
                        if has_session:
                            # Session was loaded but apparently expired or wrong page
                            logger.info(f"[apply] Session loaded but still seeing login at {domain} — clearing")
                            await BrowserSessionManager.delete_session(user_id_str, domain)

                        app_id = await _create_application(
                            job, user_id, submitted=False, method=method,
                            manual_reason=f"Login required at {domain} — please log in via the setup wizard",
                            manual_url=current_url,
                        )
                        return False, app_id, method

                    # ── Registration page ────────────────────────────────────
                    if analysis.page_type == "registration" or analysis.next_action == "create_account":
                        result, _ = await _handle_registration(
                            page, analysis, user_info, user_profile,
                            domain, user_id_str, cv_path, ldm_path,
                        )
                        if result == "email_verification":
                            app_id = await _create_application(
                                job, user_id, submitted=False, method=method,
                                manual_reason="Email verification required after registration — check your inbox",
                                manual_url=current_url,
                            )
                            return False, app_id, method
                        elif result == "failed":
                            app_id = await _create_application(
                                job, user_id, submitted=False, method=method,
                                manual_reason="Registration failed — please apply manually",
                                manual_url=current_url,
                            )
                            return False, app_id, method
                        # success → loop continues to next step (application form)
                        continue

                    # ── Email verification page ──────────────────────────────
                    if analysis.page_type == "email_verification":
                        app_id = await _create_application(
                            job, user_id, submitted=False, method=method,
                            manual_reason="Email verification required — check your inbox and click the link",
                            manual_url=current_url,
                        )
                        return False, app_id, method

                    # ── Application form ─────────────────────────────────────
                    if analysis.page_type == "application_form" or analysis.next_action == "fill_and_submit":
                        success = await _fill_application_form(page, analysis, cv_path, ldm_path)
                        if not success:
                            # Couldn't fill form — mark manual
                            app_id = await _create_application(
                                job, user_id, submitted=False, method=method,
                                manual_reason="Could not fill application form fields",
                                manual_url=current_url,
                            )
                            return False, app_id, method

                        # Wait and check if multi-step or done
                        await page.wait_for_timeout(3000)

                        if not analysis.is_multi_step:
                            # Single-step → take screenshot and mark applied
                            screenshot_path = await _screenshot(page, job.get("id", "unknown"))
                            app_id = await _create_application(
                                job, user_id, submitted=True, method=method,
                                screenshot_path=screenshot_path,
                            )
                            return True, app_id, method
                        # Multi-step → loop to next step
                        continue

                    # ── Unknown / unhandled ──────────────────────────────────
                    app_id = await _create_application(
                        job, user_id, submitted=False, method=method,
                        manual_reason=f"Unhandled page state: {analysis.page_type}",
                        manual_url=current_url,
                    )
                    return False, app_id, method

                # Exceeded max steps
                app_id = await _create_application(
                    job, user_id, submitted=False, method=method,
                    manual_reason=f"Form exceeded {_MAX_FORM_STEPS} steps — please complete manually",
                    manual_url=url,
                )
                return False, app_id, method

            finally:
                await ctx.close()
                await browser.close()

    except Exception as e:
        logger.error(f"[apply] Playwright error for {job.get('company')}: {e}")
        app_id = await _create_application(
            job, user_id, submitted=False, method=method,
            manual_reason="Browser automation error — please apply manually",
            manual_url=url,
        )
        return False, app_id, method


def _determine_method(job: JobDict) -> str:
    platform = (job.get("platform") or "").lower()
    url = (job.get("application_url") or job.get("url") or "").lower()

    if "linkedin" in platform or "linkedin.com" in url:
        return "linkedin_easy_apply"
    if "indeed" in platform or "indeed.com" in url:
        return "indeed_apply"
    if "francetravail" in platform:
        return "france_travail_redirect"
    if "bonne_alternance" in platform:
        if job.get("contact_email") or job.get("application_email"):
            return "lever_email"
        return "bonne_alternance_form"
    if "lever.co" in url or "jobs.lever.co" in url:
        return "lever_email"
    if "greenhouse.io" in url or "boards.greenhouse" in url:
        return "greenhouse_form"
    if "smartrecruiters" in url:
        return "smartrecruiters_form"
    if "myworkdayjobs" in url or "workday.com" in url:
        return "workday_redirect"
    if "welcometothejungle" in url or "wttj" in url:
        return "wttj_form"
    return "direct_url"


async def _create_application(
    job: JobDict,
    user_id: uuid.UUID,
    submitted: bool,
    method: str,
    screenshot_path: str | None = None,
    manual_reason: str | None = None,
    manual_url: str | None = None,
) -> str | None:
    """Create Application record in DB. Returns application_id or None."""
    if not job.get("id"):
        return None

    job_id_str = job["id"]
    try:
        job_uuid = uuid.UUID(job_id_str)
    except ValueError:
        logger.error(f"[apply] Invalid job ID: {job_id_str}")
        return None

    try:
        async with AsyncSessionLocal() as db:
            # Idempotent: skip if already applied
            existing = await db.execute(
                select(Application).where(
                    Application.user_id == user_id,
                    Application.job_id == job_uuid,
                )
            )
            if existing.scalar_one_or_none():
                return None

            now = datetime.utcnow()
            timeline_event = {
                "event": "submitted" if submitted else "ready_for_review",
                "timestamp": now.isoformat(),
                "details": {
                    "method": method,
                    "qa_grade": job.get("qa_grade"),
                    "match_score": job.get("match_score"),
                },
            }
            if manual_reason:
                timeline_event["details"]["manual_reason"] = manual_reason
            if manual_url:
                timeline_event["details"]["manual_url"] = manual_url

            status = ApplicationStatusEnum.SUBMITTED if submitted else ApplicationStatusEnum.PENDING

            # Determine submission_method label
            submission_method = method
            if not submitted and manual_reason:
                submission_method = "pending_manual"

            app = Application(
                user_id=user_id,
                job_id=job_uuid,
                status=status,
                submitted_at=now if submitted else None,
                submission_method=submission_method,
                submission_screenshot_path=screenshot_path,
                follow_up_due_at=now + timedelta(days=7) if submitted else None,
                timeline=[timeline_event],
            )
            db.add(app)

            # Update job status in DB
            db_result = await db.execute(select(Job).where(Job.id == job_uuid))
            db_job = db_result.scalar_one_or_none()
            if db_job:
                db_job.status = JobStatusEnum.APPLIED if submitted else JobStatusEnum.READY_TO_APPLY

            await db.commit()
            await db.refresh(app)
            return str(app.id)
    except Exception as e:
        logger.error(f"[apply] DB error creating application: {e}")
        return None


# ── LangGraph node ────────────────────────────────────────────────────────────


async def node_submit(state: PipelineState) -> dict:
    """Submit applications for all QA-approved jobs."""
    jobs_ready = state.get("jobs_ready") or []
    prefs = state.get("user_preferences") or {}
    user_id_str = state.get("user_id") or ""
    user_info = state.get("user_info") or {}
    user_profile = state.get("user_profile") or {}
    auto_apply = prefs.get("auto_apply_enabled") or False

    if not jobs_ready:
        return {"applications_submitted": 0, "errors": []}

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        logger.error(f"[submit] Invalid user_id: {user_id_str}")
        return {"applications_submitted": 0, "errors": [f"Invalid user_id: {user_id_str}"]}

    logger.info(
        f"[submit] {len(jobs_ready)} candidatures à traiter "
        f"(auto_apply={'ON' if auto_apply else 'OFF'})"
    )

    semaphore = asyncio.Semaphore(3)

    async def submit_with_sem(job: JobDict) -> tuple[bool, str | None, str]:
        async with semaphore:
            # Random delay to avoid rate-limiting
            await asyncio.sleep(2 + (hash(job.get("id", "")) % 4))
            return await _process_one(
                job, user_uuid, user_id_str, user_info, user_profile, auto_apply
            )

    results = await asyncio.gather(
        *[submit_with_sem(j) for j in jobs_ready],
        return_exceptions=True,
    )

    submitted_count = 0
    errors: list[str] = []
    enriched_jobs: list[JobDict] = []

    for job, result in zip(jobs_ready, results):
        if isinstance(result, tuple):
            submitted, app_id, method = result
            if submitted:
                submitted_count += 1
            enriched = dict(job)
            enriched["application_id"] = app_id
            enriched["submission_method"] = method
            enriched_jobs.append(enriched)  # type: ignore
        elif isinstance(result, Exception):
            errors.append(f"[submit] {job.get('company')}: {result}")
            enriched_jobs.append(job)

    logger.info(
        f"[submit] {submitted_count} soumises automatiquement, "
        f"{len(jobs_ready) - submitted_count} en attente de revue"
    )
    return {
        "jobs_ready": enriched_jobs,
        "applications_submitted": submitted_count,
        "errors": errors,
    }
