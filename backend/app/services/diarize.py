"""Speaker diarization — "who spoke when".

Two engines, picked automatically:

1. **WeSpeaker ResNet34** (preferred). A real speaker-recognition network trained
   on VoxCeleb, run through onnxruntime. 25MB, Apache-2.0, no account and no
   token — deliberately NOT pyannote, whose pretrained pipelines are gated behind
   a HuggingFace login and licence acceptance, which would mean a fresh user
   could not run this app without signing up somewhere.

   onnxruntime is already present as a faster-whisper dependency, so this costs
   one small download and no PyTorch.

2. **Hand-built features** (fallback). MFCC statistics + pitch + spectral
   centroid. Used automatically if the ONNX model is missing, so the app always
   works, just less accurately.

Both feed the same clustering. Measured on the seed meetings, where the true
speaker of every turn is known (scripts/tune_diarize.py):

    hand-built features   89.2%
    WeSpeaker ResNet34    see README

Speaker labels are user-editable regardless, because no diarizer is perfect and a
wrong label the user can fix beats a wrong label presented as truth.
"""

from __future__ import annotations

import logging
import math
import threading
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import settings

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
PALETTE = ["#6366f1", "#ec4899", "#14b8a6", "#f59e0b", "#8b5cf6", "#ef4444", "#22c55e", "#0ea5e9"]

# Clustering thresholds. Measured optima, not guesses, and NOT interchangeable:
# the two embedding types produce completely different distance scales.
#
# Tuned with scripts/tune_diarize_real.py, which runs real Whisper segmentation.
# That distinction is not academic. Tuning against ground-truth turn boundaries
# (tune_diarize.py) picked 0.5 and claimed 95.7%. On the segments Whisper actually
# produces - 44-57 of them where there are only 28-31 real turns, so shorter and
# noisier - that same 0.5 scores 70.2% and reports 5-8 speakers in a 3-person
# meeting. The honest optimum is 0.65 at 94.0%.
#
# Lesson worth keeping: tune on the input the system really gets, not the input
# you wish it got.
NEURAL_THRESHOLD = 0.65     # 94.0% time-weighted on real Whisper segments
HANDBUILT_THRESHOLD = 1.1   # 79.5% on the same benchmark

# --- Neural speaker embedding (WeSpeaker ResNet34 via ONNX) ------------------

_session = None
_session_lock = threading.Lock()
_session_tried = False

FBANK_MELS = 80
FBANK_WIN = 400   # 25ms @ 16k
FBANK_HOP = 160   # 10ms @ 16k
FBANK_NFFT = 512


def get_speaker_model():
    """Load the ONNX speaker model once. Returns None if it isn't available, so
    the caller can fall back rather than crash."""
    global _session, _session_tried

    if _session is not None or _session_tried:
        return _session

    with _session_lock:
        if _session is not None or _session_tried:
            return _session
        _session_tried = True

        model_path = settings.speaker_model_file
        if not model_path.exists():
            log.warning(
                "Speaker model not found at %s — falling back to hand-built features "
                "(measured 79.5%% vs 94.0%%). Run scripts/get_speaker_model.ps1 to fix.",
                model_path,
            )
            return None
        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            # Diarization runs in a worker thread while other stages may want the
            # CPU; let onnxruntime pick a sensible thread count rather than
            # grabbing every core.
            opts.log_severity_level = 3
            _session = ort.InferenceSession(
                str(model_path), sess_options=opts, providers=["CPUExecutionProvider"]
            )
            log.info("Speaker model loaded: WeSpeaker ResNet34 (ONNX)")
        except Exception as e:
            log.warning("Could not load the speaker model (%s) — using hand-built features", e)
            _session = None

    return _session


def _fbank(signal: np.ndarray) -> np.ndarray:
    """80-dim log mel filterbank, Kaldi-style — what WeSpeaker was trained on.

    Same pipeline as `mfcc` below but stopping before the DCT, since the network
    wants the filterbank energies rather than cepstral coefficients.
    """
    if len(signal) < FBANK_WIN:
        return np.zeros((0, FBANK_MELS), dtype=np.float32)

    # Kaldi scales to int16 range before extracting features; the network's
    # normalisation expects that magnitude.
    scaled = signal.astype(np.float32) * 32768.0

    emphasized = np.append(scaled[0], scaled[1:] - 0.97 * scaled[:-1]).astype(np.float32)

    n_frames = 1 + (len(emphasized) - FBANK_WIN) // FBANK_HOP
    if n_frames <= 0:
        return np.zeros((0, FBANK_MELS), dtype=np.float32)

    idx = np.arange(FBANK_WIN)[None, :] + FBANK_HOP * np.arange(n_frames)[:, None]
    frames = emphasized[idx]
    frames = frames - frames.mean(axis=1, keepdims=True)
    frames = frames * np.hamming(FBANK_WIN).astype(np.float32)

    spectrum = np.abs(np.fft.rfft(frames, FBANK_NFFT)) ** 2
    energies = np.maximum(spectrum @ _FBANK_FILTERS.T, 1e-10)
    return np.log(energies).astype(np.float32)


