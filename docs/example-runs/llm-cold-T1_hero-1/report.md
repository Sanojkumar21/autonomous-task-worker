# Run cold-T1_hero-1: completed

**Request:** Find the latest invoice from Northwind Supplies, extract the amount and due date, enter it into Ledger, and tell me once it is done

**Outcome:** Found the latest Northwind Supplies invoice NW-1043-R (revised, supersedes NW-1043) on the Supplier Portal. Read the PDF: total Rs 59,800.00, due date 2026-11-08, PO-7734, vendor GSTIN 07AAACN1234F1Z5. Confirmed no duplicate in Ledger ERP. Recorded the bill in Ledger ERP as Bill #4, status posted. Verified the record matches all expected fields.

**Verifier:** `completed` — all 1 assertion(s) hold; no undeclared writes

## Understanding
- Intent: `record_supplier_invoice` on `ledger`
- Find the latest Northwind Supplies invoice on the Supplier Portal, read its PDF for amount/due date/PO, check for revisions and duplicates, then record the bill in Ledger ERP and verify.
- Parameters: `{"vendor": "Northwind Supplies", "which": "latest"}`

## Plan
- [x] **Locate latest Northwind Supplies invoice on Supplier Portal** — done when: I have opened the latest Northwind Supplies invoice page and can see its invoice number and PDF link
- [x] **Read PDF and check for revisions/duplicates** — done when: I have recorded pdf_total, due_date, po, vendor_gstin facts from the PDF, confirmed no newer -R revision exists, and confirmed no duplicate in Ledger ERP
- [x] **Record the bill in Ledger ERP** — done when: The bill is saved in Ledger ERP with correct invoice number, amount, due date, PO and vendor (write)
- [x] **Verify the recorded bill** — done when: I have opened the bill in Ledger ERP and confirmed it exists with the expected fields

## Facts gathered (with provenance)
| step | fact | value | source |
|---|---|---|---|
| 5 | `pdf_total:NW-1043-R` | 5980000 | PDF /portal/invoices/3/pdf |
| 5 | `due_date:NW-1043-R` | 2026-11-08 | PDF /portal/invoices/3/pdf |
| 5 | `po:NW-1043-R` | PO-7734 | PDF /portal/invoices/3/pdf |
| 5 | `vendor_gstin:NW-1043-R` | 07AAACN1234F1Z5 | PDF /portal/invoices/3/pdf |
| 11 | `duplicate_check:NW-1043-R` | none | Ledger ERP search for NW-1043-R returned no results |
| 19 | `readback:NW-1043-R` | Bill #4 posted in Ledger ERP: vendor Northwind Supplies (GSTIN 07AAACN1234F1Z5), invoice NW-1043-R, amount 59,800.00, due date 2026-11-08, PO-7734, status posted | Ledger ERP bill #4 page |
| 19 | `readback:NW-1043-R` | Bill #4 posted in Ledger ERP: vendor Northwind Supplies (GSTIN 07AAACN1234F1Z5), invoice NW-1043-R, amount 59,800.00, due date 2026-11-08, PO-7734, status posted | Ledger ERP bill #4 page |

## Policy decisions
- step 18: allowed — allowed [-]

## Verification (independent, via the admin API)
| ok | assertion | detail |
|---|---|---|
| ✅ | exists ledger/bill {"invoice_number": "NW-1043-R"} {"amount_paise": 5980000, "due_date": "2026-11-08", "po_number": "PO-7734", "vendor_gstin": "07AAACN1234F1Z5", "status": "posted"} | row exists with the expected values |

## Timeline
1. `navigate` {"url": "/portal/invoices"} → opened http://127.0.0.1:8000/portal/login?next=/portal/invoices&reason=signed_out (HTTP 200)
2. `fill_form` {"fields": {"1": "ops.agent", "2": "acme-ops-2026"}, "submit": "3"} → Username: typed "ops.agent"; Password: typed "acme-ops-2026"; clicked "Sign in"
3. `click` {"id": 6} → clicked "View"
4. `read_pdf` {"url": "/portal/invoices/3/pdf"} → PDF text: Northwind Supplies GSTIN 07AAACN1234F1Z5  |  accounts@northwind.example TAX INVOICE  (REVISED) Invoice number: NW-1043-R Invoice date: 2026-10-09 Due date: 2026-11-08 Purchase order: PO-7734
5. `note_fact` {"facts": {"pdf_total": 5980000, "due_date": "2026-11-08", "po": "PO-7734", "vendor_gstin": "07AAACN1234F1Z5"}, "invoice": "NW-1043-R", "source": "PDF /portal/i → noted pdf_total:NW-1043-R = '5980000'; due_date:NW-1043-R = '2026-11-08'; po:NW-1043-R = 'PO-7734'; vendor_gstin:NW-1043-R = '07AAACN1234F1Z5' (source: PDF /portal/invoices/3/pdf)
6. `navigate` {"url": "/ledger/"} → opened http://127.0.0.1:8000/ledger/login?next=/ledger/&reason=signed_out (HTTP 200)
7. `fill_form` {"fields": {"1": "ops.agent", "2": "acme-ops-2026"}, "submit": "3"} → Username: typed "ops.agent"; Password: typed "acme-ops-2026"; clicked "Sign in"
8. `click` {"id": 1} → clicked "Bills"
9. `type` {"id": 5, "text": "NW-1043-R"} → typed "NW-1043-R"
10. `click` {"id": 6} → clicked "Search"
11. `note_fact` {"facts": {"duplicate_check": "none"}, "invoice": "NW-1043-R", "source": "Ledger ERP search for NW-1043-R returned no results"} → noted duplicate_check:NW-1043-R = 'none' (source: Ledger ERP search for NW-1043-R returned no results)
12. `click` {"id": 2} → clicked "New bill"
13. `select` {"id": 5, "option": "Northwind Supplies"} → selected "Northwind Supplies"
14. `type` {"id": 6, "text": "NW-1043-R"} → typed "NW-1043-R"
15. `type` {"id": 7, "text": "59800.00"} → typed "59800.00"
16. `type` {"id": 8, "text": "2026-11-08"} → typed "2026-11-08"
17. `type` {"id": 9, "text": "PO-7734"} → typed "PO-7734"
18. `commit` {"id": 12, "intent": {"type": "create_bill", "system": "ledger", "vendor_name": "Northwind Supplies", "invoice_number": "NW-1043-R", "amount_paise": 5980000, "d → clicked "Save bill"; submitted. Now verify on the page that the record exists with the right values.
19. `note_fact` {"facts": {"readback:NW-1043-R": "Bill #4 posted in Ledger ERP: vendor Northwind Supplies (GSTIN 07AAACN1234F1Z5), invoice NW-1043-R, amount 59,800.00, due date → noted readback:NW-1043-R = 'Bill #4 posted in Ledger ERP: vendor Northwind Supplies (GSTIN 07AAACN1234F1Z5), invoice NW-1043-R, amount 59,800.00, due date 2026-11-08, PO-7734, status posted'; readback
20. `done` {"summary": "Found the latest Northwind Supplies invoice NW-1043-R (revised, supersedes NW-1043) on the Supplier Portal. Read the PDF: total Rs 59,800.00, due d → assertions recorded; verification will decide the status

## Cost
- steps: 20, browser actions: 21, human interventions: 0
- LLM calls: 22, tokens in/out: 52877/2824, est. cost: $0.0170
- wall time: 449s, brain: llm qwen/qwen3.8-27b, memory: off
