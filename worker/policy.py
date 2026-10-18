"""The policy gate: code decides what the model may write.

The brain can propose any write it likes. Before the browser clicks a
submit button, the gate checks the declared intent against company policy
(company_context/policy.yaml) and against learned rules (memory/rules.json).
It can allow, block with a reason the brain can act on, or require a human's
approval first. Every decision is recorded on the step.

This is deliberately boring, explicit code. "The model said it was fine" is
never a reason a write goes through.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from worker.types import PolicyDecision, RunRecord

ROOT = Path(__file__).resolve().parent.parent
WRITE_INTENTS = {"create_bill", "record_payable", "post_bill", "update_record"}


def load_policy(path: Path | None = None) -> dict:
    return yaml.safe_load((path or ROOT / "company_context" / "policy.yaml").read_text())


def intent_hash(intent: dict) -> str:
    key = {k: intent.get(k) for k in ("type", "system", "invoice_number", "amount_paise", "vendor_name")}
    return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:10]


class PolicyGate:
    def __init__(self, policy: dict, learned_rules: list | None = None):
        self.policy = policy
        self.learned = learned_rules or []

    # ---- effective settings after learned policy rules
    def approval_threshold(self) -> tuple[int, str]:
        threshold = int(self.policy["approval"]["threshold_paise"])
        source = "policy.yaml"
        for rule in self.learned:
            if rule.kind == "policy" and rule.active and "approval_threshold_paise" in (rule.structured or {}):
                threshold = int(rule.structured["approval_threshold_paise"])
                source = rule.id
        return threshold, source

    def approvers(self) -> list[str]:
        return list(self.policy["approval"].get("approvers", []))

    def blocked_vendors(self) -> dict[str, str]:
        """Learned facts of the form {'avoid_vendor': name, 'use_instead': name}."""
        out = {}
        for rule in self.learned:
            s = rule.structured or {}
            if rule.active and "avoid_vendor" in s:
                out[s["avoid_vendor"].lower()] = s.get("use_instead", "")
        return out

    def extra_required_facts(self) -> list[tuple[str, str]]:
        out = []
        for rule in self.learned:
            s = rule.structured or {}
            if rule.active and "require_fact" in s:
                out.append((s["require_fact"], rule.id))
        return out

    # ---- the decision
    def evaluate(self, intent: dict, run: RunRecord) -> PolicyDecision:
        reasons, rule_ids = [], []
        itype = (intent.get("type") or "").strip()
        if itype in self.policy.get("forbidden", []) or itype in ("delete", "external_email", "admin_api"):
            return PolicyDecision(allowed=False, reasons=[f"'{itype}' is forbidden by company policy"], rule_ids=["policy.forbidden"])
        if itype not in WRITE_INTENTS:
            # Everything that reaches the gate is a write (commit = a submit button). A missing or unknown
            # type never relaxes the checks: infer the strictest fitting kind.
            if intent.get("invoice_number") or intent.get("amount_paise") is not None:
                itype = "record_payable" if intent.get("system") == "nova" else "create_bill"
            else:
                itype = "update_record"
            intent["type"] = itype

        inv = (intent.get("invoice_number") or "").strip()
        amount = intent.get("amount_paise")
        writes = self.policy.get("writes", {})

        if itype in ("create_bill", "record_payable"):
            if not inv:
                reasons.append("intent must name the invoice number")
            for fact_key in writes.get("require_facts", []):
                value = run.fact(f"{fact_key}:{inv}")
                if value is None:
                    reasons.append(f"missing fact '{fact_key}:{inv}': record it with note_fact before this write")
                    rule_ids.append(f"policy.writes.require_facts.{fact_key}")
            for fact_key, rid in self.extra_required_facts():
                if run.fact(f"{fact_key}:{inv}") is None:
                    reasons.append(f"missing fact '{fact_key}:{inv}' (learned rule {rid})")
                    rule_ids.append(rid)
            dup = run.fact(f"duplicate_check:{inv}")
            if writes.get("block_if_duplicate") and dup and not dup.lower().startswith(("none", "no ", "not found", "absent")):
                reasons.append(f"duplicate: '{inv}' already exists ({dup}); do not record it again, report it")
                rule_ids.append("policy.writes.block_if_duplicate")
            pdf_total = run.fact(f"pdf_total:{inv}")
            if writes.get("amount_must_match_pdf") and pdf_total is not None and amount is not None:
                try:
                    if int(pdf_total) != int(amount):
                        reasons.append(f"amount {amount} paise does not match the PDF total {pdf_total} paise")
                        rule_ids.append("policy.writes.amount_must_match_pdf")
                except ValueError:
                    reasons.append(f"pdf_total fact for {inv} is not an integer number of paise: {pdf_total!r}")
            if writes.get("readback_after_unknown_outcome") and run.fact(f"unknown_outcome:{inv}") == "pending" \
                    and run.fact(f"readback:{inv}") is None:
                reasons.append(f"a previous submit for {inv} ended with an unknown outcome; read the list back "
                               f"(note_fact readback:{inv}) before trying again")
                rule_ids.append("policy.writes.readback_after_unknown_outcome")
            vendor = (intent.get("vendor_name") or "").lower()
            avoid = self.blocked_vendors()
            if vendor in avoid:
                hint = f" (use '{avoid[vendor]}' instead)" if avoid[vendor] else ""
                reasons.append(f"vendor '{intent.get('vendor_name')}' must not be used{hint}")
                rule_ids.append("learned.avoid_vendor")

        if reasons:
            return PolicyDecision(allowed=False, reasons=reasons, rule_ids=rule_ids)

        # approval threshold applies to anything that posts/records money
        needs_approval = False
        if amount is not None and itype in ("create_bill", "record_payable", "post_bill"):
            threshold, source = self.approval_threshold()
            if int(amount) >= threshold:
                granted = [a for a in run.approvals if a.granted and intent_hash(a.intent) == intent_hash(intent)]
                if not granted:
                    needs_approval = True
                    reasons.append(f"amount {int(amount) / 100:,.2f} is at or above the approval threshold "
                                   f"{threshold / 100:,.2f} ({source}); a manager must approve first")
                    rule_ids.append(f"approval_threshold:{source}")
                else:
                    approver = granted[-1].approver
                    if (intent.get("approved_by") or "").strip() != approver:
                        reasons.append(f"approved by {approver}: fill the approval field with '{approver}' before submitting")
                        rule_ids.append("policy.approval.record_approver")
                        return PolicyDecision(allowed=False, reasons=reasons, rule_ids=rule_ids)
                    reasons.append(f"approved by {approver} (approval {granted[-1].step})")
                    rule_ids.append(f"approval_threshold:{source}")
        return PolicyDecision(allowed=not needs_approval, needs_approval=needs_approval, reasons=reasons or ["allowed"],
                              rule_ids=rule_ids)
