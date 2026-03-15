import re
import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator, AnyHttpUrl
from typing import Optional


def _validate_password_strength(password: str) -> str:
    """Enforce minimum password security requirements."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if len(password) > 128:
        raise ValueError("Password must be at most 128 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")
    return password


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("Name must be 1–100 characters")
        return v


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

    @field_validator("phone")
    @classmethod
    def phone_safe(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        # Allow only digits, spaces, +, -, (, ) — reject anything else
        if v and not re.match(r"^[\d\s\+\-\(\)]{0,20}$", v):
            raise ValueError("Invalid phone number format")
        return v

    @field_validator("ville")
    @classmethod
    def ville_safe(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) > 100:
            raise ValueError("City name too long")
        return v

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def url_safe(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if len(v) > 500:
            raise ValueError("URL too long")
        if not re.match(r"^https?://", v):
            raise ValueError("URL must start with https:// or http://")
        return v


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
