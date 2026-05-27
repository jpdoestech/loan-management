"""User account management view (admin only)."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional
from ..data.db_manager import DBManager
from ..services.auth_service import AuthService
from ..services.user_service import UserService
from .dialogs import FormDialog, show_error, show_info


class UserView(ttk.Frame):
    def __init__(self, parent, db: DBManager, auth: AuthService):
        super().__init__(parent)
        self.db = db
        self.auth = auth
        self.user_svc = UserService(db)
        self._build()
        self.refresh()

    def _build(self):
        tb = ttk.Frame(self)
        tb.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(tb, text="User Accounts", font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        ttk.Button(tb, text="＋ Add", command=self._add).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="✏ Edit", command=self._edit).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="🔑 Reset PW", command=self._reset_pw).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="↺", command=self.refresh).pack(side=tk.RIGHT, padx=2)

        cols = ("ID", "Username", "Full Name", "Role", "Branch", "Active", "Last Login")
        self._tree = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, (40, 110, 150, 70, 100, 55, 130)):
            self._tree.heading(c, text=c)
            self._tree.column(c, width=w)
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8,0), pady=4)
        sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0,8), pady=4)
        self._tree.bind("<Double-Button-1>", lambda _: self._edit())

    def refresh(self):
        self._tree.delete(*self._tree.get_children())
        for r in self.db.list_users():
            self._tree.insert("", tk.END, iid=str(r["id"]),
                              values=(r["id"], r["username"], r.get("full_name",""),
                                      r["role"], r.get("branch_name",""),
                                      "Yes" if r.get("is_active") else "No",
                                      r.get("last_login","") or "Never"))

    def _selected_id(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self):
        if not self.auth.require_role("admin"):
            show_error("Access", "Admins only."); return
        branches = self.db.list_branches()
        bmap = {b["name"]: b["id"] for b in branches}
        fields = [
            {"key": "username", "label": "Username"},
            {"key": "full_name", "label": "Full Name"},
            {"key": "password", "label": "Password", "password": True},
            {"key": "role", "label": "Role", "type": "combobox",
             "values": ["admin", "manager", "staff"], "default": "staff"},
            {"key": "branch", "label": "Branch", "type": "combobox",
             "values": [""] + [b["name"] for b in branches]},
        ]
        def save(data):
            uid = self.auth.current_user.id if self.auth.current_user else None
            ok, msg = self.user_svc.create_user(
                data["username"], data["password"], data.get("full_name",""),
                data["role"], bmap.get(data.get("branch","")), uid)
            if ok:
                self.refresh(); dlg.destroy(); show_info("Success", msg)
            else:
                show_error("Error", msg)
        dlg = FormDialog(self, "Add User", fields, save)

    def _edit(self):
        uid_sel = self._selected_id()
        if not uid_sel:
            show_error("Select", "Select a user first."); return
        user = self.user_svc.get_user(uid_sel)
        if not user: return
        branches = self.db.list_branches()
        bmap = {b["name"]: b["id"] for b in branches}
        initial = user.to_dict()
        initial["branch"] = next((b["name"] for b in branches if b["id"] == user.branch_id), "")
        initial["is_active"] = "Yes" if user.is_active else "No"
        fields = [
            {"key": "full_name", "label": "Full Name"},
            {"key": "role", "label": "Role", "type": "combobox",
             "values": ["admin", "manager", "staff"]},
            {"key": "branch", "label": "Branch", "type": "combobox",
             "values": [""] + [b["name"] for b in branches]},
            {"key": "is_active", "label": "Active", "type": "combobox",
             "values": ["Yes", "No"]},
        ]
        def save(data):
            actor = self.auth.current_user.id if self.auth.current_user else None
            active = 1 if data.get("is_active") == "Yes" else 0
            ok, msg = self.user_svc.update_user(uid_sel, data.get("full_name",""),
                                                data["role"], bmap.get(data.get("branch","")),
                                                active, actor)
            if ok:
                self.refresh(); dlg.destroy(); show_info("Success", msg)
            else:
                show_error("Error", msg)
        dlg = FormDialog(self, "Edit User", fields, save, initial)

    def _reset_pw(self):
        uid_sel = self._selected_id()
        if not uid_sel:
            show_error("Select", "Select a user first."); return
        fields = [{"key": "password", "label": "New Password", "password": True}]
        def save(data):
            actor = self.auth.current_user.id if self.auth.current_user else None
            ok, msg = self.user_svc.reset_password(uid_sel, data["password"], actor)
            if ok:
                self.refresh(); dlg.destroy(); show_info("Success", msg)
            else:
                show_error("Error", msg)
        dlg = FormDialog(self, "Reset Password", fields, save)
