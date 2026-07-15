"""Transcribe + diarize one seed file and print the result.

Exercises the two hardest, least predictable parts of the pipeline (Whisper and
the clustering diarizer) in isolation, without needing the LLM. If this looks
right, the rest is plumbing.

Run:  python scripts/test_transcribe.py [path-to-audio]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services import diarize, transcribe  # noqa: E402


def ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def main() -> int:
    default = Path(__file__).resolve().parents[1] / "storage" / "seed" / "sprint-standup.wav"
    audio = Path(sys.argv[1]) if len(sys.argv) > 1 else default

    if not audio.exists():
        print(f"[error] No audio at {audio}")
        print("        Run: python scripts/make_seed_audio.py")
        return 1

    print(f"Audio: {audio.name}")
    print("=" * 72)

    print("\nLoading Whisper (first run downloads the model)...")
    t0 = time.perf_counter()
    device, compute = transcribe._resolve_device()
    print(f"  device={device} compute={compute}")

    result = transcribe.transcribe(audio)
    t_transcribe = time.perf_counter() - t0

    print(f"\nTranscribed in {t_transcribe:.1f}s")
    print(f"  language: {result.language}")
    print(f"  duration: {ts(result.duration)}")
    print(f"  segments: {len(result.segments)}")
    print(f"  speed:    {result.duration / max(t_transcribe, 0.01):.1f}x realtime")

    if not result.segments:
        print("\n[error] No speech detected.")
        return 1

    print("\nDiarizing...")
    t1 = time.perf_counter()
    assignment = diarize.diarize_segments(audio, result.segments)
    assignment = diarize.smooth_speakers(result.segments, assignment)
    t_diarize = time.perf_counter() - t1

    speakers = sorted(set(assignment.values()))
    print(f"  done in {t_diarize:.1f}s - found {len(speakers)} speakers: {', '.join(speakers)}")

    print("\n" + "=" * 72)
    print("TRANSCRIPT")
    print("=" * 72)
    for i, seg in enumerate(result.segments):
        who = assignment.get(i, "?")
        print(f"[{ts(seg.start)}] {who}: {seg.text}")

    print("\n" + "=" * 72)
    print("Talk time per speaker")
    print("=" * 72)
    totals: dict[str, float] = {}
    for i, seg in enumerate(result.segments):
        who = assignment.get(i, "?")
        totals[who] = totals.get(who, 0.0) + (seg.end - seg.start)
    total = sum(totals.values()) or 1
    for who, secs in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {who}: {ts(secs)}  ({secs / total * 100:.0f}%)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
