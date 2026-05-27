"""User management service."""
from __future__ import annotations
from typing import List, Optional, Tuple
from ..data.db_manager import DBManager
from ..models.user import User, ROLES
from ..utils.crypto import hash_password
from ..utils.logger import get_logger

log = get_logger()


class UserService:
    """CRUD operations for user accounts."""

    def __init__(self, db: DBManager) -> None:
        self.db = db

    def list_users(self) -> List[User]:
        return [User.from_row(r) for r in self.db.list_users()]

    def get_user(self, user_id: int) -> Optional[User]:
        row = self.db.get_user_by_id(user_id)
        return User.from_row(row) if row else None

    def create_user(self, username: str, password: str, full_name: str,
                    role: str, branch_id: Optional[int],
                    actor_id: Optional[int]) -> Tuple[bool, str]:
        """Create a new user. Returns (success, message)."""
        if not username.strip():
            return False, "Username is required"
        if role not in ROLES:
            return False, f"Role must be one of {ROLES}"
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        existing = self.db.get_user_by_username(username)
        if existing:
            return False, f"Username '{username}' already exists"
        uid = self.db.create_user(username, hash_password(password), full_name, role, branch_id)
        self.db.log_action(actor_id, "CREATE_USER", "users", uid, f"Created user {username}")
        log.info("Created user '%s' (id=%d)", username, uid)
        return True, "User created successfully"

    def update_user(self, user_id: int, full_name: str, role: str,
                    branch_id: Optional[int], is_active: int,
                    actor_id: Optional[int]) -> Tuple[bool, str]:
        if role not in ROLES:
            return False, f"Invalid role '{role}'"
        self.db.update_user(user_id, full_name, role, branch_id, is_active)
        self.db.log_action(actor_id, "UPDATE_USER", "users", user_id)
        return True, "User updated"

    def reset_password(self, user_id: int, new_password: str,
                       actor_id: Optional[int]) -> Tuple[bool, str]:
        if len(new_password) < 6:
            return False, "Password must be at least 6 characters"
        self.db.update_user_password(user_id, hash_password(new_password))
        self.db.log_action(actor_id, "RESET_PASSWORD", "users", user_id)
        return True, "Password reset"
