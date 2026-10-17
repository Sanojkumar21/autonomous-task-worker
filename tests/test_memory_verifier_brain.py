"""Memory persistence, the verifier's judgement, and the LLM brain's plumbing."""
import tempfile
from pathlib import Path

from worker.brain import BrainState
from worker.brains.llm_brain import LLMBrain
from worker.brains.scripted import ScriptedBrain
from worker.context import CompanyContext
from worker.llm.base import extract_json
from worker.llm.fake import FakeLLM
from worker.memory.store import MemoryStore, Rule, Skill
from worker.types import Assertion, Element, Observation, RunRecord
from worker.verifier import Verifier


def test_memory_roundtrip_and_supersede():
    store = MemoryStore(Path(tempfile.mkdtemp()))
    store.add_skill(Skill(name="a", intent="record_supplier_invoice", system="ledger", trigger="t", workflow=["w"], procedure=["p"]))
    store.add_skill(Skill(name="b", intent="record_supplier_invoice", system="ledger", trigger="t", workflow=["w2"], procedure=["p2"]))
    assert [s.name for s in store.skills] == ["b"]  # newer verified skill replaces the old one
    assert store.find_skills("record_supplier_invoice", "nova")[0].system == "ledger"  # workflow transfers
    store.add_rule(Rule(kind="policy", text="1L", structured={"approval_threshold_paise": 10000000}))
    store.add_rule(Rule(kind="policy", text="50k", structured={"approval_threshold_paise": 5000000}))
    active = [r for r in store.active_rules() if "approval_threshold_paise" in r.structured]
    assert len(active) == 1 and active[0].text == "50k"
    again = MemoryStore(store.dir)
    assert len(again.skills) == 1 and len(again.rules) == 2 and "50k" in again.describe()


def test_extract_json_tolerates_prose_and_fences():
    assert extract_json('Sure! ```json\n{"a": 1}\n```')["a"] == 1
    assert extract_json('text {"a": {"b": [1, 2]}} more')["a"]["b"] == [1, 2]
    assert extract_json("no json") is None


class FakeVerifier(Verifier):
    def __init__(self, snap, audit):
        super().__init__("http://x")
        self._snap, self._audit = snap, audit

    def snapshot(self):
        return self._snap

    def audit(self, since):
        return self._audit


SNAP = {"ledger_vendors": [{"id": 11, "name": "Northwind Supplies", "gstin": "07AAACN1234F1Z5", "active": 1}],
        "ledger_bills": [{"id": 4, "vendor_id": 11, "invoice_number": "NW-1043-R", "amount_paise": 5980000, "due_date": "2026-11-08",
                          "po_number": "PO-7734", "status": "posted", "approved_by": None}],
        "nova_suppliers": [], "nova_payables": [], "mail": [], "portal_invoices": []}


def test_verifier_checks_and_unexplained_writes():
    audit = [{"action": "create_bill", "system": "ledger", "detail": '{"invoice_number": "NW-1043-R"}'},
             {"action": "create_bill", "system": "ledger", "detail": '{"invoice_number": "ZZ-9"}'}]
    run = RunRecord(run_id="t", request="x")
    run.assertions = [Assertion(kind="exists", system="ledger", entity="bill", match={"invoice_number": "NW-1043-R"},
                                expect={"amount_paise": 5980000, "status": "posted"})]
    v = FakeVerifier(SNAP, audit).verify(run)
    assert v.status == "completed_with_exceptions" and v.unexplained_changes[0]["invoice_number"] == "ZZ-9"
    run.assertions[0].expect["amount_paise"] = 1
    assert FakeVerifier(SNAP, audit[:1]).verify(run).status == "failed"
    run.assertions = [Assertion(kind="count", system="ledger", entity="bill", match={"invoice_number": "NW-1043-R"}, expect={"count": 1})]
    assert FakeVerifier(SNAP, []).verify(run).status == "completed"
    run.assertions = []
    assert FakeVerifier(SNAP, []).verify(run).status == "unverified"


def test_llm_brain_plumbing():
    ctx = CompanyContext()
    mem = MemoryStore(Path(tempfile.mkdtemp()))
    fake = FakeLLM(replies=[
        {"intent": "record_supplier_invoice", "summary": "s", "target_system": "ledger", "params": {"vendor": "Northwind Supplies"}, "questions": []},
        {"milestones": [{"id": "M1", "title": "Find", "done_when": "noted"}, {"id": "M2", "title": "Record", "done_when": "saved", "writes": True}]},
        {"thought": "go", "milestone": "M1", "action": {"tool": "navigate", "args": {"url": "/portal/invoices"}}},
        "garbage", {"thought": "retry", "milestone": "M2", "action": {"tool": "done", "args": {"summary": "x", "assertions": []}}},
        {"rules": [{"kind": "policy", "text": "50k", "structured": {"approval_threshold_paise": "5000000"}}, {"kind": "guideline", "text": "check mail"}]},
    ])
    brain = LLMBrain(fake)
    c = brain.understand("Record Northwind's latest invoice in Ledger", ctx, mem)
    run = RunRecord(run_id="t", request="x", contract=c)
    run.milestones = brain.plan(c, ctx, mem, [])
    obs = Observation(url="http://127.0.0.1:8000/", elements=[Element(id=1, role="link", name="Supplier Portal", href="/portal")])
    thought, action = brain.decide(BrainState(run=run, context=ctx, memory=mem, observation=obs))
    assert action.tool == "navigate" and run.milestones[0].status == "active"
    thought, action = brain.decide(BrainState(run=run, context=ctx, memory=mem, observation=obs))
    assert action.tool == "done" and run.milestones[0].status == "done" and run.milestones[1].status == "done"
    rules = brain.extract_rules("From now on bills over 50,000 need my approval", "priya.manager", None, ctx)
    assert rules[0].structured["approval_threshold_paise"] == 5000000 and rules[1].kind == "guideline"
    assert "Company handbook" in fake.prompts[0][0]


def test_scripted_brain_rules():
    brain = ScriptedBrain()
    rules = brain.extract_rules("From now on bills over 50,000 need my approval before posting.", "priya.manager", None, CompanyContext())
    assert rules[0].structured["approval_threshold_paise"] == 5000000
    rules = brain.extract_rules("Don't use 'Northwind Supplies Ltd' in Ledger; use 'Northwind Supplies' (GSTIN 07AAACN1234F1Z5).", "x", None, CompanyContext())
    assert rules[0].structured == {"avoid_vendor": "Northwind Supplies Ltd", "use_instead": "Northwind Supplies"}
