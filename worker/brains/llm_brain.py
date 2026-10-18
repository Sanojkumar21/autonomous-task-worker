"""The LLM brain: a model reads the company context, plans in target states,
and picks one tool call per step from a compact text view of the page.

The prompts are deliberately plain. The model is told what the runtime will
and will not let it do (writes go through `commit`; facts need provenance;
the verifier decides when the task is done), and it gets the company's
learned memory: skills from earlier verified runs, and rules people taught it.
"""
from __future__ import annotations

import json
import re

from worker.brain import Brain, BrainState
from worker.context import CompanyContext
from worker.llm.base import LLM, LLMError
from worker.memory.store import MemoryStore, Rule, Skill
from worker.runtime import TOOLS
from worker.types import Action, Contract, Milestone, RunRecord

SYSTEM_PROMPT = """You are an autonomous operations worker at {company}. You complete back-office tasks in the
company's web systems through a browser, the way a careful clerk would, and you prove your work.

How you work
- You see the current page as text: URL, page text, and numbered INTERACTIVE ELEMENTS. You act by naming an element id.
  Ids are renumbered after every action: only use ids from the latest observation.
- Read, don't guess. Amounts, dates and numbers come from documents (PDFs) and pages, and you record them with
  note_fact so they carry provenance. The runtime refuses writes whose facts are missing.
- Writes go through `commit`: you name the submit button and declare the intent (what will be created, for which
  vendor, invoice number, amount in paise, due date, PO). Code checks the form matches, applies company policy and
  learned rules, and asks a manager for approval when the amount requires it. If commit is refused, fix the reason.
- If a request is ambiguous (two invoices or two vendors could match and nothing settles it), use ask_human before
  writing anything. Never ask what you could find out by reading.
- If a submit returns a server error, do not resubmit blindly: open the list, check whether the record exists, and
  note_fact readback:<invoice> with what you saw.
- If a page is a sign-in form, your session expired: sign in again with the credentials below and continue.
- When the outcome is achieved, call `done` with a short summary and assertions: data the verifier checks against the
  systems of record. Your word never sets the status; the verifier does. Assertions look like
  {{"kind": "exists", "system": "ledger", "entity": "bill", "match": {{"invoice_number": "NW-1043-R", "vendor_gstin": "07AAACN1234F1Z5"}},
    "expect": {{"amount_paise": 5980000, "due_date": "2026-11-08", "po_number": "PO-7734", "status": "posted"}}}}
  or {{"kind": "count", "system": "ledger", "entity": "bill", "match": {{"invoice_number": "KL-0915"}}, "expect": {{"count": 1}}}} when the
  right outcome is to record nothing. Entities: ledger/bill, nova/payable. Fields: invoice_number, vendor_name,
  vendor_gstin, amount_paise, due_date (YYYY-MM-DD), po_number, status, approved_by.
- Facts to record for every invoice you handle, keyed by invoice number: pdf_total:<inv> (integer paise from the PDF),
  due_date:<inv>, po:<inv>, vendor_gstin:<inv>, duplicate_check:<inv> ("none" or "exists: ..."), and any mail_check:<inv>.
- Keep going until the task is done or you must stop. Prefer navigate with a path over clicking through menus when
  you know the path. Do not repeat an action that did not change anything.
- Be economical: read a PDF once and record every fact you need from it in the following steps (do not read it again);
  use `look` only when the text view is not enough; the intent of `commit` must include "type"
  (create_bill | record_payable | post_bill) and the system.

Tools (reply with exactly one per step): {tools}
Use fill_form to enter several fields at once (and to sign in: fields + submit). Use commit, never fill_form's submit, for buttons that save or record.

Reply with JSON only:
{{"thought": "<one or two sentences>", "milestone": "<id of the milestone you are working on>",
 "action": {{"tool": "<tool>", "args": {{...}}}}}}

Company systems
{systems}

Company policy (enforced in code)
- Bills at or above Rs {threshold:,.2f} need a manager's approval before posting (approvers: {approvers}). Learned rules may change this.
- Every create/record needs these facts first: duplicate_check and pdf_total for the invoice. The amount must equal the PDF total.
- Never delete, never email outside the company, never call admin APIs.

Company handbook (summary; the full text was used to understand and plan the task)
{handbook_short}
"""


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + " …"


