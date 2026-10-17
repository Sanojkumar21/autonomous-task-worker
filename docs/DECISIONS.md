# Design decisions

Each entry: the decision, the alternative, why.

1. **One brain, one loop, no framework.** Alternative: LangGraph/CrewAI multi-agent. Hand-offs lose state and hide decisions; a single reactive loop with explicit phases is easier to reason about, test and explain. The brain is an interface, so the same runtime runs an LLM or a scripted controller.

2. **Plans are target states, not click sequences.** Alternative: the planner emits steps like "click New bill". Target states ("the bill exists with the PDF total") stay true when a label is renamed or a flow changes, and they double as the verification criteria.

3. **Code enforces, the model proposes.** Alternative: ask the model to follow policy. Models forget; the gate does not. Required facts, duplicates, PDF-total match, approval thresholds, read-back after an unknown outcome and vendor bans are all checked in `policy.py`, with learned rules layered on top.

4. **Facts carry provenance.** Every number the worker uses was read somewhere (`note_fact key value source`). The report shows the table; the gate refuses writes whose facts are missing. "I think the amount is X" is not a fact.

5. **Declare the write before clicking.** `commit` takes an intent and cross-checks it against the form. This catches the model filling the wrong field or the wrong amount before anything is submitted, and it is the hook for approvals.

6. **Unknown outcomes are first-class.** A 5xx after a submit is neither success nor failure. The runtime records it; the gate blocks a retry until the list was read back. This is the single most common way agents create duplicate records, and the chaos suite proves it cannot happen here.

7. **The verifier is independent and model-free.** It reads the admin API, a channel the worker is forbidden to use, and compares data to data. The brain's "done" is a claim; only the verifier sets `completed`.

8. **Learn only from verified runs, and never silently.** Skills are distilled only when the verifier said `completed`. Rules record who said what, when, in which run. Memory is plain JSON a person can read, edit or delete.

9. **Two memory levels: workflow and procedure.** A skill's workflow is app-agnostic and transfers to an unseen app; its procedure is app-specific. Facts and policy rules are about the company, so they transfer everywhere.

10. **Frozen code and memory during measurement.** Evaluation runs with `learn=False`; the "learned" condition is produced by a separate teacher phase. Otherwise the benchmark would measure the worker learning the benchmark.

11. **Honesty is scored.** A run that claims `completed` while the ground truth disagrees is a false claim and fails even if the data happened to be right for another reason. The harness reports `honest` separately.

12. **Text-first observation, vision on demand.** A compact DOM-derived text view is cheaper, deterministic and works with free models; `look` attaches a screenshot for vision-capable models when the text view is not enough.

13. **Free models by default.** Gemini Flash, Groq and OpenRouter free tiers are supported through plain HTTPS; an Anthropic provider is included. The scripted brain runs the whole suite with no key at all, so reviewers can reproduce the runtime guarantees for free.

14. **A simulated company, not mocks.** Four real web apps with logins, validation, PDFs, a mailbox, an audit log and fault injection. "It works on a mock" proves nothing; "it survived commit-then-502 with zero duplicates" does.
