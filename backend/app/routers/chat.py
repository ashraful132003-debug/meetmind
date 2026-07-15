"""'Ask the meeting' chat endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import RateLimiter, owned_meeting
from ..models import ChatMessage, Meeting, TranscriptChunk
from ..schemas import ChatMessageOut, ChatRequest, ChatResponse, Citation
from ..security import decrypt_text, encrypt_text
from ..services import rag
from ..services.llm import LLMError, LLMUnavailable, embed

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings/{meeting_id}/chat", tags=["chat"])

chat_limiter = RateLimiter(30, 60, "chat")


def _to_out(msg: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        role=msg.role,
        content=decrypt_text(msg.content_enc),
        citations=[Citation(**c) for c in (msg.citations or [])] or None,
        created_at=msg.created_at,
    )


@router.get("", response_model=list[ChatMessageOut])
async def get_history(
    meeting: Meeting = Depends(owned_meeting), db: AsyncSession = Depends(get_db)
) -> list[ChatMessageOut]:
    messages = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.meeting_id == meeting.id)
            .order_by(ChatMessage.created_at)
        )
    ).all()
    return [_to_out(m) for m in messages]


@router.get("/suggestions", response_model=list[str])
async def get_suggestions(
    meeting: Meeting = Depends(owned_meeting), db: AsyncSession = Depends(get_db)
) -> list[str]:
    """Starter questions grounded in this specific meeting. Generated on demand;
    if the LLM is unreachable we return nothing rather than inventing generic
    questions the transcript can't answer."""
    if meeting.status != "ready" or not meeting.transcript_text_enc:
        return []
    try:
        return await rag.suggest_questions(decrypt_text(meeting.transcript_text_enc))
    except (LLMError, LLMUnavailable) as e:
        log.warning("Suggestion generation failed: %s", e)
        return []


@router.post("", response_model=ChatResponse)
async def ask(
    payload: ChatRequest,
    meeting: Meeting = Depends(owned_meeting),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(chat_limiter),
) -> ChatResponse:
    if meeting.status != "ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This meeting is still processing. The chat becomes available once it's ready.",
        )

    # Scoped to this meeting in the WHERE clause. Another meeting's chunks
    # cannot enter the context — not "are filtered out later", cannot enter.
    chunk_rows = (
        await db.scalars(
            select(TranscriptChunk).where(TranscriptChunk.meeting_id == meeting.id)
        )
    ).all()
    if not chunk_rows:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This meeting has no searchable transcript yet. Try reprocessing it.",
        )

    history = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.meeting_id == meeting.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(6)
        )
    ).all()
    history_payload = [
        {"role": m.role, "content": decrypt_text(m.content_enc)} for m in reversed(history)
    ]

    try:
        query_vec = (await embed([payload.question]))[0]
        chunks = [
            {
                "text": decrypt_text(c.text_enc),
                "speakers": c.speakers or [],
                "start_time": c.start_time,
                "end_time": c.end_time,
                "embedding": c.embedding,
            }
            for c in chunk_rows
        ]
        retrieved = rag.rank_chunks(query_vec, chunks)
        answer_text = await rag.answer_question(payload.question, retrieved, history_payload)
    except LLMUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    except LLMError as e:
        log.exception("Chat failed")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The language model failed to answer. Please try again."
        ) from e

    citations = rag.build_citations(retrieved)

    db.add(
        ChatMessage(meeting_id=meeting.id, role="user", content_enc=encrypt_text(payload.question))
    )
    assistant = ChatMessage(
        meeting_id=meeting.id,
        role="assistant",
        content_enc=encrypt_text(answer_text),
        citations=citations,
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)

    return ChatResponse(answer=_to_out(assistant), suggestions=[])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def clear_history(
    meeting: Meeting = Depends(owned_meeting), db: AsyncSession = Depends(get_db)
) -> None:
    await db.execute(delete(ChatMessage).where(ChatMessage.meeting_id == meeting.id))
    await db.commit()
