"""Employee list and management view."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from src.data import db_manager as db
from src.gui.dialogs import FormDialog, show_error, show_info
from src.services import auth_service
from src.utils.logger import get_logger

log = get_logger(__name__)

_COLUMNS = [
    ("id", "ID", 40), ("employee_code", "Code", 80), ("name", "Name", 180),
    ("position", "Position", 120), ("department", "Dept", 100),
    ("monthly_salary", "Salary", 90), ("client_name", "Client", 120),
    ("branch_name", "Branch", 100),
]


class EmployeeView(ttk.Frame):
    """CRUD view for employees.

    Args:
        master: Parent widget.
    """

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._rows: List[Dict] = []
        self._build_ui()
        self.refresh()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(toolbar, text="🔍 Search:").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        ttk.Entry(toolbar, textvariable=self._search_var, width=25).pack(side=tk.LEFT, padx=4)

        ttk.Button(toolbar, text="➕ Add", command=self._add).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="✏️ Edit", command=self._edit).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🔄 Refresh", command=self.refresh).pack(side=tk.LEFT, padx=2)

        cols = [c[0] for c in _COLUMNS]
        self._tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for cid, label, width in _COLUMNS:
            self._tree.heading(cid, text=label, command=lambda c=cid: self._sort(c))
            self._tree.column(cid, width=width, anchor=tk.W)

        scroll_y = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll_y.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<Double-1>", lambda _e: self._edit())

    def refresh(self) -> None:
        """Reload employees from the database in a background thread."""
        def _load() -> None:
            rows = db.get_all_employees(active_only=False)
            self.after(0, lambda: self._populate(rows))

        threading.Thread(target=_load, daemon=True).start()

    def _populate(self, rows: List[Dict]) -> None:
        self._rows = rows
        self._filter()

    def _filter(self) -> None:
        query = self._search_var.get().lower()
        self._tree.delete(*self._tree.get_children())
        for row in self._rows:
            text = f"{row.get('name', '')} {row.get('employee_code', '')} {row.get('department', '')}".lower()
            if query and query not in text:
                continue
            tag = "" if row.get("is_active") else "inactive"
            values = [row.get(c[0], "") or "" for c in _COLUMNS]
            self._tree.insert("", tk.END, iid=str(row["id"]), values=values, tags=(tag,))
        self._tree.tag_configure("inactive", foreground="gray")

    def _sort(self, col: str) -> None:
        self._rows.sort(key=lambda r: str(r.get(col) or "").lower())
        self._filter()

    def _selected_id(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    # ── Actions ───────────────────────────────────────────────────────────────

    def _add(self) -> None:
        dlg = _EmployeeDialog(self, title="Add Employee")
        data = dlg.get_data()
        if data:
            try:
                db.create_employee(data)
                self.refresh()
            except Exception as exc:
                show_error("Error", str(exc))

    def _edit(self) -> None:
        emp_id = self._selected_id()
        if not emp_id:
            show_info("Select", "Please select an employee to edit.")
            return
        row = db.get_employee_by_id(emp_id)
        if not row:
            return
        dlg = _EmployeeDialog(self, title="Edit Employee", prefill=dict(row))
        data = dlg.get_data()
        if data:
            try:
                db.update_employee(emp_id, data)
                self.refresh()
            except Exception as exc:
                show_error("Error", str(exc))


class _EmployeeDialog(FormDialog):
    """Add / edit employee form."""

    def __init__(self, master: tk.Misc, title: str, prefill: Optional[Dict] = None) -> None:
        self._prefill = prefill or {}
        super().__init__(master, title=title)

    def _build_form(self, frame: ttk.Frame) -> None:
        p = self._prefill
        fields = [
            ("Employee Code", "employee_code", p.get("employee_code", "")),
            ("Full Name *", "name", p.get("name", "")),
            ("Position", "position", p.get("position", "")),
            ("Department", "department", p.get("department", "")),
            ("Date Hired (YYYY-MM-DD)", "date_hired", p.get("date_hired", "")),
            ("Monthly Salary", "monthly_salary", p.get("monthly_salary", "")),
            ("Phone", "phone", p.get("phone", "")),
            ("Email", "email", p.get("email", "")),
        ]
        for i, (label, key, default) in enumerate(fields):
            self._add_field(frame, label, key, row=i, default=default)

        # Client dropdown
        clients = db.get_all_clients()
        client_opts = [""] + [f"{c['id']}:{c['name']}" for c in clients]
        current_client = ""
        if p.get("client_id"):
            for c in clients:
                if c["id"] == p["client_id"]:
                    current_client = f"{c['id']}:{c['name']}"
                    break
        self._add_field(frame, "Client", "client_id_str", row=len(fields),
                        widget_type=ttk.Combobox, options=client_opts, default=current_client)

        # Active checkbox
        self._active_var = tk.IntVar(value=int(p.get("is_active", 1)))
        ttk.Checkbutton(frame, text="Active", variable=self._active_var).grid(
            row=len(fields)+1, column=1, sticky=tk.W)

    def _on_save(self) -> None:
        data = {k: v.get() for k, v in self._vars.items()}
        # Parse client_id
        cid_str = data.pop("client_id_str", "")
        data["client_id"] = int(cid_str.split(":")[0]) if cid_str and ":" in cid_str else None
        data["is_active"] = self._active_var.get()
        if not data.get("name", "").strip():
            from src.gui.dialogs import show_error
            show_error("Validation", "Employee name is required.")
            return
        self._result = data
        self.destroy()
