"""Employee domain model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .base_model import BaseModel


@dataclass
class Employee(BaseModel):
    """Represents an employee who can apply for cash advances."""

    name: str = ""
    employee_code: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    branch_id: Optional[int] = None
    client_id: Optional[int] = None
    is_active: int = 1

    @property
    def display_name(self) -> str:
        code = f" ({self.employee_code})" if self.employee_code else ""
        return f"{self.name}{code}"

    @classmethod
    def from_row(cls, row: dict) -> "Employee":
        return cls(
            id=row.get("id"),
            name=row.get("name", ""),
            employee_code=row.get("employee_code"),
            department=row.get("department"),
            position=row.get("position"),
            email=row.get("email"),
            phone=row.get("phone"),
            branch_id=row.get("branch_id"),
            client_id=row.get("client_id"),
            is_active=row.get("is_active", 1),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
