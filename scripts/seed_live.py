"""Seed a deployed MeetMind with the demo meetings.

Why this exists: meetings are per-user by design, so a freshly deployed instance
shows an empty dashboard to everyone who opens it. This creates a demo account and
pushes the seed meetings through the REAL pipeline on the server — same upload
endpoint, same Whisper, same LLM, same everything a live recording gets.

Nothing here is fabricated. The audio is synthesised (scripts/make_seed_audio.py,
Windows SAPI voices, invented people and companies) but the transcript, speakers,
summary, action items and embeddings are all produced by the deployed app itself.

Run:
    BASE=https://your-app.onrender.com python scripts/seed_live.py
    BASE=... python scripts/seed_live.py --reset     # wipe the demo's meetings first
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.getenv("BASE", "http://127.0.0.1:8000").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "storage" / "seed"

DEMO_EMAIL = "demo@meetmind.app"
DEMO_NAME = "Demo User"
# Deliberately public — this account exists to be logged into. It owns only
# synthetic meetings about invented companies, so there is nothing here worth
# protecting. Anyone wanting private meetings registers their own account, and
# the ownership rules keep the two apart.
DEMO_PASSWORD = "meetmind-demo-2026"

FILES = ["sprint-standup.wav", "client-call.wav", "product-planning.wav"]

# Free instances are slow and occasionally return an HTML error page from the
# edge instead of JSON. Retry rather than fail the whole seed over a hiccup.
RETRIES = 6


def get_json(client: httpx.Client, url: str, **kw):
    for _ in range(RETRIES):
        try:
            return client.get(url, **kw).json()
        except Exception:
            time.sleep(8)
    return {}


def main() -> int:
    reset = "--reset" in sys.argv

    missing = [f for f in FILES if not (SEED_DIR / f).exists()]
    if missing:
        print(f"[error] Missing seed audio: {', '.join(missing)}")
        print("        Run: python scripts/make_seed_audio.py")
        return 1

    print(f"Seeding {BASE}")
    print("=" * 66)

    c = httpx.Client(timeout=300)

    try:
        h = c.get(f"{BASE}/api/health", timeout=90).json()
    except Exception as e:
        print(f"[error] {BASE} is not reachable: {e}")
        return 1

    print(f"  health: {h.get('status')} | llm: {h['llm']['provider']} | db: {h.get('database')}")
    if h.get("status") != "healthy":
        print(f"  [warn] instance is degraded: {h['llm'].get('detail')}")

    # Register, or sign in if the demo account already exists.
    r = c.post(
        f"{BASE}/api/auth/register",
        json={"email": DEMO_EMAIL, "full_name": DEMO_NAME, "password": DEMO_PASSWORD},
    )
    if r.status_code == 201:
        print(f"  created demo account: {DEMO_EMAIL}")
    elif r.status_code == 409:
        r = c.post(f"{BASE}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        if r.status_code != 200:
            print(f"[error] Demo account exists but the password is wrong: {r.status_code}")
            return 1
        print(f"  signed in as existing demo account: {DEMO_EMAIL}")
    else:
        print(f"[error] Could not create the demo account: {r.status_code} {r.text[:160]}")
        return 1

    token = r.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    existing = get_json(c, f"{BASE}/api/meetings", headers=auth) or []
    if existing and not reset:
        print(f"\n  Demo account already has {len(existing)} meeting(s):")
        for m in existing:
            print(f"    {m['status']:6}  {m['title'][:52]}")
        print("\n  Nothing to do. Use --reset to wipe and re-seed.")
        return 0

    if existing and reset:
        print(f"\n  --reset: deleting {len(existing)} existing meeting(s)")
        for m in existing:
            c.delete(f"{BASE}/api/meetings/{m['id']}", headers=auth)

    print()
    ids: list[str] = []
    for name in FILES:
        path = SEED_DIR / name
        size_mb = path.stat().st_size / 1024 / 1024
        print(f"  uploading {name} ({size_mb:.1f} MB)...", end=" ", flush=True)
        t0 = time.time()
        with path.open("rb") as f:
            r = c.post(
                f"{BASE}/api/meetings",
                headers=auth,
                files={"file": (name, f, "audio/wav")},
                # Blank title on purpose: the AI names the meeting, which is a
                # better demo than a title we typed in ourselves.
                data={"title": "", "source": "upload"},
            )
        if r.status_code != 201:
            print(f"FAILED {r.status_code}: {r.text[:120]}")
            continue
        ids.append(r.json()["id"])
        print(f"{time.time() - t0:.0f}s")

    if not ids:
        print("\n[error] Nothing uploaded.")
        return 1

    print(f"\n  processing {len(ids)} meeting(s) on the server...")
    for mid in ids:
        t0 = time.time()
        last = ""
        while time.time() - t0 < 900:
            m = get_json(c, f"{BASE}/api/meetings/{mid}", headers=auth)
            stage = m.get("stage_label", "")
            if stage != last and stage:
                print(f"    {stage} ({m.get('progress', 0)}%)")
                last = stage
            if m.get("status") in ("ready", "failed"):
                break
            time.sleep(8)

        if m.get("status") == "ready":
            print(
                f"    READY in {time.time() - t0:.0f}s — \"{m['title']}\" "
                f"({len(m['speakers'])} speakers, {len(m['action_items'])} actions)"
            )
        else:
            print(f"    {m.get('status')}: {m.get('error_message', '?')[:120]}")

    final = get_json(c, f"{BASE}/api/meetings", headers=auth) or []
    ready = [m for m in final if m["status"] == "ready"]

    print()
    print("=" * 66)
    print(f"  {len(ready)}/{len(FILES)} meetings ready on {BASE}")
    print()
    print(f"  Sign in:  {DEMO_EMAIL}")
    print(f"  Password: {DEMO_PASSWORD}")
    print("=" * 66)
    return 0 if len(ready) == len(FILES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
