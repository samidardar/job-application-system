"""
BrowserSessionManager — Playwright persistent context manager.

Saves/loads cookies and localStorage per user per domain so the user
only needs to log in once to LinkedIn, Indeed, etc. Subsequent pipeline
runs reuse the saved session automatically.

Session files are stored at: storage/browser_states/{user_id}/{domain_safe}.json
"""
import logging
import re
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Base directory for all browser state files (resolved absolute path)
_STATES_DIR = Path("storage/browser_states").resolve()


def _domain_safe(domain: str) -> str:
    """Sanitize domain string for use as a filename (allow only safe chars)."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", domain)
    # Limit length to prevent filesystem issues
    return safe[:100]


def _validate_user_id(user_id: str) -> str:
    """Validate user_id is a canonical UUID string to prevent path traversal."""
    try:
        return str(uuid.UUID(user_id))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid user_id (must be UUID): {user_id!r}")


def state_path(user_id: str, domain: str) -> Path:
    """Returns the path to the Playwright storage state JSON for this user+domain.

    Validates user_id is a UUID and resolves the path to prevent traversal attacks.
    """
    safe_uid = _validate_user_id(user_id)
    safe_dom = _domain_safe(domain)
    path = (_STATES_DIR / safe_uid / f"{safe_dom}.json").resolve()
    # Guard: ensure path stays within _STATES_DIR
    if not str(path).startswith(str(_STATES_DIR)):
        raise ValueError(f"Path traversal detected: {path}")
    return path


class BrowserSessionManager:
    """Manages Playwright persistent browser contexts per user per domain."""

    @staticmethod
    def has_session(user_id: str, domain: str) -> bool:
        """Returns True if a saved session exists for this user+domain."""
        return state_path(user_id, domain).exists()

    @staticmethod
    async def load_context(playwright, user_id: str, domain: str):
        """
        Returns a Playwright BrowserContext.
        If a saved session exists, loads it (cookies + localStorage).
        Otherwise returns a fresh context with stealth settings.
        """
        sp = state_path(user_id, domain)
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
        browser = await playwright.chromium.launch(headless=True, args=launch_args)

        if sp.exists():
            logger.info(f"[browser] Loading saved session for {domain} (user={user_id})")
            try:
                ctx = await browser.new_context(
                    storage_state=str(sp),
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    ),
                    locale="fr-FR",
                    timezone_id="Europe/Paris",
                )
                return browser, ctx
            except Exception as e:
                logger.warning(f"[browser] Failed to load session state ({e}), using fresh context")

        # Fresh context (stealth)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        return browser, ctx

    @staticmethod
    async def save_context(ctx, user_id: str, domain: str) -> str:
        """
        Saves the current browser context state (cookies + localStorage) to disk.
        Returns the path where the state was saved.
        """
        sp = state_path(user_id, domain)
        sp.parent.mkdir(parents=True, exist_ok=True)
        await ctx.storage_state(path=str(sp))
        logger.info(f"[browser] Session saved for {domain} (user={user_id}) → {sp}")
        return str(sp)

    @staticmethod
    async def delete_session(user_id: str, domain: str) -> None:
        """Removes a saved session (e.g. after detecting it's expired)."""
        sp = state_path(user_id, domain)
        if sp.exists():
            sp.unlink()
            logger.info(f"[browser] Deleted session for {domain} (user={user_id})")

    @staticmethod
    def derive_site_password(user_email: str, domain: str, secret: str) -> str:
        """
        Deterministic password derivation for site registrations.
        Uses PBKDF2-HMAC-SHA256 with domain+email as salt for stronger derivation.
        Never stored in plaintext — always re-derived from user_email + domain + SECRET_KEY.

        Output format (16 chars + suffix) always satisfies: uppercase, lowercase, digit, special.
        """
        import hashlib
        # PBKDF2 with domain+email as salt — much stronger than plain SHA256
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode(),
            f"{domain}:{user_email}".encode(),
            iterations=100_000,
            dklen=24,
        )
        import base64
        b64 = base64.urlsafe_b64encode(dk).decode().rstrip("=")
        # Guarantee complexity: first char uppercase, inject digit and special
        core = b64[:20]
        return f"{core[0].upper()}{core[1:]}1!A"
