"""Ledger ERP: where Acme's clerks record supplier bills.

Bills are saved as drafts or posted. The ERP does not enforce company policy
(approval thresholds, duplicate checks); that is the clerk's job, which is why
the worker needs a policy gate of its own.
"""
import re
import time
from datetime import date

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from company import auth, chaos, db

SYSTEM = "ledger"
STATUSES = ("draft", "posted")


def parse_amount(text):
    """'59,800.00' -> 5980000 paise. Returns None if not a positive amount."""
    cleaned = re.sub(r"[,\s]|rs\.?|inr|₹", "", (text or "").lower())
    try:
        value = round(float(cleaned) * 100)
    except ValueError:
        return None
    return value if value > 0 else None


def parse_date(text):
    try:
        return date.fromisoformat((text or "").strip()).isoformat()
    except ValueError:
        return None


def register(app, templates):
    def render_form(request, user, values, errors, vendors, status=200):
        return templates.TemplateResponse(request, "ledger_bill_form.html", {
            "request": request, "user": user, "v": values, "errors": errors, "vendors": vendors}, status_code=status)

    @app.get("/ledger/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = "/ledger/", reason: str = ""):
        return templates.TemplateResponse(request, "login.html", {
            "request": request, "system": SYSTEM, "title": "Ledger ERP", "next": next, "reason": reason, "error": ""})

    @app.post("/ledger/login")
    def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/ledger/")):
        if auth.check_password(SYSTEM, username, password):
            with db.tx() as con:
                db.audit(con, SYSTEM, username, "login")
            return auth.login(RedirectResponse(next or "/ledger/", status_code=303), SYSTEM, username)
        return templates.TemplateResponse(request, "login.html", {
            "request": request, "system": SYSTEM, "title": "Ledger ERP", "next": next, "reason": "",
            "error": "Invalid username or password."}, status_code=401)

    @app.get("/ledger/logout")
    def logout():
        return auth.logout(RedirectResponse("/ledger/login", status_code=303), SYSTEM)

    @app.get("/ledger", response_class=HTMLResponse)
    @app.get("/ledger/", response_class=HTMLResponse)
    def dashboard(request: Request):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            counts = db.one(con, "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN status='draft' THEN 1 END),0) AS drafts "
                                 "FROM ledger_bills")
        return templates.TemplateResponse(request, "ledger_dashboard.html", {"request": request, "user": user, "counts": counts})

    @app.get("/ledger/bills", response_class=HTMLResponse)
    def bills(request: Request, q: str = ""):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            sql = ("SELECT b.*, v.name AS vendor_name FROM ledger_bills b JOIN ledger_vendors v ON v.id = b.vendor_id")
            args = []
            if q:
                sql += " WHERE b.invoice_number LIKE ? OR v.name LIKE ? OR b.po_number LIKE ?"
                args += [f"%{q}%"] * 3
            sql += " ORDER BY b.id DESC"
            items = db.rows(con, sql, *args)
        return templates.TemplateResponse(request, "ledger_bills.html", {"request": request, "user": user, "items": items, "q": q})

    @app.get("/ledger/vendors", response_class=HTMLResponse)
    def vendors(request: Request):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            items = db.rows(con, "SELECT * FROM ledger_vendors ORDER BY name")
        return templates.TemplateResponse(request, "ledger_vendors.html", {"request": request, "user": user, "items": items})

    @app.get("/ledger/bills/new", response_class=HTMLResponse)
    def new_bill(request: Request):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            vendors = db.rows(con, "SELECT * FROM ledger_vendors WHERE active = 1 ORDER BY name")
        return render_form(request, user, {}, {}, vendors)

    @app.post("/ledger/bills/new")
    def create_bill(request: Request, vendor_id: str = Form(""), invoice_number: str = Form(""),
                    amount: str = Form(""), due_date: str = Form(""), po_number: str = Form(""),
                    approved_by: str = Form(""), memo: str = Form(""), action: str = Form("post")):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        values = dict(vendor_id=vendor_id, invoice_number=invoice_number.strip(), amount=amount, due_date=due_date,
                      po_number=po_number.strip(), approved_by=approved_by.strip(), memo=memo.strip(), action=action)
        errors = {}
        with db.tx() as con:
            vendors = db.rows(con, "SELECT * FROM ledger_vendors WHERE active = 1 ORDER BY name")
            vendor = db.one(con, "SELECT * FROM ledger_vendors WHERE id = ? AND active = 1", vendor_id) if vendor_id.isdigit() else None
        if not vendor:
            errors["vendor_id"] = "Choose a vendor."
        if not values["invoice_number"]:
            errors["invoice_number"] = "Invoice number is required."
        paise = parse_amount(amount)
        if paise is None:
            errors["amount"] = "Enter a positive amount, e.g. 59,800.00."
        due = parse_date(due_date)
        if due is None:
            errors["due_date"] = "Enter the due date as YYYY-MM-DD."
        status = "posted" if action == "post" else "draft"
        if errors:
            return render_form(request, user, values, errors, vendors, status=400)
        now = time.time()
        with db.tx() as con:
            cur = con.execute(
                "INSERT INTO ledger_bills (vendor_id, invoice_number, amount_paise, due_date, po_number, status, "
                "approved_by, memo, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (vendor["id"], values["invoice_number"], paise, due, values["po_number"] or None, status,
                 values["approved_by"] or None, values["memo"] or None, user, now, now))
            bill_id = cur.lastrowid
            db.audit(con, SYSTEM, user, "create_bill", bill_id=bill_id, vendor=vendor["name"],
                     invoice_number=values["invoice_number"], amount_paise=paise, status=status)
        if chaos.roll("commit_then_502"):
            with db.tx() as con:
                db.audit(con, "chaos", "chaos", "commit_then_502", bill_id=bill_id)
            return HTMLResponse("<h1>502 Bad Gateway</h1><p>The upstream server returned an invalid response.</p>",
                                status_code=502)
        return RedirectResponse(f"/ledger/bills/{bill_id}?flash=saved", status_code=303)

    @app.get("/ledger/bills/{bid}", response_class=HTMLResponse)
    def bill(request: Request, bid: int, flash: str = ""):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            item = db.one(con, "SELECT b.*, v.name AS vendor_name, v.gstin FROM ledger_bills b "
                               "JOIN ledger_vendors v ON v.id = b.vendor_id WHERE b.id = ?", bid)
        if not item:
            return HTMLResponse("<h1>404 Not found</h1>", status_code=404)
        return templates.TemplateResponse(request, "ledger_bill.html", {"request": request, "user": user, "b": item, "flash": flash})

    @app.post("/ledger/bills/{bid}/post")
    def post_bill(request: Request, bid: int, approved_by: str = Form("")):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        now = time.time()
        with db.tx() as con:
            item = db.one(con, "SELECT * FROM ledger_bills WHERE id = ?", bid)
            if not item:
                return HTMLResponse("<h1>404 Not found</h1>", status_code=404)
            con.execute("UPDATE ledger_bills SET status = 'posted', approved_by = COALESCE(NULLIF(?, ''), approved_by), "
                        "updated_at = ? WHERE id = ?", (approved_by.strip(), now, bid))
            db.audit(con, SYSTEM, user, "post_bill", bill_id=bid, approved_by=approved_by.strip() or item["approved_by"])
        if chaos.roll("commit_then_502"):
            return HTMLResponse("<h1>502 Bad Gateway</h1>", status_code=502)
        return RedirectResponse(f"/ledger/bills/{bid}?flash=posted", status_code=303)
