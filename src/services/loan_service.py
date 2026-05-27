"""Loan and repayment business-logic service."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from ..data.db_manager import DBManager
from ..models.loan import Loan
from ..models.repayment import Repayment
from ..utils.helpers import generate_reference
from ..utils.logger import get_logger

log = get_logger()


class LoanService:
    """Orchestrates cash advance lifecycle."""

    def __init__(self, db: DBManager) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Loans
    # ------------------------------------------------------------------ #

    def list_loans(self, status: Optional[str] = None,
                   employee_id: Optional[int] = None) -> List[Loan]:
        return [Loan.from_row(r) for r in self.db.list_loans(status, employee_id)]

    def get_loan(self, loan_id: int) -> Optional[Loan]:
        row = self.db.get_loan_by_id(loan_id)
        return Loan.from_row(row) if row else None

    def create_loan(self, employee_id: int, requested_amount: float,
                    interest_rate: float, term_months: int,
                    purpose: Optional[str], branch_id: Optional[int],
                    created_by: Optional[int]) -> Tuple[bool, str, Optional[int]]:
        """Create a new pending loan application."""
        if requested_amount <= 0:
            return False, "Amount must be positive", None
        if term_months < 1:
            return False, "Term must be at least 1 month", None

        ref = generate_reference("CA")
        app_date = date.today().isoformat()
        due_date = (date.today() + timedelta(days=30 * term_months)).isoformat()
        total = requested_amount * (1 + (interest_rate / 100) * term_months)

        loan_data = {
            "reference_number": ref,
            "employee_id": employee_id,
            "requested_amount": requested_amount,
            "approved_amount": None,
            "interest_rate": interest_rate,
            "term_months": term_months,
            "status": "pending",
            "purpose": purpose,
            "application_date": app_date,
            "due_date": due_date,
            "outstanding_balance": total,
            "branch_id": branch_id,
            "created_by": created_by,
        }
        loan_id = self.db.create_loan(loan_data)
        self.db.log_action(created_by, "CREATE_LOAN", "loans", loan_id,
                           f"Ref:{ref} Emp:{employee_id} Amt:{requested_amount}")
        log.info("Created loan %s (id=%d)", ref, loan_id)
        return True, f"Loan {ref} created", loan_id

    def approve_loan(self, loan_id: int, approved_amount: float,
                     actor_id: Optional[int]) -> Tuple[bool, str]:
        """Approve a pending loan."""
        loan = self.get_loan(loan_id)
        if not loan:
            return False, "Loan not found"
        if loan.status != "pending":
            return False, f"Cannot approve a loan with status '{loan.status}'"
        today = date.today().isoformat()
        self.db.update_loan_status(loan_id, "approved", approved_amount, today)
        # recalculate outstanding balance
        total = approved_amount * (1 + (loan.interest_rate / 100) * loan.term_months)
        self.db.update_outstanding_balance(loan_id, total)
        self.db.log_action(actor_id, "APPROVE_LOAN", "loans", loan_id,
                           f"Approved amount: {approved_amount}")
        return True, "Loan approved"

    def disburse_loan(self, loan_id: int, actor_id: Optional[int]) -> Tuple[bool, str]:
        """Mark an approved loan as active/disbursed."""
        loan = self.get_loan(loan_id)
        if not loan:
            return False, "Loan not found"
        if loan.status != "approved":
            return False, f"Loan must be approved before disbursement (status: {loan.status})"
        self.db.execute(
            "UPDATE loans SET status='active', disbursement_date=date('now'), "
            "updated_at=datetime('now') WHERE id=?",
            (loan_id,),
        )
        self.db.log_action(actor_id, "DISBURSE_LOAN", "loans", loan_id)
        return True, "Loan disbursed and marked active"

    def reject_loan(self, loan_id: int, actor_id: Optional[int]) -> Tuple[bool, str]:
        loan = self.get_loan(loan_id)
        if not loan:
            return False, "Loan not found"
        self.db.update_loan_status(loan_id, "rejected")
        self.db.log_action(actor_id, "REJECT_LOAN", "loans", loan_id)
        return True, "Loan rejected"

    # ------------------------------------------------------------------ #
    # Repayments
    # ------------------------------------------------------------------ #

    def list_repayments(self, loan_id: Optional[int] = None) -> List[Repayment]:
        return [Repayment.from_row(r) for r in self.db.list_repayments(loan_id)]

    def record_repayment(self, loan_id: int, amount: float, payment_date: str,
                         payment_method: str, reference: Optional[str],
                         notes: Optional[str], recorded_by: Optional[int]) -> Tuple[bool, str]:
        """Record a repayment and update outstanding balance."""
        loan = self.get_loan(loan_id)
        if not loan:
            return False, "Loan not found"
        if loan.status not in ("active", "approved"):
            return False, f"Cannot record payment for loan with status '{loan.status}'"
        if amount <= 0:
            return False, "Payment amount must be positive"

        rep_id = self.db.create_repayment(
            loan_id, amount, payment_date, payment_method, reference, notes, recorded_by
        )
        # Recalculate outstanding
        total_paid = self.db.sum_repayments(loan_id)
        total_payable = Loan.from_row(self.db.get_loan_by_id(loan_id)).total_payable()
        new_balance = max(0.0, total_payable - total_paid)
        self.db.update_outstanding_balance(loan_id, new_balance)

        # Auto-close if fully paid
        if new_balance == 0.0:
            self.db.update_loan_status(loan_id, "closed")
            self.db.log_action(recorded_by, "CLOSE_LOAN", "loans", loan_id, "Fully repaid")

        self.db.log_action(recorded_by, "RECORD_REPAYMENT", "repayments", rep_id,
                           f"LoanID:{loan_id} Amt:{amount} Date:{payment_date}")
        return True, f"Payment of {amount:,.2f} recorded"

    def get_loan_summary(self, loan_id: int) -> Optional[Dict]:
        """Return a dict with loan + repayment summary."""
        loan = self.get_loan(loan_id)
        if not loan:
            return None
        repayments = self.list_repayments(loan_id)
        total_paid = sum(r.amount for r in repayments)
        return {
            "loan": loan,
            "repayments": repayments,
            "total_paid": total_paid,
            "outstanding": loan.outstanding_balance or 0.0,
            "repayment_count": len(repayments),
        }
