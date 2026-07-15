"""Seed the app with fully-processed demo meetings.

Important: this does NOT insert fabricated results. It uploads the generated
audio through the real HTTP API as a real user, and the normal background
pipeline transcribes, diarizes, summarises and indexes it exactly as it would for
a recording made in the browser. Every summary, action item, timestamp and
embedding in the seeded data was produced by the same code path a live meeting
uses. Nothing here is hardcoded.

The point is only that the demo account isn't empty on day one.

Run:  python scripts/seed_meetings.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "storage" / "seed"
BASE = "http://127.0.0.1:8000"

# example.com is the RFC 2606 reserved domain for exactly this purpose, and it
# passes validation. A .local address does not: it is a reserved special-use name
# and email-validator rejects it - correctly, since mail could never be delivered.
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-meetmind-2026"
DEMO_NAME = "Ashray Sharma"

# Titles are deliberately left empty for two of these so the LLM names them -
# it demonstrates the auto-titling and proves the model actually read the content.
MEETINGS = [
    ("sprint-standup.wav", ""),
    ("client-call.wav", "Acme Salesforce integration - scope call"),
    ("product-planning.wav", ""),
]

TERMINAL = {"ready", "failed"}


def log(msg: str) -> None:
    print(msg, flush=True)


def ensure_user(client: httpx.Client) -> str:
    """Register the demo user, or log in if it already exists."""
    r = client.post(
        f"{BASE}/api/auth/register",
        json={"email": DEMO_EMAIL, "full_name": DEMO_NAME, "password": DEMO_PASSWORD},
    )
    if r.status_code == 201:
        log(f"  created demo account: {DEMO_EMAIL}")
        return r.json()["access_token"]

    if r.status_code == 409:
        r = client.post(f"{BASE}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        r.raise_for_status()
        log(f"  using existing demo account: {DEMO_EMAIL}")
        return r.json()["access_token"]

    raise RuntimeError(f"Could not create the demo account: {r.status_code} {r.text[:200]}")


def wait_for(client: httpx.Client, headers: dict, meeting_id: str, timeout: float = 1800) -> dict:
    """Poll until the pipeline finishes. Prints stage changes as they happen."""
    started = time.perf_counter()
    last_stage = ""

    while time.perf_counter() - started < timeout:
        r = client.get(f"{BASE}/api/meetings/{meeting_id}", headers=headers)
        r.raise_for_status()
        m = r.json()

        stage = f"{m['stage_label']} ({m['progress']}%)"
        if stage != last_stage:
            log(f"    {stage}")
            last_stage = stage

        if m["status"] in TERMINAL:
            return m

        time.sleep(3)

    raise TimeoutError(f"Meeting {meeting_id} did not finish within {timeout}s")


def main() -> int:
    log("Seeding MeetMind with real, fully-processed meetings")
    log("=" * 64)

    try:
        health = httpx.get(f"{BASE}/api/health", timeout=10).json()
    except Exception:
        log(f"\n[error] No API at {BASE}. Start the backend first.")
        return 1

    if not health.get("database"):
        log("\n[error] The database is unreachable. Run: .\\scripts\\pg.ps1 start")
        return 1

    llm = health.get("llm", {})
    if not llm.get("reachable"):
        log(f"\n[error] The LLM is unreachable ({llm.get('detail')}).")
        log("        Start Ollama, then re-run this script.")
        return 1
    if llm.get("detail"):
        log(f"\n[error] {llm['detail']}")
        return 1

    missing = [name for name, _ in MEETINGS if not (SEED_DIR / name).exists()]
    if missing:
        log(f"\n[error] Missing seed audio: {', '.join(missing)}")
        log("        Run: python scripts/make_seed_audio.py")
        return 1

    with httpx.Client(timeout=120) as client:
        token = ensure_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        existing = client.get(f"{BASE}/api/meetings", headers=headers).json()
        if existing and "--force" in sys.argv:
            log(f"\n  --force: removing {len(existing)} existing meeting(s)")
            for m in existing:
                client.delete(f"{BASE}/api/meetings/{m['id']}", headers=headers)
        elif existing:
            log(f"\n  This account already has {len(existing)} meeting(s).")
            log("  Re-run with --force to wipe them and seed fresh. Nothing to do.")
            return 0

        results = []
        for filename, title in MEETINGS:
            path = SEED_DIR / filename
            size_mb = path.stat().st_size / (1024 * 1024)
            log(f"\n  {filename} ({size_mb:.1f} MB)")

            with path.open("rb") as f:
                r = client.post(
                    f"{BASE}/api/meetings",
                    headers=headers,
                    files={"file": (filename, f, "audio/wav")},
                    data={"title": title, "source": "upload"},
                )
            if r.status_code != 201:
                log(f"    [error] Upload failed: {r.status_code} {r.text[:200]}")
                return 1

            meeting_id = r.json()["id"]
            t0 = time.perf_counter()
            final = wait_for(client, headers, meeting_id)
            elapsed = time.perf_counter() - t0

            if final["status"] == "failed":
                log(f"    [FAILED] {final['error_message']}")
                return 1

            speed = final["duration_seconds"] / max(elapsed, 0.01)
            log(f"    [ready in {elapsed:.0f}s - {speed:.1f}x realtime]")
            log(f"    title:    {final['title']}")
            log(f"    speakers: {len(final['speakers'])}  actions: {len(final['action_items'])}")
            log(f"    topics:   {', '.join(final.get('topics') or []) or '-'}")
            results.append(final)

    log("\n" + "=" * 64)
    log(f"  Seeded {len(results)} meetings")
    log(f"  Sign in at http://localhost:5173 with:")
    log(f"    {DEMO_EMAIL}")
    log(f"    {DEMO_PASSWORD}")
    log("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
