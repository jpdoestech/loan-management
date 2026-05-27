"""Import dialog — file selection, column mapping, fuzzy review, dry-run/commit."""
from __future__ import annotations
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Dict, List, Optional

from ..data.db_manager import DBManager
from ..services.auth_service import AuthService
from ..services.import_service import ImportRowResult, ImportService
from .dialogs import show_error, show_info


class ImportView(tk.Toplevel):
    """Multi-step import dialog window."""

    STEPS = ("1. File", "2. Map Columns", "3. Preview & Match", "4. Import")

    def __init__(self, parent, db: DBManager, auth: AuthService):
        super().__init__(parent)
        self.db = db
        self.auth = auth
        self.title("Import Loans / Repayments")
        self.geometry("900x620")
        self.resizable(True, True)
        self.grab_set()

        # State
        self._file_path: str = ""
        self._headers: List[str] = []
        self._raw_rows: List[Dict] = []
        self._mapping: Dict[str, Optional[str]] = {}
        self._results: List[ImportRowResult] = []
        self._import_type = "loan"
        self._threshold = 89.0

        cfg = db.get_import_settings()
        self._threshold = float(cfg.get("fuzzy_threshold", 89.0))
        self._svc = ImportService(db, self._threshold)

        self._build()
        self._show_step(0)

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #

    def _build(self):
        # Step indicator
        step_bar = ttk.Frame(self, relief=tk.GROOVE)
        step_bar.pack(fill=tk.X, padx=0, pady=0)
        self._step_labels: List[ttk.Label] = []
        for i, s in enumerate(self.STEPS):
            lbl = ttk.Label(step_bar, text=s, padding=(12, 6), relief=tk.FLAT,
                            anchor=tk.CENTER)
            lbl.pack(side=tk.LEFT, expand=True, fill=tk.X)
            self._step_labels.append(lbl)

        # Content notebook (hidden tabs, driven by step buttons)
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._nb.configure(takefocus=False)

        self._page_file = ttk.Frame(self._nb)
        self._page_map = ttk.Frame(self._nb)
        self._page_preview = ttk.Frame(self._nb)
        self._page_result = ttk.Frame(self._nb)
        for pg in (self._page_file, self._page_map, self._page_preview, self._page_result):
            self._nb.add(pg)
        self._nb.tab(0, state="normal")

        # Bottom nav
        nav = ttk.Frame(self)
        nav.pack(fill=tk.X, padx=8, pady=6)
        self._back_btn = ttk.Button(nav, text="◀ Back", command=self._back, state=tk.DISABLED)
        self._back_btn.pack(side=tk.LEFT)
        self._next_btn = ttk.Button(nav, text="Next ▶", command=self._next)
        self._next_btn.pack(side=tk.RIGHT)
        self._dry_btn = ttk.Button(nav, text="🔍 Dry Run", command=self._dry_run)
        self._import_btn = ttk.Button(nav, text="✔ Import", command=self._commit)
        self._status_var = tk.StringVar()
        ttk.Label(nav, textvariable=self._status_var).pack(side=tk.LEFT, padx=12)

        self._current_step = 0
        self._build_step_file()
        self._build_step_map()
        self._build_step_preview()
        self._build_step_result()

    # ------------------------------------------------------------------ #
    # Step 1 — File selection
    # ------------------------------------------------------------------ #

    def _build_step_file(self):
        f = self._page_file
        ttk.Label(f, text="Select import file and options",
                  font=("Segoe UI", 11, "bold")).pack(pady=(16, 8))

        row = ttk.Frame(f); row.pack(pady=4)
        self._file_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._file_var, width=50).pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="Browse…", command=self._browse).pack(side=tk.LEFT)

        row2 = ttk.Frame(f); row2.pack(pady=8)
        ttk.Label(row2, text="Import type:").pack(side=tk.LEFT, padx=4)
        self._type_var = tk.StringVar(value="loan")
        ttk.Radiobutton(row2, text="Loans / Cash Advances", variable=self._type_var,
                        value="loan").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(row2, text="Repayments", variable=self._type_var,
                        value="repayment").pack(side=tk.LEFT, padx=4)

        row3 = ttk.Frame(f); row3.pack(pady=4)
        ttk.Label(row3, text="Fuzzy threshold (%):").pack(side=tk.LEFT, padx=4)
        self._thresh_var = tk.StringVar(value=str(self._threshold))
        ttk.Entry(row3, textvariable=self._thresh_var, width=6).pack(side=tk.LEFT)
        ttk.Label(row3, text="(0-100; default 89)", foreground="gray").pack(side=tk.LEFT, padx=4)

        ttk.Label(f, text="Supported formats: CSV (.csv) and Excel (.xlsx)",
                  foreground="gray").pack(pady=(12, 0))

    def _browse(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV/Excel", "*.csv *.xlsx"), ("CSV", "*.csv"),
                       ("Excel", "*.xlsx"), ("All", "*.*")])
        if path:
            self._file_var.set(path)

    # ------------------------------------------------------------------ #
    # Step 2 — Column mapping
    # ------------------------------------------------------------------ #

    def _build_step_map(self):
        f = self._page_map
        ttk.Label(f, text="Map file columns to model fields",
                  font=("Segoe UI", 11, "bold")).pack(pady=(16, 8))
        self._map_frame = ttk.Frame(f)
        self._map_frame.pack(fill=tk.BOTH, expand=True, padx=16)
        self._map_combos: Dict[str, ttk.Combobox] = {}

    def _populate_mapping(self):
        for w in self._map_frame.winfo_children():
            w.destroy()
        self._map_combos.clear()
        itype = self._type_var.get()
        field_map = (ImportService.LOAN_FIELDS if itype == "loan"
                     else ImportService.REPAYMENT_FIELDS)
        auto = self._svc.auto_map_columns(self._headers, itype)
        options = ["(skip)"] + self._headers

        for row_i, (field, _) in enumerate(field_map.items()):
            ttk.Label(self._map_frame,
                      text=field.replace("_", " ").title() + ":").grid(
                row=row_i, column=0, sticky=tk.W, pady=3, padx=(0, 12))
            var = tk.StringVar(value=auto.get(field) or "(skip)")
            cb = ttk.Combobox(self._map_frame, textvariable=var,
                              values=options, state="readonly", width=28)
            cb.grid(row=row_i, column=1, sticky=tk.W, pady=3)
            self._map_combos[field] = cb

    # ------------------------------------------------------------------ #
    # Step 3 — Preview & fuzzy match review
    # ------------------------------------------------------------------ #

    def _build_step_preview(self):
        f = self._page_preview
        ttk.Label(f, text="Preview — review validation and employee matching",
                  font=("Segoe UI", 11, "bold")).pack(pady=(12, 4))

        # Summary bar
        self._preview_summary = tk.StringVar()
        ttk.Label(f, textvariable=self._preview_summary, foreground="#2980B9"
                  ).pack(anchor=tk.W, padx=10)

        # Table
        cols = ("Row", "Status", "Employee (raw)", "Matched Employee", "Score",
                "Amount", "Errors / Warnings")
        self._prev_tree = ttk.Treeview(f, columns=cols, show="headings", height=14)
        widths = (40, 65, 160, 160, 55, 90, 260)
        for col, w in zip(cols, widths):
            self._prev_tree.heading(col, text=col)
            self._prev_tree.column(col, width=w,
                                   anchor=tk.CENTER if col in ("Row","Score") else tk.W)
        vsb = ttk.Scrollbar(f, orient=tk.VERTICAL, command=self._prev_tree.yview)
        self._prev_tree.configure(yscrollcommand=vsb.set)
        self._prev_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=4)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=4)

        # Tags
        self._prev_tree.tag_configure("valid", foreground="#27AE60")
        self._prev_tree.tag_configure("invalid", foreground="#E74C3C")
        self._prev_tree.tag_configure("warning", foreground="#F39C12")

        # Fix employee button
        btn_bar = ttk.Frame(f)
        btn_bar.pack(fill=tk.X, padx=10, pady=(0, 4))
        ttk.Button(btn_bar, text="🔧 Fix Employee for Selected Row",
                   command=self._fix_employee).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="↺ Re-validate", command=self._revalidate).pack(side=tk.LEFT)

    def _populate_preview(self):
        self._prev_tree.delete(*self._prev_tree.get_children())
        valid = sum(1 for r in self._results if r.is_valid)
        invalid = len(self._results) - valid
        self._preview_summary.set(
            f"Total: {len(self._results)}   ✔ Valid: {valid}   ✗ Invalid/Unmatched: {invalid}")
        for res in self._results:
            top = res.match_suggestions[0] if res.match_suggestions else None
            matched = top.employee_name if top else ("✔ matched" if res.employee_id else "—")
            score = f"{top.score:.0f}%" if top else ""
            amt_key = "requested_amount" if "requested_amount" in res.normalized else "amount"
            amt = res.normalized.get(amt_key, "")
            amt_str = f"{amt:,.2f}" if isinstance(amt, float) else str(amt)
            msgs = "; ".join(res.errors + res.warnings)[:80]
            tag = "valid" if res.is_valid else ("warning" if res.warnings and not res.errors else "invalid")
            self._prev_tree.insert("", tk.END, iid=str(res.row_index),
                                   tags=(tag,),
                                   values=(res.row_index, res.status,
                                           res.employee_name_raw[:30], matched, score,
                                           amt_str, msgs))

    def _fix_employee(self):
        sel = self._prev_tree.selection()
        if not sel:
            show_error("Select", "Select a row first."); return
        row_idx = int(sel[0])
        result = next((r for r in self._results if r.row_index == row_idx), None)
        if not result: return

        employees = self.db.list_employees()
        items = [(e["id"], f"{e['name']} ({e.get('employee_code','')}) — {e.get('department','')}")
                 for e in employees]

        def on_select(emp_id):
            result.employee_id = emp_id
            result.status = "valid" if not result.errors else "invalid"
            self._populate_preview()

        from .dialogs import SearchableListDialog
        SearchableListDialog(self, "Pick Employee", items, on_select)

    def _revalidate(self):
        self._status_var.set("Re-validating…")
        self._build_mapping_dict()
        threading.Thread(target=self._do_validate, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Step 4 — Result
    # ------------------------------------------------------------------ #

    def _build_step_result(self):
        f = self._page_result
        self._result_text = tk.Text(f, wrap=tk.WORD, state=tk.DISABLED,
                                    font=("Consolas", 10))
        sb = ttk.Scrollbar(f, orient=tk.VERTICAL, command=self._result_text.yview)
        self._result_text.configure(yscrollcommand=sb.set)
        self._result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)

    def _show_result_text(self, text: str):
        self._result_text.configure(state=tk.NORMAL)
        self._result_text.delete("1.0", tk.END)
        self._result_text.insert(tk.END, text)
        self._result_text.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #

    def _show_step(self, step: int):
        self._current_step = step
        self._nb.select(step)
        for i, lbl in enumerate(self._step_labels):
            lbl.configure(
                background="#2980B9" if i == step else "",
                foreground="white" if i == step else "black",
            )
        self._back_btn.configure(state=tk.NORMAL if step > 0 else tk.DISABLED)
        # Show/hide import buttons only on step 3
        if step == 3:
            self._next_btn.pack_forget()
            self._dry_btn.pack(side=tk.RIGHT, padx=4)
            self._import_btn.pack(side=tk.RIGHT, padx=4)
        else:
            self._dry_btn.pack_forget()
            self._import_btn.pack_forget()
            self._next_btn.pack(side=tk.RIGHT)
            self._next_btn.configure(
                text="Finish" if step == len(self.STEPS) - 1 else "Next ▶")

    def _next(self):
        if self._current_step == 0:
            if not self._load_file(): return
            self._show_step(1)
        elif self._current_step == 1:
            self._build_mapping_dict()
            self._status_var.set("Validating rows…")
            self._next_btn.configure(state=tk.DISABLED)
            threading.Thread(target=self._do_validate, daemon=True).start()
        elif self._current_step == 2:
            self._show_step(3)
        elif self._current_step == 3:
            self.destroy()

    def _back(self):
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    # ------------------------------------------------------------------ #
    # Business logic
    # ------------------------------------------------------------------ #

    def _load_file(self) -> bool:
        path = self._file_var.get().strip()
        if not path or not os.path.exists(path):
            show_error("File", "Please select a valid file."); return False
        try:
            self._threshold = float(self._thresh_var.get())
        except ValueError:
            self._threshold = 89.0
        self._svc.threshold = self._threshold
        self._svc.matcher.threshold = self._threshold
        self._import_type = self._type_var.get()
        self._file_path = path
        try:
            self._headers, self._raw_rows = self._svc.parse_file(path)
        except Exception as e:
            show_error("Parse Error", str(e)); return False
        self._status_var.set(f"Loaded {len(self._raw_rows)} rows, {len(self._headers)} columns.")
        self._populate_mapping()
        return True

    def _build_mapping_dict(self):
        self._mapping = {
            field: (cb.get() if cb.get() != "(skip)" else None)
            for field, cb in self._map_combos.items()
        }

    def _do_validate(self):
        try:
            self._results = self._svc.validate_rows(
                self._raw_rows, self._mapping, self._import_type)
            self.after(0, self._on_validate_done)
        except Exception as e:
            self.after(0, lambda: show_error("Validation Error", str(e)))

    def _on_validate_done(self):
        self._populate_preview()
        self._status_var.set(
            f"Validated {len(self._results)} rows. "
            f"Valid: {sum(1 for r in self._results if r.is_valid)}")
        self._next_btn.configure(state=tk.NORMAL)
        self._show_step(2)

    def _dry_run(self):
        summary = self._svc.dry_run_import(self._results, self._import_type)
        text = (f"DRY RUN — No data was written.\n\n"
                f"File: {self._file_path}\n"
                f"Type: {summary.import_type}\n"
                f"Total rows: {summary.total_rows}\n"
                f"Would import: {summary.imported}\n"
                f"Would skip/fail: {summary.skipped + summary.failed}\n\n"
                f"Review the Preview tab to fix unmatched or invalid rows.")
        self._show_result_text(text)
        self._show_step(3)

    def _commit(self):
        valid = sum(1 for r in self._results if r.is_valid)
        if not messagebox.askyesno("Confirm Import",
                                   f"Import {valid} valid rows?\n"
                                   f"({len(self._results) - valid} rows will be skipped)"):
            return
        uid = self.auth.current_user.id if self.auth.current_user else None
        self._import_btn.configure(state=tk.DISABLED)
        self._status_var.set("Importing…")

        def do():
            summary = self._svc.commit_import(
                self._results, self._import_type, uid,
                os.path.basename(self._file_path))
            self.after(0, lambda: self._on_commit_done(summary))

        threading.Thread(target=do, daemon=True).start()

    def _on_commit_done(self, summary):
        text = (f"IMPORT COMPLETE\n\n"
                f"File: {summary.file_name}\n"
                f"Type: {summary.import_type}\n"
                f"Total rows: {summary.total_rows}\n"
                f"✔ Imported: {summary.imported}\n"
                f"⚠ Skipped: {summary.skipped}\n"
                f"✗ Failed: {summary.failed}\n\n"
                f"Log saved to:\n{summary.log_path}")
        self._show_result_text(text)
        self._show_step(3)
        self._import_btn.configure(state=tk.NORMAL)
        self._status_var.set(f"Done. Imported {summary.imported} rows.")
