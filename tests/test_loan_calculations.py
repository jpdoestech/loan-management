"""Unit tests for Loan model calculations."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models.loan import Loan


class TestLoanCalculations(unittest.TestCase):

    def _make(self, requested, approved=None, rate=0.0, term=1):
        return Loan(
            reference_number="TEST-001",
            employee_id=1,
            requested_amount=requested,
            approved_amount=approved,
            interest_rate=rate,
            term_months=term,
        )

    def test_total_payable_no_interest(self):
        loan = self._make(10_000, approved=10_000, rate=0.0, term=6)
        self.assertAlmostEqual(loan.total_payable(), 10_000.0)

    def test_total_payable_with_interest(self):
        # 10,000 @ 5% flat for 3 months = 10,000 * (1 + 0.05*3) = 11,500
        loan = self._make(10_000, approved=10_000, rate=5.0, term=3)
        self.assertAlmostEqual(loan.total_payable(), 11_500.0)

    def test_monthly_payment_no_interest(self):
        loan = self._make(12_000, approved=12_000, rate=0.0, term=6)
        self.assertAlmostEqual(loan.monthly_payment(), 2_000.0)

    def test_monthly_payment_with_interest(self):
        # total = 12,000 * (1 + 0.10 * 12) = 12,000 * 2.2 = 26,400
        # monthly = 26,400 / 12 = 2,200
        loan = self._make(12_000, approved=12_000, rate=10.0, term=12)
        self.assertAlmostEqual(loan.monthly_payment(), 2_200.0)

    def test_uses_approved_amount_when_set(self):
        loan = self._make(10_000, approved=8_000, rate=0.0, term=4)
        self.assertAlmostEqual(loan.total_payable(), 8_000.0)

    def test_uses_requested_when_approved_none(self):
        loan = self._make(5_000, approved=None, rate=0.0, term=5)
        self.assertAlmostEqual(loan.total_payable(), 5_000.0)

    def test_single_term(self):
        loan = self._make(3_000, approved=3_000, rate=2.0, term=1)
        # total = 3_000 * (1 + 0.02 * 1) = 3_060
        self.assertAlmostEqual(loan.total_payable(), 3_060.0)
        self.assertAlmostEqual(loan.monthly_payment(), 3_060.0)

    def test_display_name_minimal(self):
        from src.models.employee import Employee
        e = Employee(name="Juan dela Cruz")
        self.assertEqual(e.display_name, "Juan dela Cruz")

    def test_display_name_with_code(self):
        from src.models.employee import Employee
        e = Employee(name="Maria Santos", employee_code="EMP-001")
        self.assertEqual(e.display_name, "Maria Santos (EMP-001)")


if __name__ == "__main__":
    unittest.main()
