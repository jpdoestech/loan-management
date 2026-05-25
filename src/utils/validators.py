"""Field-level validation helpers used by ImportService and GUI forms."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

_DATE_FMTS = [
    "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
    "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y",
    "%B %d, %Y", "%b %d, %Y",
]


def parse_date(value: Any) -> Optional[date]:
    """Try to parse *value* as a date using common formats.

    Args:
        value: String (or already a ``date``/``datetime``) to parse.

    Returns:
        A :class:`datetime.date` if parsing succeeds, else ``None``.
    """
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    text = str(value).strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_decimal(value: Any) -> Optional[float]:
    """Parse a numeric/decimal value, stripping currency symbols.

    Args:
        value: Raw value from CSV/Excel cell.

    Returns:
        Float if parseable, else ``None``.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    cleaned = re.sub(r"[₱$,\s]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(value: Any) -> Optional[int]:
    """Parse an integer value.

    Args:
        value: Raw value.

    Returns:
        ``int`` if parseable, else ``None``.
    """
    v = parse_decimal(value)
    return int(v) if v is not None else None


def is_valid_email(email: str) -> bool:
    """Basic RFC-5322-ish email check."""
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(pattern, email or ""))


def validate_loan_row(row: dict) -> list[str]:
    """Return a list of error strings for an import loan row.

    Args:
        row: Normalised dict with potential loan fields.

    Returns:
        List of human-readable error messages; empty means valid.
    """
    errors: list[str] = []
    if not row.get("employee_name") and not row.get("employee_code"):
        errors.append("Missing employee name or employee_code.")
    amt = parse_decimal(row.get("requested_amount"))
    if amt is None:
        errors.append("requested_amount is missing or non-numeric.")
    elif amt <= 0:
        errors.append(f"requested_amount must be > 0 (got {amt}).")
    rate = row.get("interest_rate")
    if rate is not None and parse_decimal(rate) is None:
        errors.append(f"interest_rate is not numeric: {rate!r}.")
    term = row.get("term_months")
    if term is not None and parse_int(term) is None:
        errors.append(f"term_months is not an integer: {term!r}.")
    app_date = row.get("application_date")
    if app_date and parse_date(app_date) is None:
        errors.append(f"Cannot parse application_date: {app_date!r}.")
    return errors


def validate_repayment_row(row: dict) -> list[str]:
    """Return a list of error strings for an import repayment row.

    Args:
        row: Normalised dict with potential repayment fields.

    Returns:
        List of human-readable error messages; empty means valid.
    """
    errors: list[str] = []
    pdate = row.get("payment_date")
    if not pdate:
        errors.append("payment_date is required.")
    elif parse_date(pdate) is None:
        errors.append(f"Cannot parse payment_date: {pdate!r}.")
    amt = parse_decimal(row.get("amount"))
    if amt is None:
        errors.append("amount is missing or non-numeric.")
    elif amt <= 0:
        errors.append(f"amount must be > 0 (got {amt}).")
    if not row.get("loan_reference") and not row.get("loan_id"):
        errors.append("loan_reference or loan_id is required.")
    return errors
