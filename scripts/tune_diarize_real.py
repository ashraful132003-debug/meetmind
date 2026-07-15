"""Measure diarization on the REAL pipeline, not an idealised version of it.

Why this exists: `tune_diarize.py` feeds the diarizer the ground-truth turn
boundaries, which flatters it badly. The app never has those. It has Whisper's
segments, which are shorter, split mid-turn, and occasionally straddle a speaker
change. Short segments give noisier embeddings, and noisy embeddings over-split
into speakers who do not exist.

Measured difference on the same audio: ideal segmentation reported 3/3/3 speakers,
the real pipeline reported 5. Same code, same threshold - the benchmark was just
measuring an easier problem than the product solves.

So this runs actual Whisper, assigns each segment its true speaker by maximum
time overlap with the ground truth, and scores what the user would really get.

Run:  python scripts/tune_diarize_real.py
"""

from __future__ import annotations

import itertools
import json
import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services import diarize, transcribe  # noqa: E402

SEED = Path(__file__).resolve().parents[1] / "storage" / "seed"
CACHE = SEED / "_whisper_cache.pkl"

SLUGS = ["sprint-standup", "client-call", "product-planning"]


def whisper_segments(slug: str):
    """Transcribe once and cache - Whisper is slow and deterministic here."""
    cache: dict = {}
    if CACHE.exists():
        try:
            cache = pickle.loads(CACHE.read_bytes())
        except Exception:
            cache = {}

    if slug in cache:
        return cache[slug]

    print(f"  transcribing {slug} (cached after this)...", flush=True)
    result = transcribe.transcribe(SEED / f"{slug}.wav")
    segs = [(s.start, s.end) for s in result.segments]
    cache[slug] = segs
    CACHE.write_bytes(pickle.dumps(cache))
    return segs


class Seg:
    def __init__(self, start: float, end: float):
        self.start = start
        self.end = end


def true_speaker_for(start: float, end: float, turns: list[dict]) -> str | None:
    """The speaker whose ground-truth turn overlaps this segment the most."""
    best, best_overlap = None, 0.0
    for t in turns:
        overlap = min(end, t["end"]) - max(start, t["start"])
        if overlap > best_overlap:
            best, best_overlap = t["speaker"], overlap
    return best


def accuracy(pred: list[str], true: list[str], weights: list[float]) -> float:
    """Time-weighted accuracy under the best cluster->speaker mapping.

    Weighting by duration is the honest metric: mislabelling a 20-second
    explanation matters more than mislabelling a one-word "yeah".
    """
    pred_ids = sorted(set(pred))
    true_ids = sorted(set(true))
    total = sum(weights) or 1.0

    best = 0.0
    for perm in itertools.permutations(true_ids, min(len(pred_ids), len(true_ids))):
        mapping = dict(zip(pred_ids, perm))
        hit = sum(w for p, t, w in zip(pred, true, weights) if mapping.get(p) == t)
        best = max(best, hit / total)
    return best


_EMB: dict[tuple[str, str], tuple] = {}


def embed_all(slug: str, engine: str):
    key = (slug, engine)
    if key in _EMB:
        return _EMB[key]

    truth = json.loads((SEED / f"{slug}.truth.json").read_text(encoding="utf-8"))
    segs = whisper_segments(slug)
    audio = diarize.load_mono_16k(SEED / f"{slug}.wav")
    fn = diarize.neural_embedding if engine == "neural" else diarize.voice_embedding

    vectors, kept = [], []
    for i, (s, e) in enumerate(segs):
        v = fn(audio[int(s * 16000) : int(e * 16000)])
        if v is not None:
            vectors.append(v)
            kept.append(i)

    seg_objs = [Seg(s, e) for s, e in segs]
    true = [true_speaker_for(s, e, truth["turns"]) for s, e in segs]
    weights = [e - s for s, e in segs]

    _EMB[key] = (vectors, kept, seg_objs, true, weights)
    return _EMB[key]


def evaluate(threshold: float, slug: str, engine: str, merge: bool) -> tuple[float, int]:
    vectors, kept, segs, true, weights = embed_all(slug, engine)
    if len(vectors) < 2:
        return 0.0, 0

    matrix = np.vstack(vectors)
    if engine == "handbuilt":
        matrix = diarize.standardize(matrix)

    labels = diarize._agglomerative(diarize._cosine_distances(matrix), threshold, 8)
    pred = {idx: f"SPEAKER_{labels[k]:02d}" for k, idx in enumerate(kept)}

    last = "SPEAKER_00"
    assignment = {}
    for i in range(len(segs)):
        last = pred.get(i, last)
        assignment[i] = last

    if merge:
        assignment = diarize.smooth_speakers(segs, assignment)

    full = [assignment[i] for i in range(len(segs))]
    keep = [i for i, t in enumerate(true) if t is not None]
    if not keep:
        return 0.0, len(set(full))

    return (
        accuracy([full[i] for i in keep], [true[i] for i in keep], [weights[i] for i in keep]),
        len(set(full)),
    )


def sweep(engine: str, label: str, thresholds: list[float]) -> None:
    print(f"\n{label}")
    print("=" * 74)
    print(f"{'threshold':<11} {'accuracy':<11} {'speakers found':<18} per-meeting")
    print("-" * 74)

    results = []
    for thr in thresholds:
        accs, founds = [], []
        for slug in SLUGS:
            a, f = evaluate(thr, slug, engine, merge=True)
            accs.append(a)
            founds.append(f)
        mean = sum(accs) / len(accs)
        results.append((mean, thr, founds))
        per = "  ".join(f"{a * 100:.0f}%" for a in accs)
        print(f"{thr:<11} {mean * 100:>6.1f}%     {str(founds):<18} {per}")

    best = max(results, key=lambda r: r[0])
    print("-" * 74)
    print(f"best: threshold={best[1]}  ->  {best[0] * 100:.1f}%  speakers={best[2]}  (true = 3,3,3)")


def main() -> int:
    missing = [s for s in SLUGS if not (SEED / f"{s}.truth.json").exists()]
    if missing:
        print(f"[error] Missing ground truth: {', '.join(missing)}")
        return 1

    print("Diarization on REAL Whisper segments (what the app actually does)")
    print("true = 3 speakers per meeting")

    for slug in SLUGS:
        segs = whisper_segments(slug)
        truth = json.loads((SEED / f"{slug}.truth.json").read_text(encoding="utf-8"))
        print(f"  {slug}: {len(segs)} whisper segments vs {len(truth['turns'])} real turns")

    sweep("handbuilt", "handbuilt (MFCC + pitch + centroid, standardized)",
          [0.9, 1.0, 1.1, 1.2, 1.3])

    if diarize.get_speaker_model() is not None:
        sweep("neural", "neural (WeSpeaker ResNet34 ONNX)",
              [0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.9])

    print(f"\nShipping: NEURAL_THRESHOLD={diarize.NEURAL_THRESHOLD}, "
          f"HANDBUILT_THRESHOLD={diarize.HANDBUILT_THRESHOLD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
