"""A scripted brain: the handbook's SOP written as a reactive controller.

It makes no model calls. Its purpose is to exercise the runtime the way a
competent clerk would, deterministically, so the runtime's guarantees can be
tested and measured under chaos: policy gate, approvals, duplicate blocking,
unknown-outcome handling, session recovery, independent verification.

It is reactive: every step looks at the current page and picks the next
action toward the current phase, so it recovers naturally from expired
sessions and error pages. It knows the SOP, not the sites' HTML: it finds
elements by their accessible names, like the LLM brain does.
"""
from __future__ import annotations

import re
from datetime import date

from worker.brain import Brain, BrainState
from worker.context import CompanyContext
from worker.memory.store import MemoryStore, Rule, Skill
from worker.types import Action, Contract, Milestone, Observation, RunRecord

INVOICE_RE = re.compile(r"\b([A-Z]{2}-\d{4}(?:-R)?)\b")
MONEY_RE = re.compile(r"Rs\s*([\d,]+\.\d{2})")
GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]{2})\b")


def find(obs: Observation, role: str | None = None, name: str = "", exact: bool = False):
    name_l = name.lower()
    for e in obs.elements:
        if role and e.role != role:
            continue
        n = e.name.lower()
        if (exact and n == name_l) or (not exact and name_l in n):
            return e
    return None


def rows(obs: Observation) -> list[list[str]]:
    out = []
    for line in obs.text.splitlines():
        if line.startswith("| "):
            out.append([c.strip() for c in line.strip("| ").split(" | ")])
    return out


