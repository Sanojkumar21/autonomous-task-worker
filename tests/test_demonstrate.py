"""A recorded demonstration becomes a skill with placeholders, never raw secrets."""
import tempfile
from pathlib import Path

from worker.context import CompanyContext
from worker.demonstrate import placeholderize, skill_from_events
from worker.memory.store import MemoryStore

EVENTS = [
    {"type": "page", "role": "document", "name": "Ledger ERP — sign in", "url": "/ledger/login", "title": "", "t": 1},
    {"type": "input", "role": "textbox", "name": "Username", "value": "ops.agent", "url": "/ledger/login", "title": "", "t": 2},
    {"type": "input", "role": "password", "name": "Password", "value": "••••", "url": "/ledger/login", "title": "", "t": 3},
    {"type": "click", "role": "button", "name": "Sign in", "href": "", "url": "/ledger/login", "title": "", "t": 4},
    {"type": "page", "role": "document", "name": "Ledger — new bill", "url": "/ledger/bills/new", "title": "", "t": 5},
    {"type": "input", "role": "select", "name": "Vendor", "value": "Orbit Office Supplies", "url": "/ledger/bills/new", "title": "", "t": 6},
    {"type": "input", "role": "textbox", "name": "Invoice number", "value": "OR-5521", "url": "/ledger/bills/new", "title": "", "t": 7},
    {"type": "input", "role": "textbox", "name": "Amount (INR)", "value": "6400.00", "url": "/ledger/bills/new", "title": "", "t": 8},
    {"type": "input", "role": "textbox", "name": "PO number", "value": "PO-7741", "url": "/ledger/bills/new", "title": "", "t": 9},
    {"type": "click", "role": "button", "name": "Save bill", "href": "", "url": "/ledger/bills/new", "title": "", "t": 10},
]


def test_placeholders_and_secret_masking():
    steps, params = placeholderize(EVENTS)
    assert params == {"username": "ops.agent", "vendor": "Orbit Office Supplies", "invoice_number": "OR-5521",
                      "amount": "6400.00", "po_number": "PO-7741"}
    joined = "\n".join(steps)
    assert "{invoice_number}" in joined and "{po_number}" in joined and "acme-ops" not in joined and "••••" not in joined


def test_skill_is_saved_with_workflow():
    store = MemoryStore(Path(tempfile.mkdtemp()))
    skill = skill_from_events(EVENTS, CompanyContext(), "record_supplier_invoice", "ledger", "Record a bill", store, who="priya")
    assert skill.system == "ledger" and skill.workflow[0].startswith("Use Ledger ERP")
    assert store.find_skills("record_supplier_invoice", "ledger")[0].id == skill.id
    assert "demonstration by priya" in skill.source_run
