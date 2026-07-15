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


def transcribe(audio_path: str | Path, language: str | None = None) -> TranscriptionResult:
    """Blocking. Callers run this in a worker thread — never on the event loop."""
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
