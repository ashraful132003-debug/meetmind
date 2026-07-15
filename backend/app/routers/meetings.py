"""Meeting CRUD, upload, processing status, transcript, and audio streaming.

Every route here depends on `owned_meeting`, so ownership is checked in SQL
before any content is loaded. There is deliberately no "get meeting by id"
that isn't scoped to the caller.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..db import get_db
from ..deps import RateLimiter, get_current_user, owned_meeting
from ..models import ActionItem, Meeting, Speaker, TranscriptSegment, User
from ..schemas import (
    ActionItemOut,
    MeetingCreated,
    MeetingDetail,
    MeetingListItem,
    RenameMeetingRequest,
    RenameSpeakerRequest,
    SegmentOut,
    SpeakerOut,
    ToggleActionRequest,
    TranscriptResponse,
)
from ..security import (
    decrypt_text,
    sign_media_token,
    verify_media_cookie,
    verify_media_token,
)
from ..services.pipeline import process_meeting

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

upload_limiter = RateLimiter(settings.rate_limit_upload_per_hour, 3600, "upload")

# Whitelist, not blacklist. Anything not on this list is refused.
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".flac", ".aac"}
ALLOWED_CONTENT_PREFIXES = ("audio/", "video/webm", "video/mp4")

# Magic bytes. A file claiming to be audio must actually look like audio —
# Content-Type and extension are both attacker-controlled.
_MAGIC = {
    b"RIFF": "wav",
    b"ID3": "mp3",
    b"OggS": "ogg",
    b"fLaC": "flac",
    b"\x1aE\xdf\xa3": "webm/matroska",
}


def _looks_like_audio(head: bytes) -> bool:
    for magic in _MAGIC:
        if head.startswith(magic):
            return True
    if head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3"):  # MPEG frame
        return True
    if len(head) > 11 and head[4:8] == b"ftyp":  # MP4/M4A container
        return True
    return False


@router.get("", response_model=list[MeetingListItem])
async def list_meetings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    search: str = Query("", max_length=120),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[MeetingListItem]:
    stmt = (
        select(Meeting)
        .where(Meeting.owner_id == user.id)
        .options(selectinload(Meeting.speakers), selectinload(Meeting.action_items))
        .order_by(Meeting.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if search.strip():
        # Title search only — transcripts are encrypted at rest, so the database
        # genuinely cannot search their contents. That is the intended trade-off.
        stmt = stmt.where(Meeting.title.ilike(f"%{search.strip()}%"))

    meetings = (await db.scalars(stmt)).all()
    return [
        MeetingListItem(
            id=m.id,
            title=m.title,
            status=m.status,
            progress=m.progress,
            stage_label=m.stage_label,
            duration_seconds=m.duration_seconds,
            language=m.language,
            topics=m.topics,
            sentiment=m.sentiment,
            speaker_count=len(m.speakers),
            action_item_count=len(m.action_items),
            open_action_count=sum(1 for a in m.action_items if not a.done),
            created_at=m.created_at,
            error_message=m.error_message,
        )
        for m in meetings
    ]


@router.post("", response_model=MeetingCreated, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    background: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    source: str = Form("upload"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(upload_limiter),
) -> MeetingCreated:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"'{ext or 'this file type'}' isn't supported. Use one of: "
            + ", ".join(sorted(ALLOWED_EXTENSIONS)),
        )
    if file.content_type and not file.content_type.startswith(ALLOWED_CONTENT_PREFIXES):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unexpected content type '{file.content_type}'. This doesn't look like audio.",
        )
    if source not in {"upload", "recording"}:
        source = "upload"

    meeting_id = uuid.uuid4()
    # Filename is generated, never taken from the client — no path traversal,
    # no collisions, no unicode surprises on disk.
    dest = settings.media_path / f"{meeting_id}{ext}"

    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    head = b""

    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                if not head:
                    head = chunk[:16]
                    if not _looks_like_audio(chunk[:16]):
                        raise HTTPException(
                            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "This file's contents don't look like audio, whatever its name says.",
                        )
                written += len(chunk)
                # Enforced while streaming: we never buffer a huge upload in RAM
                # and never trust a client-supplied Content-Length.
                if written > max_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"File is larger than the {settings.max_upload_mb}MB limit.",
                    )
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        log.exception("Upload failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not save the upload.") from e

    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")

    clean_title = " ".join((title or "").split())[:200] or "Untitled Meeting"
    meeting = Meeting(
        id=meeting_id,
        owner_id=user.id,
        title=clean_title,
        status="uploaded",
        progress=5,
        stage_label="Queued for processing",
        source=source,
        audio_filename=(file.filename or "recording")[:255],
        audio_path=str(dest),
        audio_bytes=written,
    )
    db.add(meeting)
    await db.commit()

    background.add_task(process_meeting, meeting_id)

    return MeetingCreated(
        id=meeting_id,
        title=clean_title,
        status="uploaded",
        message="Upload received. Processing has started.",
    )


def _speaker_map(speakers: list[Speaker]) -> dict[str, str]:
    return {s.tag: s.display_name for s in speakers}


@router.get("/{meeting_id}", response_model=MeetingDetail)
async def get_meeting(
    meeting: Meeting = Depends(owned_meeting),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeetingDetail:
    await db.refresh(meeting, ["speakers", "action_items"])

    audio_url = None
    if meeting.audio_path and Path(meeting.audio_path).exists():
        token = sign_media_token(meeting.id, user.id)
        audio_url = f"/api/meetings/{meeting.id}/audio?token={token}"

    return MeetingDetail(
        id=meeting.id,
        title=meeting.title,
        status=meeting.status,
        progress=meeting.progress,
        stage_label=meeting.stage_label,
        source=meeting.source,
        audio_filename=meeting.audio_filename,
        duration_seconds=meeting.duration_seconds,
        language=meeting.language,
        summary=decrypt_text(meeting.summary_enc) if meeting.summary_enc else None,
        topics=meeting.topics,
        sentiment=meeting.sentiment,
        created_at=meeting.created_at,
        processed_at=meeting.processed_at,
        error_message=meeting.error_message,
        speakers=[SpeakerOut.model_validate(s) for s in sorted(meeting.speakers, key=lambda s: s.tag)],
        action_items=[
            ActionItemOut(
                id=a.id,
                task=decrypt_text(a.task_enc),
                owner_label=a.owner_label,
                speaker_tag=a.speaker_tag,
                due_text=a.due_text,
                priority=a.priority,
                done=a.done,
                quote_time=a.quote_time,
            )
            for a in sorted(meeting.action_items, key=lambda a: (a.done, a.created_at))
        ],
        audio_url=audio_url,
    )


@router.get("/{meeting_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    meeting: Meeting = Depends(owned_meeting), db: AsyncSession = Depends(get_db)
) -> TranscriptResponse:
    await db.refresh(meeting, ["speakers"])
    names = _speaker_map(meeting.speakers)

    segments = (
        await db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting.id)
            .order_by(TranscriptSegment.start_time)
        )
    ).all()

    return TranscriptResponse(
        meeting_id=meeting.id,
        language=meeting.language,
        segments=[
            SegmentOut(
                id=s.id,
                speaker_tag=s.speaker_tag,
                speaker_name=names.get(s.speaker_tag, s.speaker_tag),
                start_time=s.start_time,
                end_time=s.end_time,
                text=decrypt_text(s.text_enc),
            )
            for s in segments
        ],
    )


@router.get("/{meeting_id}/audio")
async def stream_audio(
    meeting_id: uuid.UUID,
    request: Request,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Audio needs two independent proofs, because <audio src> cannot send an
    Authorization header:

    1. A short-lived HMAC token in the URL, binding this meeting + owner + expiry.
    2. The httpOnly media cookie, which names WHO is asking.

    The token alone would be a bearer capability - anyone with the link could
    fetch it, the way S3 pre-signed URLs work. Requiring the cookie as well means
    a leaked link is useless to anybody else: they have the capability but not the
    identity. Both must agree with the meeting's owner.
    """
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or not meeting.audio_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")

    if not verify_media_token(token, meeting.id, meeting.owner_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This audio link is invalid or has expired")

    requester_id = verify_media_cookie(request.cookies.get("meetmind_media"))
    if requester_id != meeting.owner_id:
        # Same 404 the meeting itself would give a stranger - a leaked link must
        # not even confirm that this meeting exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")

    path = Path(meeting.audio_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audio file is missing from storage")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(path, media_type=media_type, headers={"Accept-Ranges": "bytes"})

    # Range support — without it, seeking in the player silently does nothing.
    try:
        units, _, range_spec = range_header.partition("=")
        if units.strip().lower() != "bytes":
            raise ValueError("unsupported unit")
        start_raw, _, end_raw = range_spec.partition("-")
        start = int(start_raw) if start_raw else 0
        end = int(end_raw) if end_raw else file_size - 1
    except ValueError:
        raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "Malformed Range header")

    if start >= file_size or start < 0:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    end = min(end, file_size - 1)
    length = end - start + 1

    def iter_range(chunk_size: int = 256 * 1024):
        with path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                data = f.read(min(chunk_size, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(
        iter_range(),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        },
    )


@router.patch("/{meeting_id}", response_model=MeetingDetail)
async def rename_meeting(
    payload: RenameMeetingRequest,
    meeting: Meeting = Depends(owned_meeting),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeetingDetail:
    meeting.title = payload.title
    await db.commit()
    return await get_meeting(meeting=meeting, db=db, user=user)


@router.patch("/{meeting_id}/speakers/{speaker_id}", response_model=SpeakerOut)
async def rename_speaker(
    speaker_id: uuid.UUID,
    payload: RenameSpeakerRequest,
    meeting: Meeting = Depends(owned_meeting),
    db: AsyncSession = Depends(get_db),
) -> SpeakerOut:
    """Renaming 'Speaker 1' to 'Rahul' also rewrites the action-item owners that
    referred to them, so the whole meeting stays consistent."""
    speaker = await db.scalar(
        select(Speaker).where(Speaker.id == speaker_id, Speaker.meeting_id == meeting.id)
    )
    if not speaker:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Speaker not found in this meeting")

    old_name = speaker.display_name
    speaker.display_name = payload.display_name

    items = (
        await db.scalars(select(ActionItem).where(ActionItem.meeting_id == meeting.id))
    ).all()
    for item in items:
        if item.speaker_tag == speaker.tag or item.owner_label == old_name:
            item.owner_label = payload.display_name
            item.speaker_tag = speaker.tag

    await db.commit()
    await db.refresh(speaker)
    return SpeakerOut.model_validate(speaker)


@router.patch("/{meeting_id}/actions/{action_id}", response_model=ActionItemOut)
async def toggle_action(
    action_id: uuid.UUID,
    payload: ToggleActionRequest,
    meeting: Meeting = Depends(owned_meeting),
    db: AsyncSession = Depends(get_db),
) -> ActionItemOut:
    item = await db.scalar(
        select(ActionItem).where(ActionItem.id == action_id, ActionItem.meeting_id == meeting.id)
    )
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action item not found in this meeting")

    item.done = payload.done
    await db.commit()
    await db.refresh(item)
    return ActionItemOut(
        id=item.id,
        task=decrypt_text(item.task_enc),
        owner_label=item.owner_label,
        speaker_tag=item.speaker_tag,
        due_text=item.due_text,
        priority=item.priority,
        done=item.done,
        quote_time=item.quote_time,
    )


@router.post("/{meeting_id}/reprocess", response_model=MeetingCreated)
async def reprocess_meeting(
    background: BackgroundTasks,
    meeting: Meeting = Depends(owned_meeting),
    db: AsyncSession = Depends(get_db),
) -> MeetingCreated:
    """Re-run the pipeline — the retry button for a failed meeting."""
    if meeting.status in {"transcribing", "diarizing", "analyzing", "indexing"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "This meeting is already being processed.")
    if not meeting.audio_path or not Path(meeting.audio_path).exists():
        raise HTTPException(status.HTTP_410_GONE, "The original audio is no longer available.")

    meeting.status = "uploaded"
    meeting.progress = 5
    meeting.stage_label = "Queued for processing"
    meeting.error_message = None
    await db.commit()

    background.add_task(process_meeting, meeting.id)
    return MeetingCreated(
        id=meeting.id, title=meeting.title, status="uploaded", message="Reprocessing started."
    )


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_meeting(
    meeting: Meeting = Depends(owned_meeting), db: AsyncSession = Depends(get_db)
) -> None:
    """Delete means delete: the audio leaves the disk, and every derived row
    (transcript, chunks, chat, actions) cascades. Nothing is soft-deleted."""
    audio_path = meeting.audio_path
    await db.delete(meeting)
    await db.commit()

    if audio_path:
        try:
            Path(audio_path).unlink(missing_ok=True)
        except OSError as e:
            log.warning("Could not delete audio file %s: %s", audio_path, e)
