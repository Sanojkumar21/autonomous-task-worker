"""SQLite storage for the simulated company, Acme Robotics Pvt Ltd.

One database file holds every system the worker can touch: the supplier
portal, the Ledger ERP, the NovaBooks ERP (the "unseen" app used to test
generalization), the mailbox and an append-only audit log.

The worker never opens this file. It only sees web pages, exactly like a human
clerk. The independent verifier reads it through the admin API, which is a
separate channel from the one the worker acts through.
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

# COMPANY_VAR lets tests and parallel sandboxes keep their own database.
VAR = Path(os.environ.get("COMPANY_VAR") or Path(__file__).resolve().parent.parent / "var")
DB_PATH = VAR / "company.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT NOT NULL, system TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL,
    PRIMARY KEY (username, system)
);
-- suppliers as the portal knows them
CREATE TABLE IF NOT EXISTS portal_vendors (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, gstin TEXT NOT NULL, email TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS portal_invoices (
    id INTEGER PRIMARY KEY, vendor_id INTEGER NOT NULL, number TEXT NOT NULL,
    issued_on TEXT NOT NULL, listed_amount_paise INTEGER NOT NULL, currency TEXT NOT NULL,
    status TEXT NOT NULL, pdf_name TEXT NOT NULL, supersedes TEXT
);
-- the Ledger ERP has its own vendor master (with a stale near-duplicate)
CREATE TABLE IF NOT EXISTS ledger_vendors (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, gstin TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS ledger_bills (
    id INTEGER PRIMARY KEY, vendor_id INTEGER NOT NULL, invoice_number TEXT NOT NULL,
    amount_paise INTEGER NOT NULL, currency TEXT NOT NULL DEFAULT 'INR', due_date TEXT NOT NULL,
    po_number TEXT, status TEXT NOT NULL, approved_by TEXT, memo TEXT,
    created_by TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
-- NovaBooks: a different ERP with different words and a different flow
CREATE TABLE IF NOT EXISTS nova_suppliers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, tax_id TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS nova_payables (
    id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL, reference TEXT NOT NULL,
    total_paise INTEGER NOT NULL, currency TEXT NOT NULL DEFAULT 'INR', pay_by TEXT NOT NULL,
    order_ref TEXT, state TEXT NOT NULL, authorised_by TEXT, note TEXT,
    created_by TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mail (
    id INTEGER PRIMARY KEY, sender TEXT NOT NULL, recipient TEXT NOT NULL,
    subject TEXT NOT NULL, body TEXT NOT NULL, received_at TEXT NOT NULL,
    folder TEXT NOT NULL DEFAULT 'inbox', read INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, system TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, detail TEXT NOT NULL
);
"""

TABLES = ["users", "portal_vendors", "portal_invoices", "ledger_vendors", "ledger_bills",
          "nova_suppliers", "nova_payables", "mail", "audit"]


def connect():
    VAR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init():
    with tx() as con:
        con.executescript(SCHEMA)


def audit(con, system, actor, action, **detail):
    con.execute(
        "INSERT INTO audit (ts, system, actor, action, detail) VALUES (?, ?, ?, ?, ?)",
        (time.time(), system, actor, action, json.dumps(detail, sort_keys=True)),
    )


def rows(con, sql, *args):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def one(con, sql, *args):
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None


def snapshot():
    """Every table as plain dicts. Used by the admin API for the verifier."""
    with tx() as con:
        return {t: rows(con, f"SELECT * FROM {t} ORDER BY rowid") for t in TABLES}
