"""Speech-to-text via faster-whisper, running locally on GPU when available.

Model choice notes:
* `small` is the sweet spot on a 4GB-VRAM RTX 3050 — noticeably better than
  `base` on Indian-accented English and Hindi, still comfortably fast.
* Whisper natively handles Hindi and, importantly, Hinglish code-switching within
  a single utterance, which is exactly what real Indian standups sound like.
* The model is loaded once and cached — reloading per request would dominate
  runtime.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from ..config import settings

log = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class RawSegment:
    start: float
    end: float
    text: str
    confidence: float
    words: list[Word]


@dataclass
class TranscriptionResult:
    segments: list[RawSegment]
    language: str
    duration: float


def _cuda_available() -> bool:
    """Detect a usable NVIDIA GPU without pulling in PyTorch.

    faster-whisper runs on CTranslate2, which does not need Torch — importing
    Torch purely for `cuda.is_available()` would add ~2.5GB of dependencies for
    one boolean. `nvidia-smi` shipping with the driver is a reliable proxy.
    CTranslate2 still needs cuDNN present; if it isn't, the model load raises
    and we fall back to CPU rather than crashing.
    """
    import shutil
    import subprocess

    exe = shutil.which("nvidia-smi")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "-L"], capture_output=True, timeout=10, text=True)
        return r.returncode == 0 and "GPU 0" in r.stdout
    except Exception:
        return False


def _resolve_device() -> tuple[str, str]:
    """Pick CUDA when it is genuinely usable, else CPU. A broken CUDA install
    should degrade to slow-but-working, never to a crash."""
    want = settings.whisper_device.lower()
    if want == "cpu":
        return "cpu", "int8"
    if _cuda_available():
        return "cuda", "float16" if want in {"auto", "cuda"} else settings.whisper_compute_type
    if want == "cuda":
        log.warning("WHISPER_DEVICE=cuda requested but no NVIDIA GPU detected; falling back to CPU")
    return "cpu", "int8"


def _smoke_test(model) -> None:
    """Run a real inference on a moment of silence.

    Loading is not proof of anything: CTranslate2 constructs a CUDA model happily
    and only discovers a missing cuBLAS/cuDNN DLL when it runs the first kernel.
    Without this, a machine with an NVIDIA GPU but no CUDA runtime would load
    fine and then blow up on the user's first real meeting. Better to find out at
    startup, on a tenth of a second of audio.
    """
    import numpy as np

    silence = np.zeros(SAMPLE_RATE // 10, dtype=np.float32)
    segments, _ = model.transcribe(silence, beam_size=1, vad_filter=False, language="en")
    list(segments)  # generator - must be consumed for the kernels to actually run


def get_model():
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        from faster_whisper import WhisperModel

        device, compute = _resolve_device()

        if device == "cuda":
            try:
                log.info("Loading Whisper '%s' on cuda (%s)", settings.whisper_model, compute)
                candidate = WhisperModel(settings.whisper_model, device="cuda", compute_type=compute)
                _smoke_test(candidate)
                _model = candidate
                log.info("Whisper running on GPU")
                return _model
            except Exception as e:
                log.warning(
                    "GPU unusable (%s: %s) — falling back to CPU. To enable GPU, run: "
                    "pip install nvidia-cublas-cu12 nvidia-cudnn-cu12",
                    type(e).__name__,
                    str(e)[:120],
                )

        log.info("Loading Whisper '%s' on cpu (int8)", settings.whisper_model)
        _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8", cpu_threads=0)
        log.info("Whisper running on CPU")
        return _model


# Groq's Whisper reports the language as a full English name ("English", "Hindi")
# while local faster-whisper reports an ISO code ("en", "hi"). The rest of the app
# — the database column, the UI's language labels — expects the code. Without this
# the UI would show "ENGLISH" instead of "English", and a meeting transcribed on
# the server would be labelled differently from the identical meeting transcribed
# locally.
_LANGUAGE_CODES = {
    "english": "en", "hindi": "hi", "urdu": "ur", "tamil": "ta", "telugu": "te",
    "bengali": "bn", "marathi": "mr", "gujarati": "gu", "kannada": "kn",
    "malayalam": "ml", "punjabi": "pa", "spanish": "es", "french": "fr",
    "german": "de", "chinese": "zh", "japanese": "ja", "arabic": "ar",
    "portuguese": "pt", "russian": "ru",
}


def _normalise_language(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    if len(v) <= 3:  # already a code
        return v
    return _LANGUAGE_CODES.get(v, v[:2])


def _transcribe_groq(audio_path: str | Path, language: str | None = None) -> TranscriptionResult:
    """Transcribe via Groq's free Whisper endpoint.

    This exists so the app can be DEPLOYED. Local Whisper needs ~2GB of RAM,
    every free host gives 512MB, and Groq is the only free tier (no card) that
    serves Whisper as well as a chat model.

    The trade-off is real and must not be glossed over: in this mode the audio
    leaves the machine. The privacy guarantee only holds with
    TRANSCRIPTION_PROVIDER=local. See DEPLOY.md.
    """
    import httpx

    if not settings.groq_api_key:
        raise RuntimeError(
            "TRANSCRIPTION_PROVIDER=groq but GROQ_API_KEY is empty. "
            "Get a free key (no card) at https://console.groq.com/keys"
        )

    path = Path(audio_path)
    try:
        with path.open("rb") as f:
            data = {
                "model": settings.groq_whisper_model,
                "response_format": "verbose_json",  # needed for segment timings
                "timestamp_granularities[]": "segment",
            }
            if language:
                data["language"] = language

            r = httpx.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files={"file": (path.name, f, "application/octet-stream")},
                data=data,
                timeout=300.0,
            )
            r.raise_for_status()
            payload = r.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 413:
            raise RuntimeError(
                "Groq rejected the audio as too large (its free tier caps upload size). "
                "Use a shorter recording, or switch to TRANSCRIPTION_PROVIDER=local."
            ) from e
        if e.response.status_code == 429:
            raise RuntimeError("Groq rate limit reached. Wait a minute and retry.") from e
        raise RuntimeError(f"Groq transcription failed ({e.response.status_code}): {e.response.text[:200]}") from e

    segments: list[RawSegment] = []
    for seg in payload.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            RawSegment(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=text,
                # Groq reports no_speech_prob rather than a confidence; invert it
                # so the field means the same thing as on the local path.
                confidence=round(1.0 - float(seg.get("no_speech_prob", 0.0)), 3),
                words=[],
            )
        )

    duration = float(payload.get("duration") or (segments[-1].end if segments else 0.0))
    return TranscriptionResult(
        segments=segments,
        language=_normalise_language(payload.get("language")) or language or "en",
        duration=duration,
    )


def transcribe(audio_path: str | Path, language: str | None = None) -> TranscriptionResult:
    """Blocking. Callers run this in a worker thread — never on the event loop."""
    if settings.transcription_provider.lower() == "groq":
        return _transcribe_groq(audio_path, language)

    model = get_model()
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language,              # None => auto-detect (Hindi/English/mixed)
        task="transcribe",              # never "translate" — preserve what was said
        beam_size=5,
        vad_filter=True,                # drop silence so timestamps stay honest
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=True,           # needed to align speakers to words
        condition_on_previous_text=False,  # avoids runaway repetition loops
    )

    segments: list[RawSegment] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        words = [
            Word(start=w.start, end=w.end, text=w.word)
            for w in (seg.words or [])
            if w.start is not None and w.end is not None
        ]
        # avg_logprob is a log probability; exp() maps it to a 0-1 confidence.
        import math

        confidence = min(1.0, max(0.0, math.exp(seg.avg_logprob))) if seg.avg_logprob is not None else 0.0
        segments.append(
            RawSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=text,
                confidence=round(confidence, 3),
                words=words,
            )
        )

    duration = float(getattr(info, "duration", 0.0) or (segments[-1].end if segments else 0.0))
    return TranscriptionResult(
        segments=segments,
        language=getattr(info, "language", None) or language or "en",
        duration=duration,
    )
