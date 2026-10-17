# Acme Robotics — Ops handbook (accounts payable excerpt)

## SOP-AP-01: Recording a supplier invoice

1. **Find the invoice on the Supplier Portal.** Filter by supplier. Open the invoice and
   download the PDF. The PDF is the document of record: the amount, due date and purchase
   order on the PDF win over the portal listing, which suppliers type by hand.
2. **Check for revisions.** Suppliers sometimes issue a revised invoice (`-R` suffix) that
   supersedes an earlier one. Record the revision, never the superseded original. Revisions
   are usually announced by mail to the ops mailbox.
3. **Check for duplicates.** Search the ERP for the invoice number before entering it. If it is
   already recorded, do not enter it again; report it instead.
4. **Match the vendor by GSTIN, not by name.** Vendor masters contain stale or near-duplicate
   records. The GSTIN on the PDF identifies the right vendor; the ERP's Vendors page lists GSTINs.
5. **Enter the bill** with the invoice number, the PDF total, the due date and the PO number.
6. **Approval.** Bills at or above the approval threshold (currently Rs 1,00,000) must be
   approved by the finance manager before posting. Ask, record the approver, then post.
7. **Verify.** After saving, open the bill (or the list) and confirm the record exists with the
   right values before reporting done.

## Systems

- **Ledger ERP** serves the Delhi unit. Dates are `YYYY-MM-DD`.
- **NovaBooks** serves the Pune unit. It calls bills "payables", the vendor a "supplier", the
  invoice number the "reference", the amount the "total" and the due date "pay by"
  (`dd/mm/yyyy`). Recording is a three-step wizard; nothing is saved until you confirm.
- **Acme Mail** holds supplier correspondence. Check it when something about an invoice looks off.

## Conduct

- When a request is ambiguous (two invoices could match, two vendors could match and the
  GSTIN does not settle it), ask before writing anything.
- Never retry a submit blindly after an error. Read the list first: the record may already exist.
- Report what you did with evidence: which records changed, and what you checked.
