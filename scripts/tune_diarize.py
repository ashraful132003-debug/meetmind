"""Measure diarization accuracy against ground truth, and compare approaches.

The seed audio is concatenated from individual TTS lines, so we know exactly who
spoke in every time range. That turns diarization from "looks about right" into a
number, which is the only way to tell whether a change helped.

Metric: turn-level accuracy after optimally mapping predicted cluster ids to true
speakers (the Hungarian assignment, brute-forced - there are at most a handful of
speakers). Cluster labels are arbitrary, so "SPEAKER_00" being called
"SPEAKER_01" is not an error; putting two different people in one cluster is.

Run:  python scripts/tune_diarize.py
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services import diarize  # noqa: E402

SEED = Path(__file__).resolve().parents[1] / "storage" / "seed"


class Turn:
    """Stands in for a Whisper segment - diarize_segments only reads .start/.end."""

    def __init__(self, start: float, end: float):
        self.start = start
        self.end = end


def load(slug: str):
    truth = json.loads((SEED / f"{slug}.truth.json").read_text(encoding="utf-8"))
    turns = [Turn(t["start"], t["end"]) for t in truth["turns"]]
    labels = [t["speaker"] for t in truth["turns"]]
    return SEED / f"{slug}.wav", turns, labels


def accuracy(pred: list[str], true: list[str]) -> float:
    """Best achievable accuracy over all cluster->speaker mappings."""
    pred_ids = sorted(set(pred))
    true_ids = sorted(set(true))

    best = 0.0
    # Try every way of assigning predicted clusters to true speakers.
    for perm in itertools.permutations(true_ids, min(len(pred_ids), len(true_ids))):
        mapping = dict(zip(pred_ids, perm))
        hits = sum(1 for p, t in zip(pred, true) if mapping.get(p) == t)
        best = max(best, hits / len(true))
    return best


_CACHE: dict[tuple[str, str], tuple] = {}


def embed_all(slug: str, engine: str):
    """Embeddings are the slow part; the threshold sweep reuses them."""
    key = (slug, engine)
    if key in _CACHE:
        return _CACHE[key]

    audio_path, turns, true_labels = load(slug)
    audio = diarize.load_mono_16k(audio_path)
    fn = diarize.neural_embedding if engine == "neural" else diarize.voice_embedding

    vectors, kept = [], []
    for i, t in enumerate(turns):
        a, b = int(t.start * diarize.SAMPLE_RATE), int(t.end * diarize.SAMPLE_RATE)
        v = fn(audio[a:b])
        if v is not None:
            vectors.append(v)
            kept.append(i)

    _CACHE[key] = (vectors, kept, turns, true_labels)
    return _CACHE[key]


def evaluate(threshold: float, slug: str, engine: str, smooth: bool = True) -> tuple[float, int]:
    vectors, kept, turns, true_labels = embed_all(slug, engine)
    if len(vectors) < 2:
        return 0.0, 0

    matrix = np.vstack(vectors)
    if engine == "handbuilt":
        matrix = diarize.standardize(matrix)

    labels = diarize._agglomerative(diarize._cosine_distances(matrix), threshold, 8)
    pred = {idx: f"SPEAKER_{labels[k]:02d}" for k, idx in enumerate(kept)}

    last = "SPEAKER_00"
    assignment = {}
    for i in range(len(turns)):
        last = pred.get(i, last)
        assignment[i] = last

    if smooth:
        assignment = diarize.smooth_speakers(turns, assignment)

    full_pred = [assignment[i] for i in range(len(turns))]
    return accuracy(full_pred, true_labels), len(set(full_pred))


def sweep(engine: str, label: str, thresholds: list[float], slugs: list[str]) -> tuple[float, float, list[int]]:
    """`engine` is the key the code branches on ('neural' | 'handbuilt').
    `label` is only for display - keeping them separate matters, because passing
    a pretty label as the key silently makes every branch fall through to the
    default and you end up measuring the same configuration twice."""
    print(f"\n{label}")
    print("=" * 72)
    print(f"{'threshold':<11} {'accuracy':<11} {'speakers found':<18} per-meeting")
    print("-" * 72)

    results = []
    for thr in thresholds:
        accs, founds = [], []
        for slug in slugs:
            a, found = evaluate(thr, slug, engine)
            accs.append(a)
            founds.append(found)
        mean_acc = sum(accs) / len(accs)
        results.append((mean_acc, thr, founds))
        per = "  ".join(f"{a * 100:.0f}%" for a in accs)
        print(f"{thr:<11} {mean_acc * 100:>6.1f}%     {str(founds):<18} {per}")

    best = max(results, key=lambda r: r[0])
    print("-" * 72)
    print(f"best: threshold={best[1]}  ->  {best[0] * 100:.1f}%  speakers={best[2]}")
    return best[0], best[1], best[2]


def main() -> int:
    slugs = ["sprint-standup", "client-call", "product-planning"]
    missing = [s for s in slugs if not (SEED / f"{s}.truth.json").exists()]
    if missing:
        print(f"[error] Missing ground truth for: {', '.join(missing)}")
        print("        Run: python scripts/make_seed_audio.py")
        return 1

    print("Diarization accuracy vs ground truth (true = 3 speakers per meeting)")

    hb_acc, hb_thr, _ = sweep(
        "handbuilt",
        "handbuilt (MFCC + pitch + centroid, standardized)",
        [0.8, 0.9, 1.0, 1.1, 1.2],
        slugs,
    )

    if diarize.get_speaker_model() is None:
        print("\n[skip] Neural engine: storage/models/wespeaker.onnx not found.")
        print(f"\nShipping: handbuilt, threshold={hb_thr}, {hb_acc * 100:.1f}%")
        return 0

    nn_acc, nn_thr, _ = sweep(
        "neural",
        "neural (WeSpeaker ResNet34 ONNX)",
        [0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7],
        slugs,
    )

    print("\n" + "=" * 72)
    print(f"  handbuilt: {hb_acc * 100:.1f}%  (threshold {hb_thr})")
    print(f"  neural:    {nn_acc * 100:.1f}%  (threshold {nn_thr})")
    winner = "neural" if nn_acc > hb_acc else "handbuilt"
    print(f"\n  -> {winner} wins")
    print(f"  diarize.py currently ships NEURAL_THRESHOLD={diarize.NEURAL_THRESHOLD}, "
          f"HANDBUILT_THRESHOLD={diarize.HANDBUILT_THRESHOLD}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
