"""Loan (Cash Advance) domain model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .base_model import BaseModel

LOAN_STATUSES = ("pending", "approved", "active", "closed", "rejected")


@dataclass
class Loan(BaseModel):
    """Represents a cash advance / loan record."""

    reference_number: str = ""
    employee_id: int = 0
    requested_amount: float = 0.0
    approved_amount: Optional[float] = None
    interest_rate: float = 0.0
    term_months: int = 1
    status: str = "pending"
    purpose: Optional[str] = None
    application_date: Optional[str] = None
    approval_date: Optional[str] = None
    disbursement_date: Optional[str] = None
    due_date: Optional[str] = None
    outstanding_balance: Optional[float] = None
    branch_id: Optional[int] = None
    created_by: Optional[int] = None
    # joined fields (not stored in loans table directly)
    employee_name: Optional[str] = None

    def monthly_payment(self) -> float:
        """Calculate flat monthly payment amount."""
        principal = self.approved_amount or self.requested_amount
        if self.interest_rate > 0:
            total = principal * (1 + (self.interest_rate / 100) * self.term_months)
        else:
            total = principal
        return round(total / self.term_months, 2) if self.term_months else total

    def total_payable(self) -> float:
        """Return total amount payable including interest."""
        principal = self.approved_amount or self.requested_amount
        return round(principal * (1 + (self.interest_rate / 100) * self.term_months), 2)

    @classmethod
    def from_row(cls, row: dict) -> "Loan":
        return cls(
            id=row.get("id"),
            reference_number=row.get("reference_number", ""),
            employee_id=row.get("employee_id", 0),
            requested_amount=row.get("requested_amount", 0.0),
            approved_amount=row.get("approved_amount"),
            interest_rate=row.get("interest_rate", 0.0),
            term_months=row.get("term_months", 1),
            status=row.get("status", "pending"),
            purpose=row.get("purpose"),
            application_date=row.get("application_date"),
            approval_date=row.get("approval_date"),
            disbursement_date=row.get("disbursement_date"),
            due_date=row.get("due_date"),
            outstanding_balance=row.get("outstanding_balance"),
            branch_id=row.get("branch_id"),
            created_by=row.get("created_by"),
            employee_name=row.get("employee_name"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
