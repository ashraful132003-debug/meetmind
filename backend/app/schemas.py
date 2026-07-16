"""Pydantic request/response models.

These are the API contract. Note what is absent from the response models:
password hashes, owner ids, raw embeddings, file system paths. The client is
given what it needs to render and nothing else.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# --- Auth --------------------------------------------------------------------

_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "qwerty123",
    "letmein1", "welcome1", "admin123", "iloveyou", "abc12345", "meetmind",
}


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_enough(cls, v: str) -> str:
        """Length is the dominant factor, so the floor is 10 rather than a pile
        of character-class rules that push people toward P@ssw0rd1."""
        if v.lower() in _COMMON_PASSWORDS:
            raise ValueError("This password is too common. Please choose something less guessable.")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one number.")
        if len(set(v)) < 5:
            raise ValueError("Password is too repetitive. Please add more variety.")
        return v

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Name cannot be blank.")
        return cleaned


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class SessionInfo(BaseModel):
    id: uuid.UUID
    user_agent: str
    ip_address: str
    created_at: datetime
    last_used_at: datetime


# --- Meetings ----------------------------------------------------------------


class SpeakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tag: str
    display_name: str
    talk_seconds: float
    word_count: int
    segment_count: int
    color: str


class SegmentOut(BaseModel):
    id: uuid.UUID
    speaker_tag: str
    speaker_name: str
    start_time: float
    end_time: float
    text: str


class ActionItemOut(BaseModel):
    id: uuid.UUID
    task: str
    owner_label: str
    speaker_tag: str | None
    due_text: str | None
    priority: str
    done: bool
    quote_time: float | None


class MeetingListItem(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    progress: int
    stage_label: str
    duration_seconds: float
    language: str | None
    topics: list[str] | None
    sentiment: str | None
    speaker_count: int
    action_item_count: int
    open_action_count: int
    created_at: datetime
    error_message: str | None


class MeetingDetail(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    progress: int
    stage_label: str
    source: str
    audio_filename: str | None
    duration_seconds: float
    language: str | None
    summary: str | None
    topics: list[str] | None
    sentiment: str | None
    created_at: datetime
    processed_at: datetime | None
    error_message: str | None
    speakers: list[SpeakerOut]
    action_items: list[ActionItemOut]
    audio_url: str | None


class MeetingCreated(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    message: str


class RenameMeetingRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def clean(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Title cannot be blank.")
        return cleaned


class RenameSpeakerRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def clean(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Speaker name cannot be blank.")
        return cleaned


class ToggleActionRequest(BaseModel):
    done: bool


class TranscriptResponse(BaseModel):
    meeting_id: uuid.UUID
    language: str | None
    segments: list[SegmentOut]


# --- Chat --------------------------------------------------------------------


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def clean(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Question cannot be blank.")
        return cleaned


class Citation(BaseModel):
    start_time: float
    end_time: float
    timestamp: str
    speakers: list[str]
    score: float
    preview: str


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[Citation] | None
    created_at: datetime


class ChatResponse(BaseModel):
    answer: ChatMessageOut
    suggestions: list[str] = []


# --- Memory (cross-meeting chat) ---------------------------------------------


class MemoryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def clean(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Question cannot be blank.")
        return cleaned


class MemoryCitation(BaseModel):
    meeting_id: str
    meeting_title: str
    meeting_date: str
    start_time: float
    end_time: float
    timestamp: str
    speakers: list[str]
    score: float
    preview: str


class MemoryResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[MemoryCitation] | None
    created_at: datetime
    # Shown in the UI: an answer drawn from 12 meetings is a different claim from
    # one drawn from 2, and the user should be able to see which.
    searched_meetings: int
    time_filter: str | None


# --- Unified action board ----------------------------------------------------


class ActionBoardItem(BaseModel):
    id: uuid.UUID
    task: str
    owner_label: str
    due_text: str | None
    priority: str
    done: bool
    quote_time: float | None
    meeting_id: uuid.UUID
    meeting_title: str
    meeting_date: datetime


class ActionBoard(BaseModel):
    items: list[ActionBoardItem]
    total: int
    open_count: int
    done_count: int
    owners: list[dict]


# --- AI follow-up email ------------------------------------------------------


class FollowUpRequest(BaseModel):
    tone: str = Field(default="professional")
    note: str = Field(default="", max_length=500)

    @field_validator("tone")
    @classmethod
    def known_tone(cls, v: str) -> str:
        allowed = {"professional", "friendly", "brief", "formal"}
        v = v.strip().lower()
        if v not in allowed:
            raise ValueError(f"Tone must be one of: {', '.join(sorted(allowed))}")
        return v


class FollowUpDraft(BaseModel):
    subject: str
    body: str
    tone: str


# --- Analytics ---------------------------------------------------------------


class SpeakerShare(BaseModel):
    name: str
    tag: str
    color: str
    talk_seconds: float
    share_percent: float
    word_count: int
    words_per_minute: float


class TimelineBlock(BaseModel):
    speaker_tag: str
    speaker_name: str
    color: str
    start_time: float
    end_time: float


class MeetingAnalytics(BaseModel):
    meeting_id: uuid.UUID
    duration_seconds: float
    total_words: int
    speaker_count: int
    speakers: list[SpeakerShare]
    timeline: list[TimelineBlock]
    topics: list[str]
    sentiment: str | None
    balance_score: float
    longest_monologue_seconds: float
    longest_monologue_speaker: str | None


class WorkspaceStats(BaseModel):
    total_meetings: int
    ready_meetings: int
    processing_meetings: int
    total_duration_seconds: float
    total_action_items: int
    open_action_items: int
    hours_saved_estimate: float
    top_topics: list[dict]
    recent_activity: list[dict]


# --- Email -------------------------------------------------------------------


class SendEmailRequest(BaseModel):
    recipients: list[EmailStr] = Field(min_length=1, max_length=20)
    include_transcript: bool = False
    note: str = Field(default="", max_length=1000)


class EmailDeliveryOut(BaseModel):
    id: uuid.UUID
    recipients: list[str]
    subject: str
    transport: str
    status: str
    detail: str | None
    preview_url: str | None
    created_at: datetime


# --- System ------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    database: bool
    llm: dict
    whisper_model: str
    version: str
