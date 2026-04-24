from __future__ import annotations

"""
One-time DB rename to make lugwit_auth tables use generic names.

Default behavior (PostgreSQL):
  - If legacy ChatRoom `users` exists, rename it to `users_legacy`
  - Rename lugwit_auth tables:
      auth_users       -> users
      auth_user_roles  -> user_roles
      auth_sessions    -> sessions

This is meant to help you end up with ONE `users` table (no auth_ prefix).
"""

import argparse
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def run(database_url: str, *, legacy_users_name: str) -> None:
    engine = create_async_engine(database_url, future=True)
    async with engine.begin() as conn:
        # Rename existing `users` out of the way (if present)
        legacy_exists = await conn.scalar(text("select to_regclass('public.users') is not null"))
        auth_users_exists = await conn.scalar(text("select to_regclass('public.auth_users') is not null"))
        if legacy_exists and auth_users_exists:
            target_taken = await conn.scalar(
                text("select to_regclass(:t) is not null"), {"t": f"public.{legacy_users_name}"}
            )
            if target_taken:
                raise RuntimeError(f"target legacy table already exists: {legacy_users_name}")
            await conn.execute(text(f'ALTER TABLE public.users RENAME TO "{legacy_users_name}"'))

        # Now rename auth tables if present
        if auth_users_exists:
            await conn.execute(text('ALTER TABLE public.auth_users RENAME TO "users"'))

        roles_exists = await conn.scalar(text("select to_regclass('public.auth_user_roles') is not null"))
        if roles_exists:
            await conn.execute(text('ALTER TABLE public.auth_user_roles RENAME TO "user_roles"'))

        sessions_exists = await conn.scalar(text("select to_regclass('public.auth_sessions') is not null"))
        if sessions_exists:
            await conn.execute(text('ALTER TABLE public.auth_sessions RENAME TO "sessions"'))

    await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rename lugwit_auth auth_* tables to generic names")
    p.add_argument(
        "--database-url",
        default=(os.environ.get("LUGWIT_AUTH_DATABASE_URL") or "").strip(),
        help="Target DB url (or env LUGWIT_AUTH_DATABASE_URL)",
    )
    p.add_argument("--legacy-users-name", default="users_legacy", help="Rename existing users to this (default: users_legacy)")
    args = p.parse_args(argv)

    if not args.database_url:
        raise SystemExit("Missing --database-url or env LUGWIT_AUTH_DATABASE_URL")
    asyncio.run(run(str(args.database_url), legacy_users_name=str(args.legacy_users_name)))
    print("rename_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

