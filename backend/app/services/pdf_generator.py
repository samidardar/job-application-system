import logging
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)


async def generate_pdf(html_content: str, output_path: str) -> int:
    """
    Generate a PDF from HTML content using WeasyPrint.
    Returns the file size in bytes.
    """
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration

        font_config = FontConfiguration()
        css = CSS(string="""
            @page {
                margin: 1.5cm 1.5cm 2cm;
                size: A4;
            }
        """, font_config=font_config)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        HTML(string=html_content).write_pdf(
            output_path,
            stylesheets=[css],
            font_config=font_config,
        )

        return Path(output_path).stat().st_size

    except ImportError:
        logger.error("WeasyPrint not installed")
        raise
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise
