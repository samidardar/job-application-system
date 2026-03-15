import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User, UserProfile
from app.models.document import Document, DocumentTypeEnum
from app.services.cv_parser import CVParser
from app.core.storage import save_file

router = APIRouter(prefix="/cv", tags=["cv"])


@router.post("/upload")
async def upload_cv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # Save original file
    file_path, file_name = await save_file(
        content,
        subdir=f"cvs/{current_user.id}",
        filename=f"cv_original_{uuid.uuid4()}.pdf"
    )

    # Parse CV
    parser = CVParser()
    parsed_data = await parser.parse(content)

    # Generate HTML template from parsed data
    html_template = parser.generate_html_template(parsed_data, current_user)

    # Update user profile
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)

    profile.cv_original_path = file_path
    profile.cv_parsed_data = parsed_data
    profile.cv_text_content = parsed_data.get("raw_text", "")
    profile.cv_html_template = html_template
    profile.skills_technical = parsed_data.get("skills_technical", [])
    profile.skills_soft = parsed_data.get("skills_soft", [])
    profile.education = parsed_data.get("education", [])
    profile.experience = parsed_data.get("experience", [])
    profile.languages = parsed_data.get("languages", [])
    profile.certifications = parsed_data.get("certifications", [])

    # Save document record
    doc = Document(
        user_id=current_user.id,
        document_type=DocumentTypeEnum.CV_ORIGINAL,
        content_text=parsed_data.get("raw_text", ""),
        content_html=html_template,
        file_path=file_path,
        file_name=file_name,
        file_size_bytes=len(content),
    )
    db.add(doc)

    await db.commit()

    return {
        "message": "CV uploaded and parsed successfully",
        "file_name": file_name,
        "parsed_sections": list(parsed_data.keys()),
        "skills_count": len(profile.skills_technical or []),
        "experience_count": len(profile.experience or []),
    }


@router.get("/parsed")
async def get_parsed_cv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile or not profile.cv_parsed_data:
        raise HTTPException(status_code=404, detail="No CV uploaded yet")
    return profile.cv_parsed_data
