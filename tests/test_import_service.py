"""Unit tests for ImportService and FuzzyMatcher."""
import os
import csv
import tempfile
import unittest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.fuzzy_match import FuzzyMatcher


class TestFuzzyMatcher(unittest.TestCase):

    def setUp(self):
        self.matcher = FuzzyMatcher(threshold=89.0)
        self.candidates = [
            "Juan dela Cruz",
            "Maria Santos",
            "Pedro Reyes",
            "Ana Garcia",
            "Jose Rizal",
        ]

    def test_exact_match_scores_100(self):
        results = self.matcher.match("Juan dela Cruz", self.candidates, top_n=1)
        self.assertGreaterEqual(results[0][1], 95.0)

    def test_typo_still_matches(self):
        results = self.matcher.match("Juan dela Cruzz", self.candidates, top_n=1)
        self.assertEqual(results[0][0], "Juan dela Cruz")
        self.assertGreater(results[0][1], 70.0)

    def test_top_n_limit(self):
        results = self.matcher.match("Maria", self.candidates, top_n=3)
        self.assertLessEqual(len(results), 3)

    def test_best_match_returns_single(self):
        result = self.matcher.best_match("Pedro Reyes", self.candidates)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Pedro Reyes")

    def test_no_candidates_returns_empty(self):
        results = self.matcher.match("anyone", [], top_n=3)
        self.assertEqual(results, [])

    def test_is_match_above_threshold(self):
        self.assertTrue(self.matcher.is_match("Jose Rizal", self.candidates))

    def test_is_match_below_threshold(self):
        self.matcher.threshold = 99.9
        self.assertFalse(self.matcher.is_match("Xyz Abc", self.candidates))

    def test_backend_string(self):
        backend = FuzzyMatcher.backend()
        self.assertIn(backend, ("rapidfuzz", "difflib"))


class TestImportServiceCSV(unittest.TestCase):

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        from src.data.db_manager import DBManager
        from src.services.import_service import ImportService
        self.db = DBManager(db_path=self.tmp_db.name)
        self.db.initialize()
        # Seed an employee
        self.db.create_employee("Juan dela Cruz", "EMP001", "Finance",
                                "Accountant", None, None, None, None)
        self.svc = ImportService(self.db, fuzzy_threshold=85.0)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp_db.name)

    def _write_csv(self, rows, headers):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv",
                                        delete=False, newline="")
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        f.close()
        return f.name

    def test_parse_csv(self):
        path = self._write_csv(
            [{"employee_name": "Juan dela Cruz", "requested_amount": "5000",
              "interest_rate": "2", "term_months": "3", "purpose": "Medical"}],
            ["employee_name", "requested_amount", "interest_rate", "term_months", "purpose"],
        )
        headers, rows = self.svc.parse_file(path)
        self.assertEqual(len(rows), 1)
        self.assertIn("employee_name", headers)
        os.unlink(path)

    def test_auto_map_columns(self):
        headers = ["employee_name", "amount", "rate", "term", "purpose"]
        mapping = self.svc.auto_map_columns(headers, "loan")
        self.assertEqual(mapping.get("employee_name"), "employee_name")
        self.assertEqual(mapping.get("requested_amount"), "amount")

    def test_validate_valid_loan_row(self):
        mapping = {
            "employee_name": "employee_name",
            "requested_amount": "requested_amount",
            "interest_rate": "interest_rate",
            "term_months": "term_months",
            "purpose": "purpose",
            "employee_code": None,
            "application_date": None,
        }
        row = {"employee_name": "Juan dela Cruz", "requested_amount": "5000",
               "interest_rate": "2", "term_months": "3", "purpose": ""}
        result = self.svc.validate_loan_row(row, mapping, 1)
        self.assertFalse(result.errors or not result.employee_id,
                         msg=f"Errors: {result.errors}, emp_id: {result.employee_id}")

    def test_validate_missing_amount(self):
        mapping = {
            "employee_name": "employee_name",
            "requested_amount": "requested_amount",
            "interest_rate": None, "term_months": None,
            "purpose": None, "employee_code": None,
            "application_date": None,
        }
        row = {"employee_name": "Juan dela Cruz", "requested_amount": ""}
        result = self.svc.validate_loan_row(row, mapping, 1)
        self.assertTrue(any("Amount" in e or "amount" in e.lower() for e in result.errors))

    def test_dry_run_does_not_commit(self):
        mapping = {
            "employee_name": "employee_name",
            "requested_amount": "requested_amount",
            "interest_rate": None, "term_months": None,
            "purpose": None, "employee_code": None,
            "application_date": None,
        }
        rows = [{"employee_name": "Juan dela Cruz", "requested_amount": "1000"}]
        results = self.svc.validate_rows(rows, mapping, "loan")
        summary = self.svc.dry_run_import(results, "loan")
        self.assertTrue(summary.dry_run)
        # No loans should be in DB
        loans = self.db.list_loans()
        self.assertEqual(len(loans), 0)

    def test_commit_import_creates_loan(self):
        mapping = {
            "employee_name": "employee_name",
            "requested_amount": "requested_amount",
            "interest_rate": None, "term_months": None,
            "purpose": None, "employee_code": None,
            "application_date": None,
        }
        rows = [{"employee_name": "Juan dela Cruz", "requested_amount": "2000"}]
        results = self.svc.validate_rows(rows, mapping, "loan")
        self.assertTrue(results[0].is_valid, msg=f"Errors: {results[0].errors}")
        summary = self.svc.commit_import(results, "loan", None, "test.csv")
        self.assertEqual(summary.imported, 1)
        loans = self.db.list_loans()
        self.assertEqual(len(loans), 1)

    def test_unmatched_employee_marks_invalid(self):
        mapping = {
            "employee_name": "employee_name",
            "requested_amount": "requested_amount",
            "interest_rate": None, "term_months": None,
            "purpose": None, "employee_code": None,
            "application_date": None,
        }
        rows = [{"employee_name": "Zzz Unknown Person XYZ", "requested_amount": "500"}]
        results = self.svc.validate_rows(rows, mapping, "loan")
        self.assertIsNone(results[0].employee_id)
        self.assertFalse(results[0].is_valid)


if __name__ == "__main__":
    unittest.main()
