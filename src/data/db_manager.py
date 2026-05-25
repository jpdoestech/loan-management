"""Database access layer.

Supports two modes:
  1. **Local / Network-share** – connects directly to an SQLite file.
  2. **Server (REST)** – sends HTTP requests to a Flask REST server; the
     server owns the SQLite file and enforces role-based access.

The public ``DBManager`` singleton is configured once at startup via
:func:`configure` and then used throughout the application.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests  # type: ignore

from src.utils.logger import get_logger

log = get_logger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data_files" / "cash_advance.db"
_DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_local = threading.local()


# ─── Configuration dataclass ─────────────────────────────────────────────────

class DBConfig:
    """Holds runtime connection settings."""

    def __init__(
        self,
        mode: str = "local",       # "local" | "server"
        db_path: str = "",
        server_url: str = "",
        auth_token: str = "",
    ) -> None:
        self.mode = mode
        self.db_path = db_path or str(_DEFAULT_DB_PATH)
        self.server_url = server_url.rstrip("/")
        self.auth_token = auth_token


_config = DBConfig()


def configure(cfg: DBConfig) -> None:
    """Set the global DB configuration.

    Args:
        cfg: :class:`DBConfig` instance.
    """
    global _config
    _config = cfg
    log.info("DBManager configured: mode=%s", cfg.mode)
    if cfg.mode == "local":
        _run_migrations(cfg.db_path)


# ─── Local SQLite helpers ─────────────────────────────────────────────────────

def _get_connection(db_path: str) -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating it if needed."""
    conn: Optional[sqlite3.Connection] = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        _local.conn = conn
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a connection and commits / rolls back.

    Yields:
        Active :class:`sqlite3.Connection`.
    """
    conn = _get_connection(_config.db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _run_migrations(db_path: str) -> None:
    """Apply pending SQL migration files in version order.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = _get_connection(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
    )
    conn.commit()

    applied: set[str] = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations;")
    }

    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        version = sql_file.stem[:3]
        if version in applied:
            continue
        log.info("Applying migration %s …", sql_file.name)
        sql = sql_file.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
            conn.commit()
            log.info("Migration %s applied.", version)
        except Exception as exc:
            log.error("Migration %s failed: %s", version, exc)
            raise


# ─── Generic DAO helpers ─────────────────────────────────────────────────────

def fetchall(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a SELECT and return all rows as plain dicts.

    Args:
        sql:    SQL query string.
        params: Positional query parameters.

    Returns:
        List of row dicts.
    """
    if _config.mode == "server":
        return _rest_get("/query", {"sql": sql, "params": list(params)})
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def fetchone(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    """Execute a SELECT and return a single row dict or ``None``.

    Args:
        sql:    SQL query string.
        params: Positional query parameters.

    Returns:
        Single row dict or ``None``.
    """
    rows = fetchall(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    """Execute a DML statement and return the last inserted/affected row id.

    Args:
        sql:    SQL statement.
        params: Positional parameters.

    Returns:
        ``lastrowid`` for INSERT, ``rowcount`` for UPDATE/DELETE.
    """
    if _config.mode == "server":
        result = _rest_post("/execute", {"sql": sql, "params": list(params)})
        return result.get("lastrowid", 0)
    with get_db() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid or cur.rowcount


def executemany(sql: str, param_list: List[tuple]) -> int:
    """Execute a DML statement for a list of parameter sets.

    Args:
        sql:        SQL statement.
        param_list: List of parameter tuples.

    Returns:
        Total rows affected.
    """
    if _config.mode == "server":
        result = _rest_post("/executemany", {"sql": sql, "params": param_list})
        return result.get("rowcount", 0)
    with get_db() as conn:
        cur = conn.executemany(sql, param_list)
        return cur.rowcount


# ─── REST client helpers ──────────────────────────────────────────────────────

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_config.auth_token}",
        "Content-Type": "application/json",
    }


def _rest_get(path: str, params: dict | None = None) -> Any:
    url = f"{_config.server_url}{path}"
    resp = requests.get(url, params=params, headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def _rest_post(path: str, body: dict) -> Any:
    url = f"{_config.server_url}{path}"
    resp = requests.post(url, json=body, headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


# ─── High-level DAO functions ─────────────────────────────────────────────────

# ── Employees ─────────────────────────────────────────────────────────────────

def get_all_employees(active_only: bool = True) -> List[Dict]:
    """Return all employees, optionally filtering inactive ones."""
    where = "WHERE e.is_active = 1" if active_only else ""
    return fetchall(
        f"""SELECT e.*, c.name AS client_name, b.name AS branch_name
            FROM employees e
            LEFT JOIN clients c ON e.client_id = c.id
            LEFT JOIN branches b ON e.branch_id = b.id
            {where}
            ORDER BY e.name""",
    )


def get_employee_by_id(emp_id: int) -> Optional[Dict]:
    return fetchone("SELECT * FROM employees WHERE id = ?", (emp_id,))


def get_employee_by_code(code: str) -> Optional[Dict]:
    return fetchone("SELECT * FROM employees WHERE employee_code = ?", (code,))


def create_employee(data: Dict) -> int:
    return execute(
        """INSERT INTO employees
               (employee_code, name, position, department, date_hired,
                monthly_salary, phone, email, client_id, branch_id, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("employee_code"), data["name"], data.get("position"),
            data.get("department"), data.get("date_hired"),
            data.get("monthly_salary"), data.get("phone"), data.get("email"),
            data.get("client_id"), data.get("branch_id"), data.get("is_active", 1),
        ),
    )


