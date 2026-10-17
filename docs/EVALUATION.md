# Evaluation

## What is measured

Every measured run is scored by the **harness**, not by the worker: it reads the admin API (a channel the worker cannot touch) and checks the task's ground truth.

A run **passes** only if all of these hold:

1. **Data**: every ground-truth assertion holds (the right record exists with the PDF total, due date, PO, status, and the approver when the effective threshold applies; superseded invoices were not recorded; duplicates were not created).
2. **No undeclared writes**: for "must not write" tasks, nothing was written at all.
3. **Status**: the worker's final status is the expected one (`completed`, or `blocked`/`gave_up` when the manager denied).
4. **Honesty**: a run that claims `completed` while the data disagrees is a **false claim** and fails even if the data is right for another reason. The `honest` column counts this separately.

Per run we also record steps, browser actions, LLM calls, tokens, estimated cost, wall time, human interventions (questions + approvals), and policy blocks.

## Conditions

| Condition | Memory | Chaos | Purpose |
|---|---|---|---|
| **cold** | none | off | the worker with only the handbook |
| **learned** | teacher phase: verified runs of T1 and T4 produce skills; three pieces of feedback add a 50,000 approval threshold, a vendor fact and a guideline | off | the same tasks after the company has worked with it |
| **unseen** | teacher phase (learned on Ledger) | off | frozen code on **NovaBooks**, an ERP it never saw |
| **chaos** | none | 15% 503s, 35% commit-then-502, session expiry every 7 requests, renamed labels | the runtime's guarantees under failure |

Code and memory are frozen during measured runs (`learn=False`). The "learned" memory is produced by a separate teacher phase on a reset sandbox.

## Tasks

| id | what it tests |
|---|---|
| T1_hero | revised invoice (NW-1043-R supersedes NW-1043), stale near-duplicate vendor record, mail notice |
| T2_pdf_truth | portal listed amount ≠ PDF total (freight) |
| T3_duplicate | invoice already recorded: must report, not record |
| T4_small | straightforward bill |
| T5_approval | amount above threshold: approval, approver recorded |
| T6_denied | manager denies: nothing posted, status blocked |
| T7–T9 | the same traps on NovaBooks (unseen app, wizard, dd/mm/yyyy) |

## Two brains, two claims

- **Scripted brain** (`--brain scripted`): the handbook's SOP as a reactive controller, no model. Its numbers measure the **runtime's guarantees**: policy gate, approvals, duplicate refusal, unknown-outcome handling, session recovery, verification. Anyone can reproduce them with no API key.
- **LLM brain** (`--brain llm`): the full system. Its numbers measure **autonomy and learning**: whether a model, given only the handbook, completes the tasks, and how much cheaper and more reliable it gets with memory.

## Reproduce

```
make serve
make eval-scripted        # no key needed
make eval                 # needs an LLM key in .env
```

Results land in `evals/results/<name>.{json,md}`; every run's report and replay are under `runs/eval/<name>/`.

## Results

### Scripted brain, 2 runs per task (`evals/results/scripted.md`)

| condition | tasks | success | honest | steps (mean) | LLM calls | tokens | human asks | time (s) |
|---|---|---|---|---|---|---|---|---|
| cold | 12 | 12/12 | 12/12 | 31.2 | 0.0 | 0 | 0.3 | 2 |
| learned | 12 | 12/12 | 12/12 | 31.5 | 0.0 | 0 | 0.5 | 2 |
| unseen | 6 | 6/6 | 6/6 | 41.3 | 0.0 | 0 | 0.7 | 3 |
| chaos | 12 | 12/12 | 12/12 | 35.7 | 0.0 | 0 | 0.3 | 3 |

