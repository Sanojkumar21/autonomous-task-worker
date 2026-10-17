"""End-to-end runs against the live sandbox with the scripted brain.

Skipped unless the sandbox is up (make serve). These prove the runtime's
guarantees: verified completion, duplicate refusal, approval flow, and
recovery from commit-then-502 and expired sessions.
"""
import tempfile
from pathlib import Path

import httpx
import pytest

from worker.brains.scripted import ScriptedBrain
from worker.context import CompanyContext
from worker.human import ScriptedHuman
from worker.loop import Worker
from worker.memory.store import MemoryStore

BASE = "http://127.0.0.1:8000"


def sandbox_up():
    try:
        return httpx.get(f"{BASE}/admin/api/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not sandbox_up(), reason="sandbox not running (make serve)")


def reset(chaos=None):
    httpx.post(f"{BASE}/admin/api/reset")
    httpx.post(f"{BASE}/admin/api/chaos", json={"enabled": False, **(chaos or {})})


def make_worker(human=None):
    ctx = CompanyContext(base_url=BASE)
    mem = MemoryStore(Path(tempfile.mkdtemp()), enabled=False)
    return Worker(ScriptedBrain(), ctx, mem, human or ScriptedHuman([{"match": ".*", "approve": True, "approver": "priya.manager"}]),
                  runs_dir=Path(tempfile.mkdtemp()), learn=False)


def bills():
    return httpx.get(f"{BASE}/admin/api/snapshot").json()["ledger_bills"]


def test_hero_task_verified():
    reset()
    run = make_worker().run("Find the latest invoice from Northwind Supplies, enter it into Ledger, and tell me once it is done")
    assert run.final_status == "completed" and run.verification.status == "completed"
    assert [b for b in bills() if b["invoice_number"] == "NW-1043-R" and b["amount_paise"] == 5980000 and b["status"] == "posted"]
    assert not [b for b in bills() if b["invoice_number"] == "NW-1043"]


def test_duplicate_is_reported_not_recorded():
    reset()
    run = make_worker().run("Enter Kestrel Logistics' invoice KL-0915 into Ledger")
    assert run.final_status == "completed" and "already recorded" in run.final_summary
    assert len([b for b in bills() if b["invoice_number"] == "KL-0915"]) == 1


def test_approval_required_and_recorded():
    reset()
    run = make_worker().run("Record the latest invoice from Meridian Metals in Ledger")
    assert run.final_status == "completed" and run.approvals and run.approvals[0].granted
    row = [b for b in bills() if b["invoice_number"] == "MM-0882"][0]
    assert row["approved_by"] == "priya.manager" and row["status"] == "posted"


def test_denied_approval_blocks_posting():
    reset()
    human = ScriptedHuman([{"match": "MM-0882", "approve": False, "approver": "priya.manager", "note": "hold"}])
    run = make_worker(human).run("Record the latest invoice from Meridian Metals in Ledger")
    assert run.final_status == "blocked"
    assert not [b for b in bills() if b["invoice_number"] == "MM-0882" and b["status"] == "posted"]


def test_commit_then_502_creates_no_duplicate():
    reset({"enabled": True, "commit_then_502": 1.0, "seed": 3})
    run = make_worker().run("Please record the latest invoice from Orbit Office Supplies in Ledger")
    assert run.final_status == "completed"
    assert len([b for b in bills() if b["invoice_number"] == "OR-5521"]) == 1
    assert any(f.key.startswith("readback:") for f in run.facts)


def test_session_expiry_and_ui_drift_are_survived():
    reset({"enabled": True, "session_expiry_every": 5, "ui_drift": True, "seed": 5})
    run = make_worker().run("Record Brightline Components' invoice BL-2207 in Ledger")
    assert run.final_status == "completed"
    assert [b for b in bills() if b["invoice_number"] == "BL-2207" and b["amount_paise"] == 3480000]


def test_nova_unseen_app():
    reset()
    run = make_worker().run("Record the latest invoice from Northwind Supplies in NovaBooks")
    assert run.final_status == "completed"
    nova = httpx.get(f"{BASE}/admin/api/snapshot").json()["nova_payables"]
    assert [p for p in nova if p["reference"] == "NW-1043-R" and p["total_paise"] == 5980000 and p["state"] == "recorded"]