def update_employee(emp_id: int, data: Dict) -> int:
    return execute(
        """UPDATE employees SET employee_code=?, name=?, position=?,
               department=?, date_hired=?, monthly_salary=?, phone=?,
               email=?, client_id=?, branch_id=?, is_active=?
           WHERE id=?""",
        (
            data.get("employee_code"), data["name"], data.get("position"),
            data.get("department"), data.get("date_hired"),
            data.get("monthly_salary"), data.get("phone"), data.get("email"),
            data.get("client_id"), data.get("branch_id"), data.get("is_active", 1),
            emp_id,
        ),
    )


# ── Loans ─────────────────────────────────────────────────────────────────────

def get_all_loans(status: Optional[str] = None) -> List[Dict]:
    where = "WHERE l.status = ?" if status else ""
    params = (status,) if status else ()
    return fetchall(
        f"""SELECT l.*, e.name AS employee_name, e.employee_code,
                   b.name AS branch_name
            FROM loans l
            LEFT JOIN employees e ON l.employee_id = e.id
            LEFT JOIN branches b ON l.branch_id = b.id
            {where}
            ORDER BY l.created_at DESC""",
        params,
    )


def get_loan_by_id(loan_id: int) -> Optional[Dict]:
    return fetchone(
        """SELECT l.*, e.name AS employee_name FROM loans l
           LEFT JOIN employees e ON l.employee_id = e.id
           WHERE l.id = ?""",
        (loan_id,),
    )


def get_loan_by_reference(ref: str) -> Optional[Dict]:
    return fetchone("SELECT * FROM loans WHERE reference_number = ?", (ref,))


def create_loan(data: Dict) -> int:
    return execute(
        """INSERT INTO loans
               (reference_number, employee_id, branch_id, requested_amount,
                approved_amount, interest_rate, term_months, purpose, status,
                application_date, approval_date, first_payment_date,
                processed_by, approved_by, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("reference_number"), data["employee_id"],
            data.get("branch_id"), data["requested_amount"],
            data.get("approved_amount"), data.get("interest_rate", 0),
            data.get("term_months", 1), data.get("purpose"),
            data.get("status", "pending"), data.get("application_date"),
            data.get("approval_date"), data.get("first_payment_date"),
            data.get("processed_by"), data.get("approved_by"),
            data.get("notes"),
        ),
    )


def update_loan_status(loan_id: int, status: str, user_id: Optional[int] = None) -> int:
    return execute(
        "UPDATE loans SET status=?, approved_by=? WHERE id=?",
        (status, user_id, loan_id),
    )


# ── Repayments ────────────────────────────────────────────────────────────────

def get_repayments_for_loan(loan_id: int) -> List[Dict]:
    return fetchall(
        "SELECT * FROM repayments WHERE loan_id = ? ORDER BY payment_date",
        (loan_id,),
    )


def create_repayment(data: Dict) -> int:
    return execute(
        """INSERT INTO repayments
               (loan_id, payment_date, amount, payment_method, reference, notes, recorded_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data["loan_id"], data["payment_date"], data["amount"],
            data.get("payment_method", "cash"), data.get("reference"),
            data.get("notes"), data.get("recorded_by"),
        ),
    )


