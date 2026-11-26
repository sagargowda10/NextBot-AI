"""JWT access/refresh tokens (PyJWT)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.exceptions import AuthenticationError


def create_token(*, subject: str, roles: list[str], secret: str, algorithm: str, expires_in: timedelta, token_type: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "roles": roles,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        "jti": uuid.uuid4().hex,
        "iss": "nextbot-ai",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, *, secret: str, algorithm: str, expected_type: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, secret, algorithms=[algorithm], issuer="nextbot-ai")
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid token") from exc
    if payload.get("type") != expected_type:
        raise AuthenticationError("Wrong token type")
    return payload
