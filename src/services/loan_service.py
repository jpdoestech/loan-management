"""Loan and repayment business logic."""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from src.data import db_manager as db
from src.services import auth_service
from src.utils.helpers import generate_reference_number
from src.utils.logger import get_logger

log = get_logger(__name__)


def apply_loan(
    employee_id: int,
    requested_amount: float,
    term_months: int,
    interest_rate: float = 0.0,
    purpose: Optional[str] = None,
    branch_id: Optional[int] = None,
    notes: Optional[str] = None,
    application_date: Optional[str] = None,
) -> int:
    """Submit a cash-advance application.

    Args:
        employee_id:      Employee PK.
        requested_amount: Amount requested.
        term_months:      Repayment period in months.
        interest_rate:    Monthly interest percentage.
        purpose:          Reason for the advance.
        branch_id:        Branch PK.
        notes:            Free-form notes.
        application_date: ISO date string; defaults to today.

    Returns:
        New loan PK.
    """
    actor = auth_service.get_current_user()
    ref = generate_reference_number("CA")
    app_date = application_date or date.today().isoformat()
    data = {
        "reference_number": ref,
        "employee_id": employee_id,
        "branch_id": branch_id,
        "requested_amount": requested_amount,
        "interest_rate": interest_rate,
        "term_months": term_months,
        "purpose": purpose,
        "status": "pending",
        "application_date": app_date,
        "processed_by": actor.id if actor else None,
        "notes": notes,
    }
    loan_id = db.create_loan(data)
    db.write_audit_log(
        "CREATE", user_id=actor.id if actor else None,
        table_name="loans", record_id=loan_id,
        detail=f"ref={ref}, amount={requested_amount}, employee_id={employee_id}",
    )
    log.info("Loan %s created (id=%d, employee_id=%d).", ref, loan_id, employee_id)
    return loan_id


def approve_loan(
    loan_id: int,
    approved_amount: float,
    approval_date: Optional[str] = None,
    first_payment_date: Optional[str] = None,
) -> None:
    """Approve a pending loan application.

    Args:
        loan_id:           Loan PK.
        approved_amount:   Actual disbursed amount.
        approval_date:     ISO date; defaults to today.
        first_payment_date: ISO date of first repayment.
    """
    auth_service.require_role("manager")
    actor = auth_service.get_current_user()
    app_date = approval_date or date.today().isoformat()
    db.execute(
        """UPDATE loans SET status='active', approved_amount=?,
               approval_date=?, first_payment_date=?, approved_by=?
           WHERE id=?""",
        (approved_amount, app_date, first_payment_date, actor.id if actor else None, loan_id),
    )
    db.write_audit_log(
        "UPDATE", user_id=actor.id if actor else None,
        table_name="loans", record_id=loan_id,
        detail=f"approved_amount={approved_amount}, status=active",
    )


def reject_loan(loan_id: int, reason: Optional[str] = None) -> None:
    """Reject a pending loan.

    Args:
        loan_id: Loan PK.
        reason:  Optional rejection reason stored in notes.
    """
    auth_service.require_role("manager")
    actor = auth_service.get_current_user()
    db.execute(
        "UPDATE loans SET status='rejected', notes=? WHERE id=?",
        (reason, loan_id),
    )
    db.write_audit_log(
        "UPDATE", user_id=actor.id if actor else None,
        table_name="loans", record_id=loan_id,
        detail=f"status=rejected, reason={reason}",
    )


def record_repayment(
    loan_id: int,
    amount: float,
    payment_date: str,
    payment_method: str = "cash",
    reference: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    """Record a loan repayment and update loan status if fully paid.

    Args:
        loan_id:        Loan PK.
        amount:         Payment amount.
        payment_date:   ISO date of payment.
        payment_method: ``"cash"``, ``"bank"``, or ``"deduction"``.
        reference:      External reference / receipt number.
        notes:          Optional notes.

    Returns:
        New repayment PK.
    """
    actor = auth_service.get_current_user()
    repay_id = db.create_repayment({
        "loan_id": loan_id,
        "payment_date": payment_date,
        "amount": amount,
        "payment_method": payment_method,
        "reference": reference,
        "notes": notes,
        "recorded_by": actor.id if actor else None,
    })
    _check_loan_completion(loan_id)
    db.write_audit_log(
        "CREATE", user_id=actor.id if actor else None,
        table_name="repayments", record_id=repay_id,
        detail=f"loan_id={loan_id}, amount={amount}",
    )
    return repay_id


def _check_loan_completion(loan_id: int) -> None:
    """Mark loan as *completed* if total payments cover the payable amount."""
    loan = db.get_loan_by_id(loan_id)
    if not loan or loan["status"] not in ("active", "pending"):
        return
    principal = float(loan.get("approved_amount") or loan["requested_amount"])
    rate = float(loan.get("interest_rate") or 0)
    term = int(loan.get("term_months") or 1)
    total_payable = principal * (1 + rate / 100 * term)
    total_paid = db.get_total_paid(loan_id)
    if total_paid >= total_payable:
        db.execute("UPDATE loans SET status='completed' WHERE id=?", (loan_id,))
        log.info("Loan id=%d marked completed (paid=%.2f).", loan_id, total_paid)


def get_loan_summary(loan_id: int) -> Dict:
    """Return a summary dict for a loan including balance and payment status.

    Args:
        loan_id: Loan PK.

    Returns:
        Dict with keys: loan, repayments, total_paid, balance, status.
    """
    loan = db.get_loan_by_id(loan_id)
    if not loan:
        return {}
    principal = float(loan.get("approved_amount") or loan["requested_amount"])
    rate = float(loan.get("interest_rate") or 0)
    term = int(loan.get("term_months") or 1)
    total_payable = principal * (1 + rate / 100 * term)
    total_paid = db.get_total_paid(loan_id)
    repayments = db.get_repayments_for_loan(loan_id)
    return {
        "loan": dict(loan),
        "repayments": repayments,
        "total_payable": total_payable,
        "total_paid": total_paid,
        "balance": max(total_payable - total_paid, 0),
        "status": loan["status"],
    }
