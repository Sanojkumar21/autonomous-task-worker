"""The simulated company behaves like a real one: logins, validation, chaos."""
import pytest
from fastapi.testclient import TestClient

from company import chaos, db
from company.app import app
from company.seed import seed


@pytest.fixture()
def client():
    seed(quiet=True)
    chaos.save(dict(chaos.DEFAULT))
    with TestClient(app, follow_redirects=False) as c:
        yield c
    chaos.save(dict(chaos.DEFAULT))


def login(c, system, user="ops.agent", pw="acme-ops-2026"):
    r = c.post(f"/{system}/login", data={"username": user, "password": pw, "next": f"/{system}/"})
    assert r.status_code == 303


def test_each_system_requires_login(client):
    for path in ("/portal/invoices", "/ledger/bills", "/nova/payables", "/mail/inbox"):
        r = client.get(path)
        assert r.status_code == 303 and "/login" in r.headers["location"]


def test_login_redirect_keeps_query(client):
    r = client.get("/ledger/bills?q=NW-1043-R")
    assert "next=/ledger/bills%3Fq%3DNW-1043-R" in r.headers["location"]


def test_portal_lists_revision_and_pdf(client):
    login(client, "portal")
    r = client.get("/portal/invoices?vendor=Northwind")
    assert "NW-1043-R" in r.text and "superseded" in r.text
    r = client.get("/portal/invoices/3")
    assert "supersedes NW-1043" in r.text
    assert client.get("/portal/invoices/3/pdf").headers["content-type"].startswith("application/pdf")


def test_ledger_create_and_validate(client):
    login(client, "ledger")
    r = client.post("/ledger/bills/new", data={"vendor_id": "11", "invoice_number": "NW-1043-R", "amount": "59,800.00",
                                              "due_date": "2026-11-08", "po_number": "PO-7734", "action": "post"})
    assert r.status_code == 303
    r = client.get(r.headers["location"])
    assert "posted" in r.text and "59,800.00" in r.text
    bad = client.post("/ledger/bills/new", data={"vendor_id": "", "invoice_number": "", "amount": "x", "due_date": "y"})
    assert bad.status_code == 400 and "Choose a vendor" in bad.text
    # the ERP does not enforce duplicates: that is the clerk's (worker's) job
    dup = client.post("/ledger/bills/new", data={"vendor_id": "14", "invoice_number": "KL-0915", "amount": "18750",
                                                "due_date": "2026-10-28", "action": "post"})
    assert dup.status_code == 303
    with db.tx() as con:
        assert con.execute("SELECT COUNT(*) FROM ledger_bills WHERE invoice_number='KL-0915'").fetchone()[0] == 2


def test_nova_wizard(client):
    login(client, "nova")
    r = client.post("/nova/payables/record/details", data={"supplier_id": "26"})
    assert "step 2" in r.text
    bad = client.post("/nova/payables/record/review", data={"supplier_id": "26", "reference": "OR-5521", "total": "6400", "pay_by": "2026-10-21"})
    assert bad.status_code == 400 and "dd/mm/yyyy" in bad.text
    ok = client.post("/nova/payables/record/review", data={"supplier_id": "26", "reference": "OR-5521", "total": "6400", "pay_by": "21/10/2026"})
    assert "step 3" in ok.text
    r = client.post("/nova/payables/record/confirm", data={"supplier_id": "26", "reference": "OR-5521", "total_paise": "640000",
                                                           "pay_by_iso": "2026-10-21", "state": "recorded"})
    assert r.status_code == 303
    snap = client.get("/admin/api/snapshot").json()
    assert any(p["reference"] == "OR-5521" and p["state"] == "recorded" for p in snap["nova_payables"])


def test_chaos_commit_then_502_still_writes(client):
    login(client, "ledger")
    chaos.save({"enabled": True, "commit_then_502": 1.0})
    r = client.post("/ledger/bills/new", data={"vendor_id": "15", "invoice_number": "OR-5521", "amount": "6400",
                                              "due_date": "2026-10-21", "action": "post"})
    assert r.status_code == 502
    snap = client.get("/admin/api/snapshot").json()
    assert any(b["invoice_number"] == "OR-5521" for b in snap["ledger_bills"])


def test_chaos_ui_drift_and_session_expiry(client):
    login(client, "ledger")
    chaos.save({"enabled": True, "ui_drift": True})
    assert "Invoice total (INR)" in client.get("/ledger/bills/new").text
    chaos.save({"enabled": True, "session_expiry_every": 2})
    codes = [client.get("/ledger/bills").status_code for _ in range(4)]
    assert 303 in codes


def test_admin_reset_and_audit(client):
    login(client, "ledger")
    client.post("/ledger/bills/new", data={"vendor_id": "15", "invoice_number": "X-1", "amount": "1", "due_date": "2026-10-21", "action": "post"})
    audit = client.get("/admin/api/audit").json()
    assert any(a["action"] == "create_bill" for a in audit)
    client.post("/admin/api/reset")
    assert len(client.get("/admin/api/snapshot").json()["ledger_bills"]) == 3
