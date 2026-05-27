"""Password hashing utilities — bcrypt preferred, PBKDF2-SHA256 fallback."""
import os
import hashlib

try:
    import bcrypt as _bcrypt
    _BCRYPT = True
except ImportError:
    _BCRYPT = False


def hash_password(password: str) -> str:
    """Return a secure hash of *password*.

    Uses bcrypt when available; falls back to PBKDF2-HMAC-SHA256 with a
    random 32-byte salt stored as ``<hex_salt>:<hex_key>``.
    """
    if _BCRYPT:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=12)).decode()
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return f"{salt.hex()}:{key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Return True if *password* matches *hashed*."""
    if hashed.startswith("$2") and _BCRYPT:
        return _bcrypt.checkpw(password.encode(), hashed.encode())
    try:
        salt_hex, key_hex = hashed.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
        return key.hex() == key_hex
    except (ValueError, AttributeError):
        return False
