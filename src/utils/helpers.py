"""Miscellaneous helper functions."""
from __future__ import annotations
import os
import json
import uuid
from datetime import date, datetime
from typing import Any, Dict, Optional


def generate_reference(prefix: str = "CA") -> str:
    """Generate a unique reference number like CA-20250525-A1B2."""
    today = date.today().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"{prefix}-{today}-{suffix}"


def format_currency(amount: Optional[float], symbol: str = "₱") -> str:
    """Format *amount* as a currency string."""
    if amount is None:
        return f"{symbol}0.00"
    return f"{symbol}{amount:,.2f}"


def format_date(value: Any, fmt: str = "%Y-%m-%d") -> str:
    """Return *value* formatted as a date string, or '' if None."""
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime(fmt)
    return str(value)


def load_json(path: str) -> Any:
    """Load and return JSON from *path*."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: str) -> None:
    """Save *data* as pretty-printed JSON to *path*."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def ensure_dir(path: str) -> None:
    """Create *path* (and parents) if it does not exist."""
    os.makedirs(path, exist_ok=True)


def chunk_list(lst: list, size: int) -> list:
    """Split *lst* into chunks of *size*."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def get_app_data_dir() -> str:
    """Return a writable directory for application data."""
    base = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.normpath(os.path.join(base, "..", "..", "data_files"))
    ensure_dir(data_dir)
    return data_dir
