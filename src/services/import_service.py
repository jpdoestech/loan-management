"""Import service: parsing, validation, fuzzy matching, commit/dry-run.

Supports CSV and Excel (.xlsx) bulk import of:
  - Loan / cash-advance applications
  - Repayments / payments

Typical usage::

    svc = ImportService(user_id=1, threshold=89)
    rows = svc.parse_file("advances.xlsx", import_type="loan")
    results = svc.validate_and_match(rows)
    # review results in GUI ...
    report = svc.commit_import(results, dry_run=False)
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.data import db_manager as db
from src.utils.fuzzy_match import FuzzyMatcher
from src.utils.helpers import IMPORT_LOGS_DIR, timestamp_filename
from src.utils.logger import get_logger
from src.utils.validators import (
    parse_date, parse_decimal, parse_int,
    validate_loan_row, validate_repayment_row,
)

log = get_logger(__name__)


# ─── Row result status constants ─────────────────────────────────────────────
STATUS_VALID = "valid"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_MATCHED = "matched"
STATUS_UNMATCHED = "unmatched"
STATUS_IMPORTED = "imported"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"


@dataclass
class EmployeeMatch:
    """Represents a single fuzzy-match candidate."""
    employee_id: int
    name: str
    employee_code: Optional[str]
    score: float
    auto_selected: bool = False


@dataclass
class ImportRowResult:
    """Holds parsed data, validation results, and match info for one row."""
    row_number: int
    raw: Dict[str, Any]
    normalized: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    status: str = STATUS_VALID
    employee_matches: List[EmployeeMatch] = field(default_factory=list)
    selected_employee_id: Optional[int] = None
    final_status: Optional[str] = None
    final_message: str = ""


class ImportService:
    """Orchestrates the full import pipeline.

    Args:
        user_id:    ID of the user performing the import.
        threshold:  Fuzzy match threshold (0-100).
    """

    def __init__(self, user_id: Optional[int] = None, threshold: float = 89.0) -> None:
        self.user_id = user_id
        self.threshold = threshold
        self.matcher = FuzzyMatcher(threshold=threshold)

    # ── Parsing ───────────────────────────────────────────────────────────────

    def parse_file(
        self,
        file_path: str,
        import_type: str,
        column_mapping: Optional[Dict[str, str]] = None,
        sheet_index: int = 0,
    ) -> List[Dict[str, Any]]:
        """Parse a CSV or XLSX file into a list of raw row dicts.

        Args:
            file_path:      Absolute path to the import file.
            import_type:    ``"loan"`` or ``"repayment"``.
            column_mapping: Maps file column headers to model field names.
            sheet_index:    XLSX sheet index (0-based).

        Returns:
            List of raw row dicts with file-column keys (or mapped keys).
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext == ".csv":
            rows = self._parse_csv(path)
        elif ext in (".xlsx", ".xls"):
            rows = self._parse_xlsx(path, sheet_index=sheet_index)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        if column_mapping:
            rows = [self._apply_mapping(r, column_mapping) for r in rows]

        log.info("Parsed %d rows from %s (type=%s).", len(rows), path.name, import_type)
        return rows

    def _parse_csv(self, path: Path) -> List[Dict]:
        """Read CSV rows using Python's csv module."""
        rows = []
        with path.open(newline="", encoding="utf-8-sig") as fh:
            # Sniff delimiter
            sample = fh.read(4096)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(fh, dialect=dialect)
            for row in reader:
                rows.append(dict(row))
        return rows

    def _parse_xlsx(self, path: Path, sheet_index: int = 0) -> List[Dict]:
        """Read XLSX rows using openpyxl."""
        try:
            import openpyxl  # type: ignore
        except ImportError as exc:
            raise ImportError("openpyxl is required for Excel imports.") from exc

        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.worksheets[sheet_index]
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h).strip() if h is not None else "" for h in next(rows_iter, [])]
        result = []
        for row_vals in rows_iter:
            if all(v is None for v in row_vals):
                continue
            result.append({h: v for h, v in zip(headers, row_vals)})
        return result

    def _apply_mapping(self, row: Dict, mapping: Dict[str, str]) -> Dict:
        """Remap column keys according to user-supplied mapping."""
        mapped: Dict[str, Any] = {}
        for src_col, target_field in mapping.items():
            if src_col in row:
                mapped[target_field] = row[src_col]
        # pass through unmapped columns too
        for k, v in row.items():
            if k not in mapping:
                mapped[k] = v
        return mapped

    # ── Validation + Fuzzy Matching ───────────────────────────────────────────

    def validate_and_match(
        self,
        rows: List[Dict],
        import_type: str = "loan",
    ) -> List[ImportRowResult]:
        """Validate rows and run fuzzy employee matching.

        Args:
            rows:        Raw row dicts from :meth:`parse_file`.
            import_type: ``"loan"`` or ``"repayment"``.

        Returns:
            List of :class:`ImportRowResult` objects.
        """
        employees = db.get_all_employees(active_only=False)
        candidate_names = [e["name"] for e in employees]
        candidate_codes = [e.get("employee_code") or "" for e in employees]

        results = []
        for i, row in enumerate(rows, start=1):
            result = ImportRowResult(row_number=i, raw=row)
            result.normalized = self._normalize(row, import_type)

            # Validation
            if import_type == "loan":
                result.errors = validate_loan_row(result.normalized)
            else:
                result.errors = validate_repayment_row(result.normalized)

            if result.errors:
                result.status = STATUS_ERROR
            else:
                result.status = STATUS_VALID

            # Fuzzy matching
            query_name = str(result.normalized.get("employee_name") or "").strip()
            query_code = str(result.normalized.get("employee_code") or "").strip()

            if query_name or query_code:
                result.employee_matches = self._match_employees(
                    query_name, query_code, employees, candidate_names, candidate_codes
                )
                if result.employee_matches:
                    best = result.employee_matches[0]
                    if best.score >= self.threshold:
                        best.auto_selected = True
                        result.selected_employee_id = best.employee_id
                        if result.status == STATUS_VALID:
                            result.status = STATUS_MATCHED
                    else:
                        result.status = STATUS_UNMATCHED
                        result.warnings.append(
                            f"No employee match above {self.threshold}% "
                            f"(best: '{best.name}' at {best.score:.1f}%)."
                        )
                else:
                    result.status = STATUS_UNMATCHED
                    result.warnings.append("No employee candidates found in database.")

            results.append(result)

        return results

    def _normalize(self, row: Dict, import_type: str) -> Dict:
        """Normalise raw row values to model-compatible types."""
        n: Dict[str, Any] = {}
        # employee identifiers
        n["employee_name"] = str(row.get("employee_name") or row.get("name") or "").strip()
        n["employee_code"] = str(row.get("employee_code") or row.get("emp_code") or "").strip()

        if import_type == "loan":
            n["requested_amount"] = parse_decimal(
                row.get("requested_amount") or row.get("amount") or row.get("loan_amount")
            )
            n["interest_rate"] = parse_decimal(row.get("interest_rate") or 0)
            n["term_months"] = parse_int(row.get("term_months") or 1)
            n["purpose"] = str(row.get("purpose") or "").strip()
            n["application_date"] = parse_date(
                row.get("application_date") or row.get("date")
            )
            n["notes"] = str(row.get("notes") or "").strip()
            n["status"] = str(row.get("status") or "pending").strip().lower()
            n["reference_number"] = str(row.get("reference_number") or row.get("reference") or "").strip()

        elif import_type == "repayment":
            n["amount"] = parse_decimal(row.get("amount") or row.get("payment_amount"))
            n["payment_date"] = parse_date(row.get("payment_date") or row.get("date"))
            n["payment_method"] = str(row.get("payment_method") or "cash").strip().lower()
            n["reference"] = str(row.get("reference") or "").strip()
            n["loan_reference"] = str(row.get("loan_reference") or row.get("loan_ref") or "").strip()
            n["loan_id"] = parse_int(row.get("loan_id"))
            n["notes"] = str(row.get("notes") or "").strip()

        return n

    def _match_employees(
        self,
        query_name: str,
        query_code: str,
        employees: List[Dict],
        candidate_names: List[str],
        candidate_codes: List[str],
    ) -> List[EmployeeMatch]:
        """Run fuzzy match against employee names and codes."""
        score_map: Dict[int, float] = {}

        # Match by name
        if query_name:
            name_results = self.matcher.match(query_name, candidate_names, top_n=5)
            for cand_name, score, idx in name_results:
                emp_id = employees[idx]["id"]
                score_map[emp_id] = max(score_map.get(emp_id, 0), score)

        # Match by code (exact first, then fuzzy)
        if query_code:
            for emp in employees:
                if emp.get("employee_code") == query_code:
                    score_map[emp["id"]] = max(score_map.get(emp["id"], 0), 100.0)
            code_results = self.matcher.match(query_code, candidate_codes, top_n=3)
            for cand_code, score, idx in code_results:
                if cand_code:
                    emp_id = employees[idx]["id"]
                    score_map[emp_id] = max(score_map.get(emp_id, 0), score)

        # Build sorted EmployeeMatch list
        matches = []
        emp_index = {e["id"]: e for e in employees}
        for emp_id, score in sorted(score_map.items(), key=lambda x: -x[1])[:3]:
            emp = emp_index[emp_id]
            matches.append(EmployeeMatch(
                employee_id=emp_id,
                name=emp["name"],
                employee_code=emp.get("employee_code"),
                score=score,
            ))
        return matches

    # ── Dry-run / Commit ──────────────────────────────────────────────────────

    def commit_import(
        self,
        results: List[ImportRowResult],
        import_type: str,
        dry_run: bool = False,
        file_name: str = "unknown",
    ) -> Dict[str, Any]:
        """Commit or dry-run validated import results.

        Args:
            results:     Validated :class:`ImportRowResult` list.
            import_type: ``"loan"`` or ``"repayment"``.
            dry_run:     If ``True``, simulate without writing to DB.
            file_name:   Original file name for audit logging.

        Returns:
            Summary dict with counts and log path.
        """
        committed = 0
        skipped = 0
        failed = 0
        log_rows = []

        for res in results:
            if res.status in (STATUS_ERROR, STATUS_UNMATCHED) and not res.selected_employee_id:
                res.final_status = STATUS_SKIPPED
                res.final_message = "; ".join(res.errors) or "Unmatched / error"
                skipped += 1
                log_rows.append(self._log_row(res))
                continue

            if dry_run:
                res.final_status = "dry_run_ok"
                res.final_message = "Would be imported."
                committed += 1
                log_rows.append(self._log_row(res))
                continue

            try:
                if import_type == "loan":
                    self._insert_loan(res)
                else:
                    self._insert_repayment(res)
                res.final_status = STATUS_IMPORTED
                res.final_message = "Imported successfully."
                committed += 1
            except Exception as exc:  # noqa: BLE001
                res.final_status = STATUS_FAILED
                res.final_message = str(exc)
                failed += 1
                log.error("Import row %d failed: %s", res.row_number, exc)

            log_rows.append(self._log_row(res))

        summary = {
            "dry_run": dry_run,
            "import_type": import_type,
            "file_name": file_name,
            "total": len(results),
            "committed": committed,
            "skipped": skipped,
            "failed": failed,
            "timestamp": datetime.now().isoformat(),
        }

        log_path = self._write_import_log(log_rows, summary)
        summary["log_path"] = log_path

        if not dry_run:
            db.write_audit_log(
                action="IMPORT",
                user_id=self.user_id,
                table_name=import_type + "s",
                detail=json.dumps(summary),
            )

        log.info("Import %s: committed=%d skipped=%d failed=%d (dry_run=%s).",
                 file_name, committed, skipped, failed, dry_run)
        return summary

    def _insert_loan(self, res: ImportRowResult) -> None:
        """Insert a single validated loan row into the DB."""
        n = res.normalized
        emp_id = res.selected_employee_id
        if not emp_id:
            raise ValueError("No employee selected.")
        from src.utils.helpers import generate_reference_number
        db.create_loan({
            "reference_number": n.get("reference_number") or generate_reference_number("CA"),
            "employee_id": emp_id,
            "requested_amount": float(n["requested_amount"]),
            "interest_rate": float(n.get("interest_rate") or 0),
            "term_months": int(n.get("term_months") or 1),
            "purpose": n.get("purpose"),
            "status": n.get("status", "pending"),
            "application_date": str(n["application_date"]) if n.get("application_date") else None,
            "notes": n.get("notes"),
            "processed_by": self.user_id,
        })

    def _insert_repayment(self, res: ImportRowResult) -> None:
        """Insert a single validated repayment row into the DB."""
        n = res.normalized
        # Resolve loan_id
        loan_id = n.get("loan_id")
        if not loan_id and n.get("loan_reference"):
            loan = db.get_loan_by_reference(n["loan_reference"])
            if not loan:
                raise ValueError(f"Loan reference '{n['loan_reference']}' not found.")
            loan_id = loan["id"]
        if not loan_id:
            raise ValueError("Cannot resolve loan_id or loan_reference.")
        db.create_repayment({
            "loan_id": int(loan_id),
            "payment_date": str(n["payment_date"]),
            "amount": float(n["amount"]),
            "payment_method": n.get("payment_method", "cash"),
            "reference": n.get("reference"),
            "notes": n.get("notes"),
            "recorded_by": self.user_id,
        })

    # ── Log helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _log_row(res: ImportRowResult) -> Dict:
        return {
            "row": res.row_number,
            "status": res.final_status or res.status,
            "employee_id": res.selected_employee_id,
            "errors": "; ".join(res.errors),
            "warnings": "; ".join(res.warnings),
            "message": res.final_message,
        }

    def _write_import_log(self, log_rows: List[Dict], summary: Dict) -> str:
        """Write a detailed CSV import log to data_files/import_logs/.

        Args:
            log_rows: List of row-level dicts.
            summary:  Import summary dict.

        Returns:
            Path to the written log file.
        """
        fname = timestamp_filename("import_log", "csv")
        log_path = IMPORT_LOGS_DIR / fname

        import csv as _csv
        with open(log_path, "w", newline="", encoding="utf-8") as fh:
            # Write summary header
            fh.write(f"# Import Log – {summary.get('timestamp')}\n")
            fh.write(f"# file={summary.get('file_name')}, type={summary.get('import_type')}, "
                     f"dry_run={summary.get('dry_run')}\n")
            fh.write(f"# total={summary.get('total')}, committed={summary.get('committed')}, "
                     f"skipped={summary.get('skipped')}, failed={summary.get('failed')}\n")

            if log_rows:
                writer = _csv.DictWriter(fh, fieldnames=list(log_rows[0].keys()))
                writer.writeheader()
                writer.writerows(log_rows)

        log.info("Import log written: %s", log_path)
        return str(log_path)

    # ── Column detection ──────────────────────────────────────────────────────

    @staticmethod
    def detect_columns(file_path: str, sheet_index: int = 0) -> List[str]:
        """Return the column headers found in the file without loading all rows.

        Args:
            file_path:   Path to CSV or XLSX.
            sheet_index: XLSX sheet (0-based).

        Returns:
            List of column header strings.
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as fh:
                sample = fh.read(4096)
                fh.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(fh, dialect=dialect)
                return list(reader.fieldnames or [])
        else:
            import openpyxl  # type: ignore
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.worksheets[sheet_index]
            first_row = next(ws.iter_rows(values_only=True), [])
            return [str(h).strip() if h is not None else "" for h in first_row]

    @staticmethod
    def get_sheet_names(file_path: str) -> List[str]:
        """Return sheet names for an Excel file.

        Args:
            file_path: Path to XLSX.

        Returns:
            List of sheet name strings.
        """
        import openpyxl  # type: ignore
        wb = openpyxl.load_workbook(file_path, read_only=True)
        return wb.sheetnames
