"""BCrypt password hashing via pwdlib (passlib is unmaintained)."""

from __future__ import annotations

from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

_hasher = PasswordHash((BcryptHasher(rounds=12),))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(password, hashed)
    except Exception:  # malformed hash
        return False
