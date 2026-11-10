import base64, hashlib, logging
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from cryptography.fernet import Fernet

from .errors import err
from .settings import DEV_JWT, settings

log = logging.getLogger("security")
_ph = PasswordHasher()
DUMMY_HASH = _ph.hash("dummy-password-for-timing")


def hash_password(p: str) -> str:
    return _ph.hash(p)


def verify_password(hashed: str, p: str) -> bool:
    try:
        return _ph.verify(hashed, p)
    except Exception:
        return False


def create_token(user_id, role: str, company_id=None, impersonator=None, minutes: int | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes or settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "role": role, "cid": str(company_id) if company_id else None, "exp": exp}
    if impersonator:
        payload["imp"] = str(impersonator)
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise err(401, "token_expired", "Your session has expired. Please log in again.")
    except jwt.PyJWTError:
        raise err(401, "invalid_token", "Invalid authentication token.")


def _fernet() -> Fernet:
    key = settings.secrets_encryption_key
    if not key:  # dev fallback only; production startup refuses to run without a key
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_secret(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt_secret(blob: bytes) -> str:
    return _fernet().decrypt(bytes(blob)).decode()


def assert_production_safe():
    if settings.environment == "production":
        if settings.jwt_secret == DEV_JWT or len(settings.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be set to a long random value in production")
        if not settings.secrets_encryption_key:
            raise RuntimeError("SECRETS_ENCRYPTION_KEY must be set in production")
