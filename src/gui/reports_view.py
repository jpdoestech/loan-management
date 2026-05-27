"""Reports view — loans summary, repayments, outstanding balances, exports."""
from __future__ import annotations
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import date
from ..data.db_manager import DBManager
from ..services.auth_service import AuthService
from ..services.report_service import ReportService
from .dialogs import show_error, show_info


class ReportsView(ttk.Frame):
    def __init__(self, parent, db: DBManager, auth: AuthService):
        super().__init__(parent)
        self.db = db
        self.auth = auth
        self.report_svc = ReportService(db)
        self._build()

    def _build(self):
        # Controls
        ctrl = ttk.LabelFrame(self, text="Filters & Export")
        ctrl.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(ctrl, text="Report:").grid(row=0, column=0, padx=6, pady=4, sticky=tk.W)
        self._report_var = tk.StringVar(value="Loans Summary")
        ttk.Combobox(ctrl, textvariable=self._report_var, state="readonly", width=22,
                     values=["Loans Summary", "Repayments", "Outstanding Balances"]
                     ).grid(row=0, column=1, padx=4, pady=4)

        ttk.Label(ctrl, text="Status:").grid(row=0, column=2, padx=6, sticky=tk.W)
        self._status_var = tk.StringVar(value="")
        ttk.Combobox(ctrl, textvariable=self._status_var, state="readonly", width=12,
                     values=["", "pending", "approved", "active", "closed", "rejected"]
                     ).grid(row=0, column=3, padx=4)

        ttk.Label(ctrl, text="From:").grid(row=0, column=4, padx=6, sticky=tk.W)
        self._from_var = tk.StringVar()
        ttk.Entry(ctrl, textvariable=self._from_var, width=12).grid(row=0, column=5, padx=4)

        ttk.Label(ctrl, text="To:").grid(row=0, column=6, padx=4, sticky=tk.W)
        self._to_var = tk.StringVar()
        ttk.Entry(ctrl, textvariable=self._to_var, width=12).grid(row=0, column=7, padx=4)

        ttk.Button(ctrl, text="▶ Run", command=self._run).grid(row=0, column=8, padx=8)
        ttk.Button(ctrl, text="📥 Export CSV", command=lambda: self._export("csv")
                   ).grid(row=0, column=9, padx=4)
        ttk.Button(ctrl, text="📊 Export Excel", command=lambda: self._export("xlsx")
                   ).grid(row=0, column=10, padx=4)

        # Status bar
        self._status_lbl = ttk.Label(self, text="")
        self._status_lbl.pack(anchor=tk.W, padx=8)

        # Results treeview (dynamic columns)
        self._tree_frame = ttk.Frame(self)
        self._tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._tree: ttk.Treeview | None = None
        self._rows: list = []

    def _run(self):
        self._status_lbl.config(text="Loading…")
        self.after(50, self._fetch)

    def _fetch(self):
        report = self._report_var.get()
        status = self._status_var.get() or None
        from_d = self._from_var.get() or None
        to_d = self._to_var.get() or None

        if report == "Loans Summary":
            self._rows = self.report_svc.loans_summary(status, from_d, to_d)
        elif report == "Repayments":
            self._rows = self.report_svc.repayments_summary(from_d, to_d)
        else:
            self._rows = self.report_svc.outstanding_balances()

        self._render_table()
        self._status_lbl.config(text=f"{len(self._rows)} rows loaded.")

    def _render_table(self):
        for w in self._tree_frame.winfo_children():
            w.destroy()
        if not self._rows:
            ttk.Label(self._tree_frame, text="No data found.").pack(pady=20)
            return
        cols = list(self._rows[0].keys())
        self._tree = ttk.Treeview(self._tree_frame, columns=cols, show="headings")
        for col in cols:
            self._tree.heading(col, text=col.replace("_", " ").title())
            self._tree.column(col, width=max(80, len(col) * 9), anchor=tk.W)
        vsb = ttk.Scrollbar(self._tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(self._tree_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)
        for r in self._rows:
            self._tree.insert("", tk.END, values=[r.get(c, "") for c in cols])

    def _export(self, fmt: str):
        if not self._rows:
            show_error("No Data", "Run a report first."); return
        default = self.report_svc.default_export_path(
            self._report_var.get().lower().replace(" ", "_"), fmt)
        path = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}"), ("All", "*.*")],
            initialfile=os.path.basename(default),
            initialdir=os.path.dirname(default),
        )
        if not path:
            return
        def do_export():
            if fmt == "csv":
                self.report_svc.export_csv(self._rows, path)
            else:
                self.report_svc.export_excel(self._rows, path, self._report_var.get())
            self.after(0, lambda: show_info("Exported", f"Saved to:\n{path}"))
        threading.Thread(target=do_export, daemon=True).start()
