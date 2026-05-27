"""Branch management view."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional
from ..data.db_manager import DBManager
from ..services.auth_service import AuthService
from .dialogs import FormDialog, ask_confirm, show_error, show_info

FIELDS = [
    {"key": "name", "label": "Branch Name"},
    {"key": "code", "label": "Branch Code"},
    {"key": "address", "label": "Address"},
    {"key": "is_active", "label": "Active", "type": "combobox",
     "values": ["Yes", "No"], "default": "Yes"},
]


class BranchView(ttk.Frame):
    def __init__(self, parent, db: DBManager, auth: AuthService):
        super().__init__(parent)
        self.db = db
        self.auth = auth
        self._build()
        self.refresh()

    def _build(self):
        tb = ttk.Frame(self)
        tb.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(tb, text="Branches", font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        ttk.Button(tb, text="＋ Add", command=self._add).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="✏ Edit", command=self._edit).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="↺", command=self.refresh).pack(side=tk.RIGHT, padx=2)

        cols = ("ID", "Name", "Code", "Address", "Active")
        self._tree = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, (40, 160, 80, 260, 60)):
            self._tree.heading(c, text=c)
            self._tree.column(c, width=w)
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
        sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=4)
        self._tree.bind("<Double-Button-1>", lambda _: self._edit())

    def refresh(self):
        self._tree.delete(*self._tree.get_children())
        for r in self.db.list_branches():
            self._tree.insert("", tk.END, iid=str(r["id"]),
                              values=(r["id"], r["name"], r["code"],
                                      r.get("address",""), "Yes" if r.get("is_active") else "No"))

    def _selected_id(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self):
        def save(data):
            if not data.get("name") or not data.get("code"):
                show_error("Validation", "Name and Code are required.")
                return
            self.db.create_branch(data["name"], data["code"], data.get("address") or None)
            self.refresh()
            dlg.destroy()
            show_info("Success", "Branch created.")
        dlg = FormDialog(self, "Add Branch", FIELDS, save)

    def _edit(self):
        bid = self._selected_id()
        if not bid:
            show_error("Select", "Select a branch first.")
            return
        row = next((r for r in self.db.list_branches() if r["id"] == bid), None)
        if not row:
            return
        initial = dict(row)
        initial["is_active"] = "Yes" if row.get("is_active") else "No"
        def save(data):
            active = 1 if data.get("is_active") == "Yes" else 0
            self.db.update_branch(bid, data["name"], data["code"],
                                  data.get("address") or None, active)
            self.refresh()
            dlg.destroy()
            show_info("Success", "Branch updated.")
        dlg = FormDialog(self, "Edit Branch", FIELDS, save, initial)