class LLMBrain(Brain):
    name = "llm"

    def __init__(self, llm: LLM, history_steps: int = 5):
        self.llm = llm
        self.model = llm.model
        self.history_steps = history_steps
        self._system_cache: dict[str, str] = {}
        self._pending_image: bytes | None = None

    def usage(self):
        return {"llm_calls": self.llm.calls, "input_tokens": self.llm.input_tokens,
                "output_tokens": self.llm.output_tokens, "cost_usd": self.llm.cost_usd}

    # ---- prompts
    def system_prompt(self, context: CompanyContext) -> str:
        key = context.base_url
        if key not in self._system_cache:
            tools = "; ".join(f"{name}({', '.join(args) if args else ''})" for name, args in TOOLS.items())
            self._system_cache[key] = SYSTEM_PROMPT.format(
                company="Acme Robotics Pvt Ltd", tools=tools, systems=context.systems_summary(),
                threshold=context.approval_threshold_paise() / 100, approvers=", ".join(context.policy["approval"]["approvers"]),
                handbook_short=self._handbook_short(context))
        return self._system_cache[key]

    @staticmethod
    def _handbook_short(context: CompanyContext) -> str:
        """Keep the numbered SOP lines and the system notes; drop the rest to save tokens per step."""
        keep = []
        for line in context.handbook.splitlines():
            if re.match(r"^\s*\d+\.\s", line) or line.startswith("- **"):
                keep.append(re.sub(r"\*\*", "", line).strip())
        return "\n".join(keep)

    def _ask(self, system: str, user: str, images=None) -> dict:
        res = self.llm.complete(system, [{"role": "user", "content": user}], want_json=True, images=images)
        if not isinstance(res.json, dict):
            raise LLMError(f"expected a JSON object, got: {_short(res.text, 200)}")
        return res.json

    # ---- understand
    def understand(self, request: str, context: CompanyContext, memory: MemoryStore) -> Contract:
        user = f"""Request from the ops team: "{request}"

Full company handbook:
{context.handbook}

{memory.describe() or 'No learned rules yet.'}

Work out what this request means before touching anything. Reply with JSON:
{{"intent": "<one of: record_supplier_invoice, update_bill, mark_bill_paid, find_information, reply_to_mail, other>",
 "summary": "<what you will do, one or two sentences>",
 "target_system": "<ledger|nova|portal|mail>",
 "params": {{"vendor": "...", "which": "latest|<invoice number>|unspecified", ...}},
 "questions": ["<only questions that must be answered BEFORE acting and that reading the systems cannot answer; usually empty>"],
 "deliverable": "<what you will report at the end>"}}"""
        data = self._ask(self.system_prompt(context), user)
        return Contract(intent=str(data.get("intent", "task")).strip() or "task", summary=str(data.get("summary", "")),
                        target_system=str(data.get("target_system", "")), params=dict(data.get("params") or {}),
                        questions=[str(q) for q in (data.get("questions") or [])][:3],
                        deliverable=str(data.get("deliverable", "A short summary with evidence.")))

    # ---- plan
    def plan(self, contract: Contract, context: CompanyContext, memory: MemoryStore, skills: list[Skill]) -> list[Milestone]:
        skill_text = self._render_skills(skills, contract.target_system)
        user = f"""Task: {contract.summary}
Intent: {contract.intent}; target system: {contract.target_system}; params: {json.dumps(contract.params)}

{skill_text or 'No skill from earlier runs applies; plan from the handbook.'}

{memory.describe(contract.target_system)}

Write 3 to 6 milestones. Each is a STATE to reach, not a click sequence, so it stays true if the pages change.
Mark the ones that change a system of record with "writes": true. Reply with JSON:
{{"milestones": [{{"id": "M1", "title": "...", "done_when": "<observable state>", "writes": false}}, ...]}}"""
        data = self._ask(self.system_prompt(context), user)
        out = []
        for i, m in enumerate(data.get("milestones") or [], 1):
            out.append(Milestone(id=str(m.get("id") or f"M{i}"), title=str(m.get("title", "")),
                                 done_when=str(m.get("done_when", "")), writes=bool(m.get("writes", False))))
        return out or [Milestone(id="M1", title="Complete the task", done_when="the outcome is verified", writes=True)]

    def _render_skills(self, skills: list[Skill], system: str) -> str:
        if not skills:
            return ""
        parts = []
        for s in skills[:2]:
            same = s.system == system
            parts.append(f"Skill `{s.id}` from a verified earlier run ({'same system' if same else 'different system: ' + s.system + ', reuse the workflow, not the clicks'}): {s.name}\n"
                         f"  When: {s.trigger}\n  Workflow: " + " → ".join(s.workflow)
                         + (("\n  Procedure on " + s.system + ": " + " | ".join(s.procedure)) if same and s.procedure else "")
                         + (("\n  Pitfalls: " + "; ".join(s.pitfalls)) if s.pitfalls else "")
                         + (("\n  Verify: " + "; ".join(s.verification)) if s.verification else ""))
        return "\n".join(parts)

    # ---- decide
    def decide(self, state: BrainState) -> tuple[str, Action]:
        run, ctx = state.run, state.context
        milestones = "\n".join(f"- {m.id} [{m.status}] {m.title} — done when: {m.done_when}{' (write)' if m.writes else ''}"
                               for m in run.milestones)
        facts = "\n".join(f"- {f.key} = {f.value} (from {f.source})" for f in run.facts[-30:]) or "- none yet"
        history = []
        recent = state.last_results[-self.history_steps:]
        for i, r in enumerate(recent):
            is_last = i == len(recent) - 1
            limit = (2500 if is_last else 160) if "PDF text" in r else (400 if is_last else 200)
            history.append(_short(r, limit))
        clar = "\n".join(f"- Q: {c.question} A: {c.answer}" for c in run.clarifications if c.answer)
        appr = "\n".join(f"- {('granted by ' + a.approver) if a.granted else 'DENIED'}: {json.dumps(a.intent)[:160]}" for a in run.approvals)
        user = f"""Request: "{run.request}"
Understanding: {run.contract.summary if run.contract else ''}
Milestones:
{milestones}

{self._render_skills(state.skills, run.contract.target_system if run.contract else '')}
{state.memory.describe(run.contract.target_system if run.contract else '')}

Facts recorded so far:
{facts}
{('Answers from people:\n' + clar) if clar else ''}
{('Approvals:\n' + appr) if appr else ''}
Recent steps (oldest first):
{chr(10).join(history) or '- none yet'}
{('RUNTIME HINTS: ' + ' '.join(state.hints)) if state.hints else ''}

Current page:
{state.observation.render()}

Step {len(run.steps) + 1}. Decide the single next action. Reply with JSON only."""
        images = [self._pending_image] if (self._pending_image and self.llm.supports_vision) else None
        self._pending_image = None
        try:
            data = self._ask(self.system_prompt(ctx), user, images=images)
        except LLMError as e:
            return f"model error: {e}", Action(tool="give_up", args={"reason": f"the model failed: {e}"})
        thought = str(data.get("thought", ""))
        mid = str(data.get("milestone", ""))
        for m in run.milestones:
            if m.id == mid and m.status == "pending":
                for prev in run.milestones:
                    if prev.status == "active" and prev.id != mid:
                        prev.status = "done"
                m.status = "active"
        act = data.get("action") or {}
        tool = str(act.get("tool", "")).strip()
        args = act.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        if tool not in TOOLS:
            return thought, Action(tool="give_up", args={"reason": f"the model chose an unknown tool '{tool}'"})
        if tool == "done":
            for m in run.milestones:
                if m.status == "active":
                    m.status = "done"
        return thought, Action(tool=tool, args=args)

    def note_image(self, image: bytes | None):
        self._pending_image = image

    # ---- learning
    def distill_skill(self, run: RunRecord, context: CompanyContext) -> Skill | None:
        steps = "\n".join(f"{s.index}. {s.action.tool} {json.dumps(s.action.args)[:140]} -> {_short(s.result, 120)}"
                          for s in run.steps if s.action.tool not in ("look",))
        user = f"""A run just completed and the verifier confirmed the outcome. Turn it into a reusable skill.

Request: "{run.request}"
Intent: {run.contract.intent}; system: {run.contract.target_system}
Facts: {json.dumps([f.model_dump() for f in run.facts][:40])}
Steps:
{steps}

Write the skill so it transfers: a short app-agnostic workflow (what to establish, in order), a concrete procedure for
this system (paths, which page shows what, field names) with {{placeholders}} for vendor/invoice/amount/date, the
pitfalls you hit or avoided, and how to verify. Reply with JSON:
{{"name": "...", "trigger": "<when to use it>", "workflow": ["..."], "procedure": ["..."], "pitfalls": ["..."],
 "verification": ["..."], "params": ["vendor", "invoice_number"]}}"""
        try:
            data = self._ask(self.system_prompt(context), user)
        except LLMError:
            return None
        return Skill(name=str(data.get("name", "skill")), intent=run.contract.intent, system=run.contract.target_system,
                     trigger=str(data.get("trigger", "")), workflow=[str(x) for x in data.get("workflow") or []],
                     procedure=[str(x) for x in data.get("procedure") or []], pitfalls=[str(x) for x in data.get("pitfalls") or []],
                     verification=[str(x) for x in data.get("verification") or []], params=[str(x) for x in data.get("params") or []])

    def extract_rules(self, feedback: str, who: str, run: RunRecord | None, context: CompanyContext) -> list[Rule]:
        user = f"""Someone at the company ({who}) said this{(' during the task "' + run.request + '"') if run else ''}:
"{feedback}"

Extract durable rules the worker should remember for future tasks (not one-off answers like "the second one").
Each rule has kind "policy" (changes what the policy gate enforces), "fact" (a truth about this company's data, e.g.
which vendor record is the real one) or "guideline" (advice). Add "structured" only when it maps to a known setting:
- {{"approval_threshold_paise": <int>}} for a new approval threshold
- {{"avoid_vendor": "<name>", "use_instead": "<name>"}} for a vendor record not to use
- {{"require_fact": "<fact key prefix>"}} for an extra check to do before every write
Reply with JSON: {{"rules": [{{"kind": "...", "text": "...", "structured": {{}}, "scope": {{}}}}]}} (empty list if nothing durable)."""
        try:
            data = self._ask(self.system_prompt(context), user)
        except LLMError:
            return []
        out = []
        for r in data.get("rules") or []:
            kind = str(r.get("kind", "guideline"))
            if kind not in ("policy", "fact", "guideline"):
                kind = "guideline"
            structured = r.get("structured") or {}
            if "approval_threshold_paise" in structured:
                try:
                    structured["approval_threshold_paise"] = int(structured["approval_threshold_paise"])
                except (TypeError, ValueError):
                    structured.pop("approval_threshold_paise")
            out.append(Rule(kind=kind, text=str(r.get("text", "")).strip(), structured=structured, scope=r.get("scope") or {}))
        return [r for r in out if r.text]
