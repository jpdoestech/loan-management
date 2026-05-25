"""User domain model."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from src.models.base_model import BaseModel


@dataclass
class User(BaseModel):
    """Represents an application user / operator."""

    id: Optional[int] = None
    username: str = ""
    password_hash: str = ""
    full_name: str = ""
    email: Optional[str] = None
    role: str = "viewer"          # admin|manager|cashier|viewer
    branch_id: Optional[int] = None
    is_active: int = 1
    last_login: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
