"""
BrowserSessionManager — Playwright persistent context manager.

Saves/loads cookies and localStorage per user per domain so the user
only needs to log in once to LinkedIn, Indeed, etc. Subsequent pipeline
runs reuse the saved session automatically.

Session files are stored at: storage/browser_states/{user_id}/{domain_safe}.json
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Base directory for all browser state files
_STATES_DIR = Path("storage/browser_states")


def _domain_safe(domain: str) -> str:
    """Sanitize domain string for use as a filename."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", domain)


def state_path(user_id: str, domain: str) -> Path:
    """Returns the path to the Playwright storage state JSON for this user+domain."""
    return _STATES_DIR / str(user_id) / f"{_domain_safe(domain)}.json"


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
        Never stored in plaintext — always re-derived from user_email + domain + SECRET_KEY.
        Format: 10 hex chars capitalized + "!7" → always valid (uppercase, digit, special).
        """
        import hashlib
        raw = hashlib.sha256(f"{user_email}:{domain}:{secret}".encode()).hexdigest()
        return f"{raw[:10].capitalize()}!7"
