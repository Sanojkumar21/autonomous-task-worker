# Run chaos-T4_small-2: completed

**Request:** Please record the latest invoice from Orbit Office Supplies in Ledger

**Outcome:** Recorded OR-5521 (Orbit Office Supplies) for 6,400.00 INR due 2026-10-21 in ledger. Verified on the list page (record #4).

**Verifier:** `completed` — all 1 assertion(s) hold; no undeclared writes

## Understanding
- Intent: `record_supplier_invoice` on `ledger`
- Record Orbit Office Supplies's latest invoice in ledger after reading its PDF, checking for revisions and duplicates, and getting approval if the amount requires it.
- Parameters: `{"vendor": "Orbit Office Supplies", "which": "latest"}`

## Plan
- [x] **Identify the invoice and read its PDF** — done when: invoice number, PDF total, due date, PO and GSTIN are noted
- [x] **Check the mailbox for revisions or corrections** — done when: any revision notice is noted
- [x] **Resolve the vendor in ledger by GSTIN and check for duplicates** — done when: duplicate_check fact noted
- [x] **Record the bill in ledger** — done when: the record is saved (approval obtained first if required) (write)
- [x] **Verify the record and report** — done when: the list shows the record with the right values

## Facts gathered (with provenance)
| step | fact | value | source |
|---|---|---|---|
| 9 | `invoice_number` | OR-5521 | http://127.0.0.1:8000/portal/invoices |
| 12 | `pdf_total:OR-5521` | 640000 | /portal/invoices/6/pdf |
| 13 | `due_date:OR-5521` | 2026-10-21 | /portal/invoices/6/pdf |
| 14 | `po:OR-5521` | PO-7741 | /portal/invoices/6/pdf |
| 15 | `vendor_gstin:OR-5521` | 06AAACO3456P1Z1 | /portal/invoices/6/pdf |
| 20 | `mail_check:OR-5521` | no relevant mail | http://127.0.0.1:8000/mail/inbox?q=Orbit |
| 25 | `vendor_name:OR-5521` | Orbit Office Supplies | http://127.0.0.1:8000/ledger/vendors |
| 27 | `duplicate_check:OR-5521` | none | http://127.0.0.1:8000/ledger/bills?q=OR-5521 |

## Policy decisions
- step 37: allowed — allowed [-]

## Verification (independent, via the admin API)
| ok | assertion | detail |
|---|---|---|
| ✅ | exists ledger/bill {"invoice_number": "OR-5521", "vendor_gstin": "06AAACO3456P1Z1"} {"amount_paise": 640000, "due_date": "2026-10-21", "status": "posted", "po_number": "PO-7741"} | row exists with the expected values |

## Timeline
1. `navigate` {"url": "http://127.0.0.1:8000/portal/invoices?vendor=Orbit Office Supplies&status=open"} → opened http://127.0.0.1:8000/portal/login?next=/portal/invoices%3Fvendor%3DOrbit%2520Office%2520Supplies%26status%3Dopen&reason=signed_out (HTTP 200)
2. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
3. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
4. `click` {"id": 3} → clicked "Sign in"
5. `navigate` {"url": "http://127.0.0.1:8000/portal/login"} → opened http://127.0.0.1:8000/portal/login (HTTP 200)
6. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
7. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
8. `click` {"id": 3} → clicked "Sign in"
9. `note_fact` {"key": "invoice_number", "value": "OR-5521", "source": "http://127.0.0.1:8000/portal/invoices"} → noted invoice_number = 'OR-5521' (source: http://127.0.0.1:8000/portal/invoices)
10. `click` {"id": 8} → clicked "View"
11. `read_pdf` {"url": "/portal/invoices/6/pdf"} → PDF text: Orbit Office Supplies GSTIN 06AAACO3456P1Z1  |  ar@orbit.example TAX INVOICE Invoice number: OR-5521 Invoice date: 2026-10-07 Due date: 2026-10-21 Purchase order: PO-7741 Bill to: Acme Robot
12. `note_fact` {"key": "pdf_total:OR-5521", "value": "640000", "source": "/portal/invoices/6/pdf"} → noted pdf_total:OR-5521 = '640000' (source: /portal/invoices/6/pdf)
13. `note_fact` {"key": "due_date:OR-5521", "value": "2026-10-21", "source": "/portal/invoices/6/pdf"} → noted due_date:OR-5521 = '2026-10-21' (source: /portal/invoices/6/pdf)
14. `note_fact` {"key": "po:OR-5521", "value": "PO-7741", "source": "/portal/invoices/6/pdf"} → noted po:OR-5521 = 'PO-7741' (source: /portal/invoices/6/pdf)
15. `note_fact` {"key": "vendor_gstin:OR-5521", "value": "06AAACO3456P1Z1", "source": "/portal/invoices/6/pdf"} → noted vendor_gstin:OR-5521 = '06AAACO3456P1Z1' (source: /portal/invoices/6/pdf)
16. `navigate` {"url": "http://127.0.0.1:8000/mail/inbox?q=Orbit"} → opened http://127.0.0.1:8000/mail/login?next=/mail/inbox%3Fq%3DOrbit&reason=signed_out (HTTP 200)
17. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
18. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
19. `click` {"id": 3} → clicked "Sign in"
20. `note_fact` {"key": "mail_check:OR-5521", "value": "no relevant mail", "source": "http://127.0.0.1:8000/mail/inbox?q=Orbit"} → noted mail_check:OR-5521 = 'no relevant mail' (source: http://127.0.0.1:8000/mail/inbox?q=Orbit)
21. `navigate` {"url": "http://127.0.0.1:8000/ledger/vendors"} → opened http://127.0.0.1:8000/ledger/login?next=/ledger/vendors&reason=signed_out (HTTP 200)
22. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
23. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
24. `click` {"id": 3} → clicked "Sign in"
25. `note_fact` {"key": "vendor_name:OR-5521", "value": "Orbit Office Supplies", "source": "http://127.0.0.1:8000/ledger/vendors"} → noted vendor_name:OR-5521 = 'Orbit Office Supplies' (source: http://127.0.0.1:8000/ledger/vendors)
26. `navigate` {"url": "http://127.0.0.1:8000/ledger/bills?q=OR-5521"} → opened http://127.0.0.1:8000/ledger/bills?q=OR-5521 (HTTP 200)
27. `note_fact` {"key": "duplicate_check:OR-5521", "value": "none", "source": "http://127.0.0.1:8000/ledger/bills?q=OR-5521"} → noted duplicate_check:OR-5521 = 'none' (source: http://127.0.0.1:8000/ledger/bills?q=OR-5521)
28. `navigate` {"url": "http://127.0.0.1:8000/ledger/bills/new"} → opened http://127.0.0.1:8000/ledger/login?next=/ledger/bills/new&reason=signed_out (HTTP 200)
29. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
30. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
31. `click` {"id": 3} → clicked "Sign in"
32. `select` {"id": 5, "option": "Orbit Office Supplies"} → selected "Orbit Office Supplies"
33. `type` {"id": 6, "text": "OR-5521"} → typed "OR-5521"
34. `type` {"id": 7, "text": "6400.00"} → typed "6400.00"
35. `type` {"id": 8, "text": "2026-10-21"} → typed "2026-10-21"
36. `type` {"id": 9, "text": "PO-7741"} → typed "PO-7741"
37. `commit` {"id": 12, "intent": {"type": "create_bill", "system": "ledger", "vendor_name": "Orbit Office Supplies", "vendor_gstin": "06AAACO3456P1Z1", "invoice_number": "O → clicked "Record invoice"; submitted. Now verify on the page that the record exists with the right values.
38. `navigate` {"url": "http://127.0.0.1:8000/ledger/bills?q=OR-5521"} → opened http://127.0.0.1:8000/ledger/bills?q=OR-5521 (HTTP 200)
39. `done` {"summary": "Recorded OR-5521 (Orbit Office Supplies) for 6,400.00 INR due 2026-10-21 in ledger. Verified on the list page (record #4).", "assertions": [{"kind" → assertions recorded; verification will decide the status

## Cost
- steps: 39, browser actions: 31, human interventions: 0
- LLM calls: 0, tokens in/out: 0/0, est. cost: $0.0000
- wall time: 3s, brain: scripted sop-controller, memory: off
