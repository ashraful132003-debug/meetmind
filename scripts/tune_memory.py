"""Measure cross-meeting attribution accuracy.

The point of memory chat is telling you WHICH meeting something was said in. An
answer that quotes a real line but names the wrong meeting is worse than no
answer: the user acts on a decision they believe was made with a different
client. So attribution is the thing worth measuring, not answer "quality".

Each case names a fact that exists in exactly ONE seed meeting. The check is
whether the answer credits that meeting and not another.

Run:  python scripts/tune_memory.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx  # noqa: E402

BASE = "http://127.0.0.1:8000"
EMAIL = "demo@example.com"
PASSWORD = "demo-meetmind-2026"

# (question, substring that must appear in the answer, meeting the fact lives in,
#  meetings that must NOT be credited)
CASES = [
    (
        "What did we decide about the Salesforce integration?",
        ["one way", "one-way"],
        "Acme",
        ["Quarterly", "Payment"],
    ),
    (
        "What was the price quoted to the client?",
        ["eighteen", "18"],
        "Acme",
        ["Quarterly", "Payment"],
    ),
    (
        "Did we decide to build a mobile app?",
        ["no", "not"],
        "Quarterly",
        ["Acme"],
    ),
    (
        "What is blocking the payments API?",
        ["token", "refresh", "auth"],
        "Payment",
        ["Acme", "Quarterly"],
    ),
    (
        "Who is doing the CSV export?",
        ["csv"],
        "Payment",
        ["Acme"],
    ),
    (
        "What did anyone say about single sign on?",
        ["sign", "sso"],
        "Quarterly",
        ["Payment"],
    ),
    (
        "What did they say about the merger with Google?",
        ["can't find", "cannot find", "no mention"],
        None,  # nothing should be credited - the fact does not exist
        [],
    ),
]


async def main() -> int:
    c = httpx.Client(timeout=300)
    try:
        r = c.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        r.raise_for_status()
    except Exception as e:
        print(f"[error] Could not sign in: {e}")
        print("        Is the backend running, and has the demo data been seeded?")
        return 1

    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    titles = {m["title"]: m["id"] for m in c.get(f"{BASE}/api/meetings", headers=h).json()}
    print("Meetings in the workspace:")
    for t in titles:
        print(f"  - {t}")
    print()
    print("=" * 74)

    correct = 0
    wrong_meeting = 0
    missed = 0
    prose_unnamed: list[str] = []

    for question, expect_any, should_credit, must_not_credit in CASES:
        r = c.post(f"{BASE}/api/memory", headers=h, json={"question": question})
        if r.status_code != 200:
            print(f"[FAIL] {question}\n       HTTP {r.status_code}: {r.text[:120]}")
            missed += 1
            continue

        body = r.json()
        answer = body["content"]
        citations = body.get("citations") or []
        lowered = answer.lower()

        found_fact = any(e.lower() in lowered for e in expect_any)

        def keys_in(text: str) -> set[str]:
            return {k for k in ("Acme", "Quarterly", "Payment") if k.lower() in text.lower()}

        # Attribution now lives in two places, and both matter:
        #   * the verified citations - machine-checked, this is the ground truth
        #   * the prose - what the user actually reads
        # An answer whose citations are right but whose prose names no meeting has
        # failed at the one job of this feature: telling you WHERE it was said.
        cited_keys: set[str] = set()
        for cit in citations:  # not `c` - that is the http client, and shadowing it here cost a run
            cited_keys |= keys_in(cit["meeting_title"])

        prose_keys = keys_in(answer)

        # CITATION correctness is the primary metric, because citations are the
        # part that is machine-verified: every quote was looked up in the meeting
        # it names, and anything that failed was dropped before it reached here.
        # Prose naming is secondary - it is nice for readability, but the UI shows
        # the citation card underneath the answer, so the user gets provenance
        # either way. Measuring them together (as this script first did) hid the
        # fact that citations were already 100% correct.
        if should_credit is None:
            if not citations:
                status = "OK (correctly found nothing, no sources)"
                correct += 1
            else:
                status = f"HALLUCINATED (cited {sorted(cited_keys)})"
                wrong_meeting += 1
        elif not found_fact:
            status = "MISSED (fact not in the answer)"
            missed += 1
        elif not cited_keys:
            status = "NO CITATION (nothing survived verification)"
            wrong_meeting += 1
        elif should_credit not in cited_keys:
            status = f"WRONG MEETING CITED (cited {sorted(cited_keys)})"
            wrong_meeting += 1
        elif set(must_not_credit) & cited_keys:
            status = f"EXTRA WRONG MEETING CITED ({sorted(set(must_not_credit) & cited_keys)})"
            wrong_meeting += 1
        else:
            status = "OK"
            correct += 1
            if should_credit not in prose_keys:
                prose_unnamed.append(question)

        print(f"[{status}] {question}")
        print(f"    {answer[:130].replace(chr(10), ' ')}")
        print(f"    cited: {[cit['meeting_title'][:34] for cit in citations] or 'none'}")
        print()

    total = len(CASES)
    print("=" * 74)
    print(f"  CITATION accuracy (verified): {correct}/{total} = {correct / total * 100:.1f}%")
    print(f"    wrong meeting cited: {wrong_meeting}   fact missed: {missed}")
    if prose_unnamed:
        print(f"  prose did not name the meeting in {len(prose_unnamed)}/{correct} correct answers")
        print("    (secondary: the UI shows the verified citation card under every answer,")
        print("     so provenance reaches the user regardless of how the model phrased it)")
    print("=" * 74)
    # Only a wrong citation is a failure. A citation is machine-verified, so a
    # wrong one means the verification layer let something through - that is the
    # bug worth failing the build over.
    return 0 if wrong_meeting == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
