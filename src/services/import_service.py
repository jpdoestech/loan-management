"""Import service — CSV/XLSX parsing, validation, fuzzy matching, commit/dry-run."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..data.db_manager import DBManager
from ..models.employee import Employee
from ..models.loan import Loan
from ..utils.fuzzy_match import FuzzyMatcher
from ..utils.helpers import generate_reference, get_app_data_dir, ensure_dir
from ..utils.logger import get_logger
from ..utils.validators import (
    parse_amount, parse_date, parse_positive_int, parse_rate, validate_required,
)

log = get_logger()

try:
    import openpyxl
    _OPENPYXL = True
except ImportError:
    _OPENPYXL = False


# ------------------------------------------------------------------ #
# Result types
# ------------------------------------------------------------------ #

@dataclass
class MatchSuggestion:
    """A fuzzy match candidate for an employee name."""
    employee_id: int
    employee_name: str
    employee_code: Optional[str]
    score: float


@dataclass
class ImportRowResult:
    """Validation and matching result for a single import row."""
    row_index: int
    raw_data: Dict[str, Any]
    normalized: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # Employee matching
    employee_id: Optional[int] = None
    employee_name_raw: str = ""
    match_suggestions: List[MatchSuggestion] = field(default_factory=list)
    auto_matched: bool = False
    # Outcome
    status: str = "pending"   # pending | valid | invalid | skipped | imported

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.employee_id is not None


@dataclass
class ImportSummary:
    """Aggregate result from an import run."""
    file_name: str
    import_type: str
    total_rows: int
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: bool = True
    log_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ------------------------------------------------------------------ #
# ImportService
# ------------------------------------------------------------------ #

class ImportService:
    """Parses, validates, and commits bulk loan/repayment imports."""

    LOAN_FIELDS = {
        "employee_name": ["employee_name", "employee", "name", "emp_name"],
        "employee_code": ["employee_code", "emp_code", "code"],
        "requested_amount": ["requested_amount", "amount", "loan_amount", "principal"],
        "interest_rate": ["interest_rate", "rate", "interest"],
        "term_months": ["term_months", "term", "months", "duration"],
        "purpose": ["purpose", "description", "reason"],
        "application_date": ["application_date", "date", "loan_date", "applied_date"],
    }

    REPAYMENT_FIELDS = {
        "employee_name": ["employee_name", "employee", "name", "emp_name"],
        "loan_reference": ["loan_reference", "reference", "ref", "loan_ref", "reference_number"],
        "amount": ["amount", "payment_amount", "paid_amount"],
        "payment_date": ["payment_date", "date", "paid_date"],
        "payment_method": ["payment_method", "method", "mode"],
        "reference": ["reference", "receipt", "receipt_no"],
        "notes": ["notes", "remarks", "note"],
    }

    def __init__(self, db: DBManager, fuzzy_threshold: float = 89.0) -> None:
        self.db = db
        self.threshold = fuzzy_threshold
        self.matcher = FuzzyMatcher(threshold=fuzzy_threshold)
        self._employees: List[Dict] = []

    # ------------------------------------------------------------------ #
    # File parsing
    # ------------------------------------------------------------------ #

    def parse_file(self, file_path: str, sheet_index: int = 0) -> Tuple[List[str], List[Dict]]:
        """Parse a CSV or XLSX file.

        Returns:
            (headers, rows) where rows are dicts keyed by header.
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            return self._parse_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            return self._parse_excel(file_path, sheet_index)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def _parse_csv(self, path: str) -> Tuple[List[str], List[Dict]]:
        rows: List[Dict] = []
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            # Sniff delimiter
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            headers = reader.fieldnames or []
            for row in reader:
                rows.append(dict(row))
        return list(headers), rows

    def _parse_excel(self, path: str, sheet_index: int = 0) -> Tuple[List[str], List[Dict]]:
        if not _OPENPYXL:
            raise ImportError("openpyxl is required for Excel import. Install it with: pip install openpyxl")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[sheet_index]
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h or "").strip() for h in next(rows_iter, [])]
        rows = []
        for raw_row in rows_iter:
            if all(v is None for v in raw_row):
                continue
            rows.append(dict(zip(headers, [v for v in raw_row])))
        wb.close()
        return headers, rows

    # ------------------------------------------------------------------ #
    # Column auto-mapping
    # ------------------------------------------------------------------ #

    def auto_map_columns(self, headers: List[str],
                         import_type: str = "loan") -> Dict[str, Optional[str]]:
        """Return {model_field: file_column | None} auto-detected mapping."""
        field_map = self.LOAN_FIELDS if import_type == "loan" else self.REPAYMENT_FIELDS
        headers_lower = [h.lower().strip() for h in headers]
        mapping: Dict[str, Optional[str]] = {}
        for model_field, aliases in field_map.items():
            found = None
            for alias in aliases:
                try:
                    idx = headers_lower.index(alias.lower())
                    found = headers[idx]
                    break
                except ValueError:
                    continue
            mapping[model_field] = found
        return mapping

    # ------------------------------------------------------------------ #
    # Employee lookup & fuzzy matching
    # ------------------------------------------------------------------ #

    def _load_employees(self) -> None:
        self._employees = self.db.list_employees(active_only=False)

    def _employee_candidates(self) -> List[str]:
        """Build candidate strings = 'name (code)' or 'name'."""
        out = []
        for e in self._employees:
            name = e.get("name", "")
            code = e.get("employee_code") or ""
            out.append(name)
        return out

    def match_employee(self, name_raw: str) -> List[MatchSuggestion]:
        """Return top-3 fuzzy matches for *name_raw* from the employee table."""
        if not self._employees:
            self._load_employees()
        candidates = self._employee_candidates()
        results = self.matcher.match(name_raw, candidates, top_n=3)
        suggestions = []
        for cand_str, score, idx in results:
            emp = self._employees[idx]
            suggestions.append(MatchSuggestion(
                employee_id=emp["id"],
                employee_name=emp["name"],
                employee_code=emp.get("employee_code"),
                score=round(score, 1),
            ))
        return suggestions

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    def validate_loan_row(self, row: Dict, mapping: Dict[str, Optional[str]],
                          row_index: int) -> ImportRowResult:
        result = ImportRowResult(row_index=row_index, raw_data=row)
        norm = {}

        def get(field: str) -> Any:
            col = mapping.get(field)
            return row.get(col) if col else None

        # Employee name (required)
        emp_name = str(get("employee_name") or "").strip()
        result.employee_name_raw = emp_name
        err = validate_required(emp_name, "employee_name")
        if err:
            result.errors.append(err)
        else:
            # Try employee_code first
            emp_code = str(get("employee_code") or "").strip()
            if emp_code:
                emp_row = self.db.fetch_one(
                    "SELECT * FROM employees WHERE employee_code=?", (emp_code,)
                )
                if emp_row:
                    result.employee_id = emp_row["id"]
                    result.auto_matched = True
                    norm["employee_id"] = emp_row["id"]
            if not result.employee_id:
                suggestions = self.match_employee(emp_name)
                result.match_suggestions = suggestions
                if suggestions and suggestions[0].score >= self.threshold:
                    result.employee_id = suggestions[0].employee_id
                    result.auto_matched = True
                    norm["employee_id"] = result.employee_id

        # requested_amount
        amt, err = parse_amount(get("requested_amount"))
        if err:
            result.errors.append(err)
        else:
            norm["requested_amount"] = amt

        # interest_rate (optional, default 0)
        rate, err = parse_rate(get("interest_rate"))
        if err:
            result.warnings.append(err)
            norm["interest_rate"] = 0.0
        else:
            norm["interest_rate"] = rate

        # term_months
        term, err = parse_positive_int(get("term_months") or 1, "term_months")
        if err:
            result.warnings.append(f"term_months: {err}; defaulting to 1")
            norm["term_months"] = 1
        else:
            norm["term_months"] = term

        # application_date (optional)
        dt, err = parse_date(get("application_date"))
        if err and get("application_date"):
            result.warnings.append(f"application_date: {err}")
        norm["application_date"] = dt.date().isoformat() if dt else None

        norm["purpose"] = str(get("purpose") or "").strip() or None
        result.normalized = norm
        result.status = "valid" if result.is_valid else "invalid"
        return result

    def validate_repayment_row(self, row: Dict, mapping: Dict[str, Optional[str]],
                               row_index: int) -> ImportRowResult:
        result = ImportRowResult(row_index=row_index, raw_data=row)
        norm = {}

        def get(field: str) -> Any:
            col = mapping.get(field)
            return row.get(col) if col else None

        # Employee matching
        emp_name = str(get("employee_name") or "").strip()
        result.employee_name_raw = emp_name
        if emp_name:
            suggestions = self.match_employee(emp_name)
            result.match_suggestions = suggestions
            if suggestions and suggestions[0].score >= self.threshold:
                result.employee_id = suggestions[0].employee_id
                result.auto_matched = True

        # Loan reference
        loan_ref = str(get("loan_reference") or "").strip()
        if not loan_ref:
            result.errors.append("loan_reference is required")
        else:
            loan_row = self.db.get_loan_by_reference(loan_ref)
            if loan_row:
                norm["loan_id"] = loan_row["id"]
            else:
                result.errors.append(f"Loan reference '{loan_ref}' not found")
        norm["loan_reference"] = loan_ref

        # amount
        amt, err = parse_amount(get("amount"))
        if err:
            result.errors.append(err)
        else:
            norm["amount"] = amt

        # payment_date
        dt, err = parse_date(get("payment_date"))
        if err:
            result.errors.append(f"payment_date: {err}")
        else:
            norm["payment_date"] = dt.date().isoformat() if dt else None

        norm["payment_method"] = str(get("payment_method") or "cash").strip() or "cash"
        norm["reference"] = str(get("reference") or "").strip() or None
        norm["notes"] = str(get("notes") or "").strip() or None

        result.normalized = norm
        result.status = "valid" if (not result.errors and norm.get("loan_id")) else "invalid"
        return result

    # ------------------------------------------------------------------ #
    # Validate all rows
    # ------------------------------------------------------------------ #

    def validate_rows(self, raw_rows: List[Dict], mapping: Dict[str, Optional[str]],
                      import_type: str = "loan") -> List[ImportRowResult]:
        """Validate all rows and return ImportRowResult list."""
        self._load_employees()
        results = []
        for idx, row in enumerate(raw_rows, start=1):
            if import_type == "loan":
                results.append(self.validate_loan_row(row, mapping, idx))
            else:
                results.append(self.validate_repayment_row(row, mapping, idx))
        return results

    # ------------------------------------------------------------------ #
    # Dry-run
    # ------------------------------------------------------------------ #

    def dry_run_import(self, results: List[ImportRowResult],
                       import_type: str = "loan") -> ImportSummary:
        """Simulate import without writing to DB."""
        valid = [r for r in results if r.is_valid]
        invalid = [r for r in results if not r.is_valid]
        return ImportSummary(
            file_name="",
            import_type=import_type,
            total_rows=len(results),
            imported=len(valid),
            failed=len(invalid),
            dry_run=True,
        )

    # ------------------------------------------------------------------ #
    # Commit
    # ------------------------------------------------------------------ #

    def commit_import(self, results: List[ImportRowResult], import_type: str,
                      user_id: Optional[int], file_name: str) -> ImportSummary:
        """Commit valid rows to the DB and write an import log."""
        from datetime import date as _date
        summary = ImportSummary(
            file_name=file_name,
            import_type=import_type,
            total_rows=len(results),
            dry_run=False,
        )
        log_rows = []

        for result in results:
            if not result.is_valid:
                result.status = "skipped"
                summary.skipped += 1
                log_rows.append({
                    "row": result.row_index,
                    "status": "skipped",
                    "reason": "; ".join(result.errors),
                })
                continue
            try:
                norm = result.normalized
                if import_type == "loan":
                    ref = generate_reference("CA")
                    total = norm["requested_amount"] * (
                        1 + (norm.get("interest_rate", 0) / 100) * norm.get("term_months", 1)
                    )
                    loan_data = {
                        "reference_number": ref,
                        "employee_id": result.employee_id,
                        "requested_amount": norm["requested_amount"],
                        "approved_amount": None,
                        "interest_rate": norm.get("interest_rate", 0.0),
                        "term_months": norm.get("term_months", 1),
                        "status": "pending",
                        "purpose": norm.get("purpose"),
                        "application_date": norm.get("application_date") or _date.today().isoformat(),
                        "due_date": None,
                        "outstanding_balance": total,
                        "branch_id": None,
                        "created_by": user_id,
                    }
                    loan_id = self.db.create_loan(loan_data)
                    self.db.log_action(user_id, "IMPORT_LOAN", "loans", loan_id,
                                       f"File:{file_name} Row:{result.row_index}")
                    result.status = "imported"
                    summary.imported += 1
                    log_rows.append({"row": result.row_index, "status": "imported",
                                     "reference": ref, "reason": ""})
                else:  # repayment
                    rep_id = self.db.create_repayment(
                        norm["loan_id"], norm["amount"], norm["payment_date"],
                        norm.get("payment_method", "cash"), norm.get("reference"),
                        norm.get("notes"), user_id,
                    )
                    # Update outstanding balance
                    total_paid = self.db.sum_repayments(norm["loan_id"])
                    loan_row = self.db.get_loan_by_id(norm["loan_id"])
                    if loan_row:
                        payable = Loan.from_row(loan_row).total_payable()
                        self.db.update_outstanding_balance(norm["loan_id"],
                                                           max(0.0, payable - total_paid))
                    self.db.log_action(user_id, "IMPORT_REPAYMENT", "repayments", rep_id,
                                       f"File:{file_name} Row:{result.row_index}")
                    result.status = "imported"
                    summary.imported += 1
                    log_rows.append({"row": result.row_index, "status": "imported", "reason": ""})
            except Exception as exc:
                log.error("Import error row %d: %s", result.row_index, exc)
                result.status = "failed"
                summary.failed += 1
                log_rows.append({"row": result.row_index, "status": "failed", "reason": str(exc)})

        summary.log_path = self._write_import_log(summary, log_rows)
        return summary

    # ------------------------------------------------------------------ #
    # Import log
    # ------------------------------------------------------------------ #

    def _write_import_log(self, summary: ImportSummary, log_rows: List[Dict]) -> str:
        import csv as _csv
        log_dir = os.path.join(get_app_data_dir(), "import_logs")
        ensure_dir(log_dir)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(log_dir, f"import_{summary.import_type}_{ts}.csv")
        with open(log_path, "w", newline="", encoding="utf-8") as f:
            writer = _csv.DictWriter(f, fieldnames=["row", "status", "reason", "reference"])
            writer.writeheader()
            for row in log_rows:
                row.setdefault("reference", "")
                writer.writerow(row)
        # Audit
        self.db.log_action(None, "IMPORT_COMPLETE", details=json.dumps({
            "file": summary.file_name,
            "type": summary.import_type,
            "total": summary.total_rows,
            "imported": summary.imported,
            "failed": summary.failed,
            "dry_run": summary.dry_run,
        }))
        log.info("Import log saved: %s", log_path)
        return log_path
