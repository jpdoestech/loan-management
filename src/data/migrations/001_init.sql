-- 001_init.sql  –– Initial schema for Employee Cash Advance Manager
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ─── Migrations tracker ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Branches ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS branches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    address     TEXT,
    phone       TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Users ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    full_name       TEXT    NOT NULL,
    email           TEXT,
    role            TEXT    NOT NULL DEFAULT 'viewer',   -- admin|manager|cashier|viewer
    branch_id       INTEGER REFERENCES branches(id),
    is_active       INTEGER NOT NULL DEFAULT 1,
    last_login      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Clients (companies that employ the employees) ───────────────────────────
CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    contact     TEXT,
    phone       TEXT,
    email       TEXT,
    address     TEXT,
    branch_id   INTEGER REFERENCES branches(id),
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Employees ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS employees (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_code   TEXT    UNIQUE,
    name            TEXT    NOT NULL,
    position        TEXT,
    department      TEXT,
    date_hired      DATE,
    monthly_salary  REAL,
    phone           TEXT,
    email           TEXT,
    client_id       INTEGER REFERENCES clients(id),
    branch_id       INTEGER REFERENCES branches(id),
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Loans / Cash Advances ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS loans (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_number    TEXT    UNIQUE,
    employee_id         INTEGER NOT NULL REFERENCES employees(id),
    branch_id           INTEGER REFERENCES branches(id),
    requested_amount    REAL    NOT NULL,
    approved_amount     REAL,
    interest_rate       REAL    NOT NULL DEFAULT 0.0,   -- % per month
    term_months         INTEGER NOT NULL DEFAULT 1,
    purpose             TEXT,
    status              TEXT    NOT NULL DEFAULT 'pending',  -- pending|approved|active|completed|rejected|cancelled
    application_date    DATE    NOT NULL DEFAULT (date('now')),
    approval_date       DATE,
    first_payment_date  DATE,
    processed_by        INTEGER REFERENCES users(id),
    approved_by         INTEGER REFERENCES users(id),
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Repayments ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS repayments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id         INTEGER NOT NULL REFERENCES loans(id),
    payment_date    DATE    NOT NULL,
    amount          REAL    NOT NULL,
    payment_method  TEXT    DEFAULT 'cash',   -- cash|bank|deduction
    reference       TEXT,
    notes           TEXT,
    recorded_by     INTEGER REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Audit Logs ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),
    action      TEXT    NOT NULL,   -- CREATE|UPDATE|DELETE|LOGIN|IMPORT|EXPORT
    table_name  TEXT,
    record_id   INTEGER,
    detail      TEXT,               -- JSON blob of changed fields / import summary
    ip_address  TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Triggers: auto-update updated_at ────────────────────────────────────────
CREATE TRIGGER IF NOT EXISTS trg_users_upd
    AFTER UPDATE ON users FOR EACH ROW
    BEGIN UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id; END;

CREATE TRIGGER IF NOT EXISTS trg_loans_upd
    AFTER UPDATE ON loans FOR EACH ROW
    BEGIN UPDATE loans SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id; END;

CREATE TRIGGER IF NOT EXISTS trg_employees_upd
    AFTER UPDATE ON employees FOR EACH ROW
    BEGIN UPDATE employees SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id; END;

CREATE TRIGGER IF NOT EXISTS trg_repayments_upd
    AFTER UPDATE ON repayments FOR EACH ROW
    BEGIN UPDATE repayments SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id; END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('001');
