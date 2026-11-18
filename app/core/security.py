import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import Settings


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str, email: str, purpose: str, pepper: str) -> str:
    payload = f"{email}:{purpose}:{otp}".encode()
    return hmac.new(pepper.encode(), payload, hashlib.sha256).hexdigest()


def verify_otp(otp: str, email: str, purpose: str, pepper: str, expected_hash: str) -> bool:
    actual_hash = hash_otp(otp, email, purpose, pepper)
    return hmac.compare_digest(actual_hash, expected_hash)


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)
