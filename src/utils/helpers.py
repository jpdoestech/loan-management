"""Miscellaneous helper utilities."""
from __future__ import annotations

import json
import os
import string
import random
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / "data_files"
IMPORT_LOGS_DIR = DATA_DIR / "import_logs"
IMPORT_LOGS_DIR.mkdir(parents=True, exist_ok=True)


def generate_reference_number(prefix: str = "CA") -> str:
    """Generate a unique reference number.

    Args:
        prefix: Two-letter prefix (e.g. ``"CA"`` for cash advance).

    Returns:
        A reference string like ``"CA20240501-A3X9"``.
    """
    date_part = datetime.now().strftime("%Y%m%d")
    rand_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}{date_part}-{rand_part}"


def timestamp_filename(base: str, ext: str = "csv") -> str:
    """Build a timestamped filename.

    Args:
        base: Base name without extension.
        ext:  File extension without dot.

    Returns:
        String like ``"import_report_20240501_143022.csv"``.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base}_{ts}.{ext}"


def to_json(obj: Any) -> str:
    """Serialise *obj* to a compact JSON string."""
    return json.dumps(obj, default=str)


def from_json(text: str) -> Any:
    """Deserialise a JSON string."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case.

    Args:
        name: CamelCase string.

    Returns:
        snake_case equivalent.
    """
    result = []
    for i, ch in enumerate(name):
        if ch.isupper() and i:
            result.append("_")
        result.append(ch.lower())
    return "".join(result)


def format_currency(amount: float, symbol: str = "₱") -> str:
    """Format a float as a currency string.

    Args:
        amount: Numeric amount.
        symbol: Currency symbol prefix.

    Returns:
        Formatted string like ``"₱1,234.56"``.
    """
    return f"{symbol}{amount:,.2f}"


def safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce *value* to float or return *default*."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Coerce *value* to int or return *default*."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
