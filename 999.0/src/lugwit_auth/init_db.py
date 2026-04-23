from __future__ import annotations

import os

from sqlalchemy import create_engine

from .db import Base
from .models import AuthSession, AuthUser, AuthUserRole  # noqa: F401


def init_db(database_url: str) -> None:
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)


def main() -> int:
    database_url = (os.environ.get("LUGWIT_AUTH_DATABASE_URL") or "").strip()
    if not database_url:
        raise SystemExit("Missing env LUGWIT_AUTH_DATABASE_URL")
    init_db(database_url)
    print("lugwit_auth tables created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

