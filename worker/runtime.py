"""The runtime executes the brain's actions and enforces the rules around them.

The brain (an LLM, or a scripted controller in tests) only ever proposes
actions. The runtime:

- drives the browser and returns what happened as text,
- keeps facts with provenance (`note_fact`),
- routes `ask_human` and approvals through the human channel,
- runs every write through the policy gate (`commit`), and
- tracks outcomes it could not confirm (a 5xx after a submit), so a blind
  retry is impossible.

Nothing here calls a model.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from worker.browser import Browser
from worker.context import CompanyContext
from worker.human import Human, NoHuman
from worker.policy import PolicyGate
from worker.types import Action, Approval, Assertion, Clarification, Fact, Observation, PolicyDecision, RunRecord, Step

TOOLS = {
    "navigate": {"url": "absolute URL or a path like /ledger/bills"},
    "click": {"id": "element id from the observation"},
    "type": {"id": "element id", "text": "text to enter (replaces the field's value)"},
    "select": {"id": "element id of a select", "option": "visible option text"},
    "check": {"id": "element id of a checkbox/radio"},
    "back": {},
    "read_pdf": {"url": "URL or path of a PDF link on the current site"},
    "note_fact": {"key": "e.g. invoice_number, pdf_total:<invoice>, duplicate_check:<invoice>", "value": "the value",
                  "source": "where you read it (URL or PDF name)"},
    "ask_human": {"question": "what you need decided", "options": "optional list of choices"},
    "commit": {"id": "element id of the submit button", "intent": "declared write: {type, system, vendor_name, vendor_gstin, "
               "invoice_number, amount_paise, due_date, po_number, approved_by}"},
    "look": {},
    "done": {"summary": "what was done, with evidence", "assertions": "list of {kind, system, entity, match, expect}"},
    "give_up": {"reason": "why the task cannot be completed safely"},
}


@dataclass
class ToolResult:
    text: str
    stop: bool = False
    status: str = ""
    policy: PolicyDecision | None = None
    image: bytes | None = None


class Runtime:
    def __init__(self, run: RunRecord, context: CompanyContext, browser: Browser, gate: PolicyGate,
                 human: Human | None = None, run_dir: Path | None = None):
        self.run = run
        self.ctx = context
        self.browser = browser
        self.gate = gate
        self.human = human or NoHuman()
        self.run_dir = run_dir
        self.last_observation: Observation | None = None
        self.pending_assertions: list[Assertion] = []

    # ---- helpers
    def _abs(self, url: str) -> str:
        if url.startswith("http"):
            return url
        return self.ctx.base_url + (url if url.startswith("/") else "/" + url)

    def observe(self) -> Observation:
        self.last_observation = self.browser.observe()
        return self.last_observation

    def add_fact(self, key: str, value, source: str, step: int) -> Fact:
        fact = Fact(key=key.strip(), value=str(value).strip(), source=source, step=step)
        self.run.facts.append(fact)
        return fact

    def system_of(self, obs: Observation | None) -> str:
        return self.ctx.system_for_url(obs.url) if obs else ""

    # ---- dispatch
    def execute(self, action: Action, step_index: int) -> ToolResult:
        handler = getattr(self, f"t_{action.tool}", None)
        if handler is None:
            return ToolResult(f"unknown tool '{action.tool}'. Tools: {', '.join(TOOLS)}")
        try:
            return handler(step_index, **action.args)
        except TypeError as e:
            return ToolResult(f"bad arguments for {action.tool}: {e}. Expected: {TOOLS.get(action.tool)}")

    # ---- browser tools
    def t_navigate(self, step, url=""):
        return ToolResult(self.browser.navigate(self._abs(str(url))))

    def t_click(self, step, id=None):
        return ToolResult(self.browser.click(int(id)))

    def t_type(self, step, id=None, text=""):
        return ToolResult(self.browser.type(int(id), str(text)))

    def t_select(self, step, id=None, option=""):
        return ToolResult(self.browser.select(int(id), str(option)))

    def t_check(self, step, id=None):
        return ToolResult(self.browser.check(int(id)))

    def t_back(self, step):
        return ToolResult(self.browser.go_back())

    def t_read_pdf(self, step, url=""):
        text = self.browser.fetch_pdf_text(self._abs(str(url)))
        if len(text) > 4000:
            text = text[:4000] + " …[truncated]"
        return ToolResult("PDF text:\n" + text)

    def t_look(self, step):
        return ToolResult("screenshot attached", image=self.browser.screenshot_bytes())

    # ---- knowledge tools
    def t_note_fact(self, step, key="", value="", source=""):
        if not key:
            return ToolResult("note_fact needs a key")
        src = source or (self.last_observation.url if self.last_observation else "unknown")
        fact = self.add_fact(key, value, src, step)
        return ToolResult(f"noted {fact.key} = {fact.value!r} (source: {fact.source})")

    def t_ask_human(self, step, question="", options=None):
        options = list(options or []) if not isinstance(options, str) else [options]
        self.run.usage.human_interventions += 1
        answer = self.human.clarify(str(question), options, context=self.run.request)
        self.run.clarifications.append(Clarification(step=step, question=str(question), options=options, answer=answer.text))
        if not answer.text:
            return ToolResult("no one is available to answer; stop and report what is missing with give_up",
                              stop=True, status="needs_clarification")
        self.add_fact(f"human_answer:{step}", answer.text, "human", step)
        return ToolResult(f"human answered: {answer.text}")

    # ---- the governed write
    def t_commit(self, step, id=None, intent=None):
        if not isinstance(intent, dict):
            return ToolResult("commit needs an 'intent' object describing the write (type, system, invoice_number, amount_paise, ...)")
        intent = dict(intent)
        intent.setdefault("system", self.system_of(self.last_observation))
        if "amount_paise" in intent and intent["amount_paise"] is not None:
            try:
                intent["amount_paise"] = int(round(float(intent["amount_paise"])))
            except (TypeError, ValueError):
                return ToolResult("intent.amount_paise must be an integer number of paise")
        mismatch = self._cross_check_form(intent)
        if mismatch:
            return ToolResult("commit refused: " + mismatch, policy=PolicyDecision(allowed=False, reasons=[mismatch],
                                                                                   rule_ids=["runtime.form_matches_intent"]))
        decision = self.gate.evaluate(intent, self.run)
        if decision.needs_approval:
            self.run.usage.human_interventions += 1
            answer = self.human.approve(intent, "; ".join(decision.reasons), context=self.run.request)
            granted = bool(answer.approved)
            self.run.approvals.append(Approval(step=step, intent=intent, reason="; ".join(decision.reasons),
                                               granted=granted, approver=answer.approver, note=answer.note))
            if answer.approved is None:
                return ToolResult("approval required but no approver is available; save as draft if possible and give_up "
                                  "with status blocked", policy=decision, stop=False)
            if not granted:
                return ToolResult(f"approval DENIED{(': ' + answer.note) if answer.note else ''}. Do not post this. "
                                  "Save as draft if the system allows it, then report.", policy=decision)
            return ToolResult(f"approval GRANTED by {answer.approver}{(' (' + answer.note + ')') if answer.note else ''} — "
                              f"fill the approval field with '{answer.approver}' and commit again.", policy=decision)
        if not decision.allowed:
            return ToolResult("commit refused by policy: " + "; ".join(decision.reasons), policy=decision)
        inv = (intent.get("invoice_number") or "").strip()
        result = self.browser.click(int(id))
        obs = self.observe()
        if obs.http_error and obs.http_error >= 500:
            if inv:
                self.add_fact(f"unknown_outcome:{inv}", "pending", obs.url, step)
            return ToolResult(f"{result}, but the server answered HTTP {obs.http_error}. The write MAY have gone through. "
                              f"Do not resubmit: open the list, check whether the record exists, and note_fact readback:{inv} "
                              "with what you found.", policy=decision)
        if inv and self.run.fact(f"unknown_outcome:{inv}") == "pending":
            self.add_fact(f"unknown_outcome:{inv}", "resolved", obs.url, step)
        return ToolResult(f"{result}; submitted. Now verify on the page that the record exists with the right values.",
                          policy=decision)

    def _cross_check_form(self, intent: dict) -> str:
        """The declared intent must agree with what is actually in the form."""
        obs = self.last_observation
        if not obs:
            return ""
        values = " ".join(e.value for e in obs.elements if e.role in ("textbox", "textarea", "select"))
        inv = (intent.get("invoice_number") or "").strip()
        if inv and inv.lower() not in values.lower() and intent.get("type") in ("create_bill", "record_payable"):
            # the review page of a wizard shows values as text rather than fields
            if inv.lower() not in obs.text.lower():
                return f"the form does not contain invoice number '{inv}'"
        approver = (intent.get("approved_by") or "").strip()
        if approver and approver.lower() not in (values + " " + obs.text).lower():
            return f"the form does not show the approver '{approver}'; enter it in the approval field first"
        amount = intent.get("amount_paise")
        if amount is not None and intent.get("type") in ("create_bill", "record_payable"):
            rupees = int(amount) / 100
            candidates = {f"{rupees:,.2f}", f"{rupees:.2f}", f"{rupees:,.0f}" if rupees.is_integer() else "", f"{int(rupees)}" if rupees.is_integer() else ""}
            haystack = (values + " " + obs.text).replace("Rs ", "")
            if not any(c and c in haystack for c in candidates):
                return f"the form does not contain the amount {rupees:,.2f}"
        return ""

    # ---- terminal tools
    def t_done(self, step, summary="", assertions=None):
        parsed = []
        for a in assertions or []:
            try:
                parsed.append(Assertion(**a) if isinstance(a, dict) else a)
            except Exception as e:  # pydantic validation
                return ToolResult(f"bad assertion {a!r}: {e}")
        if not parsed:
            return ToolResult("done needs at least one assertion describing what must now be true in a system of record "
                              "(or kind='absent'/'count' for tasks that must not write)")
        self.run.assertions = parsed
        self.run.final_summary = str(summary)
        return ToolResult("assertions recorded; verification will decide the status", stop=True, status="claimed_done")

    def t_give_up(self, step, reason=""):
        self.run.final_summary = str(reason)
        return ToolResult(f"stopped: {reason}", stop=True, status="gave_up")
