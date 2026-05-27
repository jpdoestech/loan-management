"""Repayment domain model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .base_model import BaseModel

PAYMENT_METHODS = ("cash", "bank_transfer", "check", "salary_deduction", "other")


@dataclass
class Repayment(BaseModel):
    """Represents a single loan repayment / payment record."""

    loan_id: int = 0
    amount: float = 0.0
    payment_date: str = ""
    payment_method: str = "cash"
    reference: Optional[str] = None
    notes: Optional[str] = None
    recorded_by: Optional[int] = None
    # joined
    loan_reference: Optional[str] = None
    employee_name: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Repayment":
        return cls(
            id=row.get("id"),
            loan_id=row.get("loan_id", 0),
            amount=row.get("amount", 0.0),
            payment_date=row.get("payment_date", ""),
            payment_method=row.get("payment_method", "cash"),
            reference=row.get("reference"),
            notes=row.get("notes"),
            recorded_by=row.get("recorded_by"),
            loan_reference=row.get("loan_reference"),
            employee_name=row.get("employee_name"),
            created_at=row.get("created_at"),
        )
