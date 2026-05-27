"""User domain model."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .base_model import BaseModel

ROLES = ("admin", "manager", "staff")


@dataclass
class User(BaseModel):
    """Represents an application user account."""

    username: str = ""
    password_hash: str = ""
    full_name: str = ""
    role: str = "staff"
    branch_id: Optional[int] = None
    is_active: int = 1
    last_login: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_manager(self) -> bool:
        return self.role in ("admin", "manager")

    @classmethod
    def from_row(cls, row: dict) -> "User":
        return cls(
            id=row.get("id"),
            username=row.get("username", ""),
            password_hash=row.get("password_hash", ""),
            full_name=row.get("full_name", ""),
            role=row.get("role", "staff"),
            branch_id=row.get("branch_id"),
            is_active=row.get("is_active", 1),
            last_login=row.get("last_login"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
