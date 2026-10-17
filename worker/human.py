"""The human channel: clarifications, approvals and corrections.

The worker asks a person only when it cannot safely proceed: a request is
ambiguous, or policy says a manager must approve. Three implementations:

- CliHuman: prompts in the terminal (interactive use).
- ScriptedHuman: pre-written answers, for evaluation runs and tests.
- NoHuman: no one is available; the worker must stop and report.

Every answer is recorded on the run with the step it belonged to, so the
report can show exactly what a person decided.
"""
from __future__ import annotations

import re


class HumanAnswer:
    def __init__(self, text: str = "", approved: bool | None = None, approver: str = "", note: str = ""):
        self.text = text
        self.approved = approved
        self.approver = approver
        self.note = note


class Human:
    name = "none"

    def clarify(self, question: str, options: list[str], context: str) -> HumanAnswer:
        raise NotImplementedError

    def approve(self, intent: dict, reason: str, context: str) -> HumanAnswer:
        raise NotImplementedError


class NoHuman(Human):
    name = "none"

    def clarify(self, question, options, context):
        return HumanAnswer(text="")

    def approve(self, intent, reason, context):
        return HumanAnswer(approved=None)


class CliHuman(Human):
    name = "cli"

    def clarify(self, question, options, context):
        print("\n=== The worker needs your input ===")
        print(question)
        for i, o in enumerate(options, 1):
            print(f"  {i}. {o}")
        raw = input("Your answer (number or text, empty to stop the worker): ").strip()
        if raw.isdigit() and options and 1 <= int(raw) <= len(options):
            raw = options[int(raw) - 1]
        return HumanAnswer(text=raw)

    def approve(self, intent, reason, context):
        print("\n=== Approval required ===")
        print(reason)
        for k, v in intent.items():
            print(f"  {k}: {v}")
        raw = input("Approve? [y/N] (you may add a note after a comma): ").strip()
        approved = raw.lower().startswith("y")
        note = raw.partition(",")[2].strip()
        approver = input("Your username (e.g. priya.manager): ").strip() if approved else ""
        return HumanAnswer(approved=approved, approver=approver, note=note)


class ScriptedHuman(Human):
    """Answers from a script: a list of {match, answer, approve, approver, note}.

    `match` is a regex tested against the question (clarify) or the intent's
    invoice number / reason (approve). The first match wins. Unmatched
    clarifications get an empty answer; unmatched approvals are denied.
    """
    name = "scripted"

    def __init__(self, script: list[dict] | None = None):
        self.script = script or []
        self.log: list[dict] = []

    def _find(self, text):
        for item in self.script:
            if re.search(item.get("match", ".*"), text, re.I):
                return item
        return None

    def clarify(self, question, options, context):
        item = self._find(question)
        answer = item.get("answer", "") if item else ""
        self.log.append({"type": "clarify", "question": question, "answer": answer})
        return HumanAnswer(text=answer)

    def approve(self, intent, reason, context):
        key = f"{intent.get('invoice_number', '')} {intent.get('type', '')} {reason}"
        item = self._find(key)
        if not item:
            self.log.append({"type": "approve", "intent": intent, "approved": False})
            return HumanAnswer(approved=False)
        self.log.append({"type": "approve", "intent": intent, "approved": bool(item.get("approve", True))})
        return HumanAnswer(approved=bool(item.get("approve", True)), approver=item.get("approver", "priya.manager"),
                           note=item.get("note", ""))
