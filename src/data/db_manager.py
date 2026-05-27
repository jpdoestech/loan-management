"""Database manager — local SQLite mode and REST (Flask) client mode.

Usage (local):
    db = DBManager()
    db.initialize()
    users = db.fetch_all("SELECT * FROM users")

Usage (REST):
    db = DBManager(mode="rest", server_url="http://192.168.1.10:5000", token="secret")
    db.initialize()
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

log = get_logger()

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data_files" / "ecam.db"
_CONFIG_PATH = Path(__file__).parent.parent.parent / "data_files" / "config.json"


class DBManager:
    """Unified data access layer.

    Supports two modes controlled by ``config.json``:
    - ``"local"``  — direct SQLite connection (WAL mode, supports SMB share path).
    - ``"rest"``   — HTTP client that calls the Flask REST server.
    """

    def __init__(
        self,
        mode: str = "local",
        db_path: Optional[str] = None,
        server_url: Optional[str] = None,
        token: Optional[str] = None,
    ) -> None:
        self.mode = mode
        self.db_path = db_path or str(_DEFAULT_DB_PATH)
        self.server_url = server_url
        self.token = token
        self._conn: Optional[sqlite3.Connection] = None

        # Load saved config if available
        self._load_config()

    # ------------------------------------------------------------------ #
    # Config persistence
    # ------------------------------------------------------------------ #

    def _load_config(self) -> None:
        """Overlay saved config.json over constructor defaults."""
        if _CONFIG_PATH.exists():
            try:
                cfg = json.loads(_CONFIG_PATH.read_text())
                self.mode = cfg.get("mode", self.mode)
                self.db_path = cfg.get("db_path", self.db_path)
                self.server_url = cfg.get("server_url", self.server_url)
                self.token = cfg.get("token", self.token)
            except (json.JSONDecodeError, OSError):
                pass

    def save_config(self) -> None:
        """Persist current connection settings to config.json."""
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cfg = {
            "mode": self.mode,
            "db_path": self.db_path,
            "server_url": self.server_url,
            "token": self.token,
        }
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))

    # ------------------------------------------------------------------ #
    # Initialisation
    # ------------------------------------------------------------------ #

    def initialize(self) -> None:
        """Set up the DB (run migrations) or verify REST connectivity."""
        if self.mode == "local":
            self._local_initialize()
        else:
            self._rest_ping()

    def _local_initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._run_migrations(conn)
        log.info("Local DB initialized: %s", self.db_path)

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS migrations "
            "(id INTEGER PRIMARY KEY, version TEXT NOT NULL UNIQUE, "
            "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        applied = {r[0] for r in conn.execute("SELECT version FROM migrations")}
        for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            version = sql_file.stem
            if version not in applied:
                log.info("Applying migration %s", version)
                conn.executescript(sql_file.read_text())
                conn.execute("INSERT INTO migrations (version) VALUES (?)", (version,))
                conn.commit()

    # ------------------------------------------------------------------ #
    # Connection helpers (local mode)
    # ------------------------------------------------------------------ #

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30,
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------ #
    # Query helpers (local mode)
    # ------------------------------------------------------------------ #

    def fetch_all(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute *sql* and return all rows as dicts."""
        if self.mode == "rest":
            return self._rest_query(sql, params)
        cur = self._get_conn().execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute *sql* and return the first row as a dict, or None."""
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Execute a DML statement; return last inserted row id."""
        if self.mode == "rest":
            return self._rest_execute(sql, params)
        conn = self._get_conn()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid or 0

    def executemany(self, sql: str, param_list: List[tuple]) -> None:
        """Execute *sql* for each tuple in *param_list* in one transaction."""
        conn = self._get_conn()
        conn.executemany(sql, param_list)
        conn.commit()

    def execute_transaction(self, statements: List[tuple]) -> None:
        """Execute a list of (sql, params) tuples atomically."""
        conn = self._get_conn()
        try:
            for sql, params in statements:
                conn.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ------------------------------------------------------------------ #
    # REST client helpers
    # ------------------------------------------------------------------ #

    def _rest_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _rest_ping(self) -> None:
        try:
            import requests
            r = requests.get(f"{self.server_url}/ping", headers=self._rest_headers(), timeout=5)
            r.raise_for_status()
            log.info("REST server reachable: %s", self.server_url)
        except Exception as exc:
            log.warning("REST server unreachable: %s", exc)

    def _rest_query(self, sql: str, params: tuple) -> List[Dict[str, Any]]:
        import requests
        payload = {"sql": sql, "params": list(params)}
        r = requests.post(
            f"{self.server_url}/query",
            json=payload,
            headers=self._rest_headers(),
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("rows", [])

    def _rest_execute(self, sql: str, params: tuple) -> int:
        import requests
        payload = {"sql": sql, "params": list(params)}
        r = requests.post(
            f"{self.server_url}/execute",
            json=payload,
            headers=self._rest_headers(),
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("lastrowid", 0)

    # ------------------------------------------------------------------ #
    # Convenience DAO helpers
    # ------------------------------------------------------------------ #

    # -- Users --
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        return self.fetch_one("SELECT * FROM users WHERE username=?", (username,))

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        return self.fetch_one("SELECT * FROM users WHERE id=?", (user_id,))

    def list_users(self) -> List[Dict]:
        return self.fetch_all(
            "SELECT u.*, b.name AS branch_name FROM users u "
            "LEFT JOIN branches b ON u.branch_id=b.id ORDER BY u.username"
        )

    def create_user(self, username: str, password_hash: str, full_name: str,
                    role: str, branch_id: Optional[int]) -> int:
        return self.execute(
            "INSERT INTO users (username, password_hash, full_name, role, branch_id) "
            "VALUES (?,?,?,?,?)",
            (username, password_hash, full_name, role, branch_id),
        )

    def update_user(self, user_id: int, full_name: str, role: str,
                    branch_id: Optional[int], is_active: int) -> None:
        self.execute(
            "UPDATE users SET full_name=?, role=?, branch_id=?, is_active=?, "
            "updated_at=datetime('now') WHERE id=?",
            (full_name, role, branch_id, is_active, user_id),
        )

    def update_user_password(self, user_id: int, password_hash: str) -> None:
        self.execute(
            "UPDATE users SET password_hash=?, updated_at=datetime('now') WHERE id=?",
            (password_hash, user_id),
        )

    def update_last_login(self, user_id: int) -> None:
        self.execute(
            "UPDATE users SET last_login=datetime('now') WHERE id=?", (user_id,)
        )

    # -- Branches --
    def list_branches(self) -> List[Dict]:
        return self.fetch_all("SELECT * FROM branches ORDER BY name")

    def create_branch(self, name: str, code: str, address: Optional[str]) -> int:
        return self.execute(
            "INSERT INTO branches (name, code, address) VALUES (?,?,?)",
            (name, code, address),
        )

    def update_branch(self, bid: int, name: str, code: str,
                      address: Optional[str], is_active: int) -> None:
        self.execute(
            "UPDATE branches SET name=?, code=?, address=?, is_active=? WHERE id=?",
            (name, code, address, is_active, bid),
        )

    # -- Clients --
    def list_clients(self) -> List[Dict]:
        return self.fetch_all(
            "SELECT c.*, b.name AS branch_name FROM clients c "
            "LEFT JOIN branches b ON c.branch_id=b.id ORDER BY c.name"
        )

    def create_client(self, name: str, code: Optional[str], email: Optional[str],
                      phone: Optional[str], address: Optional[str],
                      branch_id: Optional[int]) -> int:
        return self.execute(
            "INSERT INTO clients (name, code, email, phone, address, branch_id) "
            "VALUES (?,?,?,?,?,?)",
            (name, code, email, phone, address, branch_id),
        )

    def update_client(self, cid: int, name: str, code: Optional[str], email: Optional[str],
                      phone: Optional[str], address: Optional[str],
                      branch_id: Optional[int], is_active: int) -> None:
        self.execute(
            "UPDATE clients SET name=?, code=?, email=?, phone=?, address=?, "
            "branch_id=?, is_active=? WHERE id=?",
            (name, code, email, phone, address, branch_id, is_active, cid),
        )

    # -- Employees --
    def list_employees(self, active_only: bool = True) -> List[Dict]:
        where = "WHERE e.is_active=1" if active_only else ""
        return self.fetch_all(
            f"SELECT e.*, b.name AS branch_name, c.name AS client_name "
            f"FROM employees e "
            f"LEFT JOIN branches b ON e.branch_id=b.id "
            f"LEFT JOIN clients c ON e.client_id=c.id {where} ORDER BY e.name"
        )

    def get_employee_by_id(self, eid: int) -> Optional[Dict]:
        return self.fetch_one(
            "SELECT e.*, b.name AS branch_name FROM employees e "
            "LEFT JOIN branches b ON e.branch_id=b.id WHERE e.id=?", (eid,)
        )

    def create_employee(self, name: str, employee_code: Optional[str], department: Optional[str],
                        position: Optional[str], email: Optional[str], phone: Optional[str],
                        branch_id: Optional[int], client_id: Optional[int]) -> int:
        return self.execute(
            "INSERT INTO employees (name, employee_code, department, position, "
            "email, phone, branch_id, client_id) VALUES (?,?,?,?,?,?,?,?)",
            (name, employee_code, department, position, email, phone, branch_id, client_id),
        )

    def update_employee(self, eid: int, name: str, employee_code: Optional[str],
                        department: Optional[str], position: Optional[str],
                        email: Optional[str], phone: Optional[str],
                        branch_id: Optional[int], client_id: Optional[int],
                        is_active: int) -> None:
        self.execute(
            "UPDATE employees SET name=?, employee_code=?, department=?, position=?, "
            "email=?, phone=?, branch_id=?, client_id=?, is_active=?, "
            "updated_at=datetime('now') WHERE id=?",
            (name, employee_code, department, position, email, phone,
             branch_id, client_id, is_active, eid),
        )

    # -- Loans --
    def list_loans(self, status: Optional[str] = None,
                   employee_id: Optional[int] = None) -> List[Dict]:
        conditions = []
        params: list = []
        if status:
            conditions.append("l.status=?")
            params.append(status)
        if employee_id:
            conditions.append("l.employee_id=?")
            params.append(employee_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return self.fetch_all(
            f"SELECT l.*, e.name AS employee_name, e.employee_code, "
            f"b.name AS branch_name FROM loans l "
            f"LEFT JOIN employees e ON l.employee_id=e.id "
            f"LEFT JOIN branches b ON l.branch_id=b.id "
            f"{where} ORDER BY l.created_at DESC",
            tuple(params),
        )

    def get_loan_by_id(self, loan_id: int) -> Optional[Dict]:
        return self.fetch_one(
            "SELECT l.*, e.name AS employee_name FROM loans l "
            "LEFT JOIN employees e ON l.employee_id=e.id WHERE l.id=?",
            (loan_id,),
        )

    def get_loan_by_reference(self, ref: str) -> Optional[Dict]:
        return self.fetch_one(
            "SELECT * FROM loans WHERE reference_number=?", (ref,)
        )

    def create_loan(self, loan_data: Dict) -> int:
        return self.execute(
            "INSERT INTO loans (reference_number, employee_id, requested_amount, "
            "approved_amount, interest_rate, term_months, status, purpose, "
            "application_date, due_date, outstanding_balance, branch_id, created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                loan_data["reference_number"], loan_data["employee_id"],
                loan_data["requested_amount"], loan_data.get("approved_amount"),
                loan_data.get("interest_rate", 0.0), loan_data.get("term_months", 1),
                loan_data.get("status", "pending"), loan_data.get("purpose"),
                loan_data.get("application_date"), loan_data.get("due_date"),
                loan_data.get("outstanding_balance"), loan_data.get("branch_id"),
                loan_data.get("created_by"),
            ),
        )

    def update_loan_status(self, loan_id: int, status: str,
                           approved_amount: Optional[float] = None,
                           approval_date: Optional[str] = None) -> None:
        self.execute(
            "UPDATE loans SET status=?, approved_amount=COALESCE(?,approved_amount), "
            "approval_date=COALESCE(?,approval_date), updated_at=datetime('now') WHERE id=?",
            (status, approved_amount, approval_date, loan_id),
        )

    def update_outstanding_balance(self, loan_id: int, balance: float) -> None:
        self.execute(
            "UPDATE loans SET outstanding_balance=?, updated_at=datetime('now') WHERE id=?",
            (balance, loan_id),
        )

    # -- Repayments --
    def list_repayments(self, loan_id: Optional[int] = None) -> List[Dict]:
        where = "WHERE r.loan_id=?" if loan_id else ""
        params = (loan_id,) if loan_id else ()
        return self.fetch_all(
            f"SELECT r.*, l.reference_number AS loan_reference, e.name AS employee_name "
            f"FROM repayments r "
            f"LEFT JOIN loans l ON r.loan_id=l.id "
            f"LEFT JOIN employees e ON l.employee_id=e.id "
            f"{where} ORDER BY r.payment_date DESC",
            params,
        )

    def create_repayment(self, loan_id: int, amount: float, payment_date: str,
                         payment_method: str, reference: Optional[str],
                         notes: Optional[str], recorded_by: Optional[int]) -> int:
        return self.execute(
            "INSERT INTO repayments (loan_id, amount, payment_date, payment_method, "
            "reference, notes, recorded_by) VALUES (?,?,?,?,?,?,?)",
            (loan_id, amount, payment_date, payment_method, reference, notes, recorded_by),
        )

    def sum_repayments(self, loan_id: int) -> float:
        row = self.fetch_one(
            "SELECT COALESCE(SUM(amount),0) AS total FROM repayments WHERE loan_id=?",
            (loan_id,),
        )
        return float(row["total"]) if row else 0.0

    # -- Audit logs --
    def log_action(self, user_id: Optional[int], action: str,
                   table_name: Optional[str] = None, record_id: Optional[int] = None,
                   details: Optional[str] = None) -> None:
        self.execute(
            "INSERT INTO audit_logs (user_id, action, table_name, record_id, details) "
            "VALUES (?,?,?,?,?)",
            (user_id, action, table_name, record_id, details),
        )

    def list_audit_logs(self, limit: int = 200) -> List[Dict]:
        return self.fetch_all(
            "SELECT a.*, u.username FROM audit_logs a "
            "LEFT JOIN users u ON a.user_id=u.id "
            "ORDER BY a.created_at DESC LIMIT ?",
            (limit,),
        )

    # -- Import settings --
    def get_import_settings(self) -> Dict:
        """Return persisted import settings from config."""
        if _CONFIG_PATH.exists():
            cfg = json.loads(_CONFIG_PATH.read_text())
            return cfg.get("import_settings", {"fuzzy_threshold": 89.0})
        return {"fuzzy_threshold": 89.0}

    def save_import_settings(self, settings: Dict) -> None:
        cfg: Dict = {}
        if _CONFIG_PATH.exists():
            cfg = json.loads(_CONFIG_PATH.read_text())
        cfg["import_settings"] = settings
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
