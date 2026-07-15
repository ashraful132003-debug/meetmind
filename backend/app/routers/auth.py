"""Authentication: register, login, refresh, logout, sessions.

Threat-model notes worth being able to defend out loud:

* Refresh tokens rotate on every use and are stored only as hashes. If a stolen
  token is replayed after the legitimate client rotated it, we detect reuse and
  revoke the whole family — the attacker and the victim both get logged out,
  which is the correct, safe outcome.
* Login says "Invalid email or password" for both unknown-email and wrong-password,
  and burns equivalent CPU on the unknown-email path, so neither the message nor
  the response time reveals whether an account exists.
* Repeated failures lock the account temporarily — brute force protection that
  survives the attacker rotating IPs, which IP rate limiting alone does not.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..deps import RateLimiter, get_current_user
from ..models import AuthSession, User
from ..schemas import (
    LoginRequest,
    RegisterRequest,
    SessionInfo,
    TokenResponse,
    UserPublic,
)
from ..security import (
    create_access_token,
    dummy_verify,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    sign_media_cookie,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE = "meetmind_refresh"
MEDIA_COOKIE = "meetmind_media"
MAX_FAILED_LOGINS = 8
LOCKOUT_MINUTES = 15

login_limiter = RateLimiter(settings.rate_limit_login_per_minute, 60, "login")
# Note: this counts attempts, not successes - a rejected weak password still
# consumes quota, which is what stops the endpoint being used as a free
# validation oracle.
register_limiter = RateLimiter(20, 3600, "register")

_INVALID_CREDENTIALS = HTTPException(
    status.HTTP_401_UNAUTHORIZED, "Invalid email or password"
)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,            # JavaScript cannot read it — XSS can't exfiltrate it
        secure=settings.is_production,  # HTTPS-only in prod; localhost has no TLS
        samesite="lax",           # blocks cross-site CSRF use of the cookie
        max_age=settings.refresh_token_ttl_days * 86400,
        path="/api/auth",         # only sent to auth endpoints, not every request
    )


def _set_media_cookie(response: Response, user_id) -> None:
    """Names the requester for media routes, which cannot carry a Bearer header.
    Scoped to /api/meetings so it is not sent with every other request."""
    response.set_cookie(
        key=MEDIA_COOKIE,
        value=sign_media_cookie(user_id),
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.refresh_token_ttl_days * 86400,
        path="/api/meetings",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.delete_cookie(MEDIA_COOKIE, path="/api/meetings")


async def _issue_session(db: AsyncSession, user: User, request: Request, response: Response) -> TokenResponse:
    refresh = generate_refresh_token()
    session = AuthSession(
        user_id=user.id,
        refresh_hash=hash_refresh_token(refresh),
        user_agent=(request.headers.get("user-agent") or "")[:255],
        ip_address=(request.client.host if request.client else "")[:64],
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days),
    )
    db.add(session)
    await db.flush()

    access, expires_in = create_access_token(user.id, session.id)
    await db.commit()
    _set_refresh_cookie(response, refresh)
    _set_media_cookie(response, user.id)
    return TokenResponse(
        access_token=access,
        expires_in=expires_in,
        user=UserPublic.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(register_limiter),
) -> TokenResponse:
    email = payload.email.lower().strip()
    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        # Registration necessarily reveals that an email is taken — there is no
        # way around it without an email-verification flow. Rate limiting above
        # keeps this from being a practical enumeration oracle.
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    await db.flush()
    return await _issue_session(db, user, request, response)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(login_limiter),
) -> TokenResponse:
    email = payload.email.lower().strip()
    user = await db.scalar(select(User).where(User.email == email))

    if not user:
        dummy_verify()  # equalise timing with the real path
        raise _INVALID_CREDENTIALS

    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds() / 60) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {remaining} minute(s).",
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        await db.commit()
        raise _INVALID_CREDENTIALS

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled")

    # Transparently upgrade the hash if the cost parameters have moved on.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    user.failed_login_count = 0
    user.locked_until = None
    return await _issue_session(db, user, request, response)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")

    token_hash = hash_refresh_token(token)
    session = await db.scalar(select(AuthSession).where(AuthSession.refresh_hash == token_hash))

    if not session:
        # Not the current token. Before rejecting it as garbage, check whether it
        # is a token we already rotated away — that is not a mistake, it is a
        # replay, and it means the token leaked.
        stale = await db.scalar(select(AuthSession).where(AuthSession.previous_hash == token_hash))
        if stale:
            await _revoke_all_for_user(db, stale.user_id, reason="reuse_detected")
            _clear_refresh_cookie(response)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "This session was ended for security reasons. Please sign in again.",
            )
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    now = datetime.now(timezone.utc)

    if session.revoked:
        # Reuse of a revoked token means the token leaked. Kill every session
        # this user has — better an inconvenient logout than a live intruder.
        await _revoke_all_for_user(db, session.user_id, reason="reuse_detected")
        _clear_refresh_cookie(response)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "This session was ended for security reasons. Please sign in again.",
        )

    if session.expires_at <= now:
        session.revoked = True
        session.revoked_reason = "expired"
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")

    user = await db.get(User, session.user_id)
    if not user or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or disabled")

    # Rotate: the presented token is retired and replaced in the same family.
    # The retired hash is kept so a replay of it is recognised as theft rather
    # than dismissed as an unknown token.
    new_refresh = generate_refresh_token()
    session.previous_hash = session.refresh_hash
    session.refresh_hash = hash_refresh_token(new_refresh)
    session.last_used_at = now
    access, expires_in = create_access_token(user.id, session.id)
    await db.commit()

    _set_refresh_cookie(response, new_refresh)
    _set_media_cookie(response, user.id)
    return TokenResponse(
        access_token=access, expires_in=expires_in, user=UserPublic.model_validate(user)
    )


async def _revoke_all_for_user(db: AsyncSession, user_id: uuid.UUID, reason: str) -> None:
    sessions = (
        await db.scalars(
            select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked.is_(False))
        )
    ).all()
    for s in sessions:
        s.revoked = True
        s.revoked_reason = reason
    await db.commit()


# response_model=None is required, not decorative: FastAPI resolves a bare
# `-> None` return annotation to NoneType and treats it as a response model,
# which then trips its own "204 must not have a body" assertion at import time.
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        session = await db.scalar(
            select(AuthSession).where(AuthSession.refresh_hash == hash_refresh_token(token))
        )
        if session and not session.revoked:
            session.revoked = True
            session.revoked_reason = "logout"
            await db.commit()
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(user)


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[SessionInfo]:
    """Lets a user see everywhere they're signed in — and end anything they
    don't recognise."""
    rows = (
        await db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.revoked.is_(False))
            .order_by(AuthSession.last_used_at.desc())
        )
    ).all()
    return [
        SessionInfo(
            id=s.id,
            user_agent=s.user_agent or "Unknown device",
            ip_address=s.ip_address or "unknown",
            created_at=s.created_at,
            last_used_at=s.last_used_at,
        )
        for s in rows
    ]


@router.post("/sessions/revoke-all", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_all(
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _revoke_all_for_user(db, user.id, reason="user_revoked_all")
    _clear_refresh_cookie(response)
