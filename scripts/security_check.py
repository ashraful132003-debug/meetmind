"""End-to-end security checks against a running MeetMind API.

This is an attack script, not a unit test. It signs up two users and then tries
to break the things the README claims are safe. Every check that PASSES means an
attack FAILED.

Run:  python scripts/security_check.py
"""

from __future__ import annotations

import secrets
import sys
import time
import uuid

import httpx

import os
BASE = os.getenv("BASE", "http://127.0.0.1:8000")

passed = 0
failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f"\n         {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


class RateLimited(RuntimeError):
    """The registration limiter blocked us.

    Not a failure of the app - it is the limiter doing its job. But this suite
    creates several accounts per run, so a few runs in one hour will legitimately
    exhaust the quota and every subsequent check would report a misleading
    failure. Better to stop and say so plainly.
    """


def make_user(client: httpx.Client) -> tuple[str, str, str]:
    email = f"probe-{uuid.uuid4().hex[:10]}@example.com"
    password = f"Str0ng-{secrets.token_urlsafe(12)}"
    r = client.post(
        f"{BASE}/api/auth/register",
        json={"email": email, "full_name": "Probe User", "password": password},
    )
    if r.status_code == 429:
        raise RateLimited()
    r.raise_for_status()
    return email, password, r.json()["access_token"]


