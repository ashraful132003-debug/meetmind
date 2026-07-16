"""Migration: let chat_messages hold workspace-wide conversations too.

Adds `user_id`, makes `meeting_id` nullable, and backfills `user_id` on existing
rows from the meeting they belong to.

Idempotent — safe to run against a database that already has the change, which
matters because it runs against both the local database and Neon.

Run:  python scripts/migrate_chat_scope.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402

STEPS = [
    (
        "add user_id column",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS user_id UUID "
        "REFERENCES users(id) ON DELETE CASCADE",
    ),
    (
        "index user_id",
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_user_id ON chat_messages (user_id)",
    ),
    (
        "index (user_id, created_at) for the workspace conversation",
        "CREATE INDEX IF NOT EXISTS ix_chat_user_workspace ON chat_messages (user_id, created_at)",
    ),
    (
        "make meeting_id nullable (workspace messages belong to no single meeting)",
        "ALTER TABLE chat_messages ALTER COLUMN meeting_id DROP NOT NULL",
    ),
    (
        "backfill user_id from each message's meeting",
        "UPDATE chat_messages c SET user_id = m.owner_id FROM meetings m "
        "WHERE c.meeting_id = m.id AND c.user_id IS NULL",
    ),
    (
        "require every row to have an owner path",
        "ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS ck_chat_has_owner",
    ),
    (
        "  (re-add)",
        "ALTER TABLE chat_messages ADD CONSTRAINT ck_chat_has_owner "
        "CHECK (meeting_id IS NOT NULL OR user_id IS NOT NULL)",
    ),
]


async def main() -> int:
    print(f"Migrating chat_messages on {engine.url.host}:{engine.url.port}/{engine.url.database}")
    print("=" * 66)

    async with engine.begin() as conn:
        for label, sql in STEPS:
            try:
                await conn.execute(text(sql))
                print(f"  [ok] {label}")
            except Exception as e:
                print(f"  [FAIL] {label}\n         {type(e).__name__}: {str(e)[:160]}")
                return 1

    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name='chat_messages' AND column_name IN ('user_id','meeting_id') "
                "ORDER BY column_name"
            )
        )
        print()
        for name, nullable in rows:
            print(f"  {name:12} nullable={nullable}")

        orphans = await conn.scalar(
            text("SELECT count(*) FROM chat_messages WHERE user_id IS NULL AND meeting_id IS NULL")
        )
        print(f"  orphaned rows: {orphans}")

    await engine.dispose()
    print("\n[done]")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
