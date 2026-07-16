"""Download a meeting as PDF or Word."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import RateLimiter, get_current_user, owned_meeting
from ..models import Meeting, Speaker, TranscriptSegment, User
from ..security import decrypt_text
from ..services.export import ExportData, build_docx, build_pdf, safe_filename

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings/{meeting_id}/export", tags=["export"])

# Rendering a long transcript is CPU work; a tight loop of requests could pin a
# 512MB instance. Generous enough that nobody legitimate will notice.
export_limiter = RateLimiter(20, 60, "export")

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("", response_class=Response)
async def export_meeting(
    fmt: str = Query("pdf", pattern="^(pdf|docx)$", alias="format"),
    include_transcript: bool = Query(False),
    meeting: Meeting = Depends(owned_meeting),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(export_limiter),
) -> Response:
    if meeting.status != "ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This meeting is still processing. Wait until it's ready to export.",
        )

    await db.refresh(meeting, ["speakers", "action_items"])

    transcript = None
    if include_transcript:
        names = {s.tag: s.display_name for s in meeting.speakers}
        segments = (
            await db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.meeting_id == meeting.id)
                .order_by(TranscriptSegment.start_time)
            )
        ).all()
        transcript = [
            {
                "speaker_name": names.get(s.speaker_tag, s.speaker_tag),
                "start_time": s.start_time,
                "text": decrypt_text(s.text_enc),
            }
            for s in segments
        ]

    data = ExportData(
        title=meeting.title,
        created_at=meeting.created_at,
        duration_seconds=meeting.duration_seconds,
        language=meeting.language,
        owner_name=user.full_name,
        summary=decrypt_text(meeting.summary_enc) if meeting.summary_enc else None,
        topics=meeting.topics or [],
        sentiment=meeting.sentiment,
        speakers=[
            {
                "display_name": s.display_name,
                "talk_seconds": s.talk_seconds,
                "word_count": s.word_count,
                "color": s.color,
            }
            for s in sorted(meeting.speakers, key=lambda s: -s.talk_seconds)
        ],
        action_items=[
            {
                "task": decrypt_text(a.task_enc),
                "owner_label": a.owner_label,
                "due_text": a.due_text,
                "priority": a.priority,
                "done": a.done,
            }
            for a in sorted(meeting.action_items, key=lambda a: (a.done, a.created_at))
        ],
        transcript=transcript,
    )

    builder = build_pdf if fmt == "pdf" else build_docx
    try:
        # Document generation is blocking CPU work — off the event loop, or a long
        # transcript would stall every other request on the instance.
        payload = await asyncio.to_thread(builder, data)
    except Exception as e:
        log.exception("Export failed for meeting %s", meeting.id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Could not generate the {fmt.upper()}. Please try again.",
        ) from e

    filename = safe_filename(meeting.title, fmt)
    return Response(
        content=payload,
        media_type=MEDIA_TYPES[fmt],
        headers={
            # Both forms: `filename` for old clients, `filename*` (RFC 5987) so a
            # title with non-ASCII characters (Hindi, for instance) survives.
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{quote(filename)}"
            ),
            "Content-Length": str(len(payload)),
            "Cache-Control": "no-store",
        },
    )