class ScriptedBrain(Brain):
    name = "scripted"
    model = "sop-controller"

    def __init__(self):
        self.state: dict[str, dict] = {}

    def usage(self):
        return {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    # ---- understanding the request (regex, not a model)
    def understand(self, request, context, memory):
        system = "nova" if re.search(r"nova", request, re.I) else "ledger"
        m = INVOICE_RE.search(request)
        which = m.group(1) if m else ("latest" if re.search(r"latest|newest|most recent", request, re.I) else "unspecified")
        vm = re.search(r"from ([A-Z][\w]+(?: [A-Z][\w]+)*)|([A-Z][\w]+(?: [A-Z][\w]+)*)'s", request)
        vendor = (vm.group(1) or vm.group(2)) if vm else ""
        vendor = re.sub(r"\b(Supplies|Components|Logistics|Metals|Office|Packaging)\b.*$", lambda x: x.group(0), vendor).strip()
        return Contract(intent="record_supplier_invoice", target_system=system,
                        summary=f"Record {vendor or 'the named vendor'}'s {which} invoice in {system} after reading its PDF, "
                                f"checking for revisions and duplicates, and getting approval if the amount requires it.",
                        params={"vendor": vendor, "which": which}, questions=[])

    def plan(self, contract, context, memory, skills):
        sysname = contract.target_system
        return [
            Milestone(id="M1", title="Identify the invoice and read its PDF", done_when="invoice number, PDF total, due date, PO and GSTIN are noted"),
            Milestone(id="M2", title="Check the mailbox for revisions or corrections", done_when="any revision notice is noted"),
            Milestone(id="M3", title=f"Resolve the vendor in {sysname} by GSTIN and check for duplicates", done_when="duplicate_check fact noted"),
            Milestone(id="M4", title=f"Record the bill in {sysname}", done_when="the record is saved (approval obtained first if required)", writes=True),
            Milestone(id="M5", title="Verify the record and report", done_when="the list shows the record with the right values"),
        ]

    # ---- the controller
    def decide(self, state: BrainState):
        run, ctx, obs = state.run, state.context, state.observation
        s = self.state.setdefault(run.run_id, {"phase": "portal", "inv": None, "mail_checked": False, "nova_step": 0,
                                               "approver": "", "readback_pending": False, "dup_checked": False})
        p = run.contract.params
        system = run.contract.target_system
        base = ctx.base_url

        # Always: handle sign-in pages first (chaos session expiry).
        if obs.is_login_page:
            sysname = ctx.system_for_url(obs.url) or "portal"
            user, pw = ctx.credentials(sysname)
            u, pwf, btn = find(obs, "textbox", "username"), find(obs, "password", "password"), find(obs, "button", "sign in")
            if u and not u.value:
                return "Session expired; signing in again.", Action(tool="type", args={"id": u.id, "text": user})
            if pwf and btn:
                # fill password then submit (password fields are not echoed in the observation)
                if not s.get("pw_filled_url") == obs.url:
                    s["pw_filled_url"] = obs.url
                    return "Entering the password.", Action(tool="type", args={"id": pwf.id, "text": pw})
                s["pw_filled_url"] = None
                return "Submitting the sign-in form.", Action(tool="click", args={"id": btn.id})
        if obs.http_error == 503:
            return "The service answered 503; retrying the page.", Action(tool="navigate", args={"url": obs.url})

        phase = s["phase"]
        order = {"portal": "M1", "mail": "M2", "vendor": "M3", "dup": "M3", "record": "M4", "readback": "M4", "verify": "M5", "done_dup": "M5"}
        current = order.get(phase)
        for m in run.milestones:
            if m.id == current and m.status == "pending":
                m.status = "active"
            elif current and m.id < current and m.status in ("pending", "active"):
                m.status = "done"
            if phase in ("verify", "done_dup") and m.id == "M5":
                m.status = "done"
        if phase == "portal":
            return self._portal(state, s, obs, p, base)
        if phase == "mail":
            return self._mail(state, s, obs, p, base)
        if phase == "vendor":
            return self._vendor(state, s, obs, system, base)
        if phase == "dup":
            return self._dup(state, s, obs, system, base)
        if phase == "record":
            return self._record(state, s, obs, system, base)
        if phase == "readback":
            return self._readback(state, s, obs, system, base)
        if phase == "verify":
            return self._verify(state, s, obs, system, base)
        if phase == "done_dup":
            return self._report_duplicate(state, s, system)
        return "Nothing left to do.", Action(tool="give_up", args={"reason": "controller has no phase"})

    # M1: find the invoice on the portal and read the PDF
    def _portal(self, state, s, obs, p, base):
        run = state.run
        vendor, which = p.get("vendor", ""), p.get("which", "unspecified")
        if "/portal/invoices" not in obs.url:
            url = f"{base}/portal/invoices?vendor={vendor}&status=open" if vendor else f"{base}/portal/invoices?status=open"
            return f"Opening the supplier portal filtered to {vendor or 'all'} open invoices.", Action(tool="navigate", args={"url": url})
        if re.search(r"/portal/invoices/\d+$", obs.url):
            # detail page: read the PDF
            if not s.get("pdf_read"):
                link = find(obs, "link", "download pdf")
                s["pdf_read"] = True
                s["pdf_url"] = link.href if link else ""
                return "Reading the invoice PDF, the document of record.", Action(tool="read_pdf", args={"url": link.href if link else obs.url + "/pdf"})
            # after read_pdf the runtime appended the text to last_results; parse it
            text = next((r for r in reversed(state.last_results) if "PDF text" in r), "")
            inv = s["inv"]
            total = MONEY_RE.findall(text)
            gst = GSTIN_RE.search(text)
            due = re.search(r"Due date:\s*(\d{4}-\d{2}-\d{2})", text)
            po = re.search(r"Purchase order:\s*(PO-\d+|-)", text)
            pending = s.setdefault("facts_to_note", [
                (f"pdf_total:{inv}", str(int(round(float(total[-1].replace(",", "")) * 100))) if total else "?", s.get("pdf_url", "pdf")),
                (f"due_date:{inv}", due.group(1) if due else "?", s.get("pdf_url", "pdf")),
                (f"po:{inv}", (po.group(1) if po and po.group(1) != "-" else "") if po else "", s.get("pdf_url", "pdf")),
                (f"vendor_gstin:{inv}", gst.group(1) if gst else "?", s.get("pdf_url", "pdf")),
            ])
            if pending:
                key, value, src = pending.pop(0)
                return f"Noting {key} from the PDF.", Action(tool="note_fact", args={"key": key, "value": value, "source": src})
            s["phase"] = "mail"
            return "PDF facts noted; checking the mailbox for revisions.", Action(tool="navigate", args={"url": f"{base}/mail/inbox?q={(vendor or inv).split(' ')[0]}"})
        # list page: pick the invoice
        table = [r for r in rows(obs) if len(r) >= 5 and INVOICE_RE.search(r[1] or "")]
        open_rows = [r for r in table if r[4] == "open" and (not vendor or vendor.lower() in r[0].lower())]
        if which != "latest" and which != "unspecified":
            chosen = [r for r in table if r[1] == which]
        elif which == "latest":
            chosen = sorted(open_rows, key=lambda r: r[2], reverse=True)[:1]
        else:
            if len(open_rows) > 1 and not s.get("asked"):
                s["asked"] = True
                return "More than one open invoice matches; asking which one.", Action(tool="ask_human", args={
                    "question": f"{vendor} has {len(open_rows)} open invoices: {', '.join(r[1] for r in open_rows)}. Which one should I record?",
                    "options": [r[1] for r in open_rows]})
            answer = run.fact(f"human_answer:{len(run.steps)}") or next((f.value for f in run.facts if f.key.startswith("human_answer")), "")
            m = INVOICE_RE.search(answer or "")
            chosen = [r for r in open_rows if m and r[1] == m.group(1)] or open_rows[:1]
        if not chosen:
            return "No matching open invoice on the portal.", Action(tool="give_up", args={"reason": f"no open invoice for {vendor} ({which}) on the portal"})
        inv = chosen[0][1]
        if s["inv"] != inv:
            s["inv"] = inv
            return f"Target invoice is {inv}; noting it.", Action(tool="note_fact", args={"key": "invoice_number", "value": inv, "source": obs.url})
        link = None
        for e in obs.elements:
            if e.role == "link" and e.name.lower() == "view":
                pass
        # find the View link in the same row: the observation lists links in page order, rows in table order
        view_links = [e for e in obs.elements if e.role == "link" and e.name.lower() == "view"]
        idx = [r[1] for r in table].index(inv) if inv in [r[1] for r in table] else -1
        if 0 <= idx < len(view_links):
            link = view_links[idx]
        if link:
            return f"Opening invoice {inv}.", Action(tool="click", args={"id": link.id})
        return "Cannot find the invoice link.", Action(tool="give_up", args={"reason": "portal layout not understood"})

    # M2: mailbox check
    def _mail(self, state, s, obs, p, base):
        inv = s["inv"]
        if "/mail" not in obs.url:
            return "Opening the mailbox.", Action(tool="navigate", args={"url": f"{base}/mail/inbox?q={(p.get('vendor') or inv).split(' ')[0]}"})
        if re.search(r"/mail/\d+$", obs.url):
            s["phase"] = "vendor"
            note = "revision notice found" if "supersed" in obs.text.lower() or "revised" in obs.text.lower() else "no revision notice"
            return "Noting what the mail says.", Action(tool="note_fact", args={"key": f"mail_check:{inv}", "value": f"{note}: {obs.title}", "source": obs.url})
        # inbox list: open the first mail that mentions the vendor/invoice, else move on
        links = [e for e in obs.elements if e.role == "link" and re.search(r"/mail/\d+", e.href)]
        vendor_word = (p.get("vendor") or "").split(" ")[0].lower()
        po = (state.run.fact(f"po:{inv}") or "").lower()
        relevant = [e for e in links if any(k and k in e.name.lower() for k in ("revis", "correct", vendor_word, po, inv.lower()))]
        if relevant and not s.get("mail_opened"):
            s["mail_opened"] = True
            return "Opening the mail that mentions this invoice.", Action(tool="click", args={"id": relevant[0].id})
        s["phase"] = "vendor"
        return "No relevant mail; moving to the ERP.", Action(tool="note_fact", args={"key": f"mail_check:{inv}", "value": "no relevant mail", "source": obs.url})

    # M3a: resolve vendor by GSTIN
    def _vendor(self, state, s, obs, system, base):
        run, inv = state.run, s["inv"]
        page = "/ledger/vendors" if system == "ledger" else "/nova/suppliers"
        if page not in obs.url:
            return "Opening the vendor master to match by GSTIN.", Action(tool="navigate", args={"url": base + page})
        gst = run.fact(f"vendor_gstin:{inv}")
        match = [r for r in rows(obs) if len(r) >= 3 and r[2] == gst]
        s["phase"] = "dup"
        if match:
            s["vendor_name"] = match[0][1]
            return f"GSTIN {gst} belongs to {match[0][1]}.", Action(tool="note_fact", args={"key": f"vendor_name:{inv}", "value": match[0][1], "source": obs.url})
        return "No vendor with that GSTIN.", Action(tool="give_up", args={"reason": f"no vendor in {system} with GSTIN {gst}"})

    # M3b: duplicate check
    def _dup(self, state, s, obs, system, base):
        inv = s["inv"]
        page = f"/ledger/bills?q={inv}" if system == "ledger" else f"/nova/payables?search={inv}"
        if ("/ledger/bills" not in obs.url and "/nova/payables" not in obs.url) or inv not in obs.url:
            return "Searching the ERP for this invoice number.", Action(tool="navigate", args={"url": base + page})
        hits = [r for r in rows(obs) if len(r) >= 3 and inv in r]
        if hits:
            s["phase"] = "done_dup"
            s["dup_row"] = hits[0]
            return "Already recorded; noting the duplicate.", Action(tool="note_fact", args={"key": f"duplicate_check:{inv}", "value": f"exists: record #{hits[0][0]}", "source": obs.url})
        s["phase"] = "record"
        return "No duplicate; proceeding to record.", Action(tool="note_fact", args={"key": f"duplicate_check:{inv}", "value": "none", "source": obs.url})

    # M4: record (Ledger form or Nova wizard)
    def _record(self, state, s, obs, system, base):
        run, inv = state.run, s["inv"]
        if s.get("phase") == "done_dup":
            return self._report_duplicate(state, s, system)
        if run.fact(f"duplicate_check:{inv}") and run.fact(f"duplicate_check:{inv}") != "none":
            return self._report_duplicate(state, s, system)
        amount = int(run.fact(f"pdf_total:{inv}"))
        due = run.fact(f"due_date:{inv}")
        po = run.fact(f"po:{inv}") or ""
        vendor = s.get("vendor_name") or run.fact(f"vendor_name:{inv}")
        last = state.last_results[-1] if state.last_results else ""
        granted = re.search(r"GRANTED by ([\w.\-]+)", last) or re.search(r"fill the approval field with '([^']+)'", last)
        if granted:
            s["approver"] = granted.group(1).rstrip(".")
        if "approval DENIED" in last:
            s["phase"] = "denied"
            return "Approval denied; stopping without posting.", Action(tool="give_up", args={"reason": f"manager denied approval for {inv}; nothing was posted"})
        if "HTTP 50" in last and "MAY have gone through" in last:
            s["phase"] = "readback"
            return "Unknown outcome; reading the list back before anything else.", Action(tool="navigate", args={"url": base + (f"/ledger/bills?q={inv}" if system == "ledger" else f"/nova/payables?search={inv}")})
        if "submitted" in last and "verify" in last:
            s["phase"] = "verify"
            return "Submitted; verifying on the list page.", Action(tool="navigate", args={"url": base + (f"/ledger/bills?q={inv}" if system == "ledger" else f"/nova/payables?search={inv}")})
        intent = {"type": "create_bill" if system == "ledger" else "record_payable", "system": system, "vendor_name": vendor,
                  "vendor_gstin": run.fact(f"vendor_gstin:{inv}"), "invoice_number": inv, "amount_paise": amount,
                  "due_date": due, "po_number": po, "approved_by": s.get("approver", "")}
        if system == "ledger":
            if "/ledger/bills/new" not in obs.url:
                return "Opening the new bill form.", Action(tool="navigate", args={"url": base + "/ledger/bills/new"})
            sel = find(obs, "select")
            if sel and sel.value != vendor:
                return f"Selecting vendor {vendor}.", Action(tool="select", args={"id": sel.id, "option": vendor})
            fields = [("invoice", inv), ("amount", f"{amount / 100:.2f}"), ("total", f"{amount / 100:.2f}"), ("due", due), ("payment due", due), ("po", po), ("purchase order", po), ("approved by", s.get("approver", ""))]
            for key, value in fields:
                e = find(obs, "textbox", key)
                if e and value and e.value != value:
                    return f"Entering {key}.", Action(tool="type", args={"id": e.id, "text": value})
            btn = find(obs, "button", "save bill") or find(obs, "button", "record invoice")
            return "All fields entered; committing the bill through the policy gate.", Action(tool="commit", args={"id": btn.id, "intent": intent})
        # NovaBooks wizard
        if "step 1" in obs.text.lower() or "/nova/payables/record" == obs.url.replace(base, "").split("?")[0]:
            radio = next((e for e in obs.elements if e.role == "radio" and e.name == vendor), None)
            if radio and not radio.checked:
                return f"Choosing supplier {vendor}.", Action(tool="check", args={"id": radio.id})
            if radio and radio.checked:
                return "Continuing to the details step.", Action(tool="click", args={"id": find(obs, "button", "continue").id})
        if "step 2" in obs.text.lower():
            d = date.fromisoformat(due).strftime("%d/%m/%Y")
            for key, value in [("reference", inv), ("total", f"{amount / 100:.2f}"), ("pay by", d), ("order ref", po), ("authorised by", s.get("approver", ""))]:
                e = find(obs, "textbox", key)
                if e and value and e.value != value:
                    return f"Entering {key}.", Action(tool="type", args={"id": e.id, "text": value})
            return "Going to the review step.", Action(tool="click", args={"id": find(obs, "button", "review").id})
        if "step 3" in obs.text.lower():
            btn = find(obs, "button", "confirm and record")
            return "Reviewed; committing through the policy gate.", Action(tool="commit", args={"id": btn.id, "intent": intent})
        if "/nova" not in obs.url or "/nova/payables/record" not in obs.url:
            return "Starting the record-payable wizard.", Action(tool="navigate", args={"url": base + "/nova/payables/record"})
        return "Unexpected NovaBooks page.", Action(tool="give_up", args={"reason": "NovaBooks wizard state not understood"})

    def _report_duplicate(self, state, s, system):
        inv = s["inv"]
        entity = "bill" if system == "ledger" else "payable"
        return "The invoice is already recorded; reporting instead of entering it again.", Action(tool="done", args={
            "summary": f"{inv} is already recorded in {system} ({state.run.fact(f'duplicate_check:{inv}')}). I did not enter it again.",
            "assertions": [{"kind": "count", "system": system, "entity": entity, "match": {"invoice_number": inv}, "expect": {"count": 1},
                            "note": "exactly one record must exist: the pre-existing one"}]})

    # unknown outcome: read back before retrying
    def _readback(self, state, s, obs, system, base):
        inv = s["inv"]
        hits = [r for r in rows(obs) if len(r) >= 3 and inv in r]
        if not s.get("readback_noted"):
            s["readback_noted"] = True
            value = f"exists: record #{hits[0][0]}" if hits else "not found"
            return "Noting what the list shows after the error.", Action(tool="note_fact", args={"key": f"readback:{inv}", "value": value, "source": obs.url})
        s["readback_noted"] = False
        if hits:
            s["phase"] = "verify"
            return "The write did go through; verifying.", Action(tool="navigate", args={"url": obs.url})
        s["phase"] = "record"
        return "The write did not go through; entering it again.", Action(tool="navigate", args={"url": base + ("/ledger/bills/new" if system == "ledger" else "/nova/payables/record")})

    # M5: verify on the page, then declare assertions
    def _verify(self, state, s, obs, system, base):
        run, inv = state.run, s["inv"]
        hits = [r for r in rows(obs) if len(r) >= 3 and inv in r]
        if not hits:
            return "Record not visible yet; refreshing the list.", Action(tool="navigate", args={"url": base + (f"/ledger/bills?q={inv}" if system == "ledger" else f"/nova/payables?search={inv}")})
        amount = int(run.fact(f"pdf_total:{inv}"))
        expect = {"amount_paise": amount, "due_date": run.fact(f"due_date:{inv}"), "status": "posted" if system == "ledger" else "recorded"}
        if run.fact(f"po:{inv}"):
            expect["po_number"] = run.fact(f"po:{inv}")
        if s.get("approver"):
            expect["approved_by"] = s["approver"]
        return "The list shows the record; declaring what must now be true.", Action(tool="done", args={
            "summary": f"Recorded {inv} ({s.get('vendor_name')}) for {amount / 100:,.2f} INR due {run.fact(f'due_date:{inv}')} in {system}"
                       + (f", approved by {s['approver']}" if s.get("approver") else "") + f". Verified on the list page (record #{hits[0][0]}).",
            "assertions": [{"kind": "exists", "system": system, "entity": "bill" if system == "ledger" else "payable",
                            "match": {"invoice_number": inv, "vendor_gstin": run.fact(f"vendor_gstin:{inv}")}, "expect": expect}]})

    # ---- learning (deterministic versions of what the LLM brain does)
    def distill_skill(self, run: RunRecord, context: CompanyContext):
        sysname = run.contract.target_system
        return Skill(name=f"Record a supplier invoice in {sysname}", intent=run.contract.intent, system=sysname,
                     trigger="A request to record/enter a supplier's invoice or bill in an ERP.",
                     workflow=["Find the invoice on the supplier portal; open it; read the PDF (document of record).",
                               "Check the mailbox for revision or correction notices about the invoice.",
                               "Resolve the vendor in the target ERP by GSTIN, not by name.",
                               "Search the ERP for the invoice number; if it exists, report instead of entering.",
                               "Enter the bill with the PDF total, due date and PO; get approval first if the amount requires it.",
                               "Verify on the list page, then declare assertions."],
                     procedure=[f"/{sysname}: " + " → ".join(f"{s.action.tool} {s.url.replace(context.base_url, '')}" for s in run.steps if s.action.tool in ("navigate", "commit"))],
                     pitfalls=["Portal listed amount can differ from the PDF total.", "Revised invoices (-R) supersede originals.",
                               "Vendor masters have stale near-duplicates; match GSTIN."],
                     verification=["The ERP list shows the invoice number with the PDF total and due date."],
                     params=["vendor", "invoice_number"])

    def extract_rules(self, feedback: str, who: str, run, context):
        rules = []
        m = re.search(r"(?:over|above|from|threshold(?: is| of)?)\s*(?:rs\.?|₹)?\s*([\d,]+)", feedback, re.I)
        if m and re.search(r"approv", feedback, re.I):
            paise = int(m.group(1).replace(",", "")) * 100
            rules.append(Rule(kind="policy", text=f"Bills at or above Rs {paise / 100:,.0f} need manager approval before posting (said by {who}).",
                              structured={"approval_threshold_paise": paise}))
        if re.search(r"(?:don't|do not|never) use", feedback, re.I):
            quoted = re.findall(r"['\"]([A-Z][^'\"]*)['\"]", feedback)
            if quoted:
                rules.append(Rule(kind="fact", text=feedback.strip(),
                                  structured={"avoid_vendor": quoted[0].strip(), "use_instead": quoted[1].strip() if len(quoted) > 1 else ""}))
        if not rules and feedback.strip():
            rules.append(Rule(kind="guideline", text=feedback.strip()))
        return rules
