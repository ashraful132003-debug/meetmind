"""Render the scripted meetings to real multi-speaker WAV files.

Uses the Windows SAPI voices already licensed on this machine - no online TTS
service, no account, no terms to worry about. Each speaker gets a distinct voice
so the diarizer has something real to separate.

The output is genuine audio: it goes through Whisper and the clustering diarizer
exactly like a recording from your microphone would. Nothing downstream knows or
cares that a synthesizer produced it.

Run:  python scripts/make_seed_audio.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_scripts import ALL_MEETINGS, RATES, VOICES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "storage" / "seed"
TMP_DIR = OUT_DIR / "_lines"

# Gaps between turns. Real conversation has beats; back-to-back audio with zero
# silence confuses both the VAD and the diarizer, and sounds obviously fake.
GAP_SAME_SPEAKER = 0.22
GAP_TURN_CHANGE = 0.45


def render_line(text: str, voice: str, rate: int, dest: Path) -> bool:
    """Render one utterance via SAPI. Returns False if it produced nothing."""
    # The text is passed through a file rather than the command line: quotes and
    # apostrophes in the script would otherwise break out of the PowerShell string.
    txt_file = dest.with_suffix(".txt")
    txt_file.write_text(text, encoding="utf-8")

    ps = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [IO.File]::ReadAllText('{txt_file}', [Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{
    $s.SelectVoice('{voice}')
    $s.Rate = {rate}
    $s.SetOutputToWaveFile('{dest}')
    $s.Speak($text)
}} finally {{
    $s.Dispose()
}}
"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            print(f"    [warn] SAPI failed: {r.stderr.strip()[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print("    [warn] SAPI timed out")
        return False
    finally:
        txt_file.unlink(missing_ok=True)

    return dest.exists() and dest.stat().st_size > 44  # bigger than a bare header


def concat_wavs(parts: list[tuple[Path, float, str]], dest: Path) -> tuple[float, list[dict]]:
    """Join rendered lines with silence between them.

    Returns (duration, ground_truth). The ground truth records exactly which
    speaker owns which time range - the concatenation point is the only place
    that information exists, so it is captured here. It makes diarization
    measurable instead of a matter of opinion.
    """
    if not parts:
        raise ValueError("no audio to join")

    with wave.open(str(parts[0][0]), "rb") as w0:
        params = w0.getparams()

    frames_out = bytearray()
    silence_frame = b"\x00" * params.sampwidth * params.nchannels
    bytes_per_second = params.framerate * params.sampwidth * params.nchannels
    truth: list[dict] = []

    for path, gap, speaker in parts:
        start = len(frames_out) / bytes_per_second
        with wave.open(str(path), "rb") as w:
            if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (
                params.nchannels,
                params.sampwidth,
                params.framerate,
            ):
                raise ValueError(f"{path.name} has a different format to the first clip")
            frames_out += w.readframes(w.getnframes())
        end = len(frames_out) / bytes_per_second
        truth.append({"speaker": speaker, "start": round(start, 3), "end": round(end, 3)})
        frames_out += silence_frame * int(params.framerate * gap)

    with wave.open(str(dest), "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(bytes(frames_out))

    return len(frames_out) / bytes_per_second, truth


def build(meeting: dict) -> Path | None:
    slug = meeting["slug"]
    lines = meeting["lines"]
    print(f"\n  {slug}: rendering {len(lines)} lines...")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    parts: list[tuple[Path, float, str]] = []

    for i, (speaker, text) in enumerate(lines):
        voice = VOICES[speaker]
        rate = RATES[speaker]
        dest = TMP_DIR / f"{slug}-{i:03d}.wav"

        if not render_line(text, voice, rate, dest):
            print(f"    [error] line {i} ({speaker}) failed to render")
            return None

        next_speaker = lines[i + 1][0] if i + 1 < len(lines) else None
        gap = GAP_SAME_SPEAKER if next_speaker == speaker else GAP_TURN_CHANGE
        parts.append((dest, gap, speaker))

        if (i + 1) % 10 == 0:
            print(f"    ...{i + 1}/{len(lines)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{slug}.wav"
    duration, truth = concat_wavs(parts, dest)

    (OUT_DIR / f"{slug}.truth.json").write_text(
        json.dumps({"slug": slug, "duration": round(duration, 2), "turns": truth}, indent=2),
        encoding="utf-8",
    )

    for p, _, _ in parts:
        p.unlink(missing_ok=True)

    size_mb = dest.stat().st_size / (1024 * 1024)
    speakers = sorted({t["speaker"] for t in truth})
    print(
        f"    -> {dest.name}  {int(duration // 60)}m {int(duration % 60)}s  ({size_mb:.1f} MB)  "
        f"{len(speakers)} speakers, {len(truth)} turns"
    )
    return dest


def main() -> int:
    if sys.platform != "win32":
        print("[error] This uses Windows SAPI and only runs on Windows.")
        return 1

    print("Generating seed meeting audio with Windows SAPI voices")
    print("=" * 60)

    built = []
    for meeting in ALL_MEETINGS:
        path = build(meeting)
        if path:
            built.append(path)

    if TMP_DIR.exists():
        try:
            TMP_DIR.rmdir()
        except OSError:
            pass

    print("\n" + "=" * 60)
    print(f"  {len(built)}/{len(ALL_MEETINGS)} meetings rendered into {OUT_DIR}")
    print("=" * 60)
    return 0 if len(built) == len(ALL_MEETINGS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
