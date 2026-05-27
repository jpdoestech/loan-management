"""Client management view."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional
from ..data.db_manager import DBManager
from ..services.auth_service import AuthService
from .dialogs import FormDialog, show_error, show_info


class ClientView(ttk.Frame):
    def __init__(self, parent, db: DBManager, auth: AuthService):
        super().__init__(parent)
        self.db = db
        self.auth = auth
        self._build()
        self.refresh()

    def _build(self):
        tb = ttk.Frame(self)
        tb.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(tb, text="Clients", font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        ttk.Button(tb, text="＋ Add", command=self._add).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="✏ Edit", command=self._edit).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="↺", command=self.refresh).pack(side=tk.RIGHT, padx=2)

        cols = ("ID", "Name", "Code", "Email", "Phone", "Branch", "Active")
        self._tree = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, (40, 160, 80, 160, 100, 100, 55)):
            self._tree.heading(c, text=c)
            self._tree.column(c, width=w)
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
        sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=4)
        self._tree.bind("<Double-Button-1>", lambda _: self._edit())

    def refresh(self):
        self._tree.delete(*self._tree.get_children())
        for r in self.db.list_clients():
            self._tree.insert("", tk.END, iid=str(r["id"]),
                              values=(r["id"], r["name"], r.get("code",""),
                                      r.get("email",""), r.get("phone",""),
                                      r.get("branch_name",""),
                                      "Yes" if r.get("is_active") else "No"))

    def _selected_id(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _fields(self):
        branches = self.db.list_branches()
        return [
            {"key": "name", "label": "Client Name"},
            {"key": "code", "label": "Client Code"},
            {"key": "email", "label": "Email"},
            {"key": "phone", "label": "Phone"},
            {"key": "address", "label": "Address"},
            {"key": "branch", "label": "Branch", "type": "combobox",
             "values": [""] + [b["name"] for b in branches]},
            {"key": "is_active", "label": "Active", "type": "combobox",
             "values": ["Yes", "No"], "default": "Yes"},
        ]

    def _add(self):
        branches = self.db.list_branches()
        bmap = {b["name"]: b["id"] for b in branches}
        def save(data):
            if not data.get("name"):
                show_error("Validation", "Name is required.")
                return
            self.db.create_client(data["name"], data.get("code") or None,
                                  data.get("email") or None, data.get("phone") or None,
                                  data.get("address") or None, bmap.get(data.get("branch","")))
            self.refresh(); dlg.destroy(); show_info("Success", "Client created.")
        dlg = FormDialog(self, "Add Client", self._fields(), save)

    def _edit(self):
        cid = self._selected_id()
        if not cid:
            show_error("Select", "Select a client first."); return
        rows = self.db.list_clients()
        row = next((r for r in rows if r["id"] == cid), None)
        if not row: return
        branches = self.db.list_branches()
        bmap = {b["name"]: b["id"] for b in branches}
        initial = dict(row)
        initial["branch"] = row.get("branch_name","")
        initial["is_active"] = "Yes" if row.get("is_active") else "No"
        def save(data):
            active = 1 if data.get("is_active") == "Yes" else 0
            self.db.update_client(cid, data["name"], data.get("code") or None,
                                  data.get("email") or None, data.get("phone") or None,
                                  data.get("address") or None, bmap.get(data.get("branch","")), active)
            self.refresh(); dlg.destroy(); show_info("Success", "Client updated.")
        dlg = FormDialog(self, "Edit Client", self._fields(), save, initial)
