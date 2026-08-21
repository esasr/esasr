from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import hmac
import os
import base64
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from config import cfg
import models

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = cfg.jwt_secret
ALGORITHM = cfg.auth.jwt_algorithm
ACCESS_TOKEN_EXPIRE_DAYS = cfg.auth.access_token_expire_days

# ── Password Hashing (PBKDF2-HMAC-SHA256) ────────────────────────────────────
_ITERATIONS = 600_000
_HASH_NAME = "sha256"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode(), salt, _ITERATIONS)
    encoded = base64.b64encode(salt + dk).decode()
    return f"pbkdf2:{_HASH_NAME}:{_ITERATIONS}${encoded}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        header, encoded = hashed_password.split("$", 1)
        _, hash_name, iterations_str = header.split(":")
        iterations = int(iterations_str)
        raw = base64.b64decode(encoded)
        salt, stored_dk = raw[:16], raw[16:]
        new_dk = hashlib.pbkdf2_hmac(hash_name, plain_password.encode(), salt, iterations)
        return hmac.compare_digest(stored_dk, new_dk)
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> models.User:
    """Async dependency: extracts and validates JWT, returns the User ORM object."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(models.User).where(models.User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> Optional[models.User]:
    """Optional async dependency: returns User if token valid, else None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        result = await db.execute(select(models.User).where(models.User.id == int(user_id)))
        return result.scalar_one_or_none()
    except JWTError:
        return None
