from __future__ import annotations

"""
Migrate users from ChatRoom PostgreSQL table `public.users` into lugwit_auth tables:
  - users
  - user_roles

Designed for URLs like `postgresql+asyncpg://...` (same driver stack as ChatRoom).

By default we INSERT with explicit id = ChatRoom users.id so existing FKs that reference legacy `users.id`
can keep the same IDs in the unified `users` table.
"""

import argparse
import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .db import Base
from .models import AuthUser, AuthUserRole


def _normalize_async_database_url(url: str) -> str:
    u = url.strip()
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    if u.startswith("postgresql://") and "+asyncpg" not in u:
        return "postgresql+asyncpg://" + u[len("postgresql://") :]
    return u


def _truncate(s: str | None, max_len: int) -> str | None:
    if s is None:
        return None
    if len(s) <= max_len:
        return s
    return s[:max_len]


def _user_status_to_auth_status(user_status: Any) -> str:
    try:
        v = int(user_status)
    except Exception:
        return "active"
    # ChatRoom UserStatusEnum
    if v == 0:
        return "active"
    if v == 1:
        return "disabled"
    if v == 2:
        return "deleted"
    return "active"


def _role_to_str(role: Any) -> str:
    try:
        return str(int(role))
    except Exception:
        return str(role)


async def _reset_sequence(engine: AsyncEngine, table: str, column: str = "id") -> None:
    allowed = {("users", "id"), ("user_roles", "id")}
    if (table, column) not in allowed:
        return

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT setval(pg_get_serial_sequence(:tbl, :col), "
                f"COALESCE((SELECT MAX({column}) FROM {table}), 1))"
            ),
            {"tbl": table, "col": column},
        )


async def migrate_async(
    *,
    source_url: str,
    dest_url: str,
    preserve_ids: bool,
    skip_existing: bool,
) -> tuple[int, int]:
    src_engine = create_async_engine(source_url, future=True)
    dst_engine = create_async_engine(dest_url, future=True)

    async with dst_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionDst = async_sessionmaker(dst_engine, expire_on_commit=False)

    migrated_users = 0
    migrated_roles = 0
    now = datetime.now(timezone.utc)

    async with src_engine.connect() as src, SessionDst() as dst:
        rows = (await src.execute(
            text(
                """
                SELECT id, username, hashed_password, email, nickname, role, user_status, last_login,
                       created_at, updated_at
                FROM users
                ORDER BY id
                """
            )
        )).mappings().all()

        for row in rows:
            uid = int(row["id"])
            username = str(row["username"])

            if skip_existing:
                exists = (
                    await dst.execute(
                        text("SELECT 1 FROM users WHERE username = :u LIMIT 1"),
                        {"u": username},
                    )
                ).scalar()
                if exists:
                    continue

            status = _user_status_to_auth_status(row.get("user_status"))
            role_str = _role_to_str(row.get("role"))

            user_kwargs: dict[str, Any] = {
                "username": username,
                "password_hash": str(row["hashed_password"]),
                "status": status,
                "display_name": _truncate((str(row["nickname"]) if row.get("nickname") is not None else None), 128),
                "email": _truncate((str(row["email"]) if row.get("email") is not None else None), 128),
                "phone": None,
                "last_login_at": row.get("last_login"),
                "created_at": row.get("created_at") or now,
                "updated_at": row.get("updated_at") or now,
            }
            if preserve_ids:
                user_kwargs["id"] = uid

            u = AuthUser(**user_kwargs)
            dst.add(u)
            await dst.flush()

            dst.add(
                AuthUserRole(
                    user_id=int(u.id),
                    role=role_str,
                    is_primary=True,
                    created_at=row.get("created_at") or now,
                    updated_at=row.get("updated_at") or now,
                )
            )
            migrated_users += 1
            migrated_roles += 1

        await dst.commit()

    await _reset_sequence(dst_engine, "users", "id")
    await _reset_sequence(dst_engine, "user_roles", "id")

    await src_engine.dispose()
    await dst_engine.dispose()
    return migrated_users, migrated_roles


def migrate(
    *,
    source_url: str,
    dest_url: str,
    preserve_ids: bool,
    skip_existing: bool,
) -> tuple[int, int]:
    return asyncio.run(
        migrate_async(
            source_url=source_url,
            dest_url=dest_url,
            preserve_ids=preserve_ids,
            skip_existing=skip_existing,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate ChatRoom users -> lugwit_auth.users")
    parser.add_argument(
        "--source-url",
        default=(os.environ.get("LUGWIT_CHATROOM_DATABASE_URL") or "").strip(),
        help="ChatRoom DB URL (asyncpg). Or env LUGWIT_CHATROOM_DATABASE_URL",
    )
    parser.add_argument(
        "--dest-url",
        default=(os.environ.get("LUGWIT_AUTH_DATABASE_URL") or "").strip(),
        help="lugwit_auth DB URL (asyncpg). Or env LUGWIT_AUTH_DATABASE_URL",
    )
    parser.add_argument(
        "--no-preserve-ids",
        action="store_true",
        help="Do not force users.id = ChatRoom users.id (not recommended if other tables depend on legacy ids)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Fail on username conflict instead of skipping existing usernames in users",
    )
    parser.add_argument(
        "--no-normalize-url",
        action="store_true",
        help="Do not rewrite postgresql:// -> postgresql+asyncpg://",
    )
    args = parser.parse_args(argv)

    src = args.source_url
    dst = args.dest_url
    if not src or not dst:
        raise SystemExit("Need --source-url/--dest-url or LUGWIT_CHATROOM_DATABASE_URL + LUGWIT_AUTH_DATABASE_URL")

    if not args.no_normalize_url:
        src = _normalize_async_database_url(src)
        dst = _normalize_async_database_url(dst)

    preserve_ids = not args.no_preserve_ids
    skip_existing = not args.no_skip_existing

    users_n, roles_n = migrate(
        source_url=src,
        dest_url=dst,
        preserve_ids=preserve_ids,
        skip_existing=skip_existing,
    )
    print(f"migrated_users={users_n} migrated_roles={roles_n} preserve_ids={preserve_ids} skip_existing={skip_existing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
