"""Generate a .env with real, unique secrets.

Run once: python scripts/bootstrap_env.py

Never overwrites an existing .env — rotating ENCRYPTION_KEY would make every
stored transcript permanently unreadable, so that has to be a deliberate act.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"


def main() -> int:
    if ENV.exists():
        print(f"[skip] {ENV} already exists — not touching it.")
        print("       Delete it manually if you really want fresh secrets.")
        print("       WARNING: a new ENCRYPTION_KEY makes existing transcripts unreadable forever.")
        return 0

    if not EXAMPLE.exists():
        print(f"[error] {EXAMPLE} is missing.", file=sys.stderr)
        return 1

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("[error] cryptography isn't installed yet.", file=sys.stderr)
        print("        Run: pip install -r backend/requirements.txt", file=sys.stderr)
        return 1

    replacements = {
        "JWT_SECRET": secrets.token_urlsafe(64),
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "MEDIA_SIGNING_SECRET": secrets.token_urlsafe(64),
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
    }

    lines = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.startswith("#") else None
        if key in replacements:
            lines.append(f"{key}={replacements[key]}")
        else:
            lines.append(line)

    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Best-effort on Windows; the real protection is .gitignore + local-only.
    try:
        ENV.chmod(0o600)
    except OSError:
        pass

    print(f"[ok] Wrote {ENV} with freshly generated secrets.")
    print("     This file is git-ignored. Never commit it, never paste it anywhere.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
