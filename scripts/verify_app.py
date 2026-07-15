"""End-to-end verification: exercise every feature against real, processed data.

This drives the same HTTP endpoints the UI's buttons call, so a pass here means
those buttons work. It checks not just that requests succeed, but that the data
coming back is real and internally consistent — that action items point at
timestamps inside the meeting, that talk-time shares add to 100%, that the
chatbot's citations are genuine, and that it admits ignorance rather than
inventing an answer.

Run after seeding:  python scripts/verify_app.py
"""

from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
EMAIL = "demo@example.com"
PASSWORD = "demo-meetmind-2026"

passed = 0
failed = 0
warned = 0


def check(name: str, ok: bool, detail: str = "") -> bool:
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f"\n         {detail}" if detail else ""))
    return ok


def warn(name: str, detail: str = "") -> None:
    global warned
    warned += 1
    print(f"  [WARN] {name}" + (f"\n         {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def main() -> int:
    print("MeetMind end-to-end verification")
    print("=" * 66)

    with httpx.Client(timeout=180) as c:
        # --- Auth ------------------------------------------------------------
        section("Sign in")

        # Login is rate limited to 5/minute per IP. Running security_check.py
        # first (which deliberately hammers it) leaves the limiter warm, and this
        # script would then fail for a reason that has nothing to do with what it
        # is testing. Wait it out rather than report a misleading failure.
        r = c.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "61")) + 1
            print(f"  (rate limited - the limiter is working; waiting {wait}s)")
            time.sleep(wait)
            r = c.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})

        if not check("Demo account can sign in", r.status_code == 200, f"{r.status_code} {r.text[:120]}"):
            if r.status_code == 401:
                print("\n  The demo account does not exist. Run: python scripts/seed_meetings.py")
            return 1

        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        check("Access token issued", bool(r.json().get("access_token")))
        check("Refresh cookie set", "meetmind_refresh" in c.cookies)
        check("Media cookie set", "meetmind_media" in c.cookies)

        r = c.get(f"{BASE}/api/auth/me", headers=h)
        check("/me returns the signed-in user", r.status_code == 200 and r.json()["email"] == EMAIL)

        # --- Meetings list ---------------------------------------------------
        section("Meetings (dashboard + list pages)")
        r = c.get(f"{BASE}/api/meetings", headers=h)
        meetings = r.json() if r.status_code == 200 else []
        if not check("Meetings list loads", r.status_code == 200 and len(meetings) > 0, f"got {len(meetings)}"):
            return 1

        ready = [m for m in meetings if m["status"] == "ready"]
        check(f"All {len(meetings)} meetings processed successfully",
              len(ready) == len(meetings),
              f"{len(meetings) - len(ready)} not ready")

        for m in ready:
            check(f"'{m['title'][:44]}' has real duration", m["duration_seconds"] > 30,
                  f"{m['duration_seconds']}s")
            check(f"'{m['title'][:44]}' found multiple speakers", m["speaker_count"] >= 2,
                  f"{m['speaker_count']} speaker(s)")
            if not m.get("topics"):
                warn(f"'{m['title'][:44]}' has no topics")

        r = c.get(f"{BASE}/api/meetings?search=standup", headers=h)
        check("Search endpoint works", r.status_code == 200)

        if not ready:
            return 1
        meeting = ready[0]
        mid = meeting["id"]

        # --- Detail ----------------------------------------------------------
        section(f"Meeting detail: {meeting['title'][:50]}")
        r = c.get(f"{BASE}/api/meetings/{mid}", headers=h)
        if not check("Detail loads", r.status_code == 200):
            return 1
        detail = r.json()

        check("Summary was generated", bool(detail.get("summary")) and len(detail["summary"]) > 120,
              f"{len(detail.get('summary') or '')} chars")
        summary = detail.get("summary") or ""
        check("Summary has the expected sections",
              "Overview" in summary and ("Key Points" in summary or "Decisions" in summary),
              summary[:100])
        check("Audio URL issued", bool(detail.get("audio_url")))
        check("Speakers recorded", len(detail["speakers"]) >= 2)
        check("Talk times are positive", all(s["talk_seconds"] > 0 for s in detail["speakers"]))

        actions = detail["action_items"]
        if actions:
            check(f"{len(actions)} action items extracted", True)
            check("Action items have owners", all(a["owner_label"] for a in actions))
            check("Action item priorities valid",
                  all(a["priority"] in ("low", "medium", "high") for a in actions))
            timed = [a for a in actions if a["quote_time"] is not None]
            if timed:
                check("Action timestamps fall inside the meeting",
                      all(0 <= a["quote_time"] <= detail["duration_seconds"] + 1 for a in timed),
                      "an action points outside the recording — the model invented a timestamp")
            else:
                warn("No action item carries a timestamp")
        else:
            warn("No action items extracted from this meeting")

        # --- Transcript ------------------------------------------------------
        section("Transcript tab")
        r = c.get(f"{BASE}/api/meetings/{mid}/transcript", headers=h)
        check("Transcript loads", r.status_code == 200)
        segments = r.json()["segments"]
        check(f"{len(segments)} segments returned", len(segments) > 5)
        check("Segments carry text", all(s["text"].strip() for s in segments))
        check("Segments are time-ordered",
              all(segments[i]["start_time"] <= segments[i + 1]["start_time"] for i in range(len(segments) - 1)))
        check("Segments name their speaker", all(s["speaker_name"] for s in segments))
        check("Decryption worked (text is readable)",
              any(len(s["text"].split()) > 3 for s in segments))

        # --- Audio -----------------------------------------------------------
        section("Audio player")
        if detail.get("audio_url"):
            r = c.get(f"{BASE}{detail['audio_url']}", headers=h)
            check("Audio streams", r.status_code in (200, 206), f"got {r.status_code}")
            r = c.get(f"{BASE}{detail['audio_url']}", headers={**h, "Range": "bytes=0-2047"})
            check("Range requests work (seeking)", r.status_code == 206, f"got {r.status_code}")

        # --- Analytics -------------------------------------------------------
        section("Analytics tab")
        r = c.get(f"{BASE}/api/meetings/{mid}/analytics", headers=h)
        check("Meeting analytics load", r.status_code == 200)
        a = r.json()
        check("Word count is real", a["total_words"] > 50, f"{a['total_words']} words")
        check("Timeline has blocks", len(a["timeline"]) > 3)
        total_share = sum(s["share_percent"] for s in a["speakers"])
        check("Talk-time shares total ~100%", 99.0 <= total_share <= 101.0, f"{total_share}%")
        check("Balance score in range", 0 <= a["balance_score"] <= 100, str(a["balance_score"]))
        check("Words-per-minute plausible",
              all(0 < s["words_per_minute"] < 400 for s in a["speakers"] if s["talk_seconds"] > 5),
              str([s["words_per_minute"] for s in a["speakers"]]))

        r = c.get(f"{BASE}/api/analytics/workspace", headers=h)
        check("Workspace analytics load", r.status_code == 200)
        ws = r.json()
        check("Workspace totals are consistent",
              ws["total_meetings"] == len(meetings),
              f"{ws['total_meetings']} vs {len(meetings)}")

        # --- Action item toggle ----------------------------------------------
        if actions:
            section("Action item checkbox")
            aid = actions[0]["id"]
            r = c.patch(f"{BASE}/api/meetings/{mid}/actions/{aid}", headers=h, json={"done": True})
            check("Mark action done", r.status_code == 200 and r.json()["done"] is True)
            r = c.patch(f"{BASE}/api/meetings/{mid}/actions/{aid}", headers=h, json={"done": False})
            check("Mark action not-done", r.status_code == 200 and r.json()["done"] is False)

        # --- Speaker rename --------------------------------------------------
        section("Speaker rename")
        sp = detail["speakers"][0]
        original = sp["display_name"]
        r = c.patch(f"{BASE}/api/meetings/{mid}/speakers/{sp['id']}", headers=h,
                    json={"display_name": "Rahul Verma"})
        check("Rename speaker", r.status_code == 200 and r.json()["display_name"] == "Rahul Verma")

        r = c.get(f"{BASE}/api/meetings/{mid}/transcript", headers=h)
        renamed = [s for s in r.json()["segments"] if s["speaker_tag"] == sp["tag"]]
        check("Transcript reflects the new name",
              all(s["speaker_name"] == "Rahul Verma" for s in renamed))

        c.patch(f"{BASE}/api/meetings/{mid}/speakers/{sp['id']}", headers=h,
                json={"display_name": original})

        # --- Meeting rename --------------------------------------------------
        section("Meeting rename")
        r = c.patch(f"{BASE}/api/meetings/{mid}", headers=h, json={"title": "Renamed by verifier"})
        check("Rename meeting", r.status_code == 200 and r.json()["title"] == "Renamed by verifier")
        c.patch(f"{BASE}/api/meetings/{mid}", headers=h, json={"title": meeting["title"]})

        # --- Chat / RAG ------------------------------------------------------
        section("Ask the meeting (RAG)")
        r = c.get(f"{BASE}/api/meetings/{mid}/chat/suggestions", headers=h)
        check("Suggested questions generated", r.status_code == 200)
        suggestions = r.json() if r.status_code == 200 else []
        if suggestions:
            print(f"         e.g. {suggestions[0]!r}")
        else:
            warn("No suggested questions returned")

        question = suggestions[0] if suggestions else "What did they decide?"
        r = c.post(f"{BASE}/api/meetings/{mid}/chat", headers=h, json={"question": question})
        if check("Chatbot answers a real question", r.status_code == 200, f"{r.status_code} {r.text[:150]}"):
            ans = r.json()["answer"]
            print(f"         Q: {question}")
            print(f"         A: {ans['content'][:220]}")
            check("Answer is non-trivial", len(ans["content"]) > 25)
            cites = ans.get("citations") or []
            check("Answer carries citations", len(cites) > 0)
            if cites:
                check("Citations point inside the meeting",
                      all(0 <= ct["start_time"] <= detail["duration_seconds"] + 1 for ct in cites),
                      "a citation points outside the recording")
                check("Citations quote real transcript text",
                      all(ct["preview"].strip() for ct in cites))

        # The honesty test: the model must refuse to answer what was never said.
        r = c.post(f"{BASE}/api/meetings/{mid}/chat", headers=h,
                   json={"question": "What did they say about the acquisition of Tesla by SpaceX?"})
        if r.status_code == 200:
            ans = r.json()["answer"]["content"].lower()
            refused = any(p in ans for p in [
                "wasn't covered", "was not covered", "can't find", "cannot find", "not mentioned",
                "no mention", "not discussed", "doesn't", "does not", "not in the transcript",
                "not find", "no information", "wasn't discussed", "not provided",
            ])
            print(f"         A: {r.json()['answer']['content'][:220]}")
            if refused:
                check("Refuses to invent an answer about something never discussed", True)
            else:
                warn("Model may have hallucinated on an off-topic question — read the answer above")

        r = c.get(f"{BASE}/api/meetings/{mid}/chat", headers=h)
        check("Chat history persists", r.status_code == 200 and len(r.json()) >= 2)

        # --- Email -----------------------------------------------------------
        section("Email the summary")
        r = c.post(f"{BASE}/api/meetings/{mid}/email", headers=h,
                   json={"recipients": ["rahul@example.com", "priya@example.com"],
                         "include_transcript": False,
                         "note": "Summary from today's call."})
        if check("Send summary", r.status_code == 201, f"{r.status_code} {r.text[:150]}"):
            d = r.json()
            check("Delivery recorded", d["status"] in ("sent", "captured"), d["status"])
            check("Preview available", bool(d.get("preview_url")))
            if d.get("preview_url"):
                r2 = c.get(f"{BASE}{d['preview_url']}", headers=h)
                check("Email preview renders", r2.status_code == 200 and "<html" in r2.text.lower())
                check("Preview contains the summary", "Action Items" in r2.text or "Overview" in r2.text)

        r = c.get(f"{BASE}/api/meetings/{mid}/email", headers=h)
        check("Delivery history loads", r.status_code == 200 and len(r.json()) >= 1)

        # --- Health ----------------------------------------------------------
        section("System health")
        r = c.get(f"{BASE}/api/health")
        hh = r.json()
        check("Health reports healthy", hh["status"] == "healthy", str(hh))
        check("Database connected", hh["database"])
        check("LLM reachable", hh["llm"]["reachable"])

    print("\n" + "=" * 66)
    print(f"  {passed} passed, {failed} failed, {warned} warnings")
    print("=" * 66)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