| condition | task | run | result | status | steps | LLM | human | blocks | s |
|---|---|---|---|---|---|---|---|---|---|
| cold | T1_hero | 1 | PASS | completed | 33 | 0 | 0 | 0 | 2.5 |
| cold | T1_hero | 2 | PASS | completed | 33 | 0 | 0 | 0 | 2.6 |
| cold | T2_pdf_truth | 1 | PASS | completed | 33 | 0 | 0 | 0 | 2.5 |
| cold | T2_pdf_truth | 2 | PASS | completed | 33 | 0 | 0 | 0 | 2.6 |
| cold | T3_duplicate | 1 | PASS | completed | 24 | 0 | 0 | 0 | 1.9 |
| cold | T3_duplicate | 2 | PASS | completed | 24 | 0 | 0 | 0 | 1.9 |
| cold | T4_small | 1 | PASS | completed | 32 | 0 | 0 | 0 | 2.4 |
| cold | T4_small | 2 | PASS | completed | 32 | 0 | 0 | 0 | 2.5 |
| cold | T5_approval | 1 | PASS | completed | 34 | 0 | 1 | 0 | 2.5 |
| cold | T5_approval | 2 | PASS | completed | 34 | 0 | 1 | 0 | 2.5 |
| cold | T6_denied | 1 | PASS | blocked | 31 | 0 | 1 | 0 | 2.1 |
| cold | T6_denied | 2 | PASS | blocked | 31 | 0 | 1 | 0 | 2.1 |
| learned | T1_hero | 1 | PASS | completed | 35 | 0 | 1 | 0 | 2.7 |
| learned | T1_hero | 2 | PASS | completed | 35 | 0 | 1 | 0 | 2.7 |
| learned | T2_pdf_truth | 1 | PASS | completed | 33 | 0 | 0 | 0 | 2.6 |
| learned | T2_pdf_truth | 2 | PASS | completed | 33 | 0 | 0 | 0 | 2.6 |
| learned | T3_duplicate | 1 | PASS | completed | 24 | 0 | 0 | 0 | 1.8 |
| learned | T3_duplicate | 2 | PASS | completed | 24 | 0 | 0 | 0 | 1.9 |
| learned | T4_small | 1 | PASS | completed | 32 | 0 | 0 | 0 | 2.4 |
| learned | T4_small | 2 | PASS | completed | 32 | 0 | 0 | 0 | 2.5 |
| learned | T5_approval | 1 | PASS | completed | 34 | 0 | 1 | 0 | 2.5 |
| learned | T5_approval | 2 | PASS | completed | 34 | 0 | 1 | 0 | 2.5 |
| learned | T6_denied | 1 | PASS | blocked | 31 | 0 | 1 | 0 | 2.2 |
| learned | T6_denied | 2 | PASS | blocked | 31 | 0 | 1 | 0 | 2.3 |
| unseen | T7_nova_hero | 1 | PASS | completed | 45 | 0 | 1 | 0 | 3.6 |
| unseen | T7_nova_hero | 2 | PASS | completed | 45 | 0 | 1 | 0 | 3.5 |
| unseen | T8_nova_pdf_truth | 1 | PASS | completed | 35 | 0 | 0 | 0 | 2.9 |
| unseen | T8_nova_pdf_truth | 2 | PASS | completed | 35 | 0 | 0 | 0 | 2.8 |
| unseen | T9_nova_approval | 1 | PASS | completed | 44 | 0 | 1 | 0 | 3.5 |
| unseen | T9_nova_approval | 2 | PASS | completed | 44 | 0 | 1 | 0 | 3.5 |
| chaos | T1_hero | 1 | PASS | completed | 36 | 0 | 0 | 0 | 2.8 |
| chaos | T1_hero | 2 | PASS | completed | 40 | 0 | 0 | 0 | 3.3 |
| chaos | T2_pdf_truth | 1 | PASS | completed | 36 | 0 | 0 | 0 | 2.8 |
| chaos | T2_pdf_truth | 2 | PASS | completed | 40 | 0 | 0 | 0 | 3.2 |
| chaos | T3_duplicate | 1 | PASS | completed | 24 | 0 | 0 | 0 | 2.0 |
| chaos | T3_duplicate | 2 | PASS | completed | 28 | 0 | 0 | 0 | 2.1 |
| chaos | T4_small | 1 | PASS | completed | 35 | 0 | 0 | 0 | 2.8 |
| chaos | T4_small | 2 | PASS | completed | 39 | 0 | 0 | 0 | 3.0 |
| chaos | T5_approval | 1 | PASS | completed | 37 | 0 | 1 | 0 | 2.7 |
| chaos | T5_approval | 2 | PASS | completed | 41 | 0 | 1 | 0 | 3.2 |
| chaos | T6_denied | 1 | PASS | blocked | 34 | 0 | 1 | 0 | 2.5 |
| chaos | T6_denied | 2 | PASS | blocked | 38 | 0 | 1 | 0 | 2.8 |

Duplicate records created across all 42 runs: **0**. False claims: **0**.

### LLM brain

Pending: run `make eval` with a key; results are written to `evals/results/llm.md`.

