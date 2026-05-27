"""
Employee Cash Advance Manager
Entry point — initialises the database and launches the Tkinter GUI.

Usage:
    python app.py
    python app.py --reset-db      # delete and re-create the database
    python app.py --seed          # seed sample data after init
"""
from __future__ import annotations
import argparse
import os
import sys

# Ensure the project root is on sys.path when running as a script or .exe
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk

from src.data.db_manager import DBManager
from src.gui.main_window import MainWindow
from src.utils.logger import setup_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Employee Cash Advance Manager")
    parser.add_argument("--reset-db", action="store_true",
                        help="Delete and re-create the database")
    parser.add_argument("--seed", action="store_true",
                        help="Seed sample data on startup")
    return parser.parse_args()


def seed_data(db: DBManager) -> None:
    """Insert sample branches, employees, and an admin user from seed_data.json."""
    import json
    seed_path = os.path.join(os.path.dirname(__file__), "data_files", "seed_data.json")
    if not os.path.exists(seed_path):
        return
    with open(seed_path, encoding="utf-8") as f:
        data = json.load(f)

    from src.utils.crypto import hash_password

    for b in data.get("branches", []):
        try:
            db.create_branch(b["name"], b["code"], b.get("address"))
        except Exception:
            pass  # already exists

    for e in data.get("employees", []):
        try:
            db.create_employee(
                e["name"], e.get("employee_code"), e.get("department"),
                e.get("position"), e.get("email"), e.get("phone"),
                None, None,
            )
        except Exception:
            pass

    for u in data.get("users", []):
        try:
            db.create_user(u["username"], hash_password(u["password"]),
                           u.get("full_name", ""), u.get("role", "staff"), None)
        except Exception:
            pass


def main() -> None:
    args = parse_args()
    log = setup_logger()
    log.info("Starting Employee Cash Advance Manager")

    db = DBManager()

    if args.reset_db:
        db_path = db.db_path
        if os.path.exists(db_path):
            os.remove(db_path)
            log.info("Database deleted: %s", db_path)

    db.initialize()

    if args.seed:
        seed_data(db)
        log.info("Sample data seeded")

    root = tk.Tk()
    root.withdraw()  # hidden until login succeeds

    try:
        style = ttk.Style(root)
        style.theme_use("clam")
    except Exception:
        pass

    MainWindow(root, db)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    import tkinter.ttk as ttk  # noqa: F401 — needed for style in main()
    main()
