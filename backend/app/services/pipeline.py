"""The processing pipeline: audio in, fully-analysed meeting out.

Runs as a background task per meeting. Stages update `meetings.status` and
`progress` as they complete, so the UI shows real progress driven by actual work
rather than a fake timer.

Failure policy: a stage that fails marks the meeting `failed` with a message the
user can act on. It never leaves a meeting stuck in a half-state, and never
silently pretends a stage succeeded.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from ..db import SessionLocal
from ..models import ActionItem, Meeting, Speaker, TranscriptChunk, TranscriptSegment
from ..security import encrypt_text
from . import analysis, diarize, rag, transcribe
from .llm import LLMUnavailable

log = logging.getLogger(__name__)

# One meeting at a time: Whisper and Llama both want the GPU, and a laptop 3050
# has 4GB. Serialising keeps things predictable instead of OOM-ing under load.
_pipeline_lock = asyncio.Semaphore(1)


async def _set_stage(meeting_id: uuid.UUID, status: str, progress: int, label: str) -> None:
    async with SessionLocal() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting:
            meeting.status = status
            meeting.progress = progress
            meeting.stage_label = label
            await db.commit()


async def _fail(meeting_id: uuid.UUID, message: str) -> None:
    async with SessionLocal() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting:
            meeting.status = "failed"
            meeting.stage_label = "Failed"
            meeting.error_message = message[:1000]
            await db.commit()
    log.error("Meeting %s failed: %s", meeting_id, message)


async def process_meeting(meeting_id: uuid.UUID) -> None:
    async with _pipeline_lock:
        try:
            await _process(meeting_id)
        except LLMUnavailable as e:
            await _fail(meeting_id, str(e))
        except FileNotFoundError:
            await _fail(meeting_id, "The audio file for this meeting is missing from storage.")
        except Exception as e:
            log.exception("Pipeline crashed for %s", meeting_id)
            await _fail(meeting_id, f"Processing failed: {type(e).__name__}: {e}"[:400])


async def _process(meeting_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting or not meeting.audio_path:
            raise FileNotFoundError("Meeting or audio path not found")
        audio_path = meeting.audio_path
        owner_named_it = meeting.title.strip().lower() not in {"", "untitled meeting"}

    # --- 1. Transcribe -------------------------------------------------------
    await _set_stage(meeting_id, "transcribing", 10, "Transcribing audio")
    result = await asyncio.to_thread(transcribe.transcribe, audio_path)
    if not result.segments:
        await _fail(
            meeting_id,
            "No speech was detected in this recording. The file may be silent, "
            "corrupted, or too quiet.",
        )
        return

    # --- 2. Diarize ----------------------------------------------------------
    await _set_stage(meeting_id, "diarizing", 40, "Identifying speakers")
    assignment = await asyncio.to_thread(diarize.diarize_segments, audio_path, result.segments)
    assignment = diarize.smooth_speakers(result.segments, assignment)

    utterances = [
        analysis.Utterance(
            speaker=assignment.get(i, "SPEAKER_00"),
            start=seg.start,
            end=seg.end,
            text=seg.text,
        )
        for i, seg in enumerate(result.segments)
    ]

    # Merge consecutive same-speaker segments so the transcript reads like a
    # conversation rather than a list of fragments.
    merged = _merge_consecutive(utterances)

    tags = sorted({u.speaker for u in merged})
    speaker_names = {tag: f"Speaker {i + 1}" for i, tag in enumerate(tags)}

    # --- 3. Analyse ----------------------------------------------------------
    await _set_stage(meeting_id, "analyzing", 60, "Summarising and extracting actions")
    transcript_text = analysis.format_transcript(merged, speaker_names)
    analysis_result = await analysis.analyze(merged, speaker_names)

    title = None
    if not owner_named_it:
        try:
            title = await analysis.suggest_title(transcript_text)
        except Exception as e:
            log.warning("Title suggestion failed (non-fatal): %s", e)

    # --- 4. Index for retrieval ---------------------------------------------
    await _set_stage(meeting_id, "indexing", 80, "Building the meeting index")
    chunks = rag.build_chunks(merged, speaker_names)
    chunks = await rag.embed_chunks(chunks)

    # --- 5. Persist ----------------------------------------------------------
    await _set_stage(meeting_id, "indexing", 92, "Saving results")
    async with SessionLocal() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            return

        # Idempotent: a re-process wipes prior derived rows rather than duplicating.
        for model in (TranscriptSegment, TranscriptChunk, ActionItem, Speaker):
            await db.execute(delete(model).where(model.meeting_id == meeting_id))

        stats = _speaker_stats(merged)
        for i, tag in enumerate(tags):
            s = stats.get(tag, {"talk": 0.0, "words": 0, "count": 0})
            db.add(
                Speaker(
                    meeting_id=meeting_id,
                    tag=tag,
                    display_name=speaker_names[tag],
                    talk_seconds=round(s["talk"], 2),
                    word_count=s["words"],
                    segment_count=s["count"],
                    color=diarize.speaker_color(i),
                )
            )

        for u in merged:
            db.add(
                TranscriptSegment(
                    meeting_id=meeting_id,
                    speaker_tag=u.speaker,
                    start_time=round(u.start, 2),
                    end_time=round(u.end, 2),
                    text_enc=encrypt_text(u.text),
                    language=result.language,
                    confidence=0.0,
                )
            )

        for c in chunks:
            db.add(
                TranscriptChunk(
                    meeting_id=meeting_id,
                    chunk_index=c["chunk_index"],
                    text_enc=encrypt_text(c["text"]),
                    speakers=c.get("speakers"),
                    start_time=round(c["start_time"], 2),
                    end_time=round(c["end_time"], 2),
                    embedding=c.get("embedding"),
                )
            )

        for item in analysis_result.action_items:
            db.add(
                ActionItem(
                    meeting_id=meeting_id,
                    task_enc=encrypt_text(item.task),
                    owner_label=item.owner_label,
                    speaker_tag=item.speaker_tag,
                    due_text=item.due_text,
                    priority=item.priority,
                    quote_time=item.quote_time,
                )
            )

        meeting.summary_enc = encrypt_text(analysis_result.summary)
        meeting.transcript_text_enc = encrypt_text(transcript_text)
        meeting.topics = analysis_result.topics
        meeting.sentiment = analysis_result.sentiment
        meeting.language = result.language
        meeting.duration_seconds = round(result.duration, 2)
        meeting.status = "ready"
        meeting.progress = 100
        meeting.stage_label = "Ready"
        meeting.error_message = None
        meeting.processed_at = datetime.now(timezone.utc)
        if title:
            meeting.title = title

        await db.commit()

    log.info("Meeting %s processed: %d segments, %d speakers", meeting_id, len(merged), len(tags))


def _merge_consecutive(utterances: list, max_gap: float = 1.2) -> list:
    """Join back-to-back segments from the same speaker into one utterance."""
    if not utterances:
        return []
    merged = [
        analysis.Utterance(
            speaker=utterances[0].speaker,
            start=utterances[0].start,
            end=utterances[0].end,
            text=utterances[0].text,
        )
    ]
    for u in utterances[1:]:
        last = merged[-1]
        if u.speaker == last.speaker and (u.start - last.end) <= max_gap:
            last.text = f"{last.text} {u.text}".strip()
            last.end = u.end
        else:
            merged.append(
                analysis.Utterance(speaker=u.speaker, start=u.start, end=u.end, text=u.text)
            )
    return merged


def _speaker_stats(utterances: list) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for u in utterances:
        s = stats.setdefault(u.speaker, {"talk": 0.0, "words": 0, "count": 0})
        s["talk"] += max(0.0, u.end - u.start)
        s["words"] += len(u.text.split())
        s["count"] += 1
    return stats