def get_total_paid(loan_id: int) -> float:
    row = fetchone(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM repayments WHERE loan_id = ?",
        (loan_id,),
    )
    return float(row["total"]) if row else 0.0


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> Optional[Dict]:
    return fetchone("SELECT * FROM users WHERE username = ?", (username,))


def get_user_by_id(user_id: int) -> Optional[Dict]:
    return fetchone("SELECT * FROM users WHERE id = ?", (user_id,))


def get_all_users() -> List[Dict]:
    return fetchall("SELECT * FROM users ORDER BY full_name")


def create_user(data: Dict) -> int:
    return execute(
        """INSERT INTO users
               (username, password_hash, full_name, email, role, branch_id, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data["username"], data["password_hash"], data["full_name"],
            data.get("email"), data.get("role", "viewer"),
            data.get("branch_id"), data.get("is_active", 1),
        ),
    )


def update_user(user_id: int, data: Dict) -> None:
    execute(
        """UPDATE users SET full_name=?, email=?, role=?, branch_id=?, is_active=?
           WHERE id=?""",
        (
            data["full_name"], data.get("email"), data.get("role", "viewer"),
            data.get("branch_id"), data.get("is_active", 1), user_id,
        ),
    )


def update_last_login(user_id: int) -> None:
    execute(
        "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
        (user_id,),
    )


# ── Branches ──────────────────────────────────────────────────────────────────

def get_all_branches(active_only: bool = True) -> List[Dict]:
    where = "WHERE is_active = 1" if active_only else ""
    return fetchall(f"SELECT * FROM branches {where} ORDER BY name")


def create_branch(data: Dict) -> int:
    return execute(
        "INSERT INTO branches (name, address, phone, is_active) VALUES (?, ?, ?, ?)",
        (data["name"], data.get("address"), data.get("phone"), data.get("is_active", 1)),
    )


def update_branch(branch_id: int, data: Dict) -> None:
    execute(
        "UPDATE branches SET name=?, address=?, phone=?, is_active=? WHERE id=?",
        (data["name"], data.get("address"), data.get("phone"), data.get("is_active", 1), branch_id),
    )


# ── Clients ───────────────────────────────────────────────────────────────────

def get_all_clients(active_only: bool = True) -> List[Dict]:
    where = "WHERE is_active = 1" if active_only else ""
    return fetchall(f"SELECT * FROM clients {where} ORDER BY name")


def create_client(data: Dict) -> int:
    return execute(
        """INSERT INTO clients
               (name, contact, phone, email, address, branch_id, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data["name"], data.get("contact"), data.get("phone"),
            data.get("email"), data.get("address"),
            data.get("branch_id"), data.get("is_active", 1),
        ),
    )


def update_client(client_id: int, data: Dict) -> None:
    execute(
        """UPDATE clients SET name=?, contact=?, phone=?, email=?,
               address=?, branch_id=?, is_active=? WHERE id=?""",
        (
            data["name"], data.get("contact"), data.get("phone"),
            data.get("email"), data.get("address"),
            data.get("branch_id"), data.get("is_active", 1), client_id,
        ),
    )


# ── Audit Logs ────────────────────────────────────────────────────────────────

def write_audit_log(
    action: str,
    user_id: Optional[int] = None,
    table_name: Optional[str] = None,
    record_id: Optional[int] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Insert an audit log row.

    Args:
        action:     Action code (e.g. ``"IMPORT"``, ``"LOGIN"``).
        user_id:    ID of the acting user.
        table_name: Affected table.
        record_id:  Affected record primary key.
        detail:     JSON or freeform detail string.
        ip_address: Client IP (optional).
    """
    try:
        execute(
            """INSERT INTO audit_logs
                   (user_id, action, table_name, record_id, detail, ip_address)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, action, table_name, record_id, detail, ip_address),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to write audit log: %s", exc)
