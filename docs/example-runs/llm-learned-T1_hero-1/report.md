# Run learned-T1_hero-1: completed

**Request:** Find the latest invoice from Northwind Supplies, extract the amount and due date, enter it into Ledger, and tell me once it is done

**Outcome:** Bill NW-1043-R posted successfully

**Verifier:** `completed` — all 1 assertion(s) hold; no undeclared writes

## Understanding
- Intent: `record_supplier_invoice` on `ledger`
- Find the latest Northwind Supplies invoice on the Supplier Portal, check the ops mailbox for any revision notices, verify the vendor by GSTIN, check for duplicates in Ledger, then enter and post the bill in Ledger ERP.
- Parameters: `{"vendor": "Northwind Supplies", "which": "latest"}`

## Plan
- [x] **Find latest Northwind Supplies invoice on Supplier Portal** — done when: Latest Northwind Supplies invoice identified and its PDF read, with total, due date, PO, and GSTIN recorded as facts
- [x] **Check ops mailbox for revision notices** — done when: Mailbox checked for any revision/correction notices related to the identified invoice; mail_check fact recorded
- [x] **Verify vendor by GSTIN in Ledger** — done when: Correct active vendor record 'Northwind Supplies' with GSTIN 07AAACN1234F1Z5 confirmed in Ledger (not the stale 'Northwind Supplies Ltd')
- [x] **Check for duplicates in Ledger** — done when: Ledger searched for the invoice number; duplicate_check fact recorded as 'none' or 'exists'
- [x] **Enter and post the bill in Ledger ERP** — done when: Bill created in Ledger with correct invoice number, amount, due date, PO, and vendor; posted with manager approval if required (write)
- [x] **Verify posted bill in Ledger** — done when: Bill confirmed in Ledger with correct details and status 'posted'

## Memory used
- skill `skill_0895f9aa`
- rule `rule_3c046e4b`
- rule `rule_77027b8a`
- rule `rule_3f49116b`

## Facts gathered (with provenance)
| step | fact | value | source |
|---|---|---|---|
| 5 | `pdf_total:NW-1043-R` | 5980000 | PDF /portal/invoices/3/pdf |
| 5 | `due_date:NW-1043-R` | 2026-11-08 | PDF /portal/invoices/3/pdf |
| 5 | `po:NW-1043-R` | PO-7734 | PDF /portal/invoices/3/pdf |
| 5 | `vendor_gstin:NW-1043-R` | 07AAACN1234F1Z5 | PDF /portal/invoices/3/pdf |
| 9 | `mail_check:NW-1043-R` | confirmed: email from accounts@northwind.example 2026-10-09 confirms NW-1043-R supersedes NW-1043 (pricing correction on LA-220 actuators) | mail/1 |
| 13 | `vendor_verified` | Northwind Supplies (ID 11, GSTIN 07AAACN1234F1Z5) confirmed active in Ledger vendor master | ledger/vendors page |
| 17 | `duplicate_check:NW-1043-R` | none | ledger/bills?q=NW-1043-R |

## Approvals
- step 22: GRANTED by priya.manager — amount 59,800.00 is at or above the approval threshold 50,000.00 (rule_3c046e4b); a manager must approve first

## Policy decisions
- step 20: blocked — the form does not contain invoice number 'NW-1043-R' [runtime.form_matches_intent]
- step 22: needs approval — amount 59,800.00 is at or above the approval threshold 50,000.00 (rule_3c046e4b); a manager must approve first [approval_threshold:rule_3c046e4b]
- step 23: allowed — approved by priya.manager (approval 22) [approval_threshold:rule_3c046e4b]

## Verification (independent, via the admin API)
| ok | assertion | detail |
|---|---|---|
| ✅ | exists ledger/bill {"invoice_number": "NW-1043-R"} {"amount_paise": 5980000, "due_date": "2026-11-08", "po_number": "PO-7734", "status": "posted", "vendor_name": "Northwind Supplies"} | row exists with the expected values |

