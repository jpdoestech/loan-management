"""Authentication and authorisation service."""
from __future__ import annotations

from typing import Optional

from src.data import db_manager as db
from src.models.user import User
from src.utils.crypto import hash_password, verify_password
from src.utils.logger import get_logger

log = get_logger(__name__)

# Roles ordered by privilege level (higher index = more privilege)
ROLE_ORDER = ["viewer", "cashier", "manager", "admin"]

_current_user: Optional[User] = None


def get_current_user() -> Optional[User]:
    """Return the currently logged-in user, or ``None``."""
    return _current_user


def login(username: str, password: str) -> Optional[User]:
    """Authenticate a user by username and password.

    Args:
        username: Plaintext username.
        password: Plaintext password.

    Returns:
        :class:`User` on success, ``None`` on failure.
    """
    global _current_user
    row = db.get_user_by_username(username)
    if not row:
        log.warning("Login attempt for unknown user: %s", username)
        return None
    if not row.get("is_active"):
        log.warning("Login attempt for disabled user: %s", username)
        return None
    if not verify_password(password, row["password_hash"]):
        log.warning("Bad password for user: %s", username)
        db.write_audit_log("LOGIN_FAIL", user_id=row["id"], detail=f"user={username}")
        return None

    _current_user = User.from_dict(dict(row))
    db.update_last_login(row["id"])
    db.write_audit_log("LOGIN", user_id=row["id"], detail=f"user={username}")
    log.info("User %s logged in (role=%s).", username, _current_user.role)
    return _current_user


def logout() -> None:
    """Clear the current session."""
    global _current_user
    if _current_user:
        db.write_audit_log("LOGOUT", user_id=_current_user.id)
        log.info("User %s logged out.", _current_user.username)
    _current_user = None


def has_role(required: str) -> bool:
    """Return ``True`` if the current user has at least *required* privilege.

    Args:
        required: Minimum role name (e.g. ``"manager"``).

    Returns:
        ``True`` if allowed, ``False`` otherwise.
    """
    user = get_current_user()
    if not user:
        return False
    try:
        return ROLE_ORDER.index(user.role) >= ROLE_ORDER.index(required)
    except ValueError:
        return False


def require_role(required: str) -> None:
    """Raise :class:`PermissionError` if current user lacks *required* role.

    Args:
        required: Minimum role name.

    Raises:
        PermissionError: If access is denied.
    """
    if not has_role(required):
        user = get_current_user()
        role = user.role if user else "anonymous"
        raise PermissionError(
            f"Action requires role '{required}'; current role is '{role}'."
        )


def create_user(
    username: str,
    password: str,
    full_name: str,
    role: str = "viewer",
    email: Optional[str] = None,
    branch_id: Optional[int] = None,
) -> int:
    """Create a new user account.

    Args:
        username:  Unique login name.
        password:  Plaintext password (will be hashed).
        full_name: Display name.
        role:      Role string.
        email:     Optional email.
        branch_id: Optional branch assignment.

    Returns:
        New user primary key.
    """
    require_role("admin")
    pw_hash = hash_password(password)
    user_id = db.create_user({
        "username": username,
        "password_hash": pw_hash,
        "full_name": full_name,
        "email": email,
        "role": role,
        "branch_id": branch_id,
    })
    actor = get_current_user()
    db.write_audit_log(
        "CREATE", user_id=actor.id if actor else None,
        table_name="users", record_id=user_id,
        detail=f"username={username}, role={role}",
    )
    return user_id


def change_password(user_id: int, new_password: str) -> None:
    """Update the password for a user.

    Args:
        user_id:      Target user's primary key.
        new_password: New plaintext password.
    """
    actor = get_current_user()
    if actor and actor.id != user_id:
        require_role("admin")
    pw_hash = hash_password(new_password)
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, user_id))


def ensure_default_admin() -> None:
    """Create the default *admin* / *admin* account if no users exist.

    This is called on first run to bootstrap the application.
    """
    users = db.get_all_users()
    if not users:
        pw = hash_password("admin")
        db.create_user({
            "username": "admin",
            "password_hash": pw,
            "full_name": "System Administrator",
            "role": "admin",
            "is_active": 1,
        })
        log.info("Default admin account created (username=admin, password=admin).")
