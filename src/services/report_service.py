"""Report generation service: CSV and Excel export."""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.data import db_manager as db
from src.utils.helpers import DATA_DIR, timestamp_filename
from src.utils.logger import get_logger

log = get_logger(__name__)

REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _write_csv(filename: str, headers: List[str], rows: List[Dict]) -> str:
    path = REPORTS_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def _write_xlsx(filename: str, headers: List[str], rows: List[Dict], title: str = "") -> str:
    """Write an XLSX report with basic formatting."""
    try:
        import openpyxl  # type: ignore
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError as exc:
        raise ImportError("openpyxl is required for Excel export.") from exc

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title or "Report"

    # Header row
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, row in enumerate(rows, 2):
        for col_idx, header in enumerate(headers, 1):
            ws.cell(row=row_idx, column=col_idx, value=row.get(header, ""))

    # Auto-fit columns
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    path = REPORTS_DIR / filename
    wb.save(path)
    return str(path)


def export_loans(
    status: Optional[str] = None,
    format_: str = "csv",
    branch_id: Optional[int] = None,
) -> str:
    """Export the loan list to CSV or XLSX.

    Args:
        status:    Optional status filter.
        format_:   ``"csv"`` or ``"xlsx"``.
        branch_id: Optional branch filter.

    Returns:
        Absolute path to the written file.
    """
    loans = db.get_all_loans(status=status)
    if branch_id:
        loans = [l for l in loans if l.get("branch_id") == branch_id]

    headers = [
        "id", "reference_number", "employee_name", "employee_code",
        "requested_amount", "approved_amount", "interest_rate", "term_months",
        "status", "application_date", "approval_date", "branch_name",
    ]
    fname = timestamp_filename("loan_report", format_)
    if format_ == "xlsx":
        return _write_xlsx(fname, headers, loans, title="Loan Report")
    return _write_csv(fname, headers, loans)


def export_repayments(loan_id: Optional[int] = None, format_: str = "csv") -> str:
    """Export repayments to CSV or XLSX.

    Args:
        loan_id: Optional loan filter.
        format_: ``"csv"`` or ``"xlsx"``.

    Returns:
        Absolute path to the written file.
    """
    if loan_id:
        repayments = db.get_repayments_for_loan(loan_id)
    else:
        repayments = db.fetchall(
            "SELECT r.*, l.reference_number AS loan_ref, e.name AS employee_name "
            "FROM repayments r "
            "JOIN loans l ON r.loan_id = l.id "
            "JOIN employees e ON l.employee_id = e.id "
            "ORDER BY r.payment_date DESC"
        )
    headers = [
        "id", "loan_id", "loan_ref", "employee_name",
        "payment_date", "amount", "payment_method", "reference", "notes",
    ]
    fname = timestamp_filename("repayment_report", format_)
    if format_ == "xlsx":
        return _write_xlsx(fname, headers, repayments, title="Repayment Report")
    return _write_csv(fname, headers, repayments)


def loan_aging_report(as_of: Optional[date] = None) -> List[Dict]:
    """Return loans overdue as of *as_of* date.

    Args:
        as_of: Reference date (defaults to today).

    Returns:
        List of loan summary dicts with outstanding balance.
    """
    as_of = as_of or date.today()
    loans = db.get_all_loans(status="active")
    result = []
    for loan in loans:
        paid = db.get_total_paid(loan["id"])
        principal = float(loan.get("approved_amount") or loan["requested_amount"])
        rate = float(loan.get("interest_rate") or 0)
        term = int(loan.get("term_months") or 1)
        total_payable = principal * (1 + rate / 100 * term)
        balance = max(total_payable - paid, 0)
        if balance > 0:
            result.append({
                **loan,
                "total_payable": total_payable,
                "total_paid": paid,
                "balance": balance,
            })
    return result
