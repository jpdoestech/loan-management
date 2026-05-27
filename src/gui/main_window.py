"""Main application window — sidebar navigation, tab content, menu bar."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from ..data.db_manager import DBManager
from ..models.user import User
from ..services.auth_service import AuthService
from ..services.user_service import UserService
from ..utils.crypto import hash_password


class MainWindow:
    """Root application window built after successful login."""

    NAV_ITEMS = [
        ("🏠 Dashboard",     "dashboard"),
        ("🏢 Branches",      "branches"),
        ("🏭 Clients",       "clients"),
        ("👤 Employees",     "employees"),
        ("💰 Loans",         "loans"),
        ("📊 Reports",       "reports"),
        ("📥 Import",        "import"),
        ("👥 Users",         "users"),
    ]

    def __init__(self, root: tk.Tk, db: DBManager) -> None:
        self.root = root
        self.db = db
        self.auth = AuthService(db)
        self._current_frame: Optional[tk.Widget] = None

        root.title("Employee Cash Advance Manager")
        root.geometry("1100x680")
        root.minsize(900, 560)

        self._ensure_admin_exists()
        self._show_login()

    # ------------------------------------------------------------------ #
    # Bootstrap
    # ------------------------------------------------------------------ #

    def _ensure_admin_exists(self) -> None:
        """Create a default admin account if no users exist."""
        users = self.db.list_users()
        if not users:
            self.db.create_user("admin", hash_password("admin123"),
                                "Administrator", "admin", None)

    def _show_login(self) -> None:
        from .login_view import LoginView
        LoginView(self.root, self.auth, self._on_login_success)

    def _on_login_success(self, user: User) -> None:
        self._build_shell()
        self._navigate("dashboard")

    # ------------------------------------------------------------------ #
    # Shell layout
    # ------------------------------------------------------------------ #

    def _build_shell(self) -> None:
        self.root.configure(bg="#1C2833")

        # Top bar
        topbar = tk.Frame(self.root, bg="#1C2833", height=42)
        topbar.pack(fill=tk.X, side=tk.TOP)
        topbar.pack_propagate(False)
        tk.Label(topbar, text="💼 Employee Cash Advance Manager",
                 bg="#1C2833", fg="white",
                 font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=12)

        # User info / logout
        user_frame = tk.Frame(topbar, bg="#1C2833")
        user_frame.pack(side=tk.RIGHT, padx=8)
        user = self.auth.current_user
        tk.Label(user_frame,
                 text=f"👤 {user.full_name or user.username}  [{user.role}]",
                 bg="#1C2833", fg="#AED6F1",
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=4)
        tk.Button(user_frame, text="Logout", bg="#2E86C1", fg="white",
                  relief=tk.FLAT, cursor="hand2",
                  command=self._logout).pack(side=tk.LEFT, padx=4)
        tk.Button(user_frame, text="⚙ Settings", bg="#555", fg="white",
                  relief=tk.FLAT, cursor="hand2",
                  command=self._open_settings).pack(side=tk.LEFT, padx=4)
        tk.Button(user_frame, text="🔑 Change PW", bg="#555", fg="white",
                  relief=tk.FLAT, cursor="hand2",
                  command=self._change_pw).pack(side=tk.LEFT, padx=4)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        body = tk.Frame(self.root, bg="#1C2833")
        body.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        sidebar = tk.Frame(body, bg="#17202A", width=170)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        self._nav_buttons: dict = {}
        for label, key in self.NAV_ITEMS:
            if key == "users" and not (self.auth.current_user and
                                       self.auth.current_user.is_admin):
                continue
            btn = tk.Button(
                sidebar, text=label, anchor=tk.W, padx=14,
                bg="#17202A", fg="#BDC3C7", activebackground="#2980B9",
                activeforeground="white", relief=tk.FLAT,
                font=("Segoe UI", 10), cursor="hand2",
                command=lambda k=key: self._navigate(k),
            )
            btn.pack(fill=tk.X, ipady=8)
            self._nav_buttons[key] = btn

        # Content area
        self._content = tk.Frame(body, bg="#F0F3F4")
        self._content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #

    def _navigate(self, key: str) -> None:
        # Highlight active button
        for k, btn in self._nav_buttons.items():
            btn.configure(bg="#2980B9" if k == key else "#17202A",
                          fg="white" if k == key else "#BDC3C7")

        if self._current_frame:
            self._current_frame.destroy()

        frame = self._build_view(key)
        if frame:
            frame.pack(fill=tk.BOTH, expand=True)
            self._current_frame = frame

    def _build_view(self, key: str) -> Optional[tk.Widget]:
        from .branch_view import BranchView
        from .client_view import ClientView
        from .employee_view import EmployeeView
        from .loan_view import LoanView
        from .reports_view import ReportsView
        from .user_view import UserView

        if key == "dashboard":
            return self._build_dashboard()
        elif key == "branches":
            return BranchView(self._content, self.db, self.auth)
        elif key == "clients":
            return ClientView(self._content, self.db, self.auth)
        elif key == "employees":
            return EmployeeView(self._content, self.db, self.auth)
        elif key == "loans":
            return LoanView(self._content, self.db, self.auth)
        elif key == "reports":
            return ReportsView(self._content, self.db, self.auth)
        elif key == "import":
            from .import_view import ImportView
            ImportView(self.root, self.db, self.auth)
            return self._build_dashboard()
        elif key == "users":
            return UserView(self._content, self.db, self.auth)
        return None

    # ------------------------------------------------------------------ #
    # Dashboard
    # ------------------------------------------------------------------ #

    def _build_dashboard(self) -> ttk.Frame:
        frame = ttk.Frame(self._content)
        ttk.Label(frame, text="Dashboard",
                  font=("Segoe UI", 16, "bold")).pack(anchor=tk.W, padx=16, pady=(16, 8))

        cards = ttk.Frame(frame)
        cards.pack(fill=tk.X, padx=16, pady=8)

        stats = [
            ("Total Employees", self._count("SELECT COUNT(*) FROM employees WHERE is_active=1"),
             "#2980B9"),
            ("Active Loans", self._count("SELECT COUNT(*) FROM loans WHERE status='active'"),
             "#27AE60"),
            ("Pending Approvals", self._count("SELECT COUNT(*) FROM loans WHERE status='pending'"),
             "#F39C12"),
            ("Total Outstanding",
             self._sum("SELECT COALESCE(SUM(outstanding_balance),0) FROM loans "
                       "WHERE status IN ('active','approved')"),
             "#8E44AD"),
        ]
        for title, value, color in stats:
            card = tk.Frame(cards, bg=color, width=200, height=90)
            card.pack(side=tk.LEFT, padx=8, pady=4)
            card.pack_propagate(False)
            tk.Label(card, text=title, bg=color, fg="white",
                     font=("Segoe UI", 10)).pack(pady=(12, 2))
            tk.Label(card, text=str(value), bg=color, fg="white",
                     font=("Segoe UI", 18, "bold")).pack()

        # Recent loans
        ttk.Label(frame, text="Recent Loan Applications",
                  font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, padx=16, pady=(16, 4))
        cols = ("Reference", "Employee", "Amount", "Status", "Applied")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=8)
        for col, w in zip(cols, (130, 180, 100, 90, 100)):
            tree.heading(col, text=col)
            tree.column(col, width=w)
        tree.tag_configure("pending", foreground="#F39C12")
        tree.tag_configure("active", foreground="#2980B9")
        tree.tag_configure("closed", foreground="#7F8C8D")
        for r in self.db.list_loans()[:15]:
            tree.insert("", tk.END, tags=(r.get("status",""),), values=(
                r.get("reference_number",""), r.get("employee_name",""),
                f"₱{r.get('requested_amount',0):,.2f}",
                r.get("status",""), r.get("application_date",""),
            ))
        tree.pack(fill=tk.X, padx=16, pady=(0, 12))
        return frame

    def _count(self, sql: str) -> int:
        row = self.db.fetch_one(sql)
        return list(row.values())[0] if row else 0

    def _sum(self, sql: str) -> str:
        row = self.db.fetch_one(sql)
        val = list(row.values())[0] if row else 0
        return f"₱{float(val):,.2f}"

    # ------------------------------------------------------------------ #
    # Menu actions
    # ------------------------------------------------------------------ #

    def _logout(self) -> None:
        if messagebox.askyesno("Logout", "Log out of the application?"):
            self.auth.logout()
            for w in self.root.winfo_children():
                w.destroy()
            self._show_login()

    def _open_settings(self) -> None:
        from .network_settings_view import NetworkSettingsView
        NetworkSettingsView(self.root, self.db)

    def _change_pw(self) -> None:
        user = self.auth.current_user
        if not user:
            return
        win = tk.Toplevel(self.root)
        win.title("Change Password")
        win.geometry("300x220")
        win.resizable(False, False)
        win.grab_set()
        f = ttk.Frame(win, padding=20)
        f.pack(fill=tk.BOTH, expand=True)
        vars_ = {}
        for row_i, (lbl, key, show) in enumerate([
            ("Current Password", "old", True),
            ("New Password", "new1", True),
            ("Confirm New", "new2", True),
        ]):
            ttk.Label(f, text=f"{lbl}:").grid(row=row_i, column=0, sticky=tk.W, pady=4)
            v = tk.StringVar()
            ttk.Entry(f, textvariable=v, show="•" if show else "", width=22).grid(
                row=row_i, column=1, pady=4)
            vars_[key] = v
        msg_v = tk.StringVar()
        ttk.Label(f, textvariable=msg_v, foreground="red").grid(
            row=3, column=0, columnspan=2)

        def do_change():
            if vars_["new1"].get() != vars_["new2"].get():
                msg_v.set("Passwords do not match."); return
            ok, msg = self.auth.change_password(
                user.id, vars_["old"].get(), vars_["new1"].get())
            if ok:
                win.destroy()
                messagebox.showinfo("Success", msg)
            else:
                msg_v.set(msg)

        ttk.Button(f, text="Change Password", command=do_change).grid(
            row=4, column=0, columnspan=2, pady=(12, 0))
