"""Seed the simulated company: Acme Robotics Pvt Ltd.

The data is small but deliberately realistic. Several details only show up if
the worker reads things instead of guessing. Each one is something a real
clerk gets caught by:

- Northwind's latest invoice was REVISED: NW-1043-R supersedes NW-1043 and has
  a different amount. The portal lists both; a mail from Northwind explains.
- Brightline's portal list price differs from the amount on the PDF (the PDF
  adds freight). The PDF is the document of record.
- Kestrel's KL-0915 already exists in Ledger: entering it again is a duplicate.
- Meridian's MM-0882 is above the approval threshold in the company policy.
- Ledger's vendor master has a stale near-duplicate, "Northwind Supplies Ltd",
  with a different GSTIN. Match vendors by GSTIN, not by name.
- NovaBooks (the unseen ERP) has the same traps with different words.

Run: python -m company.seed
"""
import shutil
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from company import db

PDF_DIR = db.VAR / "pdfs"

# (id, name, gstin, email)
PORTAL_VENDORS = [
    (1, "Northwind Supplies", "07AAACN1234F1Z5", "accounts@northwind.example"),
    (2, "Brightline Components", "29AABCB5678K1Z2", "billing@brightline.example"),
    (3, "Kestrel Logistics", "27AAACK9012M1Z8", "finance@kestrel.example"),
    (4, "Orbit Office Supplies", "06AAACO3456P1Z1", "ar@orbit.example"),
    (5, "Meridian Metals", "24AAACM7890R1Z6", "invoices@meridian.example"),
]

# (id, name, gstin, active). Note the stale near-duplicate for Northwind.
LEDGER_VENDORS = [
    (11, "Northwind Supplies", "07AAACN1234F1Z5", 1),
    (12, "Northwind Supplies Ltd", "09AABCN9999Q1Z3", 1),
    (13, "Brightline Components", "29AABCB5678K1Z2", 1),
    (14, "Kestrel Logistics", "27AAACK9012M1Z8", 1),
    (15, "Orbit Office Supplies", "06AAACO3456P1Z1", 1),
    (16, "Meridian Metals", "24AAACM7890R1Z6", 1),
    (17, "Zenith Packaging", "33AAACZ1111T1Z9", 1),
]

NOVA_SUPPLIERS = [
    (21, "Brightline Components", "29AABCB5678K1Z2", 1),
    (22, "Kestrel Logistics", "27AAACK9012M1Z8", 1),
    (23, "Meridian Metals", "24AAACM7890R1Z6", 1),
    (24, "Northwind Supplies (old)", "09AABCN9999Q1Z3", 1),
    (25, "Northwind Supplies", "07AAACN1234F1Z5", 1),
    (26, "Orbit Office Supplies", "06AAACO3456P1Z1", 1),
]

# (id, vendor_id, number, issued_on, listed_paise, pdf_paise, status, due, po, supersedes, lines)
INVOICES = [
    (1, 1, "NW-1038", "2026-09-02", 4_850_000, 4_850_000, "paid", "2026-10-02", "PO-7710", None,
     [("Servo motor SM-40", 10, 485_000)]),
    (2, 1, "NW-1043", "2026-10-06", 6_200_000, 6_200_000, "superseded", "2026-11-05", "PO-7734", None,
     [("Linear actuator LA-220", 8, 775_000)]),
    (3, 1, "NW-1043-R", "2026-10-09", 5_980_000, 5_980_000, "open", "2026-11-08", "PO-7734", "NW-1043",
     [("Linear actuator LA-220", 8, 747_500)]),
    (4, 2, "BL-2207", "2026-10-03", 3_200_000, 3_480_000, "open", "2026-10-31", "PO-7729", None,
     [("PCB assembly rev C", 40, 80_000), ("Freight", 1, 280_000)]),
    (5, 3, "KL-0915", "2026-09-28", 1_875_000, 1_875_000, "open", "2026-10-28", None, None,
     [("Freight Pune-Delhi, 3 pallets", 1, 1_875_000)]),
    (6, 4, "OR-5521", "2026-10-07", 640_000, 640_000, "open", "2026-10-21", "PO-7741", None,
     [("Office chairs", 4, 160_000)]),
    (7, 5, "MM-0882", "2026-10-08", 23_450_000, 23_450_000, "open", "2026-11-07", "PO-7738", None,
     [("Aluminium plate 6061, 10 mm", 50, 469_000)]),
]

# (username, system, password, role)
USERS = [
    ("ops.agent", "portal", "acme-ops-2026", "buyer"),
    ("ops.agent", "ledger", "acme-ops-2026", "clerk"),
    ("ops.agent", "nova", "acme-ops-2026", "clerk"),
    ("ops.agent", "mail", "acme-ops-2026", "user"),
    ("priya.manager", "ledger", "manager-pass", "manager"),
    ("priya.manager", "nova", "manager-pass", "manager"),
]

MAIL = [
    ("accounts@northwind.example", "ops@acme.example", "Revised invoice for PO-7734",
     "Hello Acme team,\n\nWe have issued a revised invoice NW-1043-R for PO-7734. It replaces NW-1043 "
     "(a pricing correction on the LA-220 actuators). Please disregard NW-1043.\n\nRegards,\nNorthwind Accounts",
     "2026-10-09 10:12"),
    ("it-helpdesk@acme.example", "ops@acme.example", "Portal password rotation",
     "Reminder: supplier portal passwords rotate quarterly. No action needed this month.", "2026-10-01 09:00"),
    ("billing@brightline.example", "ops@acme.example", "Invoice BL-2207",
     "Hi,\n\nInvoice BL-2207 is now on the portal. Freight has been added to the invoice total as agreed.\n\n"
     "Thanks,\nBrightline Billing", "2026-10-03 16:40"),
    ("priya.manager@acme.example", "ops@acme.example", "Month-end",
     "Team, please have all October supplier invoices recorded by the 25th. Thanks, Priya", "2026-10-10 08:30"),
]

