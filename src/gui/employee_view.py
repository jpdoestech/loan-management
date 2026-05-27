"""Employee management view."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional
from ..data.db_manager import DBManager
from ..models.employee import Employee
from ..services.auth_service import AuthService
from .dialogs import FormDialog, ask_confirm, show_error, show_info


class EmployeeView(ttk.Frame):
    """CRUD view for employees."""

    def __init__(self, parent: tk.Widget, db: DBManager, auth: AuthService) -> None:
        super().__init__(parent)
        self.db = db
        self.auth = auth
        self._build()
        self.refresh()

    def _build(self) -> None:
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(toolbar, text="Employees", font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="＋ Add", command=self._add).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="✏ Edit", command=self._edit).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="🗑 Delete", command=self._delete).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="↺ Refresh", command=self.refresh).pack(side=tk.RIGHT, padx=2)

        # Search
        sf = ttk.Frame(self)
        sf.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Label(sf, text="Search:").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        ttk.Entry(sf, textvariable=self._search_var, width=30).pack(side=tk.LEFT, padx=4)

        # Table
        cols = ("ID", "Name", "Code", "Department", "Position", "Branch", "Active")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        widths = (40, 180, 90, 130, 130, 100, 55)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor=tk.CENTER if col in ("ID","Active") else tk.W)
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8))
        self._tree.bind("<Double-Button-1>", lambda _: self._edit())

        self._all_rows: List[dict] = []

    def refresh(self) -> None:
        self._all_rows = self.db.list_employees(active_only=False)
        self._filter()

    def _filter(self) -> None:
        q = self._search_var.get().lower()
        self._tree.delete(*self._tree.get_children())
        for r in self._all_rows:
            if q and q not in (r.get("name","") + r.get("employee_code","") +
                               r.get("department","") + r.get("position","")).lower():
                continue
            self._tree.insert("", tk.END, iid=str(r["id"]), values=(
                r["id"], r["name"], r.get("employee_code",""),
                r.get("department",""), r.get("position",""),
                r.get("branch_name",""), "Yes" if r.get("is_active") else "No",
            ))

    def _selected_id(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _fields(self, branches: List[dict], clients: List[dict]) -> list:
        branch_map = {b["name"]: b["id"] for b in branches}
        client_map = {c["name"]: c["id"] for c in clients}
        return [
            {"key": "name", "label": "Full Name"},
            {"key": "employee_code", "label": "Employee Code"},
            {"key": "department", "label": "Department"},
            {"key": "position", "label": "Position"},
            {"key": "email", "label": "Email"},
            {"key": "phone", "label": "Phone"},
            {"key": "branch", "label": "Branch", "type": "combobox",
             "values": [""] + list(branch_map.keys())},
            {"key": "client", "label": "Client", "type": "combobox",
             "values": [""] + list(client_map.keys())},
            {"key": "is_active", "label": "Active", "type": "combobox",
             "values": ["Yes", "No"], "default": "Yes"},
        ]

    def _add(self) -> None:
        branches = self.db.list_branches()
        clients = self.db.list_clients()
        branch_map = {b["name"]: b["id"] for b in branches}
        client_map = {c["name"]: c["id"] for c in clients}

        def save(data: dict) -> None:
            if not data.get("name"):
                show_error("Validation", "Name is required")
                return
            bid = branch_map.get(data.get("branch",""))
            cid = client_map.get(data.get("client",""))
            self.db.create_employee(
                data["name"], data.get("employee_code") or None,
                data.get("department") or None, data.get("position") or None,
                data.get("email") or None, data.get("phone") or None, bid, cid,
            )
            self.db.log_action(self.auth.current_user.id if self.auth.current_user else None,
                               "CREATE_EMPLOYEE")
            self.refresh()
            dlg.destroy()
            show_info("Success", "Employee added.")

        dlg = FormDialog(self, "Add Employee", self._fields(branches, clients), save)

    def _edit(self) -> None:
        eid = self._selected_id()
        if not eid:
            show_error("Select", "Please select an employee first.")
            return
        row = self.db.get_employee_by_id(eid)
        if not row:
            return
        branches = self.db.list_branches()
        clients = self.db.list_clients()
        branch_map = {b["name"]: b["id"] for b in branches}
        client_map = {c["name"]: c["id"] for c in clients}
        branch_name = next((b["name"] for b in branches if b["id"] == row.get("branch_id")), "")
        client_name = next((c["name"] for c in clients if c["id"] == row.get("client_id")), "")
        initial = dict(row)
        initial["branch"] = branch_name
        initial["client"] = client_name
        initial["is_active"] = "Yes" if row.get("is_active") else "No"

        def save(data: dict) -> None:
            if not data.get("name"):
                show_error("Validation", "Name is required")
                return
            bid = branch_map.get(data.get("branch",""))
            cid = client_map.get(data.get("client",""))
            active = 1 if data.get("is_active") == "Yes" else 0
            self.db.update_employee(eid, data["name"], data.get("employee_code") or None,
                                    data.get("department") or None, data.get("position") or None,
                                    data.get("email") or None, data.get("phone") or None,
                                    bid, cid, active)
            self.refresh()
            dlg.destroy()
            show_info("Success", "Employee updated.")

        dlg = FormDialog(self, "Edit Employee", self._fields(branches, clients), save, initial)

    def _delete(self) -> None:
        eid = self._selected_id()
        if not eid:
            show_error("Select", "Please select an employee first.")
            return
        if ask_confirm("Confirm", "Mark this employee as inactive?"):
            self.db.update_employee(eid, *[
                self.db.get_employee_by_id(eid).get(k)
                for k in ("name","employee_code","department","position","email","phone","branch_id","client_id")
            ], 0)
            self.refresh()
