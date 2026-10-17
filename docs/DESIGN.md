# Design

An autonomous task worker that turns a plain-English request into verified work in a company's web systems, and gets better at it the more the company works with it.

## The loop

```
request ─► Understand ─► Plan ─► ┌─► Observe ─► Decide ─► Act ─┐ ─► Verify ─► Learn ─► Report
           (brain)      (brain)  │   (browser)  (brain)  (runtime)│   (code)    (memory)
                                 └──────── until done ───────────┘
```

| Part | Who decides | Where |
|---|---|---|
| What the request means; which milestones (target states) get there; the next action | **the brain** (an LLM, or a scripted SOP controller in tests) | `worker/brains/` |
| What the page contains (text + numbered interactive elements) | the browser layer, from the DOM | `worker/browser.py` |
| Whether a write may happen: required facts, duplicates, PDF total, approval threshold, learned rules | **code** (policy gate) | `worker/policy.py` |
| Whether a question or approval goes to a person | the runtime, through the human channel | `worker/runtime.py`, `worker/human.py` |
| Whether the task is done | **code** (independent verifier through the admin API, a channel the worker cannot use) | `worker/verifier.py` |
| What to remember | the brain proposes, memory stores with provenance | `worker/memory/` |

The brain never sets the status, never bypasses the gate, and never reads the database. Every claim it makes is data the verifier checks.

## Observation

The page is rendered as text: URL, headings, paragraphs, table rows (`| a | b |`), alerts, and every interactive element as `[id] role "name" = value`. Ids are assigned fresh on every observation, so the brain acts on *what it sees now*, which is why renamed labels (chaos `ui_drift`) and expired sessions do not break it. A vision model can additionally be handed a screenshot (`look`).

## Writes: declare, check, then click

A write is never a bare click. The brain calls `commit(button, intent)` with a declared intent: type, system, vendor, invoice number, amount in paise, due date, PO. The runtime then:

1. cross-checks that the form (or review page) actually contains that invoice number and amount;
2. runs the policy gate: required facts (`duplicate_check:<inv>`, `pdf_total:<inv>`) must exist, the amount must equal the PDF total, no duplicate, no pending unknown outcome without a read-back, no vendor a person told us to avoid;
3. asks a manager if the amount is at or above the effective threshold, and then requires the approver's name in the form;
4. clicks, and watches the response. A 5xx after a submit records `unknown_outcome:<inv> = pending`; the gate refuses any retry until a `readback:<inv>` fact exists. That is what makes `commit_then_502` produce zero duplicates.

## Verification

`done(summary, assertions)` records assertions such as *a Ledger bill for NW-1043-R with GSTIN 07AAACN1234F1Z5 exists with amount 5980000, due 2026-11-08, status posted*. The verifier reads the admin snapshot and the audit log since the run started, checks each assertion, and flags any write that no assertion explains. Statuses: `completed`, `completed_with_exceptions`, `failed` (the brain claimed done, the data disagrees), `unverified`.

## Learning

Three kinds of memory, all JSON with provenance (`memory/skills.json`, `memory/rules.json`):

- **Skills** are distilled from *verified* runs only: an app-agnostic workflow (transfers to a system the worker has never seen) plus a concrete procedure for the app it ran on, pitfalls, and how to verify. A newer verified skill for the same intent and system replaces the older one. Skills can also be recorded from a **human demonstration** (`worker demonstrate`): the same event vocabulary, values turned into `{placeholders}`.
- **Rules** come from what people say: during a run (clarification answers, approval notes) or through `worker feedback`. A *policy* rule carries a structured setting the gate enforces (`approval_threshold_paise`); a *fact* fixes company data (`avoid_vendor` / `use_instead`); a *guideline* is advice the planner reads. A new structured value supersedes the old one; nothing is deleted.

Memory is read-only during evaluation runs (frozen code, frozen memory), so measured improvements are not the worker quietly re-learning mid-benchmark.

## Generalization

NovaBooks is a second ERP with different words (payable/supplier/reference/total/pay by), a three-step wizard, `dd/mm/yyyy` dates and its own login. The worker's code is frozen before it meets it. What carries over is the handbook, the learned rules and facts (they are about the company, not the app), and the workflow half of a skill learned on Ledger.

## Chaos

The sandbox can inject: `http_503` before a request, `commit_then_502` (the write commits, the response is 502), `session_expiry_every` N authenticated requests, `ui_drift` (labels renamed), `slow_ms`. Faults are seeded, so runs are repeatable.

## What is deliberately not here

No agent framework: the loop is ~150 lines and every decision point is visible. No tool-specific selectors. No database access for the worker. No model in the gate or the verifier.