def main() -> int:
    print("MeetMind security probe")
    print("=" * 60)

    try:
        httpx.get(f"{BASE}/api/health", timeout=5)
    except httpx.ConnectError:
        print(f"\n[error] No API at {BASE}. Start the backend first.")
        return 1

    # --- Auth basics ---------------------------------------------------------
    section("Authentication")

    with httpx.Client(timeout=30, follow_redirects=False) as c:
        r = c.get(f"{BASE}/api/meetings")
        check("Unauthenticated request is rejected", r.status_code == 401, f"got {r.status_code}")

        r = c.get(f"{BASE}/api/meetings", headers={"Authorization": "Bearer not-a-real-token"})
        check("Garbage token is rejected", r.status_code == 401, f"got {r.status_code}")

        # A token signed with the wrong key must not be accepted.
        import jwt

        forged = jwt.encode(
            {"sub": str(uuid.uuid4()), "type": "access", "exp": int(time.time()) + 3600},
            "attacker-guessed-secret",
            algorithm="HS256",
        )
        r = c.get(f"{BASE}/api/meetings", headers={"Authorization": f"Bearer {forged}"})
        check("Token signed with a wrong secret is rejected", r.status_code == 401, f"got {r.status_code}")

        # The classic alg=none forgery.
        none_token = jwt.encode({"sub": str(uuid.uuid4()), "type": "access"}, "", algorithm="none")
        r = c.get(f"{BASE}/api/meetings", headers={"Authorization": f"Bearer {none_token}"})
        check("alg=none token is rejected", r.status_code == 401, f"got {r.status_code}")

    # --- Password policy -----------------------------------------------------
    section("Password policy")

    with httpx.Client(timeout=30) as c:
        for weak, why in [
            ("short1", "too short"),
            ("password123", "common password"),
            ("aaaaaaaaaa1", "too repetitive"),
            ("abcdefghijkl", "no digits"),
        ]:
            r = c.post(
                f"{BASE}/api/auth/register",
                json={"email": f"weak-{uuid.uuid4().hex[:8]}@example.com", "full_name": "Weak", "password": weak},
            )
            if r.status_code == 429:
                raise RateLimited()
            check(f"Weak password rejected ({why})", r.status_code == 422, f"got {r.status_code}")

    # --- Login hygiene -------------------------------------------------------
    section("Login")

    with httpx.Client(timeout=30) as c:
        email, password, _ = make_user(c)

        r = c.post(f"{BASE}/api/auth/login", json={"email": email, "password": "WrongPassword123"})
        wrong_pw_msg = r.json().get("detail", "")
        check("Wrong password is rejected", r.status_code == 401, f"got {r.status_code}")

        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com", "password": "WhateverPass123"},
        )
        unknown_msg = r.json().get("detail", "")
        check(
            "Unknown email gives the same message as wrong password (no user enumeration)",
            wrong_pw_msg == unknown_msg and r.status_code == 401,
            f"wrong-pw: {wrong_pw_msg!r} vs unknown: {unknown_msg!r}",
        )

    # --- Refresh rotation + reuse detection ---------------------------------
    section("Refresh token rotation")

    with httpx.Client(timeout=30) as c:
        email, password, _ = make_user(c)
        first_cookie = c.cookies.get("meetmind_refresh")
        check("Refresh cookie is set on register", bool(first_cookie))

        r = c.post(f"{BASE}/api/auth/refresh")
        check("Refresh succeeds with a valid cookie", r.status_code == 200, f"got {r.status_code}")
        second_cookie = c.cookies.get("meetmind_refresh")
        check("Refresh token is rotated (new value issued)", first_cookie != second_cookie)

        # Replay the OLD token - this simulates a stolen cookie being reused.
        #
        # The cookie domain must match whatever BASE points at. It used to be
        # hardcoded to 127.0.0.1, which meant that against a deployed URL the
        # attacker's cookie was never sent at all: the replay silently became an
        # unauthenticated request, "rejected" for the wrong reason, and the
        # reuse-detection check that follows then failed. A test that passes
        # because it never ran the attack is worse than no test.
        from urllib.parse import urlparse

        cookie_domain = urlparse(BASE).hostname or "127.0.0.1"

        with httpx.Client(timeout=30) as attacker:
            attacker.cookies.set("meetmind_refresh", first_cookie or "", domain=cookie_domain)
            r = attacker.post(f"{BASE}/api/auth/refresh")
            sent = "meetmind_refresh" in attacker.cookies
            check(
                "Replaying a rotated refresh token is rejected",
                r.status_code == 401 and sent,
                f"got {r.status_code}"
                + ("" if sent else " - cookie was never sent, so no replay actually happened"),
            )

        # After detected reuse, the legitimate session must also be dead.
        r = c.post(f"{BASE}/api/auth/refresh")
        check(
            "Token-family is revoked after reuse is detected (victim logged out too)",
            r.status_code == 401,
            f"got {r.status_code} - the family should be revoked",
        )

    # --- Ownership isolation -------------------------------------------------
    section("Data isolation between users")

    with httpx.Client(timeout=30) as alice_c, httpx.Client(timeout=30) as mallory_c:
        _, _, alice_token = make_user(alice_c)
        _, _, mallory_token = make_user(mallory_c)

        alice_h = {"Authorization": f"Bearer {alice_token}"}
        mallory_h = {"Authorization": f"Bearer {mallory_token}"}

        # Alice uploads a meeting. A tiny valid WAV is enough - we only need a row.
        import struct

        sample_rate = 16000
        frames = b"\x00\x00" * sample_rate  # 1 second of silence
        wav = (
            b"RIFF"
            + struct.pack("<I", 36 + len(frames))
            + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
            + b"data"
            + struct.pack("<I", len(frames))
            + frames
        )

        r = alice_c.post(
            f"{BASE}/api/meetings",
            headers=alice_h,
            files={"file": ("alice-private.wav", wav, "audio/wav")},
            data={"title": "Alice confidential board meeting", "source": "upload"},
        )
        if r.status_code != 201:
            check("Alice can upload a meeting", False, f"got {r.status_code}: {r.text[:200]}")
            return 1
        check("Alice can upload a meeting", True)
        meeting_id = r.json()["id"]

        for label, path in [
            ("meeting detail", f"/api/meetings/{meeting_id}"),
            ("transcript", f"/api/meetings/{meeting_id}/transcript"),
            ("analytics", f"/api/meetings/{meeting_id}/analytics"),
            ("chat history", f"/api/meetings/{meeting_id}/chat"),
            ("email history", f"/api/meetings/{meeting_id}/email"),
        ]:
            r = mallory_c.get(f"{BASE}{path}", headers=mallory_h)
            check(f"Mallory cannot read Alice's {label}", r.status_code == 404, f"got {r.status_code}")

        r = mallory_c.delete(f"{BASE}/api/meetings/{meeting_id}", headers=mallory_h)
        check("Mallory cannot delete Alice's meeting", r.status_code == 404, f"got {r.status_code}")

        r = mallory_c.patch(
            f"{BASE}/api/meetings/{meeting_id}", headers=mallory_h, json={"title": "pwned"}
        )
        check("Mallory cannot rename Alice's meeting", r.status_code == 404, f"got {r.status_code}")

        r = mallory_c.post(
            f"{BASE}/api/meetings/{meeting_id}/chat", headers=mallory_h, json={"question": "What is secret?"}
        )
        check("Mallory cannot query Alice's meeting via chat", r.status_code == 404, f"got {r.status_code}")

        # A non-existent id and someone else's id must be indistinguishable.
        r_other = mallory_c.get(f"{BASE}/api/meetings/{meeting_id}", headers=mallory_h)
        r_fake = mallory_c.get(f"{BASE}/api/meetings/{uuid.uuid4()}", headers=mallory_h)
        check(
            "Existing-but-forbidden and non-existent are indistinguishable",
            r_other.status_code == r_fake.status_code and r_other.text == r_fake.text,
            f"{r_other.status_code}/{r_other.text[:60]} vs {r_fake.status_code}/{r_fake.text[:60]}",
        )

        # Alice still owns it.
        r = alice_c.get(f"{BASE}/api/meetings/{meeting_id}", headers=alice_h)
        check("Alice can still read her own meeting", r.status_code == 200, f"got {r.status_code}")

        # --- Signed media URLs -----------------------------------------------
        section("Signed audio URLs")

        detail = r.json()
        audio_url = detail.get("audio_url")
        check("Audio URL is issued with a signature token", bool(audio_url and "token=" in audio_url))

        if audio_url:
            r = alice_c.get(f"{BASE}{audio_url}", headers=alice_h)
            check("Valid signed URL serves audio", r.status_code in (200, 206), f"got {r.status_code}")

            tampered = audio_url.rsplit("token=", 1)[0] + "token=9999999999.deadbeef"
            r = alice_c.get(f"{BASE}{tampered}", headers=alice_h)
            check("Forged signature is rejected", r.status_code == 403, f"got {r.status_code}")

            r = alice_c.get(f"{BASE}/api/meetings/{meeting_id}/audio", headers=alice_h)
            check("Audio without a token is rejected", r.status_code == 422, f"got {r.status_code}")

            # Mallory has the exact URL Alice was given - it must still fail,
            # because the token binds the OWNER, not the requester.
            r = mallory_c.get(f"{BASE}{audio_url}")
            check(
                "Leaked audio URL is useless to another user's meeting",
                r.status_code in (403, 404),
                f"got {r.status_code}",
            )

        # --- Upload validation -----------------------------------------------
        section("Upload validation")

        r = alice_c.post(
            f"{BASE}/api/meetings",
            headers=alice_h,
            files={"file": ("evil.exe", b"MZ\x90\x00malicious", "application/octet-stream")},
            data={"title": "exe", "source": "upload"},
        )
        check("Executable upload is rejected", r.status_code == 415, f"got {r.status_code}")

        r = alice_c.post(
            f"{BASE}/api/meetings",
            headers=alice_h,
            files={"file": ("fake.wav", b"MZ\x90\x00 this is not audio at all", "audio/wav")},
            data={"title": "disguised", "source": "upload"},
        )
        check(
            "Non-audio content disguised with a .wav name is rejected (magic-byte check)",
            r.status_code == 415,
            f"got {r.status_code}",
        )

        r = alice_c.post(
            f"{BASE}/api/meetings",
            headers=alice_h,
            files={"file": ("../../../escape.wav", wav, "audio/wav")},
            data={"title": "traversal", "source": "upload"},
        )
        # Two acceptable outcomes, and the distinction matters:
        #
        #  201 - the request reached the app, which ignored the client's filename
        #        and stored the file under a generated name. This is what happens
        #        locally, and it is the app's own defence.
        #  403 - a WAF in front (Cloudflare, on Render) rejected the traversal
        #        pattern before it ever reached the app. Also fine: defence in
        #        depth. Identifiable because our X-Request-ID middleware never ran.
        #
        # A 500, or a 201 whose file landed outside storage, would be the failure.
        blocked_at_edge = r.status_code == 403 and "X-Request-ID" not in r.headers
        check(
            "Path-traversal filename cannot escape storage",
            r.status_code == 201 or blocked_at_edge,
            f"got {r.status_code}"
            + (" (blocked upstream by the host's WAF)" if blocked_at_edge else ""),
        )
        if r.status_code == 201:
            alice_c.delete(f"{BASE}/api/meetings/{r.json()['id']}", headers=alice_h)

        alice_c.delete(f"{BASE}/api/meetings/{meeting_id}", headers=alice_h)

    # --- Static/SPA serving --------------------------------------------------
    # Only meaningful in the single-image production deployment, where FastAPI
    # serves the built SPA itself. Skipped in dev, where Vite serves it.
    with httpx.Client(timeout=30) as c:
        spa = c.get(f"{BASE}/")
        if spa.status_code == 200 and "<!doctype html" in spa.text.lower():
            section("SPA serving (production single-image mode)")

            check("Client-side routes fall back to index.html",
                  c.get(f"{BASE}/meetings").status_code == 200)

            r = c.get(f"{BASE}/api/definitely-not-a-real-route")
            check(
                "Unknown /api/* 404s as JSON rather than falling through to HTML",
                r.status_code == 404 and "<!doctype" not in r.text.lower(),
                f"{r.status_code}: {r.text[:60]}",
            )

            # The SPA handler resolves user-supplied paths against the static
            # directory. If that resolution is not constrained, ".." walks out to
            # .env and hands an attacker every secret in the app.
            leaked = []
            for path in ["/../.env", "/..%2F.env", "/%2e%2e/.env", "/static/../.env",
                         "/assets/../../.env", "/.env", "/../backend/app/config.py"]:
                try:
                    body = c.get(f"{BASE}{path}").text
                except Exception:
                    continue
                if any(k in body for k in ("JWT_SECRET", "ENCRYPTION_KEY", "POSTGRES_PASSWORD")):
                    leaked.append(path)
            check(
                "Path traversal cannot read .env through the SPA route",
                not leaked,
                f"LEAKED via: {leaked}",
            )

            # The CSP has to differ between the API and the page. Get this wrong
            # and the deployed site is a blank white page with the explanation
            # only in the browser console - no command-line check catches it,
            # because curl does not enforce CSP.
            page_csp = spa.headers.get("Content-Security-Policy", "")
            check(
                "SPA page CSP allows its own scripts (or the site renders blank)",
                "script-src 'self'" in page_csp,
                f"CSP was: {page_csp[:90]}",
            )
            check(
                "SPA page CSP still forbids inline scripts (XSS defence intact)",
                "'unsafe-inline'" not in page_csp.split("style-src")[0],
                f"script-src allows inline: {page_csp[:90]}",
            )
            check(
                "SPA page CSP forbids third-party connections (privacy claim enforced)",
                "connect-src 'self'" in page_csp,
                f"CSP was: {page_csp[:90]}",
            )

            api_csp = c.get(f"{BASE}/api/health").headers.get("Content-Security-Policy", "")
            check(
                "API CSP stays locked to default-src 'none'",
                "default-src 'none'" in api_csp,
                f"CSP was: {api_csp[:90]}",
            )

    # --- Security headers ----------------------------------------------------
    section("Security headers")

    with httpx.Client(timeout=30) as c:
        r = c.get(f"{BASE}/api/health")
        for header, expected in [
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
        ]:
            check(f"{header}: {expected}", r.headers.get(header) == expected, f"got {r.headers.get(header)!r}")
        check("Content-Security-Policy is set", "Content-Security-Policy" in r.headers)

    # --- Rate limiting -------------------------------------------------------
    section("Rate limiting")

    with httpx.Client(timeout=30) as c:
        codes = [
            c.post(
                f"{BASE}/api/auth/login",
                json={"email": "ratelimit-probe@example.com", "password": "WrongPassword123"},
            ).status_code
            for _ in range(12)
        ]
        check(
            "Login brute-force is rate limited (429 appears)",
            429 in codes,
            f"codes seen: {codes}",
        )

    # --- Summary -------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"  {passed} passed, {failed} failed")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RateLimited:
        print("\n" + "=" * 60)
        print("  STOPPED: the registration rate limiter blocked this run.")
        print("=" * 60)
        print("  This is the app working correctly, not a bug - registration is")
        print("  capped at 20/hour per IP, and this suite creates several accounts")
        print("  each run.")
        print()
        print("  To run again now, restart the backend (the limiter is in-process,")
        print("  so a restart clears it):")
        print("    .\\start.ps1 -Stop  ;  .\\start.ps1")
        print()
        print("  Or just wait an hour.")
        sys.exit(2)
