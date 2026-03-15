import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User, UserProfile, UserPreferences
from app.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token, decode_token
from app.schemas.user import UserCreate, UserLogin, TokenRefresh, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# ── In-memory rate limiting (per IP) ─────────────────────────────────────────
# Structure: {ip: [timestamp, ...]}
_login_attempts: dict[str, list[float]] = defaultdict(list)
_register_attempts: dict[str, list[float]] = defaultdict(list)

_LOGIN_MAX = 10          # max 10 login attempts
_LOGIN_WINDOW = 60       # per 60 seconds
_REGISTER_MAX = 5        # max 5 registrations
_REGISTER_WINDOW = 300   # per 5 minutes


def _check_rate_limit(store: dict, key: str, max_calls: int, window: int) -> None:
    """Raise 429 if too many calls in window. Purges expired entries in-place."""
    now = time.monotonic()
    attempts = [t for t in store[key] if now - t < window]
    store[key] = attempts
    if len(attempts) >= max_calls:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Please wait {window} seconds.",
            headers={"Retry-After": str(window)},
        )
    store[key].append(now)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, data: UserCreate, db: AsyncSession = Depends(get_db)):
    _check_rate_limit(_register_attempts, _get_client_ip(request), _REGISTER_MAX, _REGISTER_WINDOW)

    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
    )
    db.add(user)
    await db.flush()

    # Create default profile and preferences
    profile = UserProfile(user_id=user.id)
    preferences = UserPreferences(user_id=user.id)
    db.add(profile)
    db.add(preferences)
    await db.commit()
    await db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, data: UserLogin, db: AsyncSession = Depends(get_db)):
    _check_rate_limit(_login_attempts, _get_client_ip(request), _LOGIN_MAX, _LOGIN_WINDOW)

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    # Always run verify_password to prevent timing-based email enumeration
    dummy_hash = "$2b$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    if not user:
        verify_password(data.password, dummy_hash)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    _check_rate_limit(_login_attempts, _get_client_ip(request), _LOGIN_MAX, _LOGIN_WINDOW)

    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
