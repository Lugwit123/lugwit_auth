from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt


@dataclass(frozen=True)
class JwtConfig:
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 24 * 60


class JwtService:
    def __init__(self, cfg: JwtConfig):
        self._cfg = cfg

    def create_access_token(self, claims: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        to_encode = dict(claims)
        now = datetime.now(timezone.utc)
        expire = now + (expires_delta or timedelta(minutes=self._cfg.access_token_expire_minutes))
        to_encode["exp"] = expire
        return jwt.encode(to_encode, self._cfg.secret_key, algorithm=self._cfg.algorithm)

    def decode(self, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        options = {"verify_exp": bool(verify_exp)}
        return jwt.decode(token, self._cfg.secret_key, algorithms=[self._cfg.algorithm], options=options)

    def verify(self, token: str) -> dict[str, Any]:
        return self.decode(token, verify_exp=True)


__all__ = ["JWTError", "JwtConfig", "JwtService"]

