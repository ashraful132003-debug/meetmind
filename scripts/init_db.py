"""Create the database schema and report what exists.

Idempotent: SQLAlchemy's create_all only creates missing tables, so running this
against an existing database is safe and touches nothing.

Run from the repo root:  python scripts/init_db.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text  # noqa: E402

from app.db import engine, init_models  # noqa: E402


async def main() -> int:
    try:
        await init_models()
    except Exception as e:
        print(f"[error] Could not create the schema: {type(e).__name__}: {e}")
        print("        Is PostgreSQL running?  .\\scripts\\pg.ps1 status")
        return 1

    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        )
        tables = [r[0] for r in rows]

    await engine.dispose()

    print(f"[ok] Schema ready - {len(tables)} tables")
    for t in tables:
        print(f"     - {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
