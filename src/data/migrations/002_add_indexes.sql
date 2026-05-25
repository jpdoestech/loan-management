-- 002_add_indexes.sql  –– Performance indexes
PRAGMA foreign_keys = ON;

CREATE INDEX IF NOT EXISTS idx_employees_name       ON employees(name);
CREATE INDEX IF NOT EXISTS idx_employees_code       ON employees(employee_code);
CREATE INDEX IF NOT EXISTS idx_employees_client     ON employees(client_id);
CREATE INDEX IF NOT EXISTS idx_loans_employee       ON loans(employee_id);
CREATE INDEX IF NOT EXISTS idx_loans_status         ON loans(status);
CREATE INDEX IF NOT EXISTS idx_loans_ref            ON loans(reference_number);
CREATE INDEX IF NOT EXISTS idx_repayments_loan      ON repayments(loan_id);
CREATE INDEX IF NOT EXISTS idx_repayments_date      ON repayments(payment_date);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user      ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_table     ON audit_logs(table_name, record_id);

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('002');
