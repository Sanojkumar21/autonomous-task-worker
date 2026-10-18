"""Data types shared by the worker's parts.

Everything the worker knows about a run is data, not prose: observations,
actions, facts with provenance, assertions, approvals. That is what makes the
run auditable and lets code (not the model) decide when the work is done.
"""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field


class Element(BaseModel):
    id: int
    role: str                      # link, button, textbox, select, checkbox, radio, ...
    name: str = ""                 # accessible name (label, aria-label, text, placeholder)
    value: str = ""                # current value for inputs
    href: str = ""
    options: list[str] = []        # for selects
    checked: bool | None = None
    disabled: bool = False
    nav: bool = False              # inside the site navigation: moves between pages, never part of a form

    def line(self) -> str:
        parts = [f"[{self.id}] {self.role} \"{self.name}\"" + (" (nav)" if self.nav else "")]
        if self.role in ("textbox", "select", "textarea", "password") or self.value:
            parts.append(f'= "{self.value}"')
        if self.options:
            parts.append("options: " + ", ".join(f'"{o}"' for o in self.options[:12]))
        if self.checked is not None:
            parts.append("(checked)" if self.checked else "(unchecked)")
        if self.href:
            parts.append(f"-> {self.href}")
        if self.disabled:
            parts.append("(disabled)")
        return " ".join(parts)


class Observation(BaseModel):
    url: str
    title: str = ""
    text: str = ""                 # compact page text: headings, paragraphs, table rows
    alerts: list[str] = []
    elements: list[Element] = []
    is_login_page: bool = False
    http_error: int | None = None
    ts: float = Field(default_factory=time.time)

    def render(self, max_text=3500) -> str:
        lines = [f"URL: {self.url}", f"TITLE: {self.title}"]
        if self.http_error:
            lines.append(f"HTTP ERROR: {self.http_error}")
        if self.is_login_page:
            lines.append("NOTE: this is a sign-in page (your session may have expired).")
        if self.alerts:
            lines.append("ALERTS: " + " | ".join(self.alerts))
        text = self.text if len(self.text) <= max_text else self.text[:max_text] + " …[truncated]"
        lines.append("PAGE TEXT:\n" + text)
        lines.append("INTERACTIVE ELEMENTS:\n" + "\n".join(e.line() for e in self.elements))
        return "\n".join(lines)


class Action(BaseModel):
    tool: str
    args: dict[str, Any] = {}

    def signature(self) -> str:
        return f"{self.tool}:{sorted(self.args.items())}"


class Fact(BaseModel):
    key: str
    value: str
    source: str                    # where it was read: a URL, a PDF name, "human", "memory"
    step: int


class Clarification(BaseModel):
    step: int
    question: str
    options: list[str] = []
    answer: str = ""
    ts: float = Field(default_factory=time.time)


class Approval(BaseModel):
    step: int
    intent: dict[str, Any]
    reason: str
    granted: bool
    approver: str = ""
    note: str = ""
    ts: float = Field(default_factory=time.time)


class PolicyDecision(BaseModel):
    allowed: bool
    needs_approval: bool = False
    reasons: list[str] = []
    rule_ids: list[str] = []       # which rules fired (built-in or learned)


class Step(BaseModel):
    index: int
    url: str
    thought: str = ""
    action: Action
    result: str = ""               # what the runtime reported back to the brain
    policy: PolicyDecision | None = None
    screenshot: str = ""
    llm_calls: int = 0
    ts: float = Field(default_factory=time.time)
    duration_ms: int = 0


class Contract(BaseModel):
    """What the worker understood the request to mean, before it acts."""
    intent: str                    # e.g. record_supplier_invoice, update_bill, list_open_invoices
    summary: str
    target_system: str = ""        # ledger | nova | portal | mail | ""
    params: dict[str, Any] = {}
    questions: list[str] = []      # ambiguities that must be resolved before writing
    deliverable: str = "A short summary with evidence."


class Milestone(BaseModel):
    id: str
    title: str
    done_when: str                 # a state, not a click sequence
    writes: bool = False
    status: Literal["pending", "active", "done", "skipped"] = "pending"


class Assertion(BaseModel):
    """A claim about a system of record, checked by the verifier through the admin API."""
    kind: Literal["exists", "absent", "count"]
    system: str                    # ledger | nova | portal | mail
    entity: str                    # bill | payable | mail
    match: dict[str, Any] = {}     # fields identifying the row(s)
    expect: dict[str, Any] = {}    # fields the row must have (exists) / count (count)
    note: str = ""


class Usage(BaseModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    browser_actions: int = 0
    human_interventions: int = 0


class Verification(BaseModel):
    status: Literal["completed", "completed_with_exceptions", "failed", "unverified", "not_run"] = "not_run"
    checks: list[dict[str, Any]] = []
    unexplained_changes: list[dict[str, Any]] = []
    summary: str = ""


class RunRecord(BaseModel):
    run_id: str
    request: str
    started_at: float = Field(default_factory=time.time)
    finished_at: float | None = None
    brain: str = ""
    model: str = ""
    memory_mode: str = "on"
    contract: Contract | None = None
    milestones: list[Milestone] = []
    steps: list[Step] = []
    facts: list[Fact] = []
    clarifications: list[Clarification] = []
    approvals: list[Approval] = []
    assertions: list[Assertion] = []
    skills_used: list[str] = []
    rules_applied: list[str] = []
    final_status: str = "running"  # running | completed | completed_with_exceptions | needs_clarification | blocked | failed | gave_up
    final_summary: str = ""
    verification: Verification = Verification()
    usage: Usage = Usage()
    learned: list[str] = []        # ids of skills/rules created from this run

    def fact(self, key: str) -> str | None:
        for f in reversed(self.facts):
            if f.key == key and f.value != "":      # an empty value is no evidence of anything
                return f.value
        return None

    def elapsed(self) -> float:
        return (self.finished_at or time.time()) - self.started_at
