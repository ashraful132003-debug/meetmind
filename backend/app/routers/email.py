"""Emailing a meeting summary to participants."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import RateLimiter, owned_meeting
from ..models import EmailDelivery, Meeting, User
from ..deps import get_current_user
from ..schemas import EmailDeliveryOut, SendEmailRequest
from ..security import decrypt_text
from ..services.emailer import render_summary_email, send_email

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings/{meeting_id}/email", tags=["email"])

email_limiter = RateLimiter(10, 3600, "email")


def _to_out(row: EmailDelivery) -> EmailDeliveryOut:
    return EmailDeliveryOut(
        id=row.id,
        recipients=row.recipients,
        subject=row.subject,
        transport=row.transport,
        status=row.status,
        detail=row.detail,
        preview_url=f"/api/meetings/{row.meeting_id}/email/{row.id}/preview" if row.preview_path else None,
        created_at=row.created_at,
    )


@router.get("", response_model=list[EmailDeliveryOut])
async def list_deliveries(
    meeting: Meeting = Depends(owned_meeting), db: AsyncSession = Depends(get_db)
) -> list[EmailDeliveryOut]:
    rows = (
        await db.scalars(
            select(EmailDelivery)
            .where(EmailDelivery.meeting_id == meeting.id)
            .order_by(EmailDelivery.created_at.desc())
        )
    ).all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=EmailDeliveryOut, status_code=status.HTTP_201_CREATED)
async def send_summary(
    payload: SendEmailRequest,
    meeting: Meeting = Depends(owned_meeting),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(email_limiter),
) -> EmailDeliveryOut:
    if meeting.status != "ready" or not meeting.summary_enc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This meeting doesn't have a summary yet. Wait for processing to finish.",
        )

    await db.refresh(meeting, ["speakers", "action_items"])

    html, text = render_summary_email(
        meeting_title=meeting.title,
        sender_name=user.full_name,
        summary_md=decrypt_text(meeting.summary_enc),
        action_items=[
            {
                "task": decrypt_text(a.task_enc),
                "owner_label": a.owner_label,
                "due_text": a.due_text,
                "priority": a.priority,
            }
            for a in sorted(meeting.action_items, key=lambda a: (a.done, a.created_at))
        ],
        speakers=[
            {"display_name": s.display_name, "color": s.color, "talk_seconds": s.talk_seconds}
            for s in sorted(meeting.speakers, key=lambda s: -s.talk_seconds)
        ],
        duration_seconds=meeting.duration_seconds,
        note=payload.note,
        transcript=(
            decrypt_text(meeting.transcript_text_enc)
            if payload.include_transcript and meeting.transcript_text_enc
            else None
        ),
    )

    subject = f"Meeting summary: {meeting.title}"
    recipients = [str(r) for r in payload.recipients]

    # smtplib is blocking — off the event loop it goes.
    result = await asyncio.to_thread(send_email, subject, recipients, html, text)

    from ..config import settings

    row = EmailDelivery(
        meeting_id=meeting.id,
        recipients=recipients,
        subject=subject,
        transport=settings.email_transport.lower(),
        status=result.status,
        detail=result.detail,
        preview_path=result.preview_path,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    if result.status == "failed":
        # Recorded above so the user can see the failure in the UI, but still a
        # 502: the button did not do what it said.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, result.detail)

    return _to_out(row)


@router.get("/{delivery_id}/preview", response_class=HTMLResponse)
async def preview_email(
    delivery_id: uuid.UUID,
    meeting: Meeting = Depends(owned_meeting),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Serves the exact rendered email that was composed — the local-transport
    equivalent of opening it in your inbox."""
    row = await db.scalar(
        select(EmailDelivery).where(
            EmailDelivery.id == delivery_id, EmailDelivery.meeting_id == meeting.id
        )
    )
    if not row or not row.preview_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No preview available for this delivery")

    path = Path(row.preview_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The preview file is no longer on disk")

    return HTMLResponse(
        path.read_text(encoding="utf-8"),
        headers={
            # The preview is attacker-influenced content (transcript text), so it
            # gets a locked-down CSP and is never framed by the app.
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:;",
            "X-Content-Type-Options": "nosniff",
        },
    )
