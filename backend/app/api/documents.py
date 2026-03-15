import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.document import Document
from app.schemas.document import DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])

# Resolved storage root — all document paths must stay inside here
_STORAGE_ROOT = Path(settings.storage_path).resolve()


def _safe_file_path(file_path: str) -> Path:
    """
    Resolve the file path and verify it stays within _STORAGE_ROOT.
    Raises HTTPException 403 if path traversal is detected.
    """
    resolved = Path(file_path).resolve()
    try:
        resolved.relative_to(_STORAGE_ROOT)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return resolved


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="Document file not found")

    # Validate the stored path is within our storage root (prevents DB-stored path traversal)
    safe_path = _safe_file_path(doc.file_path)

    return FileResponse(
        path=str(safe_path),
        filename=doc.file_name or f"document_{doc_id}.pdf",
        media_type="application/pdf",
    )


@router.get("/{doc_id}/preview")
async def preview_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"content_html": doc.content_html, "content_text": doc.content_text}
