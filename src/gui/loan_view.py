"""Loan management view — list, create, approve, disburse, record payments."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional
from ..data.db_manager import DBManager
from ..services.auth_service import AuthService
from ..services.loan_service import LoanService
from .dialogs import FormDialog, show_error, show_info, ask_confirm, SearchableListDialog


class LoanView(ttk.Frame):
    """Full loan lifecycle view."""

    def __init__(self, parent: tk.Widget, db: DBManager, auth: AuthService) -> None:
        super().__init__(parent)
        self.db = db
        self.auth = auth
        self.loan_svc = LoanService(db)
        self._build()
        self.refresh()

    def _build(self) -> None:
        # Toolbar
        tb = ttk.Frame(self)
        tb.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(tb, text="Cash Advances / Loans", font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        ttk.Button(tb, text="＋ New", command=self._new_loan).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="✔ Approve", command=self._approve).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="💸 Disburse", command=self._disburse).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="✗ Reject", command=self._reject).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="💳 Payment", command=self._payment).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="↺", command=self.refresh).pack(side=tk.RIGHT, padx=2)

        # Filters
        ff = ttk.Frame(self)
        ff.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Label(ff, text="Status:").pack(side=tk.LEFT)
        self._status_var = tk.StringVar(value="All")
        cb = ttk.Combobox(ff, textvariable=self._status_var, width=12, state="readonly",
                          values=["All", "pending", "approved", "active", "closed", "rejected"])
        cb.pack(side=tk.LEFT, padx=(4, 12))
        cb.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        ttk.Label(ff, text="Search:").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        ttk.Entry(ff, textvariable=self._search_var, width=28).pack(side=tk.LEFT, padx=4)

        # Main pane — top: loans list; bottom: repayments for selected
        pane = ttk.PanedWindow(self, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Loans treeview
        loan_frame = ttk.LabelFrame(pane, text="Loans")
        pane.add(loan_frame, weight=3)
        cols = ("ID", "Reference", "Employee", "Amount", "Approved", "Rate%",
                "Term", "Status", "Applied", "Due", "Balance")
        self._tree = ttk.Treeview(loan_frame, columns=cols, show="headings", selectmode="browse")
        widths = (40, 130, 160, 90, 90, 50, 50, 80, 90, 90, 90)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col, command=lambda c=col: self._sort(c))
            self._tree.column(col, width=w,
                              anchor=tk.CENTER if col in ("ID","Rate%","Term","Status") else tk.W)
        vsb = ttk.Scrollbar(loan_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # Tag colours
        self._tree.tag_configure("pending", foreground="#F39C12")
        self._tree.tag_configure("approved", foreground="#27AE60")
        self._tree.tag_configure("active", foreground="#2980B9")
        self._tree.tag_configure("closed", foreground="#7F8C8D")
        self._tree.tag_configure("rejected", foreground="#E74C3C")

        # Repayments treeview
        rep_frame = ttk.LabelFrame(pane, text="Repayments for Selected Loan")
        pane.add(rep_frame, weight=1)
        rcols = ("Date", "Amount", "Method", "Reference", "Notes")
        self._rep_tree = ttk.Treeview(rep_frame, columns=rcols, show="headings")
        for c in rcols:
            self._rep_tree.heading(c, text=c)
            self._rep_tree.column(c, width=120)
        self._rep_tree.pack(fill=tk.BOTH, expand=True)

        self._all_rows: list = []
        self._sort_col: str = "ID"
        self._sort_rev: bool = True

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        status = self._status_var.get()
        self._all_rows = self.db.list_loans(
            status=status if status != "All" else None
        )
        self._filter()

    def _filter(self) -> None:
        q = self._search_var.get().lower()
        self._tree.delete(*self._tree.get_children())
        for r in self._all_rows:
            text = f"{r.get('reference_number','')} {r.get('employee_name','')}".lower()
            if q and q not in text:
                continue
            bal = r.get("outstanding_balance")
            self._tree.insert("", tk.END, iid=str(r["id"]),
                              tags=(r.get("status", "pending"),),
                              values=(
                                  r["id"], r.get("reference_number",""),
                                  r.get("employee_name",""),
                                  f"{r.get('requested_amount',0):,.2f}",
                                  f"{r.get('approved_amount',0) or 0:,.2f}",
                                  r.get("interest_rate", 0),
                                  r.get("term_months", 1),
                                  r.get("status",""), r.get("application_date",""),
                                  r.get("due_date",""),
                                  f"{bal:,.2f}" if bal is not None else "",
                              ))

    def _sort(self, col: str) -> None:
        self._sort_rev = not self._sort_rev if self._sort_col == col else False
        self._sort_col = col

    def _on_select(self, _event=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        loan_id = int(sel[0])
        self._rep_tree.delete(*self._rep_tree.get_children())
        for r in self.db.list_repayments(loan_id):
            self._rep_tree.insert("", tk.END, values=(
                r.get("payment_date",""), f"{r.get('amount',0):,.2f}",
                r.get("payment_method",""), r.get("reference",""), r.get("notes",""),
            ))

    def _selected_loan_id(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    # ------------------------------------------------------------------ #
    def _new_loan(self) -> None:
        employees = self.db.list_employees()
        emp_map = {f"{e['name']} ({e.get('employee_code','')})": e["id"] for e in employees}
        branches = self.db.list_branches()
        branch_map = {b["name"]: b["id"] for b in branches}

        fields = [
            {"key": "employee", "label": "Employee", "type": "combobox",
             "values": list(emp_map.keys())},
            {"key": "requested_amount", "label": "Amount Requested"},
            {"key": "interest_rate", "label": "Interest Rate (%)", "default": "0"},
            {"key": "term_months", "label": "Term (months)", "default": "1"},
            {"key": "purpose", "label": "Purpose"},
            {"key": "branch", "label": "Branch", "type": "combobox",
             "values": [""] + list(branch_map.keys())},
        ]

        def save(data: dict) -> None:
            emp_id = emp_map.get(data.get("employee",""))
            if not emp_id:
                show_error("Validation", "Please select an employee.")
                return
            try:
                amount = float(data.get("requested_amount", 0))
                rate = float(data.get("interest_rate", 0))
                term = int(data.get("term_months", 1))
            except ValueError:
                show_error("Validation", "Amount, rate, and term must be numbers.")
                return
            bid = branch_map.get(data.get("branch",""))
            uid = self.auth.current_user.id if self.auth.current_user else None
            ok, msg, _ = self.loan_svc.create_loan(
                emp_id, amount, rate, term, data.get("purpose"), bid, uid)
            if ok:
                self.refresh()
                dlg.destroy()
                show_info("Success", msg)
            else:
                show_error("Error", msg)

        dlg = FormDialog(self, "New Cash Advance", fields, save)

    def _approve(self) -> None:
        lid = self._selected_loan_id()
        if not lid:
            show_error("Select", "Select a loan first.")
            return
        loan = self.loan_svc.get_loan(lid)
        if not loan or loan.status != "pending":
            show_error("Invalid", "Only pending loans can be approved.")
            return

        fields = [{"key": "approved_amount", "label": "Approved Amount",
                   "default": str(loan.requested_amount)}]

        def save(data: dict) -> None:
            try:
                amt = float(data["approved_amount"])
            except ValueError:
                show_error("Validation", "Enter a valid amount.")
                return
            uid = self.auth.current_user.id if self.auth.current_user else None
            ok, msg = self.loan_svc.approve_loan(lid, amt, uid)
            if ok:
                self.refresh()
                dlg.destroy()
                show_info("Approved", msg)
            else:
                show_error("Error", msg)

        dlg = FormDialog(self, "Approve Loan", fields, save)

    def _disburse(self) -> None:
        lid = self._selected_loan_id()
        if not lid:
            show_error("Select", "Select a loan first.")
            return
        if not ask_confirm("Disburse", "Mark this loan as disbursed / active?"):
            return
        uid = self.auth.current_user.id if self.auth.current_user else None
        ok, msg = self.loan_svc.disburse_loan(lid, uid)
        if ok:
            self.refresh()
            show_info("Disbursed", msg)
        else:
            show_error("Error", msg)

    def _reject(self) -> None:
        lid = self._selected_loan_id()
        if not lid:
            show_error("Select", "Select a loan first.")
            return
        if not ask_confirm("Reject", "Reject this loan application?"):
            return
        uid = self.auth.current_user.id if self.auth.current_user else None
        ok, msg = self.loan_svc.reject_loan(lid, uid)
        if ok:
            self.refresh()
            show_info("Rejected", msg)
        else:
            show_error("Error", msg)

    def _payment(self) -> None:
        lid = self._selected_loan_id()
        if not lid:
            show_error("Select", "Select a loan first.")
            return
        loan = self.loan_svc.get_loan(lid)
        if not loan or loan.status not in ("active", "approved"):
            show_error("Invalid", "Loan must be active or approved to record a payment.")
            return

        from datetime import date
        fields = [
            {"key": "amount", "label": "Amount"},
            {"key": "payment_date", "label": "Payment Date",
             "default": date.today().isoformat()},
            {"key": "payment_method", "label": "Method", "type": "combobox",
             "values": ["cash", "bank_transfer", "check", "salary_deduction", "other"],
             "default": "cash"},
            {"key": "reference", "label": "Reference / Receipt"},
            {"key": "notes", "label": "Notes"},
        ]

        def save(data: dict) -> None:
            try:
                amt = float(data["amount"])
            except ValueError:
                show_error("Validation", "Enter a valid amount.")
                return
            uid = self.auth.current_user.id if self.auth.current_user else None
            ok, msg = self.loan_svc.record_repayment(
                lid, amt, data["payment_date"], data["payment_method"],
                data.get("reference") or None, data.get("notes") or None, uid,
            )
            if ok:
                self.refresh()
                dlg.destroy()
                show_info("Recorded", msg)
            else:
                show_error("Error", msg)

        dlg = FormDialog(self, f"Record Payment — {loan.reference_number}", fields, save)
