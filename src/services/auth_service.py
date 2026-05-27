"""Authentication and session service."""
from __future__ import annotations
from typing import Optional
from ..data.db_manager import DBManager
from ..models.user import User
from ..utils.crypto import hash_password, verify_password
from ..utils.logger import get_logger

log = get_logger()


class AuthService:
    """Handles login, logout, and password management."""

    def __init__(self, db: DBManager) -> None:
        self.db = db
        self.current_user: Optional[User] = None

    def login(self, username: str, password: str) -> Optional[User]:
        """Attempt login; return User on success, None on failure."""
        row = self.db.get_user_by_username(username)
        if not row:
            log.warning("Login failed: unknown user '%s'", username)
            return None
        if not row.get("is_active"):
            log.warning("Login failed: user '%s' is inactive", username)
            return None
        if not verify_password(password, row["password_hash"]):
            log.warning("Login failed: bad password for '%s'", username)
            return None
        user = User.from_row(row)
        self.db.update_last_login(user.id)
        self.db.log_action(user.id, "LOGIN", details=f"User {username} logged in")
        self.current_user = user
        log.info("User '%s' logged in (role=%s)", username, user.role)
        return user

    def logout(self) -> None:
        """Clear the current session."""
        if self.current_user:
            self.db.log_action(self.current_user.id, "LOGOUT")
        self.current_user = None

    def change_password(self, user_id: int, old_password: str,
                        new_password: str) -> tuple[bool, str]:
        """Change password for *user_id*. Returns (success, message)."""
        row = self.db.get_user_by_id(user_id)
        if not row:
            return False, "User not found"
        if not verify_password(old_password, row["password_hash"]):
            return False, "Current password is incorrect"
        if len(new_password) < 6:
            return False, "New password must be at least 6 characters"
        self.db.update_user_password(user_id, hash_password(new_password))
        self.db.log_action(user_id, "CHANGE_PASSWORD")
        return True, "Password changed successfully"

    def is_logged_in(self) -> bool:
        return self.current_user is not None

    def require_role(self, *roles: str) -> bool:
        """Return True if current user has one of the required *roles*."""
        return self.current_user is not None and self.current_user.role in roles
