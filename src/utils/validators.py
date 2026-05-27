"""Field validation helpers used by ImportService and GUI forms."""
from __future__ import annotations
import re
from datetime import datetime
from typing import Any, Optional, Tuple

DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
    "%Y/%m/%d", "%d.%m.%Y", "%m-%d-%Y",
]


def parse_date(value: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """Try to parse *value* as a date.

    Returns:
        (datetime, None) on success or (None, error_message) on failure.
    """
    if value is None or str(value).strip() == "":
        return None, "Date is empty"
    raw = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt), None
        except ValueError:
            continue
    return None, f"Cannot parse date '{raw}'. Expected formats: YYYY-MM-DD, DD/MM/YYYY, etc."


def parse_amount(value: Any) -> Tuple[Optional[float], Optional[str]]:
    """Parse *value* as a non-negative monetary amount."""
    if value is None or str(value).strip() == "":
        return None, "Amount is empty"
    raw = str(value).strip().replace(",", "")
    try:
        amount = float(raw)
        if amount < 0:
            return None, f"Amount must be non-negative, got {amount}"
        return amount, None
    except ValueError:
        return None, f"Cannot parse amount '{raw}'"


def parse_positive_int(value: Any, field: str = "value") -> Tuple[Optional[int], Optional[str]]:
    """Parse *value* as a positive integer."""
    if value is None or str(value).strip() == "":
        return None, f"{field} is empty"
    try:
        n = int(float(str(value).strip()))
        if n <= 0:
            return None, f"{field} must be a positive integer, got {n}"
        return n, None
    except ValueError:
        return None, f"Cannot parse {field} '{value}' as integer"


def parse_rate(value: Any) -> Tuple[Optional[float], Optional[str]]:
    """Parse *value* as an interest rate (0 – 100)."""
    if value is None or str(value).strip() == "":
        return 0.0, None  # default 0%
    raw = str(value).strip().rstrip("%")
    try:
        rate = float(raw)
        if not (0 <= rate <= 100):
            return None, f"Interest rate must be 0-100, got {rate}"
        return rate, None
    except ValueError:
        return None, f"Cannot parse rate '{value}'"


def is_valid_email(email: str) -> bool:
    """Return True if *email* looks valid."""
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(pattern, email.strip())) if email else True  # optional field


def validate_required(value: Any, field: str) -> Optional[str]:
    """Return an error string if *value* is blank, else None."""
    if value is None or str(value).strip() == "":
        return f"'{field}' is required"
    return None