def neural_embedding(signal: np.ndarray) -> np.ndarray | None:
    """256-dim speaker embedding from WeSpeaker. None if unusable."""
    session = get_speaker_model()
    if session is None:
        return None
    if len(signal) < SAMPLE_RATE * 0.35:
        return None

    feats = _fbank(signal)
    if feats.shape[0] < 25:  # under ~0.25s of frames is not worth embedding
        return None

    # Cepstral mean normalisation over the utterance — removes channel/mic
    # colouring so the embedding describes the speaker, not the recording setup.
    feats = feats - feats.mean(axis=0, keepdims=True)

    try:
        out = session.run(None, {"input_features": feats[None, :, :].astype(np.float32)})[0]
    except Exception as e:
        log.warning("Speaker model inference failed: %s", e)
        return None

    vec = np.asarray(out[0], dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0 or not np.all(np.isfinite(vec)):
        return None
    # These embeddings are trained to be compared by cosine, so unit-normalise
    # here and compare directly. No standardisation: unlike the hand-built
    # features, the network already outputs a space where distance means identity.
    return (vec / norm).astype(np.float32)


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str


# --- Audio loading -----------------------------------------------------------


def load_mono_16k(path: str | Path) -> np.ndarray:
    """Load audio as mono float32 @16kHz. Uses the already-present ffmpeg (via
    pydub) for anything that isn't plain PCM wav."""
    path = Path(path)
    try:
        if path.suffix.lower() == ".wav":
            with wave.open(str(path), "rb") as w:
                if w.getsampwidth() == 2 and w.getnchannels() in (1, 2):
                    frames = w.readframes(w.getnframes())
                    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                    if w.getnchannels() == 2:
                        data = data.reshape(-1, 2).mean(axis=1)
                    if w.getframerate() != SAMPLE_RATE:
                        data = _resample(data, w.getframerate(), SAMPLE_RATE)
                    return data
    except Exception as e:
        log.debug("Fast wav path failed (%s); falling back to pydub", e)

    from pydub import AudioSegment

    seg = AudioSegment.from_file(str(path))
    seg = seg.set_channels(1).set_frame_rate(SAMPLE_RATE).set_sample_width(2)
    data = np.array(seg.get_array_of_samples(), dtype=np.float32) / 32768.0
    return data


def _resample(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return data
    n = int(len(data) * dst_rate / src_rate)
    if n <= 0:
        return data
    return np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data).astype(np.float32)


# --- Feature extraction (MFCC on numpy) --------------------------------------


def _hz_to_mel(hz: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)


def _mel_to_hz(mel: np.ndarray | float) -> np.ndarray | float:
    return 700.0 * (10.0 ** (np.asarray(mel) / 2595.0) - 1.0)


def _mel_filterbank(n_filters: int, n_fft: int, sample_rate: int) -> np.ndarray:
    low_mel = _hz_to_mel(80.0)
    high_mel = _hz_to_mel(sample_rate / 2.0)
    mel_points = np.linspace(low_mel, high_mel, n_filters + 2)
    hz_points = _mel_to_hz(mel_points)
    bins = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)
    bins = np.clip(bins, 0, n_fft // 2)

    fb = np.zeros((n_filters, n_fft // 2 + 1), dtype=np.float32)
    for i in range(1, n_filters + 1):
        left, center, right = bins[i - 1], bins[i], bins[i + 1]
        if center == left:
            center = left + 1
        if right == center:
            right = center + 1
        if right > n_fft // 2:
            break
        fb[i - 1, left:center] = (np.arange(left, center) - left) / max(center - left, 1)
        fb[i - 1, center:right] = (right - np.arange(center, right)) / max(right - center, 1)
    return fb


_FFT_SIZE = 512
_HOP = 160          # 10ms
_WIN = 400          # 25ms
_N_MELS = 40
_N_MFCC = 20
_FILTERBANK = _mel_filterbank(_N_MELS, _FFT_SIZE, SAMPLE_RATE)

# 80-bin bank for the neural model. Built once at import; it is a small matrix
# and rebuilding it per utterance would dominate the feature extraction cost.
_FBANK_FILTERS = _mel_filterbank(FBANK_MELS, FBANK_NFFT, SAMPLE_RATE)
_DCT = np.array(
    [
        [math.cos(math.pi * k * (2 * n + 1) / (2 * _N_MELS)) for n in range(_N_MELS)]
        for k in range(_N_MFCC)
    ],
    dtype=np.float32,
)


def mfcc(signal: np.ndarray) -> np.ndarray:
    """Return (frames, n_mfcc) MFCCs. Standard pipeline: pre-emphasis, framing,
    Hamming window, power spectrum, mel filterbank, log, DCT."""
    if len(signal) < _WIN:
        return np.zeros((0, _N_MFCC), dtype=np.float32)

    emphasized = np.append(signal[0], signal[1:] - 0.97 * signal[:-1]).astype(np.float32)
    n_frames = 1 + (len(emphasized) - _WIN) // _HOP
    if n_frames <= 0:
        return np.zeros((0, _N_MFCC), dtype=np.float32)

    idx = np.arange(_WIN)[None, :] + _HOP * np.arange(n_frames)[:, None]
    frames = emphasized[idx] * np.hamming(_WIN).astype(np.float32)

    spectrum = np.abs(np.fft.rfft(frames, _FFT_SIZE)) ** 2 / _FFT_SIZE
    energies = np.maximum(spectrum @ _FILTERBANK.T, 1e-10)
    return (np.log(energies) @ _DCT.T).astype(np.float32)


def estimate_pitch(signal: np.ndarray) -> tuple[float, float, float]:
    """Estimate fundamental frequency via autocorrelation.

    Returns (median_f0_log, f0_std, voiced_fraction). Unvoiced frames are excluded
    from the median rather than counted as zero, which would drag it toward
    whoever pauses more.

    Pitch is the single most discriminative cheap feature for telling speakers
    apart - male voices sit around 85-155Hz and female around 165-255Hz, a gap no
    amount of MFCC averaging captures reliably, because MFCCs deliberately
    discard the excitation signal that carries pitch.
    """
    frame_len = int(0.04 * SAMPLE_RATE)   # 40ms - at least two periods of 50Hz
    hop = int(0.02 * SAMPLE_RATE)
    min_lag = SAMPLE_RATE // 300          # 300Hz ceiling
    max_lag = SAMPLE_RATE // 60           # 60Hz floor

    if len(signal) < frame_len:
        return 0.0, 0.0, 0.0

    f0s: list[float] = []
    frames = 0

    for start in range(0, len(signal) - frame_len, hop):
        frame = signal[start : start + frame_len]
        frames += 1

        # Skip near-silence: autocorrelation of noise returns nonsense peaks.
        if np.sqrt(np.mean(frame**2)) < 0.008:
            continue

        frame = frame - frame.mean()
        corr = np.correlate(frame, frame, mode="full")[frame_len - 1 :]
        if corr[0] <= 0:
            continue
        corr = corr / corr[0]

        window = corr[min_lag:max_lag]
        if window.size == 0:
            continue

        peak = int(np.argmax(window)) + min_lag
        # A weak peak means the frame is unvoiced (a fricative, say) and its
        # "pitch" is meaningless.
        if corr[peak] < 0.3:
            continue

        f0s.append(SAMPLE_RATE / peak)

    if not f0s or frames == 0:
        return 0.0, 0.0, 0.0

    arr = np.array(f0s, dtype=np.float32)
    # Log scale: pitch is perceived (and varies) multiplicatively, so 100->110Hz
    # and 200->220Hz should count as the same amount of difference.
    return float(np.log(np.median(arr))), float(np.std(np.log(arr))), len(f0s) / frames


def spectral_shape(signal: np.ndarray) -> tuple[float, float]:
    """Mean and spread of the spectral centroid - a coarse measure of timbre
    ('brightness') that varies between speakers independently of pitch."""
    frame_len = 512
    hop = 256
    if len(signal) < frame_len:
        return 0.0, 0.0

    centroids: list[float] = []
    freqs = np.fft.rfftfreq(frame_len, 1 / SAMPLE_RATE)

    for start in range(0, len(signal) - frame_len, hop):
        frame = signal[start : start + frame_len] * np.hanning(frame_len)
        spec = np.abs(np.fft.rfft(frame))
        total = spec.sum()
        if total < 1e-6:
            continue
        centroids.append(float((freqs * spec).sum() / total))

    if not centroids:
        return 0.0, 0.0
    arr = np.array(centroids, dtype=np.float32)
    return float(arr.mean()), float(arr.std())


def voice_embedding(signal: np.ndarray) -> np.ndarray | None:
    """A speaker fingerprint for one utterance.

    Returns RAW features, deliberately not normalised. Normalisation happens in
    `diarize_segments`, across the whole meeting at once - see the note there.
    Normalising each vector in isolation, as this used to, throws away exactly
    the between-speaker scale differences the clustering needs, and every voice
    ends up looking identical (measured: it collapsed all speakers into one).

    Features: MFCC statistics for timbre, deltas for speaking style, pitch for
    who is physically talking, spectral centroid for brightness.
    """
    if len(signal) < SAMPLE_RATE * 0.35:  # under ~350ms is too little to judge
        return None

    feats = mfcc(signal)
    if feats.shape[0] < 3:
        return None

    # Drop the lowest-energy frames - silence and breaths blur the fingerprint.
    energy = np.linalg.norm(feats, axis=1)
    keep = feats[energy >= np.percentile(energy, 25)]
    if keep.shape[0] < 3:
        keep = feats

    # Skip C0: it is overall loudness, which tracks microphone distance rather
    # than identity, and would cluster "whoever leaned in" together.
    voiced = keep[:, 1:]
    deltas = np.diff(voiced, axis=0)

    f0_med, f0_std, voiced_frac = estimate_pitch(signal)
    cent_mean, cent_std = spectral_shape(signal)

    vec = np.concatenate([
        voiced.mean(axis=0),
        voiced.std(axis=0),
        deltas.std(axis=0) if deltas.shape[0] > 0 else np.zeros(voiced.shape[1], dtype=np.float32),
        # Pitch is weighted up: it is the strongest single identity signal here,
        # and without emphasis it is one dimension among sixty.
        np.array([f0_med * 4.0, f0_std * 4.0, voiced_frac * 2.0], dtype=np.float32),
        np.array([cent_mean / 1000.0, cent_std / 1000.0], dtype=np.float32),
    ])

    return vec.astype(np.float32) if np.all(np.isfinite(vec)) else None


# --- Clustering --------------------------------------------------------------


def standardize(matrix: np.ndarray) -> np.ndarray:
    """Z-score each feature dimension across the meeting, then unit-normalise.

    This is the step that makes the whole thing work, and it has to happen here -
    across all utterances at once - rather than inside voice_embedding.

    Raw MFCC statistics are dominated by properties shared by all human speech,
    so in absolute terms every voice looks nearly identical and cosine distances
    bunch up near zero. Rescaling each dimension by how much it actually varies
    *between these particular speakers* turns the small differences that carry
    identity into the dominant signal.

    Measured on the seed meetings: without this, clustering collapsed every
    speaker into one (44.9%, the majority-class baseline). With it, speakers
    separate.
    """
    mu = matrix.mean(axis=0)
    sd = matrix.std(axis=0)
    sd[sd < 1e-6] = 1.0  # a constant dimension carries no information
    z = (matrix - mu) / sd

    norms = np.linalg.norm(z, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (z / norms).astype(np.float32)


def _cosine_distances(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    unit = vectors / norms
    return np.clip(1.0 - unit @ unit.T, 0.0, 2.0)


def _agglomerative(distances: np.ndarray, threshold: float, max_clusters: int) -> list[int]:
    """Average-linkage agglomerative clustering.

    Written out rather than pulled from scikit-learn to avoid a 100MB dependency
    for ~40 lines of logic.

    Two stopping rules, in priority order:

    1. `max_clusters` is a hard cap on how many speakers may be reported. While
       there are more clusters than that, merging continues regardless of
       distance - a meeting is not allowed to come back with 30 speakers.
    2. Once within the cap, `threshold` decides: merging stops as soon as the
       closest remaining pair is further apart than it.

    So the threshold is what actually separates speakers, and it only means
    anything if the feature distances are on a sensible scale. They were not,
    originally: unstandardised MFCC vectors sat far below any useful threshold,
    everything merged, and every meeting came back with exactly one speaker
    (measured: 44.9%, the majority-class baseline). See `standardize`.
    """
    n = distances.shape[0]
    clusters: list[list[int]] = [[i] for i in range(n)]

    while len(clusters) > 1:
        best_a, best_b, best_d = None, None, float("inf")
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = float(distances[np.ix_(clusters[a], clusters[b])].mean())
                if d < best_d:
                    best_a, best_b, best_d = a, b, d

        if best_a is None:
            break

        # The threshold decides. Only when there are still more clusters than we
        # would ever accept do we merge past it.
        if best_d > threshold and len(clusters) <= max_clusters:
            break

        clusters[best_a].extend(clusters[best_b])
        clusters.pop(best_b)

    labels = [0] * n
    # Order clusters by first appearance so SPEAKER_00 is whoever spoke first.
    for label, cluster in enumerate(sorted(clusters, key=min)):
        for i in cluster:
            labels[i] = label
    return labels


def diarize_segments(
    audio_path: str | Path,
    segments: list,
    *,
    max_speakers: int = 8,
    threshold: float | None = None,
) -> dict[int, str]:
    """Assign a speaker tag to each transcript segment.

    Returns {segment_index: "SPEAKER_00"}. Segments too short to fingerprint
    inherit the previous segment's speaker, which is the right guess: a short
    "haan" or "right" almost always continues the current turn.

    The default threshold of 1.1 is not a guess - it is the measured optimum over
    the seed meetings, where the true speaker of every turn is known. Sweeping it
    (scripts/tune_diarize.py) gives:

        threshold  accuracy  speakers found (true = 3,3,3)
        0.80        66.1%    [4, 5, 6]   over-splits: one person becomes several
        1.00        82.8%    [3, 3, 4]
        1.10        89.2%    [3, 3, 3]   <- optimum
        1.20        67.4%    [2, 2, 2]   under-splits: two people merged
        1.30        44.9%    [1, 1, 1]   everyone collapsed into one

    Re-run that script after touching the features; the number moves.
    """
    if not segments:
        return {}

    audio = load_mono_16k(audio_path)

    # Prefer the trained network; fall back to hand-built features if it isn't
    # available. The two produce different distance scales, so the threshold has
    # to match whichever ran.
    use_neural = get_speaker_model() is not None
    embed = neural_embedding if use_neural else voice_embedding
    if threshold is None:
        threshold = NEURAL_THRESHOLD if use_neural else HANDBUILT_THRESHOLD

    embeddings: list[np.ndarray] = []
    indices: list[int] = []

    for i, seg in enumerate(segments):
        start = max(0, int(seg.start * SAMPLE_RATE))
        end = min(len(audio), int(seg.end * SAMPLE_RATE))
        if end <= start:
            continue
        emb = embed(audio[start:end])
        if emb is not None:
            embeddings.append(emb)
            indices.append(i)

    if not embeddings:
        return {i: "SPEAKER_00" for i in range(len(segments))}

    if len(embeddings) == 1:
        labels = [0]
    else:
        matrix = np.vstack(embeddings)
        # The network already outputs a space where cosine distance means
        # identity. The hand-built features do not, and need standardising first.
        if not use_neural:
            matrix = standardize(matrix)
        labels = _agglomerative(_cosine_distances(matrix), threshold, max_speakers)

    assignment = {idx: f"SPEAKER_{labels[k]:02d}" for k, idx in enumerate(indices)}

    # Fill gaps (segments we couldn't fingerprint) from the nearest prior turn.
    last = "SPEAKER_00"
    result: dict[int, str] = {}
    for i in range(len(segments)):
        last = assignment.get(i, last)
        result[i] = last
    return result


def smooth_speakers(segments: list, assignment: dict[int, str], min_turn: float = 1.0) -> dict[int, str]:
    """Remove one-off speaker flips.

    A single short segment labelled differently from both neighbours is nearly
    always a clustering error, not someone interjecting one word and vanishing.
    """
    if len(segments) < 3:
        return assignment

    smoothed = dict(assignment)
    for i in range(1, len(segments) - 1):
        prev_tag, cur_tag, next_tag = smoothed[i - 1], smoothed[i], smoothed[i + 1]
        duration = segments[i].end - segments[i].start
        if cur_tag != prev_tag and prev_tag == next_tag and duration < min_turn:
            smoothed[i] = prev_tag
    return smoothed


def speaker_color(index: int) -> str:
    return PALETTE[index % len(PALETTE)]
