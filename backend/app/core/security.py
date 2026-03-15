from datetime import datetime, timedelta
from typing import Any
import base64
import hashlib
import hmac
import json
import bcrypt
from app.config import settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _sign(header_payload: str, secret: str) -> str:
    sig = hmac.new(secret.encode(), header_payload.encode(), hashlib.sha256).digest()
    return _b64url_encode(sig)


def _create_token(payload: dict, secret: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url_encode(json.dumps(payload).encode())
    sig = _sign(f"{header}.{body}", secret)
    return f"{header}.{body}.{sig}"


def _decode_token_raw(token: str, secret: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    header_payload = f"{parts[0]}.{parts[1]}"
    expected_sig = _sign(header_payload, secret)
    if not hmac.compare_digest(expected_sig, parts[2]):
        raise ValueError("Invalid signature")
    payload = json.loads(_b64url_decode(parts[1]))
    exp = payload.get("exp")
    if exp and datetime.utcnow().timestamp() > exp:
        raise ValueError("Token expired")
    return payload


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"exp": expire.timestamp(), "sub": str(subject), "type": "access"}
    return _create_token(payload, settings.secret_key)


def create_refresh_token(subject: str | Any) -> str:
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    payload = {"exp": expire.timestamp(), "sub": str(subject), "type": "refresh"}
    return _create_token(payload, settings.secret_key)


def decode_token(token: str) -> dict | None:
    try:
        return _decode_token_raw(token, settings.secret_key)
    except Exception:
        return None
