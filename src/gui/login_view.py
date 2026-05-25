"""Login dialog shown at startup."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from src.services import auth_service
from src.utils.logger import get_logger

log = get_logger(__name__)


class LoginView(tk.Toplevel):
    """Modal login window.

    Args:
        master:      Parent widget.
        on_success:  Callback called with the authenticated User on success.
    """

    def __init__(self, master: tk.Misc, on_success: Callable) -> None:
        super().__init__(master)
        self.on_success = on_success
        self.title("Employee Cash Advance Manager – Login")
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()
        self._center()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=30)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="🏦 Cash Advance Manager",
                  font=("Segoe UI", 16, "bold")).pack(pady=(0, 20))

        form = ttk.LabelFrame(outer, text="Sign In", padding=15)
        form.pack(fill=tk.X)

        ttk.Label(form, text="Username:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self._username_var = tk.StringVar()
        self._username_entry = ttk.Entry(form, textvariable=self._username_var, width=28)
        self._username_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0))

        ttk.Label(form, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self._password_var = tk.StringVar()
        self._password_entry = ttk.Entry(
            form, textvariable=self._password_var, show="•", width=28)
        self._password_entry.grid(row=1, column=1, sticky=tk.EW, padx=(8, 0))
        form.columnconfigure(1, weight=1)

        self._error_var = tk.StringVar()
        ttk.Label(outer, textvariable=self._error_var,
                  foreground="red").pack(pady=(8, 0))

        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(btn_frame, text="Login", command=self._do_login).pack(
            side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_frame, text="Quit", command=self._on_close).pack(side=tk.RIGHT)

        self._username_entry.focus()
        self._password_entry.bind("<Return>", lambda _e: self._do_login())

    def _do_login(self) -> None:
        username = self._username_var.get().strip()
        password = self._password_var.get()
        if not username:
            self._error_var.set("Please enter your username.")
            return
        user = auth_service.login(username, password)
        if user:
            self._error_var.set("")
            self.destroy()
            self.on_success(user)
        else:
            self._error_var.set("Invalid username or password.")
            self._password_entry.delete(0, tk.END)

    def _on_close(self) -> None:
        self.master.destroy()

    def _center(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
