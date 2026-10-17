# Run cold-T1_hero-1: completed

**Request:** Find the latest invoice from Northwind Supplies, extract the amount and due date, enter it into Ledger, and tell me once it is done

**Outcome:** Recorded NW-1043-R (Northwind Supplies) for 59,800.00 INR due 2026-11-08 in ledger. Verified on the list page (record #4).

**Verifier:** `completed` — all 1 assertion(s) hold; no undeclared writes

## Understanding
- Intent: `record_supplier_invoice` on `ledger`
- Record Northwind Supplies's latest invoice in ledger after reading its PDF, checking for revisions and duplicates, and getting approval if the amount requires it.
- Parameters: `{"vendor": "Northwind Supplies", "which": "latest"}`

## Plan
- [x] **Identify the invoice and read its PDF** — done when: invoice number, PDF total, due date, PO and GSTIN are noted
- [x] **Check the mailbox for revisions or corrections** — done when: any revision notice is noted
- [x] **Resolve the vendor in ledger by GSTIN and check for duplicates** — done when: duplicate_check fact noted
- [x] **Record the bill in ledger** — done when: the record is saved (approval obtained first if required) (write)
- [x] **Verify the record and report** — done when: the list shows the record with the right values

## Facts gathered (with provenance)
| step | fact | value | source |
|---|---|---|---|
| 5 | `invoice_number` | NW-1043-R | http://127.0.0.1:8000/portal/invoices?vendor=Northwind%20Supplies&status=open |
| 8 | `pdf_total:NW-1043-R` | 5980000 | /portal/invoices/3/pdf |
| 9 | `due_date:NW-1043-R` | 2026-11-08 | /portal/invoices/3/pdf |
| 10 | `po:NW-1043-R` | PO-7734 | /portal/invoices/3/pdf |
| 11 | `vendor_gstin:NW-1043-R` | 07AAACN1234F1Z5 | /portal/invoices/3/pdf |
| 17 | `mail_check:NW-1043-R` | revision notice found: Revised invoice for PO-7734 | http://127.0.0.1:8000/mail/1 |
| 22 | `vendor_name:NW-1043-R` | Northwind Supplies | http://127.0.0.1:8000/ledger/vendors |
| 24 | `duplicate_check:NW-1043-R` | none | http://127.0.0.1:8000/ledger/bills?q=NW-1043-R |

## Policy decisions
- step 31: allowed — allowed [-]

## Verification (independent, via the admin API)
| ok | assertion | detail |
|---|---|---|
| ✅ | exists ledger/bill {"invoice_number": "NW-1043-R", "vendor_gstin": "07AAACN1234F1Z5"} {"amount_paise": 5980000, "due_date": "2026-11-08", "status": "posted", "po_number": "PO-7734"} | row exists with the expected values |

## Timeline
1. `navigate` {"url": "http://127.0.0.1:8000/portal/invoices?vendor=Northwind Supplies&status=open"} → opened http://127.0.0.1:8000/portal/login?next=/portal/invoices%3Fvendor%3DNorthwind%2520Supplies%26status%3Dopen&reason=signed_out (HTTP 200)
2. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
3. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
4. `click` {"id": 3} → clicked "Sign in"
5. `note_fact` {"key": "invoice_number", "value": "NW-1043-R", "source": "http://127.0.0.1:8000/portal/invoices?vendor=Northwind%20Supplies&status=open"} → noted invoice_number = 'NW-1043-R' (source: http://127.0.0.1:8000/portal/invoices?vendor=Northwind%20Supplies&status=open)
6. `click` {"id": 6} → clicked "View"
7. `read_pdf` {"url": "/portal/invoices/3/pdf"} → PDF text: Northwind Supplies GSTIN 07AAACN1234F1Z5  |  accounts@northwind.example TAX INVOICE  (REVISED) Invoice number: NW-1043-R Invoice date: 2026-10-09 Due date: 2026-11-08 Purchase order: PO-7734
8. `note_fact` {"key": "pdf_total:NW-1043-R", "value": "5980000", "source": "/portal/invoices/3/pdf"} → noted pdf_total:NW-1043-R = '5980000' (source: /portal/invoices/3/pdf)
9. `note_fact` {"key": "due_date:NW-1043-R", "value": "2026-11-08", "source": "/portal/invoices/3/pdf"} → noted due_date:NW-1043-R = '2026-11-08' (source: /portal/invoices/3/pdf)
10. `note_fact` {"key": "po:NW-1043-R", "value": "PO-7734", "source": "/portal/invoices/3/pdf"} → noted po:NW-1043-R = 'PO-7734' (source: /portal/invoices/3/pdf)
11. `note_fact` {"key": "vendor_gstin:NW-1043-R", "value": "07AAACN1234F1Z5", "source": "/portal/invoices/3/pdf"} → noted vendor_gstin:NW-1043-R = '07AAACN1234F1Z5' (source: /portal/invoices/3/pdf)
12. `navigate` {"url": "http://127.0.0.1:8000/mail/inbox?q=Northwind"} → opened http://127.0.0.1:8000/mail/login?next=/mail/inbox%3Fq%3DNorthwind&reason=signed_out (HTTP 200)
13. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
14. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
15. `click` {"id": 3} → clicked "Sign in"
16. `click` {"id": 4} → clicked "Revised invoice for PO-7734"
17. `note_fact` {"key": "mail_check:NW-1043-R", "value": "revision notice found: Revised invoice for PO-7734", "source": "http://127.0.0.1:8000/mail/1"} → noted mail_check:NW-1043-R = 'revision notice found: Revised invoice for PO-7734' (source: http://127.0.0.1:8000/mail/1)
18. `navigate` {"url": "http://127.0.0.1:8000/ledger/vendors"} → opened http://127.0.0.1:8000/ledger/login?next=/ledger/vendors&reason=signed_out (HTTP 200)
19. `type` {"id": 1, "text": "ops.agent"} → typed "ops.agent"
20. `type` {"id": 2, "text": "acme-ops-2026"} → typed "acme-ops-2026"
21. `click` {"id": 3} → clicked "Sign in"
22. `note_fact` {"key": "vendor_name:NW-1043-R", "value": "Northwind Supplies", "source": "http://127.0.0.1:8000/ledger/vendors"} → noted vendor_name:NW-1043-R = 'Northwind Supplies' (source: http://127.0.0.1:8000/ledger/vendors)
23. `navigate` {"url": "http://127.0.0.1:8000/ledger/bills?q=NW-1043-R"} → opened http://127.0.0.1:8000/ledger/bills?q=NW-1043-R (HTTP 200)
24. `note_fact` {"key": "duplicate_check:NW-1043-R", "value": "none", "source": "http://127.0.0.1:8000/ledger/bills?q=NW-1043-R"} → noted duplicate_check:NW-1043-R = 'none' (source: http://127.0.0.1:8000/ledger/bills?q=NW-1043-R)
25. `navigate` {"url": "http://127.0.0.1:8000/ledger/bills/new"} → opened http://127.0.0.1:8000/ledger/bills/new (HTTP 200)
26. `select` {"id": 5, "option": "Northwind Supplies"} → selected "Northwind Supplies"
27. `type` {"id": 6, "text": "NW-1043-R"} → typed "NW-1043-R"
28. `type` {"id": 7, "text": "59800.00"} → typed "59800.00"
29. `type` {"id": 8, "text": "2026-11-08"} → typed "2026-11-08"
30. `type` {"id": 9, "text": "PO-7734"} → typed "PO-7734"
31. `commit` {"id": 12, "intent": {"type": "create_bill", "system": "ledger", "vendor_name": "Northwind Supplies", "vendor_gstin": "07AAACN1234F1Z5", "invoice_number": "NW-1 → clicked "Save bill"; submitted. Now verify on the page that the record exists with the right values.
32. `navigate` {"url": "http://127.0.0.1:8000/ledger/bills?q=NW-1043-R"} → opened http://127.0.0.1:8000/ledger/bills?q=NW-1043-R (HTTP 200)
33. `done` {"summary": "Recorded NW-1043-R (Northwind Supplies) for 59,800.00 INR due 2026-11-08 in ledger. Verified on the list page (record #4).", "assertions": [{"kind" → assertions recorded; verification will decide the status

## Cost
- steps: 33, browser actions: 25, human interventions: 0
- LLM calls: 0, tokens in/out: 0/0, est. cost: $0.0000
- wall time: 2s, brain: scripted sop-controller, memory: off
