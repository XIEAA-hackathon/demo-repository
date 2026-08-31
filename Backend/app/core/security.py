from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
from typing import Optional
from jose import JWTError, jwt
from app.core.config import settings

BCRYPT_PREFIX_RE = re.compile(r"^\$2(?:[abxy])?\$")
SHA256_HASH_RE = re.compile(r"^sha256\$[0-9a-f]{32}\$[0-9a-f]{64}$")


def is_bcrypt_password_hash(value: str | None) -> bool:
    """Detect every known bcrypt prefix for reset verification only."""
    return isinstance(value, str) and bool(BCRYPT_PREFIX_RE.match(value.strip()))


def is_sha256_password_hash(value: str | None) -> bool:
    return isinstance(value, str) and bool(SHA256_HASH_RE.fullmatch(value.strip()))


def is_valid_password_hash(value: str) -> bool:
    """Validate the only password hash accepted for active credentials."""
    return is_sha256_password_hash(value)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"sha256${salt}${digest}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if is_sha256_password_hash(hashed_password):
        try:
            algorithm, salt, expected = hashed_password.split("$", 2)
            if algorithm != "sha256":
                return False
            actual = hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest()
            return hmac.compare_digest(actual, expected)
        except (AttributeError, TypeError, ValueError):
            return False
    return False


def get_password_hash(password: str) -> str:
    """Compatibility name used by account creation; always emits salted SHA-256."""
    return hash_password(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
