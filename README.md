# Employee Cash Advance Manager

A production-ready desktop application for managing employee cash advances and loan repayments. Built with Python 3.10+, Tkinter (GUI), and SQLite (local DB) — packagable into a Windows `.exe` via PyInstaller.

---

## Features

| Feature | Description |
|---|---|
| **Loan lifecycle** | Create → Approve → Disburse → Repay → Close |
| **Employee management** | CRUD with branch/client associations |
| **Bulk Import** | CSV & Excel import for loans and repayments |
| **Fuzzy matching** | Auto-matches employee names (rapidfuzz, threshold configurable) |
| **Reports** | Loan summary, repayment history, outstanding balances |
| **Export** | CSV and formatted Excel (.xlsx) |
| **Multi-user** | Role-based access (admin / manager / staff) |
| **Network modes** | Local SQLite, SMB/NFS share, or Flask REST server |
| **Audit log** | Every action is recorded with user and timestamp |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run with sample data
python app.py --seed

# 3. Login with default credentials
#    Username: admin   Password: admin123
```

---

## Folder Structure

```
employee_cash_advance/
├── app.py                    # Entry point
├── server.py                 # Optional Flask REST server
├── requirements.txt
├── setup.py
├── pyinstaller.spec
├── src/
│   ├── gui/                  # All Tkinter views
│   │   ├── main_window.py
│   │   ├── login_view.py
│   │   ├── branch_view.py
│   │   ├── client_view.py
│   │   ├── user_view.py
│   │   ├── employee_view.py
│   │   ├── loan_view.py
│   │   ├── reports_view.py
│   │   ├── import_view.py       ← multi-step import dialog
│   │   ├── network_settings_view.py
│   │   └── dialogs.py
│   ├── models/               # Domain dataclasses
│   ├── data/
│   │   ├── db_manager.py     # SQLite DAO + REST HTTP client
│   │   └── migrations/       # Incremental SQL files
│   ├── services/             # Business logic
│   │   ├── auth_service.py
│   │   ├── loan_service.py
│   │   ├── report_service.py
│   │   ├── user_service.py
│   │   └── import_service.py ← parsing, validation, fuzzy match, commit
│   └── utils/
│       ├── crypto.py         # bcrypt / PBKDF2 password hashing
│       ├── fuzzy_match.py    ← rapidfuzz wrapper
│       ├── validators.py
│       ├── helpers.py
│       └── logger.py
├── tests/
│   ├── test_loan_calculations.py
│   ├── test_auth.py
│   ├── test_db_manager.py
│   └── test_import_service.py
└── data_files/
    ├── seed_data.json
    ├── import_samples/       ← sample CSV/XLSX files
    └── import_logs/          ← auto-generated import logs
```

---

## Third-Party Packages

| Package | Version | Why |
|---|---|---|
| **bcrypt** | ≥4.0.1 | Secure password hashing with automatic salting |
| **rapidfuzz** | ≥3.0.0 | Fast, license-friendly fuzzy string matching for employee name lookup |
| **openpyxl** | ≥3.1.0 | Read/write Excel `.xlsx` files for import and export |
| **Flask** | ≥3.0.0 | Lightweight REST server (only required in server mode) |
| **Flask-HTTPAuth** | ≥4.8.0 | Bearer token auth for the REST API |
| **requests** | ≥2.31.0 | HTTP client used by Tkinter app in REST mode |
| **pandas** | ≥2.0.0 | Optional — faster CSV/XLSX parsing for large files |

---

## Network Modes

### A) Local / Network Share (POC)
All users access the same `.db` file on a shared drive (SMB/NFS).

1. Place `ecam.db` on a shared path accessible to all machines (e.g. `\\server\shared\ecam.db`).
2. In **Settings → Network/DB**, set mode to **Local** and update the DB path.
3. ⚠️ WAL mode is enabled automatically. Avoid >10 concurrent writers.

### B) REST Server (Recommended)
One machine runs `server.py`; all others connect over HTTP.

```bash
# On the server machine
pip install Flask Flask-HTTPAuth
python server.py --db /shared/ecam.db --token YOUR_SECRET_TOKEN --port 5000

# On each client
# Settings → Network/DB → REST Server
# URL: http://192.168.1.10:5000
# Token: YOUR_SECRET_TOKEN
```

---

## Import Feature

1. Click **📥 Import** in the sidebar.
2. **Step 1** — Select a CSV or Excel file and choose import type (Loans or Repayments).
3. **Step 2** — Map file columns to model fields (auto-detected where possible).
4. **Step 3** — Preview validation results. Employee names are fuzzy-matched (default threshold: 89%). Click **Fix Employee** on any row to manually pick one.
5. **Step 4** — Run a **Dry Run** to preview, or click **Import** to commit.

Sample files are in `data_files/import_samples/`.

---

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Or with unittest
python -m unittest discover tests/
```

---

## Building the Windows .exe

### Prerequisites
```bash
pip install pyinstaller
```

### Build
```bash
# Windows
build_scripts\build_exe.bat

# macOS / Linux
bash build_scripts/build_exe.sh
```

The executable is output to `dist/CashAdvanceManager.exe`.

### Manual command
```bash
pyinstaller pyinstaller.spec
```

### Notes
- The `data_files/` folder is bundled automatically.
- On first run the `.exe` will create `ecam.db` in its working directory.
- Run with `--seed` flag to pre-populate sample data: `CashAdvanceManager.exe --seed`

---

## Default Credentials

| Username | Password | Role |
|---|---|---|
| admin | admin123 | Admin — full access |
| manager | manager123 | Manager — approve/disburse |
| staff | staff123 | Staff — view/create only |

**Change all passwords immediately in a production environment.**

---

## PostgreSQL Migration

`db_manager.py` uses parameterised queries (`?` placeholders) throughout.
To migrate to PostgreSQL:

1. Replace `sqlite3` with `psycopg2` in `db_manager.py`.
2. Change `?` placeholders to `%s`.
3. Update `migrations/*.sql` — remove SQLite-specific pragmas.
4. Run `pg_restore` or re-run migrations against a Postgres DB.
