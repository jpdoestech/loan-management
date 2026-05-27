"""Branch domain model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .base_model import BaseModel


@dataclass
class Branch(BaseModel):
    """Represents a company branch."""

    name: str = ""
    code: str = ""
    address: Optional[str] = None
    is_active: int = 1

    @classmethod
    def from_row(cls, row: dict) -> "Branch":
        return cls(
            id=row.get("id"),
            name=row.get("name", ""),
            code=row.get("code", ""),
            address=row.get("address"),
            is_active=row.get("is_active", 1),
            created_at=row.get("created_at"),
        )
