import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenRefresh(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    phone: str | None = None
    ville: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None


class ProfileOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    phone: str | None
    ville: str | None
    linkedin_url: str | None
    github_url: str | None
    portfolio_url: str | None
    cv_original_path: str | None
    cv_parsed_data: dict | None
    skills_technical: list | None
    skills_soft: list | None
    education: list | None
    experience: list | None
    languages: list | None
    certifications: list | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class PreferencesUpdate(BaseModel):
    target_roles: list[str] | None = None
    contract_types: list[str] | None = None
    preferred_locations: list[str] | None = None
    salary_min: int | None = None
    exclude_keywords: list[str] | None = None
    min_match_score: int | None = None
    daily_application_limit: int | None = None
    auto_apply_enabled: bool | None = None
    pipeline_enabled: bool | None = None
    pipeline_hour: int | None = None


class PreferencesOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    target_roles: list | None
    contract_types: list | None
    preferred_locations: list | None
    salary_min: int | None
    exclude_keywords: list | None
    min_match_score: int
    daily_application_limit: int
    auto_apply_enabled: bool
    pipeline_enabled: bool
    pipeline_hour: int
    updated_at: datetime

    model_config = {"from_attributes": True}
