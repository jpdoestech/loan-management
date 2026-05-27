"""Audit log domain model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .base_model import BaseModel


@dataclass
class AuditLog(BaseModel):
    """Represents an immutable audit log entry."""

    user_id: Optional[int] = None
    action: str = ""
    table_name: Optional[str] = None
    record_id: Optional[int] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    # joined
    username: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "AuditLog":
        return cls(
            id=row.get("id"),
            user_id=row.get("user_id"),
            action=row.get("action", ""),
            table_name=row.get("table_name"),
            record_id=row.get("record_id"),
            details=row.get("details"),
            ip_address=row.get("ip_address"),
            username=row.get("username"),
            created_at=row.get("created_at"),
        )
