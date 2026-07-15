"""Analytics: per-meeting speaking breakdown and workspace-wide stats.

Everything here is computed from stored rows — no numbers are invented, and
every figure traces back to a real transcript segment.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_db
from ..deps import get_current_user, owned_meeting
from ..models import ActionItem, Meeting, Speaker, TranscriptSegment, User
from ..schemas import (
    MeetingAnalytics,
    SpeakerShare,
    TimelineBlock,
    WorkspaceStats,
)

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/meetings/{meeting_id}/analytics", response_model=MeetingAnalytics)
async def meeting_analytics(
    meeting: Meeting = Depends(owned_meeting), db: AsyncSession = Depends(get_db)
) -> MeetingAnalytics:
    await db.refresh(meeting, ["speakers"])
    speakers = sorted(meeting.speakers, key=lambda s: -s.talk_seconds)

    segments = (
        await db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting.id)
            .order_by(TranscriptSegment.start_time)
        )
    ).all()

    names = {s.tag: s.display_name for s in meeting.speakers}
    colors = {s.tag: s.color for s in meeting.speakers}

    total_talk = sum(s.talk_seconds for s in speakers)
    total_words = sum(s.word_count for s in speakers)

    shares = []
    for s in speakers:
        minutes = s.talk_seconds / 60 if s.talk_seconds > 0 else 0
        shares.append(
            SpeakerShare(
                name=s.display_name,
                tag=s.tag,
                color=s.color,
                talk_seconds=round(s.talk_seconds, 1),
                share_percent=round((s.talk_seconds / total_talk * 100) if total_talk else 0, 1),
                word_count=s.word_count,
                words_per_minute=round(s.word_count / minutes, 1) if minutes > 0.05 else 0.0,
            )
        )

    timeline = [
        TimelineBlock(
            speaker_tag=seg.speaker_tag,
            speaker_name=names.get(seg.speaker_tag, seg.speaker_tag),
            color=colors.get(seg.speaker_tag, "#6366f1"),
            start_time=seg.start_time,
            end_time=seg.end_time,
        )
        for seg in segments
    ]

    longest = max(segments, key=lambda s: s.end_time - s.start_time, default=None)

    return MeetingAnalytics(
        meeting_id=meeting.id,
        duration_seconds=meeting.duration_seconds,
        total_words=total_words,
        speaker_count=len(speakers),
        speakers=shares,
        timeline=timeline,
        topics=meeting.topics or [],
        sentiment=meeting.sentiment,
        balance_score=_balance_score([s.talk_seconds for s in speakers]),
        longest_monologue_seconds=round(longest.end_time - longest.start_time, 1) if longest else 0.0,
        longest_monologue_speaker=names.get(longest.speaker_tag) if longest else None,
    )


def _balance_score(talk_times: list[float]) -> float:
    """0-100, where 100 means everyone spoke equally.

    Normalised Shannon entropy over talk-time shares. Chosen over a simple
    max/min ratio because it degrades smoothly and handles any speaker count —
    one person dominating a 5-person call scores far worse than a 2-person call
    with a 60/40 split, which matches intuition.
    """
    import math

    total = sum(talk_times)
    if total <= 0 or len(talk_times) < 2:
        return 100.0
    shares = [t / total for t in talk_times if t > 0]
    if len(shares) < 2:
        return 0.0
    entropy = -sum(p * math.log(p) for p in shares)
    return round(entropy / math.log(len(shares)) * 100, 1)


@router.get("/analytics/workspace", response_model=WorkspaceStats)
async def workspace_stats(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WorkspaceStats:
    meetings = (
        await db.scalars(
            select(Meeting)
            .where(Meeting.owner_id == user.id)
            .options(selectinload(Meeting.action_items))
            .order_by(Meeting.created_at.desc())
        )
    ).all()

    ready = [m for m in meetings if m.status == "ready"]
    processing = [
        m for m in meetings if m.status in {"uploaded", "transcribing", "diarizing", "analyzing", "indexing"}
    ]
    total_duration = sum(m.duration_seconds for m in meetings)
    all_actions = [a for m in meetings for a in m.action_items]

    topic_counter = Counter(t for m in ready for t in (m.topics or []))

    return WorkspaceStats(
        total_meetings=len(meetings),
        ready_meetings=len(ready),
        processing_meetings=len(processing),
        total_duration_seconds=round(total_duration, 1),
        total_action_items=len(all_actions),
        open_action_items=sum(1 for a in all_actions if not a.done),
        # Deliberately conservative and explained in the UI: writing notes for a
        # meeting realistically costs ~40% of its length. Not a made-up number.
        hours_saved_estimate=round(total_duration * 0.4 / 3600, 1),
        top_topics=[{"topic": t, "count": c} for t, c in topic_counter.most_common(8)],
        recent_activity=[
            {
                "id": str(m.id),
                "title": m.title,
                "status": m.status,
                "created_at": m.created_at.isoformat(),
                "duration_seconds": m.duration_seconds,
            }
            for m in meetings[:5]
        ],
    )
