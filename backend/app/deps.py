"""Shared FastAPI dependencies: current user, owned-meeting lookup, rate limiting.

`owned_meeting` is the security chokepoint. No route loads a meeting by id alone —
they all go through here, and the ownership filter is part of the WHERE clause
rather than an `if` after the fetch. A wrong id and someone else's id return the
identical 404, so the API never confirms that a meeting exists.
"""

# NOTE: deliberately no `from __future__ import annotations` in this module.
#
# That import turns annotations into strings, and FastAPI resolves a dependency's
# annotations using its `__globals__`. `RateLimiter` is used as a dependency via a
# class *instance*, and instances have no `__globals__` - so FastAPI cannot resolve
# "Request", concludes it is an unknown parameter, and starts demanding a body
# field literally named `request`. Every rate-limited route then 422s.
# Python 3.10+ syntax used here works natively without the import.

import time
import uuid
from collections import defaultdict

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import Meeting, User
from .security import decode_access_token

_MEETING_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(auth[7:].strip())
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")

    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or disabled")
    return user


async def owned_meeting(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Meeting:
    meeting = await db.scalar(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.owner_id == user.id)
    )
    if not meeting:
        raise _MEETING_NOT_FOUND
    return meeting


class RateLimiter:
    """In-process sliding-window limiter. Sufficient for a single-node deploy;
    swap the backing dict for Redis if this ever runs multi-instance."""

    def __init__(self, limit: int, window_seconds: int, scope: str) -> None:
        self.limit = limit
        self.window = window_seconds
        self.scope = scope
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _key(self, request: Request) -> str:
        client = request.client.host if request.client else "unknown"
        return f"{self.scope}:{client}"

    async def __call__(self, request: Request) -> None:
        now = time.time()
        key = self._key(request)
        recent = [t for t in self._hits[key] if now - t < self.window]
        if len(recent) >= self.limit:
            retry_after = int(self.window - (now - recent[0])) + 1
            self._hits[key] = recent
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(retry_after)},
            )
        recent.append(now)
        self._hits[key] = recent
