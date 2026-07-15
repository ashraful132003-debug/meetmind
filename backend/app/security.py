"""Password hashing, token issuing/verification, media URL signing, encryption.

Design notes (the parts an interviewer will poke at):

* Passwords use Argon2id — memory-hard, the current OWASP recommendation.
* Access tokens are short-lived (15 min) JWTs held in memory by the SPA.
* Refresh tokens live in httpOnly+SameSite cookies, are rotated on every use,
  and are stored server-side only as SHA-256 hashes. Reusing an already-rotated
  refresh token is treated as theft: the entire token family is revoked.
* Media URLs are HMAC-signed and expire, so a leaked link stops working.
* Transcripts are encrypted at rest with Fernet (AES-128-CBC + HMAC).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from .config import settings

ALGORITHM = "HS256"

# Tuned for interactive login latency (~50-100ms) while staying memory-hard.
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

_fernet = Fernet(settings.encryption_key.encode())


# --- Passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _hasher.verify(stored_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except (InvalidHashError, ValueError):
        return False


def dummy_verify() -> None:
    """Burn equivalent CPU on unknown-user logins so response time doesn't leak
    whether an email is registered."""
    try:
        _hasher.verify(
            "$argon2id$v=19$m=65536,t=3,p=2$"
            "c29tZXNhbHRzb21lc2FsdA$T3n7QY7gGZ7Yb4Yl0nQO1F1a1r0mYqTqUu0mQ0k1Zqg",
            "not-the-password",
        )
    except Exception:
        pass


# --- Access tokens -----------------------------------------------------------


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_in = settings.access_token_ttl_minutes * 60
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


# --- Refresh tokens ----------------------------------------------------------


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Stored server-side. Plain SHA-256 is correct here: the token is already
    high-entropy random, so there is nothing to brute-force."""
    return hashlib.sha256(token.encode()).hexdigest()


# --- Signed media URLs -------------------------------------------------------


def sign_media_token(meeting_id: uuid.UUID, user_id: uuid.UUID, ttl_seconds: int = 300) -> str:
    expires = int(time.time()) + ttl_seconds
    msg = f"{meeting_id}:{user_id}:{expires}".encode()
    sig = hmac.new(settings.media_signing_secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def sign_media_cookie(user_id: uuid.UUID, ttl_seconds: int | None = None) -> str:
    """Identity proof for media requests.

    An <audio src> cannot send an Authorization header, so a signed URL alone is a
    bearer capability: anyone holding the link can fetch it. Browsers DO send
    cookies automatically, so pairing the signed URL with an httpOnly cookie that
    names the requester closes that gap — the link becomes useless to anyone else,
    even inside its expiry window.
    """
    expires = int(time.time()) + (ttl_seconds or settings.refresh_token_ttl_days * 86400)
    msg = f"{user_id}:{expires}".encode()
    sig = hmac.new(settings.media_signing_secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"{user_id}.{expires}.{sig}"


def verify_media_cookie(value: str | None) -> uuid.UUID | None:
    """Return the user id the cookie attests to, or None if absent/invalid/expired."""
    if not value:
        return None
    try:
        user_raw, expires_raw, sig = value.split(".", 2)
        expires = int(expires_raw)
        user_id = uuid.UUID(user_raw)
    except (ValueError, AttributeError):
        return None
    if expires < int(time.time()):
        return None
    msg = f"{user_id}:{expires}".encode()
    expected = hmac.new(settings.media_signing_secret.encode(), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    return user_id


def verify_media_token(token: str, meeting_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    try:
        expires_raw, sig = token.split(".", 1)
        expires = int(expires_raw)
    except (ValueError, AttributeError):
        return False
    if expires < int(time.time()):
        return False
    msg = f"{meeting_id}:{user_id}:{expires}".encode()
    expected = hmac.new(settings.media_signing_secret.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


# --- Encryption at rest ------------------------------------------------------


def encrypt_text(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_text(ciphertext: str) -> str:
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("Stored data could not be decrypted with the current ENCRYPTION_KEY")
