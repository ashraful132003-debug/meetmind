"""Measure action-item extraction recall against a human-labelled answer key.

The scripted meetings contain a known set of real commitments. This runs the
extractor over the real transcripts and reports how many it finds, so prompt
changes can be judged instead of guessed at.

Recall is the metric that matters here. A missed action item is invisible — the
user never learns the commitment existed. A spurious one is at least on screen to
be deleted. But precision still counts: a model that lists every sentence as an
action item is useless, so hallucinated items are reported too.

Run:  python scripts/tune_actions.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services import analysis  # noqa: E402

# The answer key: what a competent human would extract.
#
# Each entry needs ALL of `must` to be present. An earlier version used "any
# keyword matches" and cheerfully credited a hit when the word "numbers" appeared
# inside a completely unrelated item - a loose metric will happily tell you your
# prompt is working when it is not.
ANSWER_KEY = {
    "sprint-standup": [
        ("Rahul fixes the token refresh properly", ["refresh"]),
        ("Rahul gives Sneha a stub endpoint by tomorrow", ["stub"]),
        ("Sneha has the dashboard ready for review by Thursday", ["dashboard"]),
        ("Sneha builds the CSV export by next Wednesday", ["csv"]),
        ("Priya raises the staging memory issue with infra", ["staging"]),
    ],
    "client-call": [
        ("Sneha gets the API credentials from IT this week", ["credential"]),
        ("Sneha takes the one-way sync proposal back to the team", ["sync"]),
        ("Priya sends a written summary of the call", ["summary"]),
    ],
    "product-planning": [
        ("Rahul evaluates SSO libraries and writes a recommendation by Thursday", ["librar"]),
        ("Priya pulls together the usage numbers by Monday", ["usage"]),
        ("Sneha explains the no-mobile-app decision to the client", ["client"]),
    ],
}

# Words that only exist in the prompt's format example. If any of these appear in
# a real answer, the model has copied the example instead of reading the
# transcript - which is a hallucination we caused ourselves.
LEAK_MARKERS = ["dana", "kwame", "croissant", "flour", "bakery", "landlord", "freezer"]


def matches(task: str, must: list[str]) -> bool:
    low = task.lower()
    return all(k in low for k in must)


def leaked(task: str) -> bool:
    low = task.lower()
    return any(m in low for m in LEAK_MARKERS)


async def evaluate(slug: str, transcript: str, speaker_names: dict):
    """Extract once and report everything - hits, misses, extras, and leaks."""
    items = await analysis.extract_action_items(transcript, speaker_names)
    expected = ANSWER_KEY[slug]

    pairs = []
    for label, must in expected:
        hit = next((i for i in items if matches(i.task, must)), None)
        pairs.append((label, hit))

    matched = {id(h) for _, h in pairs if h}
    extra = [i for i in items if id(i) not in matched]
    leaks = [i for i in items if leaked(i.task)]

    return pairs, extra, leaks


async def main() -> int:
    from app.services.llm import LLMUnavailable, health

    h = await health()
    if not h.get("reachable"):
        print(f"[error] LLM unreachable: {h.get('detail')}")
        return 1

    seed = Path(__file__).resolve().parents[1] / "storage" / "seed"
    total_found = total_expected = total_extra = total_leaks = 0

    for slug in ANSWER_KEY:
        truth_file = seed / f"{slug}.truth.json"
        if not truth_file.exists():
            print(f"[skip] {slug}: no ground truth")
            continue

        import json

        turns = json.loads(truth_file.read_text(encoding="utf-8"))["turns"]

        # Build the transcript from ground truth, so this measures the extractor
        # rather than compounding Whisper's and the diarizer's errors into it.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from seed_scripts import ALL_MEETINGS

        script = next(m for m in ALL_MEETINGS if m["slug"] == slug)
        names = {"rahul": "Rahul", "priya": "Priya", "sneha": "Sneha"}

        utterances = [
            analysis.Utterance(speaker=names[spk], start=t["start"], end=t["end"], text=text)
            for (spk, text), t in zip(script["lines"], turns)
        ]
        transcript = analysis.format_transcript(utterances)

        try:
            pairs, extra, leaks = await evaluate(slug, transcript, {})
        except LLMUnavailable as e:
            print(f"[error] {e}")
            return 1

        found = sum(1 for _, h in pairs if h)
        total_found += found
        total_expected += len(pairs)
        total_extra += len(extra)
        total_leaks += len(leaks)

        print(f"\n{slug}: {found}/{len(pairs)} found")
        for label, hit in pairs:
            print(f"  [{'OK  ' if hit else 'MISS'}] {label}")
            if hit:
                print(f"         -> {hit.task[:76]!r}")
                print(f"            owner={hit.owner_label} due={hit.due_text} priority={hit.priority}")

        for i in extra:
            tag = "LEAK!" if leaked(i.task) else "extra"
            print(f"  [{tag}] {i.task[:76]!r} owner={i.owner_label}")

    print("\n" + "=" * 66)
    recall = total_found / total_expected * 100 if total_expected else 0
    print(f"  Recall: {total_found}/{total_expected} = {recall:.0f}%")
    print(f"  Extra items (plausibly real, or invented): {total_extra}")
    print(f"  Example leakage (must be 0): {total_leaks}")
    print("=" * 66)
    return 0 if total_leaks == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
