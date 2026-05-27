"""Client (company/employer) domain model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .base_model import BaseModel


@dataclass
class Client(BaseModel):
    """Represents a client company whose employees take cash advances."""

    name: str = ""
    code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    branch_id: Optional[int] = None
    is_active: int = 1

    @classmethod
    def from_row(cls, row: dict) -> "Client":
        return cls(
            id=row.get("id"),
            name=row.get("name", ""),
            code=row.get("code"),
            email=row.get("email"),
            phone=row.get("phone"),
            address=row.get("address"),
            branch_id=row.get("branch_id"),
            is_active=row.get("is_active", 1),
            created_at=row.get("created_at"),
        )
