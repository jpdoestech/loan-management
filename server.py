"""
Optional Flask REST server — run this on a shared machine so multiple
Tkinter clients can access one central SQLite database over HTTP.

Usage:
    pip install Flask Flask-HTTPAuth
    python server.py --db path/to/ecam.db --token mysecrettoken --port 5000

Then set clients to REST mode pointing at http://<server-ip>:5000
with the same token.
"""
from __future__ import annotations
import argparse
import sqlite3
from typing import Any, Dict, List

try:
    from flask import Flask, jsonify, request, g
    from flask_httpauth import HTTPTokenAuth
    _FLASK = True
except ImportError:
    _FLASK = False
    raise SystemExit("Flask and Flask-HTTPAuth are required: pip install Flask Flask-HTTPAuth")

app = Flask(__name__)
auth = HTTPTokenAuth(scheme="Bearer")
_DB_PATH: str = "data_files/ecam.db"
_TOKEN: str = "changeme"


@auth.verify_token
def verify_token(token: str) -> bool:
    return token == _TOKEN


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db:
        db.close()


@app.get("/ping")
@auth.login_required
def ping():
    return jsonify({"status": "ok", "message": "ECAM server running"})


@app.post("/query")
@auth.login_required
def query():
    data = request.get_json(force=True)
    sql: str = data.get("sql", "")
    params: list = data.get("params", [])
    # Only allow SELECT
    if not sql.strip().upper().startswith("SELECT"):
        return jsonify({"error": "Only SELECT queries allowed via /query"}), 403
    cur = get_db().execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    return jsonify({"rows": rows})


@app.post("/execute")
@auth.login_required
def execute():
    data = request.get_json(force=True)
    sql: str = data.get("sql", "")
    params: list = data.get("params", [])
    # Disallow SELECT through execute endpoint
    if sql.strip().upper().startswith("SELECT"):
        return jsonify({"error": "Use /query for SELECT statements"}), 403
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return jsonify({"lastrowid": cur.lastrowid, "rowcount": cur.rowcount})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ECAM REST Server")
    parser.add_argument("--db", default="data_files/ecam.db", help="Path to SQLite DB")
    parser.add_argument("--token", default="changeme", help="API bearer token")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    _DB_PATH = args.db
    _TOKEN = args.token

    # Run migrations on start
    from src.data.db_manager import DBManager
    db = DBManager(db_path=args.db)
    db.initialize()
    db.close()

    print(f"ECAM Server starting on {args.host}:{args.port}")
    print(f"DB: {args.db}")
    app.run(host=args.host, port=args.port, debug=False)