# Bills that already exist in Ledger before the worker starts.
EXISTING_LEDGER_BILLS = [
    # vendor_id, invoice_number, amount_paise, due, po, status, approved_by, created_by
    (11, "NW-1038", 4_850_000, "2026-10-02", "PO-7710", "posted", None, "meera.clerk"),
    (14, "KL-0915", 1_875_000, "2026-10-28", None, "posted", None, "meera.clerk"),
    (17, "ZP-0310", 910_000, "2026-10-15", "PO-7702", "posted", None, "meera.clerk"),
]
EXISTING_NOVA_PAYABLES = [
    (22, "KL-0915", 1_875_000, "2026-10-28", None, "recorded", None, "meera.clerk"),
    (25, "NW-1038", 4_850_000, "2026-10-02", "PO-7710", "recorded", None, "meera.clerk"),
]


def rupees(paise):
    return f"Rs {paise // 100:,}.{paise % 100:02d}"


def make_pdf(path, vendor, inv):
    _, _, number, issued, _, pdf_paise, _, due, po, supersedes, lines = inv
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, h - 60, vendor[1])
    c.setFont("Helvetica", 10)
    c.drawString(50, h - 78, f"GSTIN {vendor[2]}  |  {vendor[3]}")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, h - 120, "TAX INVOICE" + ("  (REVISED)" if supersedes else ""))
    c.setFont("Helvetica", 11)
    y = h - 150
    for label, value in [("Invoice number", number), ("Invoice date", issued), ("Due date", due),
                         ("Purchase order", po or "-"), ("Bill to", "Acme Robotics Pvt Ltd, New Delhi")]:
        c.drawString(50, y, f"{label}:")
        c.drawString(180, y, value)
        y -= 18
    if supersedes:
        c.drawString(50, y, f"This invoice supersedes {supersedes}.")
        y -= 18
    y -= 12
    c.setFont("Helvetica-Bold", 11)
    for x, t in [(50, "Item"), (330, "Qty"), (390, "Unit price"), (480, "Amount")]:
        c.drawString(x, y, t)
    c.setFont("Helvetica", 11)
    for item, qty, unit in lines:
        y -= 18
        c.drawString(50, y, item); c.drawString(330, y, str(qty))
        c.drawString(390, y, rupees(unit)); c.drawString(480, y, rupees(qty * unit))
    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.drawString(330, y, "Total due (INR):")
    c.drawString(480, y, rupees(pdf_paise))
    c.showPage()
    c.save()


def seed(quiet=False):
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db.DB_PATH) + suffix)
        if p.exists():
            p.unlink()
    shutil.rmtree(PDF_DIR, ignore_errors=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    db.init()
    vendors = {v[0]: v for v in PORTAL_VENDORS}
    with db.tx() as con:
        con.executemany("INSERT INTO users VALUES (?, ?, ?, ?)", USERS)
        con.executemany("INSERT INTO portal_vendors VALUES (?, ?, ?, ?)", PORTAL_VENDORS)
        con.executemany("INSERT INTO ledger_vendors VALUES (?, ?, ?, ?)", LEDGER_VENDORS)
        con.executemany("INSERT INTO nova_suppliers VALUES (?, ?, ?, ?)", NOVA_SUPPLIERS)
        for inv in INVOICES:
            iid, vid, number, issued, listed, _pdf, status, _due, _po, sup, _lines = inv
            pdf_name = f"{number}.pdf"
            make_pdf(PDF_DIR / pdf_name, vendors[vid], inv)
            con.execute("INSERT INTO portal_invoices VALUES (?, ?, ?, ?, ?, 'INR', ?, ?, ?)",
                        (iid, vid, number, issued, listed, status, pdf_name, sup))
        for vid, num, amt, due, po, status, approver, by in EXISTING_LEDGER_BILLS:
            con.execute("INSERT INTO ledger_bills (vendor_id, invoice_number, amount_paise, due_date, po_number, "
                        "status, approved_by, memo, created_by, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 1759000000, 1759000000)",
                        (vid, num, amt, due, po, status, approver, by))
        for sid, ref, total, pay_by, order_ref, state, auth, by in EXISTING_NOVA_PAYABLES:
            con.execute("INSERT INTO nova_payables (supplier_id, reference, total_paise, pay_by, order_ref, "
                        "state, authorised_by, note, created_by, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 1759000000, 1759000000)",
                        (sid, ref, total, pay_by, order_ref, state, auth, by))
        for sender, recipient, subject, body, received in MAIL:
            con.execute("INSERT INTO mail (sender, recipient, subject, body, received_at) VALUES (?, ?, ?, ?, ?)",
                        (sender, recipient, subject, body, received))
        db.audit(con, "admin", "seed", "reset", invoices=len(INVOICES))
    if not quiet:
        print(f"seeded {len(INVOICES)} portal invoices, {len(MAIL)} mails, PDFs in {PDF_DIR}")


if __name__ == "__main__":
    seed()
