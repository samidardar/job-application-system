"""
PDF generation using Playwright (Chromium) — pixel-perfect, same engine as Chrome.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def generate_pdf(html_content: str, output_path: str) -> int:
    """
    Render HTML to PDF using Playwright/Chromium.
    Returns file size in bytes.
    """
    from playwright.async_api import async_playwright

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page()

        # Set content directly (no file:// URL needed)
        await page.set_content(html_content, wait_until="networkidle")

        await page.pdf(
            path=output_path,
            format="A4",
            margin={"top": "1.5cm", "right": "1.5cm", "bottom": "2cm", "left": "1.5cm"},
            print_background=True,
        )

        await browser.close()

    size = Path(output_path).stat().st_size
    logger.info(f"PDF generated: {output_path} ({size} bytes)")
    return size
