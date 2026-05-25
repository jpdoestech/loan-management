"""Import dialog – CSV / Excel bulk import with column mapping, preview,
fuzzy employee matching, and dry-run / commit.
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from src.data import db_manager as db
from src.gui.dialogs import show_error, show_info
from src.services import auth_service
from src.services.import_service import (
    ImportRowResult, ImportService,
    STATUS_MATCHED, STATUS_UNMATCHED, STATUS_ERROR, STATUS_VALID,
)
from src.utils.logger import get_logger

log = get_logger(__name__)

# Model fields available for mapping
LOAN_FIELDS = [
    "employee_name", "employee_code", "requested_amount", "interest_rate",
    "term_months", "purpose", "application_date", "reference_number",
    "status", "notes",
]
REPAYMENT_FIELDS = [
    "employee_name", "employee_code", "loan_reference", "loan_id",
    "payment_date", "amount", "payment_method", "reference", "notes",
]


class ImportView(tk.Toplevel):
    """Multi-step import wizard.

    Args:
        master:    Parent widget.
        threshold: Default fuzzy match threshold (configurable).
    """

    def __init__(self, master: tk.Misc, threshold: float = 89.0) -> None:
        super().__init__(master)
        self.title("Bulk Import – Cash Advances / Repayments")
        self.geometry("1050x700")
        self.grab_set()

        self._threshold = threshold
        self._file_path: Optional[str] = None
        self._file_columns: List[str] = []
        self._mapping: Dict[str, str] = {}  # file_col -> model_field
        self._results: List[ImportRowResult] = []
        self._import_type = tk.StringVar(value="loan")
        self._sheet_var = tk.StringVar()
        self._sheet_names: List[str] = []

        self._build_ui()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._nb = nb

        self._tab_file = ttk.Frame(nb, padding=10)
        self._tab_map = ttk.Frame(nb, padding=10)
        self._tab_preview = ttk.Frame(nb, padding=10)
        self._tab_review = ttk.Frame(nb, padding=10)

        nb.add(self._tab_file, text="1 · File")
        nb.add(self._tab_map, text="2 · Map Columns")
        nb.add(self._tab_preview, text="3 · Preview & Validate")
        nb.add(self._tab_review, text="4 · Review & Import")

        self._build_file_tab()
        self._build_map_tab()
        self._build_preview_tab()
        self._build_review_tab()

    # ── Tab 1: File selection ─────────────────────────────────────────────────

    def _build_file_tab(self) -> None:
        f = self._tab_file

        ttk.Label(f, text="Import Type:").grid(row=0, column=0, sticky=tk.W, pady=4)
        type_frame = ttk.Frame(f)
        type_frame.grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(type_frame, text="Cash Advance / Loan",
                        variable=self._import_type, value="loan").pack(side=tk.LEFT)
        ttk.Radiobutton(type_frame, text="Repayment / Payment",
                        variable=self._import_type, value="repayment").pack(side=tk.LEFT, padx=10)

        ttk.Label(f, text="File:").grid(row=1, column=0, sticky=tk.W, pady=4)
        file_frame = ttk.Frame(f)
        file_frame.grid(row=1, column=1, sticky=tk.EW)
        self._file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self._file_var, width=55, state="readonly").pack(side=tk.LEFT)
        ttk.Button(file_frame, text="Browse…", command=self._browse).pack(side=tk.LEFT, padx=4)

        ttk.Label(f, text="Sheet (XLSX):").grid(row=2, column=0, sticky=tk.W, pady=4)
        self._sheet_cb = ttk.Combobox(f, textvariable=self._sheet_var, state="readonly", width=30)
        self._sheet_cb.grid(row=2, column=1, sticky=tk.W)

        ttk.Label(f, text="Fuzzy Match Threshold (%):").grid(row=3, column=0, sticky=tk.W, pady=4)
        self._threshold_var = tk.DoubleVar(value=self._threshold)
        ttk.Spinbox(f, from_=50, to=100, increment=1,
                    textvariable=self._threshold_var, width=8).grid(row=3, column=1, sticky=tk.W)

        ttk.Button(f, text="Load File & Detect Columns →",
                   command=self._load_file).grid(row=4, column=1, sticky=tk.W, pady=10)
        f.columnconfigure(1, weight=1)

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("CSV / Excel", "*.csv *.xlsx *.xls"), ("All files", "*.*")]
        )
        if path:
            self._file_path = path
            self._file_var.set(path)
            # detect sheets for xlsx
            if path.lower().endswith((".xlsx", ".xls")):
                try:
                    names = ImportService.get_sheet_names(path)
                    self._sheet_names = names
                    self._sheet_cb["values"] = names
                    self._sheet_var.set(names[0] if names else "")
                except Exception:
                    pass

    def _load_file(self) -> None:
        if not self._file_path:
            show_error("No file", "Please select a file first.")
            return
        sheet_idx = 0
        if self._sheet_var.get() and self._sheet_names:
            try:
                sheet_idx = self._sheet_names.index(self._sheet_var.get())
            except ValueError:
                pass
        try:
            cols = ImportService.detect_columns(self._file_path, sheet_index=sheet_idx)
            self._file_columns = cols
            self._build_mapping_ui(cols)
            self._nb.select(1)
        except Exception as exc:
            show_error("Load Error", str(exc))

    # ── Tab 2: Column mapping ─────────────────────────────────────────────────

    def _build_map_tab(self) -> None:
        ttk.Label(self._tab_map,
                  text="Map each file column to a model field (or leave blank to ignore).").pack(anchor=tk.W)
        self._map_scroll = ttk.Frame(self._tab_map)
        self._map_scroll.pack(fill=tk.BOTH, expand=True)
        self._map_vars: Dict[str, tk.StringVar] = {}

        ttk.Button(self._tab_map, text="Validate & Preview →",
                   command=self._run_preview).pack(anchor=tk.E, pady=6)

    def _build_mapping_ui(self, file_cols: List[str]) -> None:
        for child in self._map_scroll.winfo_children():
            child.destroy()
        self._map_vars.clear()

        import_type = self._import_type.get()
        model_fields = [""] + (LOAN_FIELDS if import_type == "loan" else REPAYMENT_FIELDS)

        header = ttk.Frame(self._map_scroll)
        header.pack(fill=tk.X)
        ttk.Label(header, text="File Column", width=28, font=("", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text="→  Model Field", font=("", 9, "bold")).pack(side=tk.LEFT)

        canvas = tk.Canvas(self._map_scroll, height=350)
        scrollbar = ttk.Scrollbar(self._map_scroll, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for col in file_cols:
            row_frame = ttk.Frame(inner)
            row_frame.pack(fill=tk.X, pady=1)
            ttk.Label(row_frame, text=col, width=28, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar()
            # Auto-guess mapping
            normalized = col.lower().replace(" ", "_")
            all_fields = LOAN_FIELDS + REPAYMENT_FIELDS
            if normalized in all_fields:
                var.set(normalized)
            cb = ttk.Combobox(row_frame, textvariable=var, values=model_fields,
                              state="readonly", width=28)
            cb.pack(side=tk.LEFT, padx=4)
            self._map_vars[col] = var

    # ── Tab 3: Preview & Validate ─────────────────────────────────────────────

    def _build_preview_tab(self) -> None:
        toolbar = ttk.Frame(self._tab_preview)
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, text="Validation results – double-click a row to override employee.").pack(side=tk.LEFT)
        self._preview_count_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self._preview_count_var).pack(side=tk.RIGHT)

        cols = ("row", "status", "employee", "match_score", "errors", "warnings")
        self._preview_tree = ttk.Treeview(self._tab_preview, columns=cols, show="headings", height=18)
        widths = {"row": 40, "status": 90, "employee": 170, "match_score": 85, "errors": 260, "warnings": 260}
        labels = {"row": "#", "status": "Status", "employee": "Matched Employee",
                  "match_score": "Score %", "errors": "Errors", "warnings": "Warnings"}
        for c in cols:
            self._preview_tree.heading(c, text=labels[c])
            self._preview_tree.column(c, width=widths[c], anchor=tk.W)
        sy = ttk.Scrollbar(self._tab_preview, orient=tk.VERTICAL, command=self._preview_tree.yview)
        self._preview_tree.configure(yscrollcommand=sy.set)
        self._preview_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)
        self._preview_tree.bind("<Double-1>", self._override_employee)

        # Row colour tags
        self._preview_tree.tag_configure(STATUS_VALID, background="#d4edda")
        self._preview_tree.tag_configure(STATUS_MATCHED, background="#d4edda")
        self._preview_tree.tag_configure(STATUS_WARNING, background="#fff3cd")
        self._preview_tree.tag_configure(STATUS_UNMATCHED, background="#fff3cd")
        self._preview_tree.tag_configure(STATUS_ERROR, background="#f8d7da")

        btn_bar = ttk.Frame(self._tab_preview)
        btn_bar.pack(fill=tk.X, pady=4)
        ttk.Button(btn_bar, text="← Back", command=lambda: self._nb.select(1)).pack(side=tk.LEFT)
        ttk.Button(btn_bar, text="Proceed to Review →", command=lambda: self._nb.select(3)).pack(side=tk.RIGHT)


    def _run_preview(self) -> None:
        if not self._file_path:
            return
        mapping = {col: var.get() for col, var in self._map_vars.items() if var.get()}
        self._mapping = mapping
        self._threshold = self._threshold_var.get()

        self._preview_count_var.set("⏳ Processing…")
        import_type = self._import_type.get()
        sheet_idx = 0
        if self._sheet_var.get() and self._sheet_names:
            try:
                sheet_idx = self._sheet_names.index(self._sheet_var.get())
            except ValueError:
                pass

        def _work() -> None:
            try:
                svc = ImportService(
                    user_id=getattr(auth_service.get_current_user(), "id", None),
                    threshold=self._threshold,
                )
                raw = svc.parse_file(
                    self._file_path, import_type=import_type,
                    column_mapping=mapping, sheet_index=sheet_idx,
                )
                results = svc.validate_and_match(raw, import_type=import_type)
                self.after(0, lambda: self._show_preview(results))
            except Exception as exc:
                self.after(0, lambda: show_error("Parse Error", str(exc)))

        threading.Thread(target=_work, daemon=True).start()
        self._nb.select(2)

    def _show_preview(self, results: List[ImportRowResult]) -> None:
        self._results = results
        self._preview_tree.delete(*self._preview_tree.get_children())
        ok = sum(1 for r in results if r.status in (STATUS_VALID, STATUS_MATCHED))
        errors = sum(1 for r in results if r.status == STATUS_ERROR)
        unmatched = sum(1 for r in results if r.status == STATUS_UNMATCHED)
        self._preview_count_var.set(
            f"{len(results)} rows  ✅{ok}  ❌{errors}  ⚠️{unmatched} unmatched")

        for res in results:
            best = res.employee_matches[0] if res.employee_matches else None
            emp_name = best.name if best else "—"
            score = f"{best.score:.1f}%" if best else "—"
            self._preview_tree.insert(
                "", tk.END, iid=str(res.row_number),
                values=(
                    res.row_number, res.status, emp_name, score,
                    "; ".join(res.errors), "; ".join(res.warnings),
                ),
                tags=(res.status,),
            )

    def _override_employee(self, _event: Any) -> None:
        """Let user manually pick an employee for the selected row."""
        sel = self._preview_tree.selection()
        if not sel:
            return
        row_num = int(sel[0])
        result = next((r for r in self._results if r.row_number == row_num), None)
        if not result:
            return
        dlg = _EmployeePickerDialog(self)
        emp = dlg.selected
        if emp:
            result.selected_employee_id = emp["id"]
            result.status = STATUS_MATCHED
            # Update tree display
            self._preview_tree.item(
                str(row_num),
                values=(
                    row_num, STATUS_MATCHED,
                    f"{emp['name']} (manual)", "100.0%",
                    "; ".join(result.errors), "; ".join(result.warnings),
                ),
                tags=(STATUS_MATCHED,),
            )

    # ── Tab 4: Review & Import ────────────────────────────────────────────────

    def _build_review_tab(self) -> None:
        f = self._tab_review
        ttk.Label(f, text="Review summary before importing.", font=("", 10, "bold")).pack(anchor=tk.W)

        self._summary_text = tk.Text(f, height=8, state=tk.DISABLED, font=("Consolas", 9))
        self._summary_text.pack(fill=tk.X, pady=6)

        opts = ttk.LabelFrame(f, text="Import Options", padding=8)
        opts.pack(fill=tk.X, pady=4)
        self._dry_run_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Dry-run only (preview without writing to database)",
                        variable=self._dry_run_var).pack(anchor=tk.W)

        self._progress = ttk.Progressbar(f, mode="indeterminate")
        self._progress.pack(fill=tk.X, pady=4)

        self._result_text = tk.Text(f, height=10, state=tk.DISABLED, font=("Consolas", 9))
        self._result_text.pack(fill=tk.BOTH, expand=True)

        btn = ttk.Frame(f)
        btn.pack(fill=tk.X)
        ttk.Button(btn, text="← Back", command=lambda: self._nb.select(2)).pack(side=tk.LEFT)
        self._import_btn = ttk.Button(btn, text="▶ Run Import", command=self._run_import)
        self._import_btn.pack(side=tk.RIGHT)

        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, _event: Any) -> None:
        if self._nb.index(self._nb.select()) == 3:
            self._refresh_summary()

    def _refresh_summary(self) -> None:
        if not self._results:
            return
        total = len(self._results)
        ok = sum(1 for r in self._results if r.status in (STATUS_VALID, STATUS_MATCHED))
        errors = sum(1 for r in self._results if r.status == STATUS_ERROR)
        unmatched = sum(1 for r in self._results if r.status == STATUS_UNMATCHED)
        lines = [
            f"File:      {self._file_path}",
            f"Type:      {self._import_type.get()}",
            f"Threshold: {self._threshold}%",
            "",
            f"Total rows:  {total}",
            f"  ✅ Ready:     {ok}",
            f"  ❌ Errors:    {errors}  (will be skipped)",
            f"  ⚠️  Unmatched: {unmatched}  (will be skipped unless manually resolved)",
            "",
            "Dry-run is ON by default – uncheck to commit." if self._dry_run_var.get()
            else "⚠️  DRY-RUN IS OFF – data WILL be written to the database.",
        ]
        self._summary_text.configure(state=tk.NORMAL)
        self._summary_text.delete("1.0", tk.END)
        self._summary_text.insert(tk.END, "\n".join(lines))
        self._summary_text.configure(state=tk.DISABLED)

    def _run_import(self) -> None:
        if not self._results:
            show_error("No data", "Please complete steps 1-3 first.")
            return
        dry_run = self._dry_run_var.get()
        self._import_btn.configure(state=tk.DISABLED)
        self._progress.start()

        import_type = self._import_type.get()
        file_name = Path(self._file_path or "unknown").name

        def _work() -> None:
            try:
                svc = ImportService(
                    user_id=getattr(auth_service.get_current_user(), "id", None),
                    threshold=self._threshold,
                )
                summary = svc.commit_import(
                    self._results, import_type=import_type,
                    dry_run=dry_run, file_name=file_name,
                )
                self.after(0, lambda: self._show_result(summary))
            except Exception as exc:
                self.after(0, lambda: show_error("Import Error", str(exc)))
            finally:
                self.after(0, lambda: (self._progress.stop(),
                                       self._import_btn.configure(state=tk.NORMAL)))

        threading.Thread(target=_work, daemon=True).start()

    def _show_result(self, summary: Dict) -> None:
        lines = [
            f"{'=== DRY RUN ===' if summary.get('dry_run') else '=== COMMITTED ==='}",
            f"Type:      {summary.get('import_type')}",
            f"File:      {summary.get('file_name')}",
            f"Timestamp: {summary.get('timestamp')}",
            "",
            f"Total rows:  {summary.get('total')}",
            f"Committed:   {summary.get('committed')}",
            f"Skipped:     {summary.get('skipped')}",
            f"Failed:      {summary.get('failed')}",
            "",
            f"Log file: {summary.get('log_path')}",
        ]
        self._result_text.configure(state=tk.NORMAL)
        self._result_text.delete("1.0", tk.END)
        self._result_text.insert(tk.END, "\n".join(lines))
        self._result_text.configure(state=tk.DISABLED)
        if not summary.get("dry_run"):
            show_info("Import Complete",
                      f"Imported {summary.get('committed')} rows.\n"
                      f"Log saved to:\n{summary.get('log_path')}")


class _EmployeePickerDialog(tk.Toplevel):
    """Search and select an employee manually."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("Pick Employee")
        self.grab_set()
        self.geometry("420x380")
        self.selected: Optional[Dict] = None
        self._all: List[Dict] = db.get_all_employees()

        ttk.Label(self, text="Type to search:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        ttk.Entry(self, textvariable=self._search_var, width=45).pack(padx=10, pady=4)

        self._lb = tk.Listbox(self, height=14)
        self._lb.pack(fill=tk.BOTH, expand=True, padx=10)
        self._lb.bind("<Double-1>", self._select)

        ttk.Button(self, text="Select", command=self._select).pack(pady=6)
        self._filter()
        self.wait_window(self)

    def _filter(self) -> None:
        q = self._search_var.get().lower()
        self._lb.delete(0, tk.END)
        self._filtered: List[Dict] = []
        for emp in self._all:
            text = f"{emp.get('name','')} {emp.get('employee_code','') or ''}".lower()
            if q in text:
                self._lb.insert(tk.END, f"[{emp.get('employee_code','') or '—'}] {emp['name']}")
                self._filtered.append(emp)

    def _select(self, _event: Any = None) -> None:
        sel = self._lb.curselection()
        if sel:
            self.selected = self._filtered[sel[0]]
        self.destroy()
