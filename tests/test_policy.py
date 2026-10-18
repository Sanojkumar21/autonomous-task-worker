"""The policy gate decides writes; the model only proposes them."""
from worker.memory.store import Rule
from worker.policy import PolicyGate, load_policy
from worker.types import Approval, Fact, RunRecord


def make_run(facts=None, approvals=None):
    run = RunRecord(run_id="t", request="x")
    for i, (k, v) in enumerate(facts or []):
        run.facts.append(Fact(key=k, value=v, source="test", step=i))
    run.approvals = approvals or []
    return run


INTENT = {"type": "create_bill", "system": "ledger", "vendor_name": "Northwind Supplies", "invoice_number": "NW-1043-R",
          "amount_paise": 5980000, "due_date": "2026-11-08", "po_number": "PO-7734"}


def test_write_needs_facts():
    gate = PolicyGate(load_policy())
    d = gate.evaluate(INTENT, make_run())
    assert not d.allowed and any("duplicate_check" in r for r in d.reasons) and any("pdf_total" in r for r in d.reasons)


def test_duplicate_blocks():
    gate = PolicyGate(load_policy())
    run = make_run([("duplicate_check:NW-1043-R", "exists: bill #4"), ("pdf_total:NW-1043-R", "5980000")])
    d = gate.evaluate(INTENT, run)
    assert not d.allowed and "duplicate" in d.reasons[0]


def test_amount_must_match_pdf():
    gate = PolicyGate(load_policy())
    run = make_run([("duplicate_check:NW-1043-R", "none"), ("pdf_total:NW-1043-R", "6200000")])
    d = gate.evaluate(INTENT, run)
    assert not d.allowed and "does not match the PDF" in d.reasons[0]


def test_allowed_below_threshold():
    gate = PolicyGate(load_policy())
    run = make_run([("duplicate_check:NW-1043-R", "none"), ("pdf_total:NW-1043-R", "5980000")])
    d = gate.evaluate(INTENT, run)
    assert d.allowed and not d.needs_approval


def test_approval_flow_above_threshold():
    gate = PolicyGate(load_policy())
    big = {**INTENT, "invoice_number": "MM-0882", "amount_paise": 23450000}
    run = make_run([("duplicate_check:MM-0882", "none"), ("pdf_total:MM-0882", "23450000")])
    d = gate.evaluate(big, run)
    assert d.needs_approval and not d.allowed
    run.approvals.append(Approval(step=5, intent=big, reason="threshold", granted=True, approver="priya.manager"))
    d = gate.evaluate(big, run)  # approved but approver not recorded in the form yet
    assert not d.allowed and "fill the approval field" in d.reasons[0]
    d = gate.evaluate({**big, "approved_by": "priya.manager"}, run)
    assert d.allowed


def test_learned_threshold_and_vendor_rules():
    rules = [Rule(kind="policy", text="50k", structured={"approval_threshold_paise": 5000000}),
             Rule(kind="fact", text="stale", structured={"avoid_vendor": "Northwind Supplies Ltd", "use_instead": "Northwind Supplies"})]
    gate = PolicyGate(load_policy(), rules)
    run = make_run([("duplicate_check:NW-1043-R", "none"), ("pdf_total:NW-1043-R", "5980000")])
    d = gate.evaluate(INTENT, run)
    assert d.needs_approval and rules[0].id in d.rule_ids[0]
    d = gate.evaluate({**INTENT, "vendor_name": "Northwind Supplies Ltd"}, run)
    assert not d.allowed and "must not be used" in d.reasons[0]


def test_readback_required_after_unknown_outcome():
    gate = PolicyGate(load_policy())
    run = make_run([("duplicate_check:NW-1043-R", "none"), ("pdf_total:NW-1043-R", "5980000"), ("unknown_outcome:NW-1043-R", "pending")])
    d = gate.evaluate(INTENT, run)
    assert not d.allowed and "unknown outcome" in d.reasons[0]
    run.facts.append(Fact(key="readback:NW-1043-R", value="not found", source="t", step=9))
    assert gate.evaluate(INTENT, run).allowed


def test_forbidden_and_non_governed():
    gate = PolicyGate(load_policy())
    assert not gate.evaluate({"type": "delete"}, make_run()).allowed
    assert gate.evaluate({"type": "read"}, make_run()).allowed


def test_missing_type_is_still_governed():
    gate = PolicyGate(load_policy())
    intent = {k: v for k, v in INTENT.items() if k != "type"}
    d = gate.evaluate(intent, make_run())
    assert not d.allowed and any("pdf_total" in r for r in d.reasons)
    run = make_run([("duplicate_check:NW-1043-R", "none"), ("pdf_total:NW-1043-R", "5980000")])
    assert gate.evaluate(dict(intent), run).allowed