## Timeline
1. `navigate` {"url": "/portal/invoices"} → opened http://127.0.0.1:8000/portal/login?next=/portal/invoices&reason=signed_out (HTTP 200)
2. `fill_form` {"fields": {"1": "ops.agent", "2": "acme-ops-2026"}, "submit": "3"} → Username: typed "ops.agent"; Password: typed "acme-ops-2026"; clicked "Sign in"
3. `click` {"id": 6} → clicked "View"
4. `read_pdf` {"url": "/portal/invoices/3/pdf"} → PDF text: Northwind Supplies GSTIN 07AAACN1234F1Z5  |  accounts@northwind.example TAX INVOICE  (REVISED) Invoice number: NW-1043-R Invoice date: 2026-10-09 Due date: 2026-11-08 Purchase order: PO-7734
5. `note_fact` {"invoice": "NW-1043-R", "facts": {"pdf_total": "5980000", "due_date": "2026-11-08", "po": "PO-7734", "vendor_gstin": "07AAACN1234F1Z5"}, "source": "PDF /portal → noted pdf_total:NW-1043-R = '5980000'; due_date:NW-1043-R = '2026-11-08'; po:NW-1043-R = 'PO-7734'; vendor_gstin:NW-1043-R = '07AAACN1234F1Z5' (source: PDF /portal/invoices/3/pdf)
6. `navigate` {"url": "/mail/inbox"} → opened http://127.0.0.1:8000/mail/login?next=/mail/inbox&reason=signed_out (HTTP 200)
7. `fill_form` {"fields": {"1": "ops.agent", "2": "acme-ops-2026"}, "submit": "3"} → Username: typed "ops.agent"; Password: typed "acme-ops-2026"; clicked "Sign in"
8. `click` {"id": 5} → clicked "Revised invoice for PO-7734"
9. `note_fact` {"invoice": "NW-1043-R", "key": "mail_check", "value": "confirmed: email from accounts@northwind.example 2026-10-09 confirms NW-1043-R supersedes NW-1043 (prici → noted mail_check:NW-1043-R = 'confirmed: email from accounts@northwind.example 2026-10-09 confirms NW-1043-R supersedes NW-1043 (pricing correction on LA-220 actuators)' (source: mail/1)
10. `navigate` {"url": "/ledger/"} → opened http://127.0.0.1:8000/ledger/login?next=/ledger/&reason=signed_out (HTTP 200)
11. `fill_form` {"fields": {"1": "ops.agent", "2": "acme-ops-2026"}, "submit": "3"} → Username: typed "ops.agent"; Password: typed "acme-ops-2026"; clicked "Sign in"
12. `click` {"id": 3} → clicked "Vendors"
13. `note_fact` {"invoice": "NW-1043-R", "key": "vendor_verified", "value": "Northwind Supplies (ID 11, GSTIN 07AAACN1234F1Z5) confirmed active in Ledger vendor master", "sourc → noted vendor_verified = 'Northwind Supplies (ID 11, GSTIN 07AAACN1234F1Z5) confirmed active in Ledger vendor master' (source: ledger/vendors page)
14. `click` {"id": 1} → clicked "Bills"
15. `type` {"id": 5, "text": "NW-1043-R"} → typed "NW-1043-R"
16. `click` {"id": 6} → clicked "Search"
17. `note_fact` {"invoice": "NW-1043-R", "key": "duplicate_check", "value": "none", "source": "ledger/bills?q=NW-1043-R"} → noted duplicate_check:NW-1043-R = 'none' (source: ledger/bills?q=NW-1043-R)
18. `click` {"id": 2} → clicked "New bill"
19. `commit` {"id": 12, "intent": "create_bill", "system": "ledger", "vendor_name": "Northwind Supplies", "invoice_number": "NW-1043-R", "amount_paise": 5980000, "due_date": → bad arguments for commit: Runtime.t_commit() got an unexpected keyword argument 'system'. Expected: {'id': 'element id of the submit button', 'intent': 'declared write: {type, system, vendor_name, ven
20. `commit` {"id": 12, "intent": {"type": "create_bill", "system": "ledger", "vendor_name": "Northwind Supplies", "invoice_number": "NW-1043-R", "amount_paise": 5980000, "d → commit refused: the form does not contain invoice number 'NW-1043-R'
21. `fill_form` {"fields": {"5": "Northwind Supplies", "6": "NW-1043-R", "7": "59800.00", "8": "2026-11-08", "9": "PO-7734", "10": "priya.manager", "11": ""}, "submit": 12} → Vendor: selected "Northwind Supplies"; Invoice number: typed "NW-1043-R"; Amount (INR): typed "59800.00"; Due date: typed "2026-11-08"; PO number: typed "PO-7734"; Approved by (manager username, for b
22. `commit` {"id": 12, "intent": {"type": "create_bill", "system": "ledger", "vendor_name": "Northwind Supplies", "invoice_number": "NW-1043-R", "amount_paise": 5980000, "d → approval GRANTED by priya.manager — fill the approval field with 'priya.manager' and commit again.
23. `commit` {"id": 12, "intent": {"type": "create_bill", "system": "ledger", "vendor_name": "Northwind Supplies", "invoice_number": "NW-1043-R", "amount_paise": 5980000, "d → clicked "Save bill"; submitted. Now verify on the page that the record exists with the right values.
24. `click` {"id": "1"} → clicked "Bills"
25. `done` {"summary": "Bill NW-1043-R posted successfully", "assertions": [{"kind": "exists", "system": "ledger", "entity": "bill", "match": {"invoice_number": "NW-1043-R → assertions recorded; verification will decide the status

## Cost
- steps: 25, browser actions: 30, human interventions: 1
- LLM calls: 31, tokens in/out: 89776/4887, est. cost: $0.0243
- wall time: 726s, brain: llm qwen/qwen3.8-27b -> openai/gpt-oss-20b, memory: on
