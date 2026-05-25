"""Password hashing utilities.

Attempts to use *bcrypt* for Argon2-class work-factor security.
Falls back to salted SHA-256 when bcrypt is not installed so the
application still runs in restricted environments.
"""
from __future__ import annotations

import hashlib
import os
import secrets

from src.utils.logger import get_logger

log = get_logger(__name__)

try:
    import bcrypt as _bcrypt  # type: ignore
    _USE_BCRYPT = True
    log.info("Using bcrypt for password hashing.")
except ImportError:
    _USE_BCRYPT = False
    log.warning("bcrypt not available – falling back to salted SHA-256.")


# ─── Public API ──────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash a plaintext password and return the storable string.

    Args:
        plain: The user's plaintext password.

    Returns:
        A hash string suitable for database storage.
    """
    if _USE_BCRYPT:
        return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt(rounds=12)).decode()
    return _sha256_hash(plain)


def verify_password(plain: str, stored: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Args:
        plain:  Plaintext password to check.
        stored: Hash previously returned by :func:`hash_password`.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    if _USE_BCRYPT and stored.startswith("$2"):
        try:
            return _bcrypt.checkpw(plain.encode(), stored.encode())
        except Exception:  # noqa: BLE001
            return False
    return _sha256_verify(plain, stored)


# ─── Private helpers ─────────────────────────────────────────────────────────

def _sha256_hash(plain: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}{plain}".encode()).hexdigest()
    return f"sha256${salt}${digest}"


def _sha256_verify(plain: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        return secrets.compare_digest(
            hashlib.sha256(f"{salt}{plain}".encode()).hexdigest(), digest
        )
    except (ValueError, AttributeError):
        return False
