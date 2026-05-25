"""User management service."""
from __future__ import annotations

from typing import Dict, List, Optional

from src.data import db_manager as db
from src.services import auth_service
from src.utils.crypto import hash_password
from src.utils.logger import get_logger

log = get_logger(__name__)


def list_users() -> List[Dict]:
    """Return all users (admin only)."""
    auth_service.require_role("admin")
    return db.get_all_users()


def update_user(user_id: int, data: Dict) -> None:
    """Update user profile fields (admin only).

    Args:
        user_id: Target user PK.
        data:    Dict of fields to update.
    """
    auth_service.require_role("admin")
    db.update_user(user_id, data)
    actor = auth_service.get_current_user()
    db.write_audit_log(
        "UPDATE", user_id=actor.id if actor else None,
        table_name="users", record_id=user_id,
    )


def deactivate_user(user_id: int) -> None:
    """Deactivate (soft-delete) a user account.

    Args:
        user_id: Target user PK.
    """
    auth_service.require_role("admin")
    db.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))


def reset_password(user_id: int, new_password: str) -> None:
    """Reset a user's password (admin only).

    Args:
        user_id:      Target user PK.
        new_password: New plaintext password.
    """
    auth_service.require_role("admin")
    pw = hash_password(new_password)
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (pw, user_id))
    actor = auth_service.get_current_user()
    db.write_audit_log(
        "UPDATE", user_id=actor.id if actor else None,
        table_name="users", record_id=user_id,
        detail="password_reset",
    )
