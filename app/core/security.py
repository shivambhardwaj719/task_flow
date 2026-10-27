import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.config import settings

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with automated salt generation.

    Passwords are never logged or stored in plain text.
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify that a plain password matches a bcrypt hashed password.

    Uses constant-time comparison internally via bcrypt.checkpw.
    """
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception as e:
        logger.error("Error verifying password hash: %s", type(e).__name__)
        return False


def create_access_token(
    subject: str | int,
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token with expiration time and standard claims."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError as e:
        logger.debug("JWT decode failed: %s", str(e))
        return None
