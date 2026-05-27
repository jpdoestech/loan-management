"""Integration tests for DBManager."""
import os
import tempfile
import unittest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data.db_manager import DBManager
from src.utils.crypto import hash_password


class TestDBManager(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db = DBManager(db_path=self.tmp.name)
        self.db.initialize()

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    # -- Users --
    def test_create_and_fetch_user(self):
        uid = self.db.create_user("alice", hash_password("pw"), "Alice", "staff", None)
        self.assertGreater(uid, 0)
        row = self.db.get_user_by_username("alice")
        self.assertIsNotNone(row)
        self.assertEqual(row["username"], "alice")

    def test_user_not_found(self):
        self.assertIsNone(self.db.get_user_by_username("nobody"))

    def test_list_users_empty(self):
        users = self.db.list_users()
        self.assertIsInstance(users, list)

    # -- Branches --
    def test_create_branch(self):
        bid = self.db.create_branch("Main Branch", "MB", "Manila")
        self.assertGreater(bid, 0)
        branches = self.db.list_branches()
        names = [b["name"] for b in branches]
        self.assertIn("Main Branch", names)

    # -- Employees --
    def test_create_employee(self):
        eid = self.db.create_employee("Juan Cruz", "EMP001", "IT", "Dev",
                                      None, None, None, None)
        self.assertGreater(eid, 0)
        emps = self.db.list_employees()
        self.assertTrue(any(e["name"] == "Juan Cruz" for e in emps))

    # -- Loans --
    def test_create_and_fetch_loan(self):
        eid = self.db.create_employee("Maria Reyes", "EMP002", None, None, None, None, None, None)
        loan_data = {
            "reference_number": "CA-TEST-001",
            "employee_id": eid,
            "requested_amount": 5000.0,
            "approved_amount": None,
            "interest_rate": 2.0,
            "term_months": 3,
            "status": "pending",
            "purpose": "Medical",
            "application_date": "2025-01-01",
            "due_date": "2025-04-01",
            "outstanding_balance": 5300.0,
            "branch_id": None,
            "created_by": None,
        }
        lid = self.db.create_loan(loan_data)
        self.assertGreater(lid, 0)
        loan = self.db.get_loan_by_id(lid)
        self.assertEqual(loan["reference_number"], "CA-TEST-001")

    def test_repayment_sum(self):
        eid = self.db.create_employee("Pedro Santos", "EMP003", None, None, None, None, None, None)
        loan_data = {
            "reference_number": "CA-TEST-002", "employee_id": eid,
            "requested_amount": 10000.0, "approved_amount": 10000.0,
            "interest_rate": 0.0, "term_months": 2, "status": "active",
            "purpose": None, "application_date": "2025-01-01",
            "due_date": "2025-03-01", "outstanding_balance": 10000.0,
            "branch_id": None, "created_by": None,
        }
        lid = self.db.create_loan(loan_data)
        self.db.create_repayment(lid, 3000.0, "2025-02-01", "cash", None, None, None)
        self.db.create_repayment(lid, 2000.0, "2025-03-01", "cash", None, None, None)
        total = self.db.sum_repayments(lid)
        self.assertAlmostEqual(total, 5000.0)

    # -- Audit --
    def test_log_action(self):
        self.db.log_action(None, "TEST_ACTION", "test_table", 1, "details")
        logs = self.db.list_audit_logs()
        self.assertTrue(any(l["action"] == "TEST_ACTION" for l in logs))


if __name__ == "__main__":
    unittest.main()
