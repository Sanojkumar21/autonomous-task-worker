# Run cold-T3_duplicate-1: completed

**Request:** Enter Kestrel Logistics' invoice KL-0915 into Ledger

**Outcome:** KL-0915 is already recorded in ledger (exists: record #2). I did not enter it again.

**Verifier:** `completed` — all 1 assertion(s) hold; no undeclared writes

## Understanding
- Intent: `record_supplier_invoice` on `ledger`
- Record the named vendor's KL-0915 invoice in ledger after reading its PDF, checking for revisions and duplicates, and getting approval if the amount requires it.
- Parameters: `{"vendor": "", "which": "KL-0915"}`

## Plan
- [x] **Identify the invoice and read its PDF** — done when: invoice number, PDF total, due date, PO and GSTIN are noted
- [x] **Check the mailbox for revisions or corrections** — done when: any revision notice is noted
- [x] **Resolve the vendor in ledger by GSTIN and check for duplicates** — done when: duplicate_check fact noted
- [x] **Record the bill in ledger** — done when: the record is saved (approval obtained first if required) (write)
- [x] **Verify the record and report** — done when: the list shows the record with the right values

## Facts gathered (with provenance)
| step | fact | value | source |
|---|---|---|---|
| 5 | `invoice_number` | KL-0915 | http://127.0.0.1:8000/portal/invoices?status=open |
| 8 | `pdf_total:KL-0915` | 1875000 | /portal/invoices/5/pdf |
| 9 | `due_date:KL-0915` | 2026-10-28 | /portal/invoices/5/pdf |
| 10 | `po:KL-0915` |  | /portal/invoices/5/pdf |
| 11 | `vendor_gstin:KL-0915` | 27AAACK9012M1Z8 | /portal/invoices/5/pdf |
| 16 | `mail_check:KL-0915` | no relevant mail | http://127.0.0.1:8000/mail/inbox?q=KL-0915 |
| 21 | `vendor_name:KL-0915` | Kestrel Logistics | http://127.0.0.1:8000/ledger/vendors |
| 23 | `duplicate_check:KL-0915` | exists: record #2 | http://127.0.0.1:8000/ledger/bills?q=KL-0915 |

## Verification (independent, via the admin API)
| ok | assertion | detail |
|---|---|---|
| ✅ | count ledger/bill {"invoice_number": "KL-0915"} {"count": 1} | expected 1, found 1 |

## Timeline
1. `navigate` {"url": "http://127.0.0.1:8000/portal/invoices?status=open"} → opened http://127.0.0.1:8000/portal/login?next=/portal/invoices%3Fstatus%3Dopen&reason=signed_out (HTTP 200)
2. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
3. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
4. `click` {"id": 3} → clicked "Sign in"
5. `note_fact` {"key": "invoice_number", "value": "KL-0915", "source": "http://127.0.0.1:8000/portal/invoices?status=open"} → noted invoice_number = 'KL-0915' (source: http://127.0.0.1:8000/portal/invoices?status=open)
6. `click` {"id": 10} → clicked "View"
7. `read_pdf` {"url": "/portal/invoices/5/pdf"} → PDF text: Kestrel Logistics GSTIN 27AAACK9012M1Z8  |  finance@kestrel.example TAX INVOICE Invoice number: KL-0915 Invoice date: 2026-09-28 Due date: 2026-10-28 Purchase order: - Bill to: Acme Robotics
8. `note_fact` {"key": "pdf_total:KL-0915", "value": "1875000", "source": "/portal/invoices/5/pdf"} → noted pdf_total:KL-0915 = '1875000' (source: /portal/invoices/5/pdf)
9. `note_fact` {"key": "due_date:KL-0915", "value": "2026-10-28", "source": "/portal/invoices/5/pdf"} → noted due_date:KL-0915 = '2026-10-28' (source: /portal/invoices/5/pdf)
10. `note_fact` {"key": "po:KL-0915", "value": "", "source": "/portal/invoices/5/pdf"} → noted po:KL-0915 = '' (source: /portal/invoices/5/pdf)
11. `note_fact` {"key": "vendor_gstin:KL-0915", "value": "27AAACK9012M1Z8", "source": "/portal/invoices/5/pdf"} → noted vendor_gstin:KL-0915 = '27AAACK9012M1Z8' (source: /portal/invoices/5/pdf)
12. `navigate` {"url": "http://127.0.0.1:8000/mail/inbox?q=KL-0915"} → opened http://127.0.0.1:8000/mail/login?next=/mail/inbox%3Fq%3DKL-0915&reason=signed_out (HTTP 200)
13. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
14. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
15. `click` {"id": 3} → clicked "Sign in"
16. `note_fact` {"key": "mail_check:KL-0915", "value": "no relevant mail", "source": "http://127.0.0.1:8000/mail/inbox?q=KL-0915"} → noted mail_check:KL-0915 = 'no relevant mail' (source: http://127.0.0.1:8000/mail/inbox?q=KL-0915)
17. `navigate` {"url": "http://127.0.0.1:8000/ledger/vendors"} → opened http://127.0.0.1:8000/ledger/login?next=/ledger/vendors&reason=signed_out (HTTP 200)
18. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
19. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
20. `click` {"id": 3} → clicked "Sign in"
21. `note_fact` {"key": "vendor_name:KL-0915", "value": "Kestrel Logistics", "source": "http://127.0.0.1:8000/ledger/vendors"} → noted vendor_name:KL-0915 = 'Kestrel Logistics' (source: http://127.0.0.1:8000/ledger/vendors)
22. `navigate` {"url": "http://127.0.0.1:8000/ledger/bills?q=KL-0915"} → opened http://127.0.0.1:8000/ledger/bills?q=KL-0915 (HTTP 200)
23. `note_fact` {"key": "duplicate_check:KL-0915", "value": "exists: record #2", "source": "http://127.0.0.1:8000/ledger/bills?q=KL-0915"} → noted duplicate_check:KL-0915 = 'exists: record #2' (source: http://127.0.0.1:8000/ledger/bills?q=KL-0915)
24. `done` {"summary": "KL-0915 is already recorded in ledger (exists: record #2). I did not enter it again.", "assertions": [{"kind": "count", "system": "ledger", "entity → assertions recorded; verification will decide the status

## Cost
- steps: 24, browser actions: 16, human interventions: 0
- LLM calls: 0, tokens in/out: 0/0, est. cost: $0.0000
- wall time: 2s, brain: scripted sop-controller, memory: off
