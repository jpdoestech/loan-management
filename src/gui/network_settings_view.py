"""Network & Import Settings dialog."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from ..data.db_manager import DBManager
from .dialogs import show_info


class NetworkSettingsView(tk.Toplevel):
    """Settings dialog for DB connection mode and import options."""

    def __init__(self, parent, db: DBManager):
        super().__init__(parent)
        self.db = db
        self.title("Settings — Network & Import")
        self.geometry("480x420")
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self._load()

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # --- Network tab ---
        net = ttk.Frame(nb, padding=16)
        nb.add(net, text="Network / DB")

        ttk.Label(net, text="Connection Mode:", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        self._mode_var = tk.StringVar(value="local")
        ttk.Radiobutton(net, text="Local / Network Share (direct SQLite)",
                        variable=self._mode_var, value="local",
                        command=self._on_mode).grid(row=1, column=0, columnspan=2, sticky=tk.W)
        ttk.Radiobutton(net, text="REST Server (recommended for multi-user)",
                        variable=self._mode_var, value="rest",
                        command=self._on_mode).grid(row=2, column=0, columnspan=2, sticky=tk.W)

        ttk.Separator(net, orient=tk.HORIZONTAL).grid(
            row=3, column=0, columnspan=2, sticky=tk.EW, pady=10)

        ttk.Label(net, text="SQLite DB Path (local/SMB):").grid(
            row=4, column=0, sticky=tk.W, pady=3)
        self._db_path_var = tk.StringVar()
        ttk.Entry(net, textvariable=self._db_path_var, width=36).grid(
            row=4, column=1, sticky=tk.EW, pady=3)

        ttk.Label(net, text="Server URL:").grid(row=5, column=0, sticky=tk.W, pady=3)
        self._url_var = tk.StringVar()
        self._url_entry = ttk.Entry(net, textvariable=self._url_var, width=36)
        self._url_entry.grid(row=5, column=1, sticky=tk.EW, pady=3)

        ttk.Label(net, text="API Token:").grid(row=6, column=0, sticky=tk.W, pady=3)
        self._token_var = tk.StringVar()
        self._token_entry = ttk.Entry(net, textvariable=self._token_var, width=36, show="•")
        self._token_entry.grid(row=6, column=1, sticky=tk.EW, pady=3)

        ttk.Label(net, text="⚠ Restart required after changing connection mode.",
                  foreground="orange").grid(row=7, column=0, columnspan=2, pady=(10, 0))

        # --- Import tab ---
        imp = ttk.Frame(nb, padding=16)
        nb.add(imp, text="Import Settings")

        ttk.Label(imp, text="Fuzzy Match Threshold (%):").grid(
            row=0, column=0, sticky=tk.W, pady=6)
        self._threshold_var = tk.StringVar(value="89")
        ttk.Entry(imp, textvariable=self._threshold_var, width=8).grid(
            row=0, column=1, sticky=tk.W, pady=6)
        ttk.Label(imp, text="(0 – 100; default 89)",
                  foreground="gray").grid(row=0, column=2, padx=6, sticky=tk.W)

        ttk.Label(imp, text="Sets the minimum similarity score for\n"
                  "auto-accepting a fuzzy employee name match.",
                  foreground="gray", justify=tk.LEFT).grid(
            row=1, column=0, columnspan=3, sticky=tk.W, pady=(0, 12))

        # Bottom buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="Test Connection", command=self._test).pack(
            side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)

    def _load(self):
        self._mode_var.set(self.db.mode)
        self._db_path_var.set(self.db.db_path or "")
        self._url_var.set(self.db.server_url or "")
        self._token_var.set(self.db.token or "")
        cfg = self.db.get_import_settings()
        self._threshold_var.set(str(cfg.get("fuzzy_threshold", 89.0)))
        self._on_mode()

    def _on_mode(self):
        is_rest = self._mode_var.get() == "rest"
        state = tk.NORMAL if is_rest else tk.DISABLED
        self._url_entry.configure(state=state)
        self._token_entry.configure(state=state)

    def _save(self):
        try:
            threshold = float(self._threshold_var.get())
            if not (0 <= threshold <= 100):
                raise ValueError
        except ValueError:
            messagebox.showerror("Validation", "Threshold must be a number 0-100.")
            return
        self.db.mode = self._mode_var.get()
        self.db.db_path = self._db_path_var.get().strip()
        self.db.server_url = self._url_var.get().strip() or None
        self.db.token = self._token_var.get().strip() or None
        self.db.save_config()
        self.db.save_import_settings({"fuzzy_threshold": threshold})
        show_info("Saved", "Settings saved. Restart the app to apply connection changes.")
        self.destroy()

    def _test(self):
        if self._mode_var.get() == "local":
            import os
            p = self._db_path_var.get().strip()
            d = os.path.dirname(p) or "."
            if os.path.isdir(d):
                show_info("OK", f"Directory is accessible:\n{d}")
            else:
                messagebox.showerror("Failed", f"Directory not found:\n{d}")
        else:
            try:
                import requests
                r = requests.get(
                    f"{self._url_var.get().strip()}/ping",
                    headers={"Authorization": f"Bearer {self._token_var.get().strip()}"},
                    timeout=5,
                )
                if r.ok:
                    show_info("OK", "Server is reachable.")
                else:
                    messagebox.showerror("Failed", f"Server returned {r.status_code}")
            except Exception as e:
                messagebox.showerror("Failed", str(e))
