"""The LLM brain's full path (prompt → JSON → runtime → verifier) without a model.

A fake model answers every prompt by delegating to the scripted controller
and wrapping its decision in the JSON the LLM brain expects. This proves the
prompt plumbing, JSON parsing, milestone bookkeeping, assertion handling and
learning hooks work end to end against the live sandbox, so a real model only
has to be good at deciding, not at fitting the harness.
"""
import json
import os
import re
import tempfile
from pathlib import Path

import httpx
import pytest

from worker.brain import BrainState
from worker.brains.llm_brain import LLMBrain
from worker.brains.scripted import ScriptedBrain
from worker.context import CompanyContext
from worker.human import ScriptedHuman
from worker.llm.fake import FakeLLM
from worker.loop import Worker
from worker.memory.store import MemoryStore

BASE = os.environ.get("TEST_COMPANY_URL") or os.environ.get("COMPANY_URL", "http://127.0.0.1:8000")


def sandbox_up():
    try:
        return httpx.get(f"{BASE}/admin/api/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not sandbox_up(), reason=f"sandbox not running at {BASE}")


class DelegatingModel:
    """Answers understand/plan/decide/distill prompts using the scripted brain."""

    def __init__(self, ctx, memory):
        self.sb = ScriptedBrain()
        self.ctx, self.memory = ctx, memory
        self.run = None
        self.state = None

    def __call__(self, system, messages):
        user = messages[-1]["content"]
        if "Work out what this request means" in user:
            req = re.search(r'Request from the ops team: "(.*?)"', user).group(1)
            c = self.sb.understand(req, self.ctx, self.memory)
            return c.model_dump()
        if "Write 3 to 6 milestones" in user:
            return {"milestones": [m.model_dump() for m in self.sb.plan(self.run.contract, self.ctx, self.memory, [])]}
        if "Decide the single next action" in user:
            thought, action = self.sb.decide(self.state)
            return {"thought": thought, "milestone": "M1", "action": {"tool": action.tool, "args": action.args}}
        if "Turn it into a reusable skill" in user:
            sk = self.sb.distill_skill(self.run, self.ctx)
            return {"name": sk.name, "trigger": sk.trigger, "workflow": sk.workflow, "procedure": sk.procedure,
                    "pitfalls": sk.pitfalls, "verification": sk.verification, "params": sk.params}
        if "Extract durable rules" in user:
            return {"rules": [{"kind": "guideline", "text": "check mail"}]}
        return {"thought": "?", "action": {"tool": "give_up", "args": {"reason": "unknown prompt"}}}


class SpyBrain(LLMBrain):
    """LLMBrain that lets the delegating model see the live run/state."""

    def __init__(self, llm, model):
        super().__init__(llm)
        self._dm = model

    def plan(self, contract, context, memory, skills):
        return super().plan(contract, context, memory, skills)

    def decide(self, state):
        self._dm.run, self._dm.state = state.run, state
        return super().decide(state)

    def distill_skill(self, run, context):
        self._dm.run = run
        return super().distill_skill(run, context)


def test_llm_brain_end_to_end_with_fake_model():
    httpx.post(f"{BASE}/admin/api/reset")
    ctx = CompanyContext(base_url=BASE)
    memory = MemoryStore(Path(tempfile.mkdtemp()))
    dm = DelegatingModel(ctx, memory)
    fake = FakeLLM(responder=dm)
    brain = SpyBrain(fake, dm)
    # the planner needs the contract before plan(); hook it through understand()
    orig_understand = brain.understand

    def understand(request, context, mem):
        c = orig_understand(request, context, mem)
        from worker.types import RunRecord
        dm.run = RunRecord(run_id="x", request=request, contract=c)
        return c
    brain.understand = understand
    worker = Worker(brain, ctx, memory, ScriptedHuman([{"match": ".*", "approve": True, "approver": "priya.manager"}]),
                    runs_dir=Path(tempfile.mkdtemp()), learn=True)
    run = worker.run("Record the latest invoice from Meridian Metals in Ledger")
    assert run.final_status == "completed", run.final_summary
    assert run.usage.llm_calls > 10 and run.approvals and run.approvals[0].granted
    assert run.milestones and run.milestones[0].status in ("active", "done")
    # learning hooks ran through the LLM brain's prompts
    assert memory.skills and memory.skills[0].intent == "record_supplier_invoice"
    snap = httpx.get(f"{BASE}/admin/api/snapshot").json()
    row = [b for b in snap["ledger_bills"] if b["invoice_number"] == "MM-0882"][0]
    assert row["approved_by"] == "priya.manager" and row["status"] == "posted"
    # the system prompt carries the handbook, systems and policy; the step prompt carries the observation
    sys_prompt, msgs, _ = fake.prompts[-2]
    assert "Company handbook" in sys_prompt and "INTERACTIVE ELEMENTS" in msgs[0]["content"]
