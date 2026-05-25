"""Loan management view with approve/reject and repayment actions."""
from __future__ import annotations

import threading
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from src.data import db_manager as db
from src.gui.dialogs import FormDialog, show_error, show_info, ask_yes_no
from src.services import auth_service, loan_service
from src.utils.helpers import format_currency
from src.utils.logger import get_logger

log = get_logger(__name__)

_COLS = [
    ("id", "ID", 40), ("reference_number", "Reference", 130),
    ("employee_name", "Employee", 160), ("requested_amount", "Requested", 95),
    ("approved_amount", "Approved", 90), ("interest_rate", "Rate%", 60),
    ("term_months", "Term", 50), ("status", "Status", 80),
    ("application_date", "App Date", 95),
]

_STATUS_COLORS = {
    "pending": "#f0ad4e",
    "active": "#5cb85c",
    "completed": "#337ab7",
    "rejected": "#d9534f",
    "cancelled": "#777",
}


class LoanView(ttk.Frame):
    """Loan list, detail, and action view.

    Args:
        master: Parent widget.
    """

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._rows: List[Dict] = []
        self._build_ui()
        self.refresh()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Top toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(toolbar, text="Status:").pack(side=tk.LEFT)
        self._status_var = tk.StringVar(value="all")
        status_cb = ttk.Combobox(
            toolbar, textvariable=self._status_var, width=12, state="readonly",
            values=["all", "pending", "active", "completed", "rejected", "cancelled"],
        )
        status_cb.pack(side=tk.LEFT, padx=4)
        status_cb.bind("<<ComboboxSelected>>", lambda _: self.refresh())

        ttk.Label(toolbar, text="Search:").pack(side=tk.LEFT, padx=(8, 0))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        ttk.Entry(toolbar, textvariable=self._search_var, width=22).pack(side=tk.LEFT, padx=4)

        ttk.Button(toolbar, text="➕ New Loan", command=self._new_loan).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="✅ Approve", command=self._approve).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="❌ Reject", command=self._reject).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💵 Repayment", command=self._add_repayment).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🔄 Refresh", command=self.refresh).pack(side=tk.LEFT, padx=2)

        # Main paned area: tree on left, detail on right
        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True)

        # Tree
        tree_frame = ttk.Frame(pane)
        pane.add(tree_frame, weight=3)

        cols = [c[0] for c in _COLS]
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for cid, label, width in _COLS:
            self._tree.heading(cid, text=label)
            self._tree.column(cid, width=width, anchor=tk.W)
        sy = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sy.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # Detail panel
        detail_frame = ttk.LabelFrame(pane, text="Loan Detail", padding=10)
        pane.add(detail_frame, weight=1)
        self._detail_text = tk.Text(detail_frame, state=tk.DISABLED, wrap=tk.WORD,
                                    width=32, font=("Consolas", 9))
        self._detail_text.pack(fill=tk.BOTH, expand=True)

        # Status-colour tags
        for status, color in _STATUS_COLORS.items():
            self._tree.tag_configure(status, background=color + "33")  # 20% alpha hex

    def refresh(self) -> None:
        """Reload loans from DB in a background thread."""
        status = self._status_var.get()

        def _load() -> None:
            rows = db.get_all_loans(status=None if status == "all" else status)
            self.after(0, lambda: self._populate(rows))

        threading.Thread(target=_load, daemon=True).start()

    def _populate(self, rows: List[Dict]) -> None:
        self._rows = rows
        self._filter()

    def _filter(self) -> None:
        q = self._search_var.get().lower()
        self._tree.delete(*self._tree.get_children())
        for row in self._rows:
            text = f"{row.get('reference_number','')} {row.get('employee_name','')}".lower()
            if q and q not in text:
                continue
            status = row.get("status", "")
            values = []
            for cid, *_ in _COLS:
                val = row.get(cid, "") or ""
                if cid in ("requested_amount", "approved_amount") and val:
                    val = format_currency(float(val))
                values.append(val)
            self._tree.insert("", tk.END, iid=str(row["id"]), values=values, tags=(status,))

    def _selected_id(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _on_select(self, _event: Any) -> None:
        loan_id = self._selected_id()
        if not loan_id:
            return
        threading.Thread(target=self._load_detail, args=(loan_id,), daemon=True).start()

    def _load_detail(self, loan_id: int) -> None:
        summary = loan_service.get_loan_summary(loan_id)
        self.after(0, lambda: self._show_detail(summary))

    def _show_detail(self, summary: Dict) -> None:
        loan = summary.get("loan", {})
        lines = [
            f"Ref:      {loan.get('reference_number','')}",
            f"Employee: {loan.get('employee_name','')}",
            f"Requested:{format_currency(loan.get('requested_amount') or 0)}",
            f"Approved: {format_currency(loan.get('approved_amount') or 0)}",
            f"Rate:     {loan.get('interest_rate',0)}% / month",
            f"Term:     {loan.get('term_months','')} months",
            f"Payable:  {format_currency(summary.get('total_payable',0))}",
            f"Paid:     {format_currency(summary.get('total_paid',0))}",
            f"Balance:  {format_currency(summary.get('balance',0))}",
            f"Status:   {loan.get('status','')}",
            "",
            "── Repayments ──────────────────",
        ]
        for r in summary.get("repayments", []):
            lines.append(f"  {r.get('payment_date','')}  {format_currency(r.get('amount',0))}"
                         f"  [{r.get('payment_method','')}]")
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.insert(tk.END, "\n".join(lines))
        self._detail_text.configure(state=tk.DISABLED)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _new_loan(self) -> None:
        dlg = _LoanDialog(self, title="New Cash Advance Application")
        data = dlg.get_data()
        if data:
            try:
                loan_service.apply_loan(
                    employee_id=int(data["employee_id"]),
                    requested_amount=float(data.get("requested_amount") or 0),
                    term_months=int(data.get("term_months") or 1),
                    interest_rate=float(data.get("interest_rate") or 0),
                    purpose=data.get("purpose"),
                    notes=data.get("notes"),
                )
                self.refresh()
                show_info("Created", "Loan application submitted.")
            except Exception as exc:
                show_error("Error", str(exc))

    def _approve(self) -> None:
        loan_id = self._selected_id()
        if not loan_id:
            show_info("Select", "Select a loan to approve.")
            return
        loan = db.get_loan_by_id(loan_id)
        if loan and loan["status"] != "pending":
            show_error("Status", f"Cannot approve a loan with status '{loan['status']}'.")
            return
        dlg = _ApproveDialog(self)
        data = dlg.get_data()
        if data:
            try:
                loan_service.approve_loan(
                    loan_id,
                    approved_amount=float(data.get("approved_amount") or 0),
                    approval_date=data.get("approval_date"),
                    first_payment_date=data.get("first_payment_date"),
                )
                self.refresh()
                show_info("Approved", "Loan approved and set to active.")
            except Exception as exc:
                show_error("Error", str(exc))

    def _reject(self) -> None:
        loan_id = self._selected_id()
        if not loan_id:
            show_info("Select", "Select a loan to reject.")
            return
        if ask_yes_no("Confirm", "Reject this loan application?"):
            try:
                loan_service.reject_loan(loan_id)
                self.refresh()
            except Exception as exc:
                show_error("Error", str(exc))

    def _add_repayment(self) -> None:
        loan_id = self._selected_id()
        if not loan_id:
            show_info("Select", "Select a loan to record repayment.")
            return
        dlg = _RepaymentDialog(self, loan_id=loan_id)
        data = dlg.get_data()
        if data:
            try:
                loan_service.record_repayment(
                    loan_id=loan_id,
                    amount=float(data.get("amount") or 0),
                    payment_date=data.get("payment_date") or date.today().isoformat(),
                    payment_method=data.get("payment_method", "cash"),
                    reference=data.get("reference"),
                    notes=data.get("notes"),
                )
                self.refresh()
                show_info("Recorded", "Repayment recorded successfully.")
            except Exception as exc:
                show_error("Error", str(exc))


# ── Inner dialogs ─────────────────────────────────────────────────────────────

class _LoanDialog(FormDialog):
    def _build_form(self, frame: ttk.Frame) -> None:
        employees = db.get_all_employees()
        emp_opts = [f"{e['id']}:{e['name']} [{e.get('employee_code','') or ''}]" for e in employees]
        fields = [
            ("Employee *", "employee_id_str", ttk.Combobox, emp_opts, ""),
            ("Requested Amount *", "requested_amount", ttk.Entry, None, ""),
            ("Interest Rate (%)", "interest_rate", ttk.Entry, None, "0"),
            ("Term (months)", "term_months", ttk.Entry, None, "1"),
            ("Purpose", "purpose", ttk.Entry, None, ""),
            ("Application Date", "application_date", ttk.Entry, None, date.today().isoformat()),
            ("Notes", "notes", ttk.Entry, None, ""),
        ]
        for i, (label, key, wtype, opts, default) in enumerate(fields):
            self._add_field(frame, label, key, row=i, widget_type=wtype,
                            options=opts, default=default)

    def _on_save(self) -> None:
        data = {k: v.get() for k, v in self._vars.items()}
        emp_str = data.pop("employee_id_str", "")
        if not emp_str:
            show_error("Validation", "Please select an employee.")
            return
        data["employee_id"] = emp_str.split(":")[0]
        self._result = data
        self.destroy()


class _ApproveDialog(FormDialog):
    def _build_form(self, frame: ttk.Frame) -> None:
        self._add_field(frame, "Approved Amount *", "approved_amount", row=0)
        self._add_field(frame, "Approval Date", "approval_date", row=1,
                        default=date.today().isoformat())
        self._add_field(frame, "First Payment Date", "first_payment_date", row=2)


class _RepaymentDialog(FormDialog):
    def __init__(self, master: tk.Misc, loan_id: int) -> None:
        self._loan_id = loan_id
        super().__init__(master, title="Record Repayment")

    def _build_form(self, frame: ttk.Frame) -> None:
        self._add_field(frame, "Amount *", "amount", row=0)
        self._add_field(frame, "Payment Date", "payment_date", row=1,
                        default=date.today().isoformat())
        self._add_field(frame, "Method", "payment_method", row=2,
                        widget_type=ttk.Combobox,
                        options=["cash", "bank", "deduction"])
        self._add_field(frame, "Reference", "reference", row=3)
        self._add_field(frame, "Notes", "notes", row=4)
