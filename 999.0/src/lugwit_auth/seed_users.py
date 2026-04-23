from __future__ import annotations

import argparse
import os
import random
import string
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .models import AuthUser, AuthUserRole
from .security import get_password_hash


def _rand_str(n: int, *, alphabet: str) -> str:
    return "".join(random.choice(alphabet) for _ in range(n))


def _candidate_usernames(prefix: str, count: int) -> Iterable[str]:
    # Example: demo_user_ab12cd
    alphabet = string.ascii_lowercase + string.digits
    for _ in range(count * 3):
        yield f"{prefix}{_rand_str(6, alphabet=alphabet)}"


def seed_users(
    *,
    database_url: str,
    count: int,
    username_prefix: str,
    default_password: str,
    role: str,
) -> int:
    engine = create_engine(database_url)
    created = 0
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        existing = set(session.scalars(select(AuthUser.username)).all())

        for uname in _candidate_usernames(username_prefix, count):
            if uname in existing:
                continue
            user = AuthUser(
                username=uname,
                password_hash=get_password_hash(default_password),
                status="active",
                display_name=uname,
                last_login_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()  # populate user.id

            session.add(
                AuthUserRole(
                    user_id=user.id,
                    role=role,
                    is_primary=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            existing.add(uname)
            created += 1
            if created >= count:
                break

        session.commit()

    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed random users into lugwit_auth.auth_users")
    parser.add_argument(
        "--database-url",
        default=(os.environ.get("LUGWIT_AUTH_DATABASE_URL") or "").strip(),
        help="DB url (or env LUGWIT_AUTH_DATABASE_URL)",
    )
    parser.add_argument("--count", type=int, default=5, help="How many users to create (default: 5)")
    parser.add_argument("--username-prefix", default="demo_user_", help="Username prefix (default: demo_user_)")
    parser.add_argument(
        "--password",
        default="lugwit123",
        help="Default password for seeded users (default: lugwit123)",
    )
    parser.add_argument(
        "--role",
        default="user",
        help="Primary role name to assign (default: user)",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        raise SystemExit("Missing --database-url or env LUGWIT_AUTH_DATABASE_URL")
    if args.count <= 0:
        raise SystemExit("--count must be positive")

    created = seed_users(
        database_url=args.database_url,
        count=int(args.count),
        username_prefix=str(args.username_prefix),
        default_password=str(args.password),
        role=str(args.role),
    )
    print(f"seeded_users={created} password={args.password} role={args.role} prefix={args.username_prefix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

