"""Login screen."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional
from ..services.auth_service import AuthService


class LoginView(tk.Toplevel):
    """Modal login dialog."""

    def __init__(self, parent: tk.Tk, auth: AuthService,
                 on_success: Callable) -> None:
        super().__init__(parent)
        self.auth = auth
        self.on_success = on_success
        self.title("Employee Cash Advance Manager — Login")
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, lambda: self._username_var.set(""))

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=30)
        frame.pack(fill=tk.BOTH, expand=True)

        # Title
        ttk.Label(frame, text="💼 Cash Advance Manager",
                  font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 20))

        ttk.Label(frame, text="Username:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self._username_var = tk.StringVar()
        self._username_entry = ttk.Entry(frame, textvariable=self._username_var, width=28)
        self._username_entry.grid(row=1, column=1, pady=4)

        ttk.Label(frame, text="Password:").grid(row=2, column=0, sticky=tk.W, pady=4)
        self._password_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._password_var, show="•", width=28).grid(
            row=2, column=1, pady=4)

        self._msg_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._msg_var, foreground="red").grid(
            row=3, column=0, columnspan=2, pady=6)

        btn = ttk.Button(frame, text="Login", command=self._attempt_login)
        btn.grid(row=4, column=0, columnspan=2, pady=(10, 0))

        self.bind("<Return>", lambda _: self._attempt_login())
        self._username_entry.focus_set()

    def _attempt_login(self) -> None:
        user = self.auth.login(
            self._username_var.get().strip(),
            self._password_var.get(),
        )
        if user:
            self.destroy()
            self.on_success(user)
        else:
            self._msg_var.set("Invalid username or password.")
            self._password_var.set("")

    def _on_close(self) -> None:
        self.master.destroy()
