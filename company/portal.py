"""Supplier invoice portal: where vendors publish invoices for Acme."""
from fastapi import Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from company import auth, db
from company.seed import PDF_DIR

SYSTEM = "portal"


def register(app, templates):
    @app.get("/portal/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = "/portal/invoices", reason: str = ""):
        return templates.TemplateResponse(request, "login.html", {
            "request": request, "system": SYSTEM, "title": "Supplier Portal", "next": next, "reason": reason, "error": ""})

    @app.post("/portal/login")
    def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/portal/invoices")):
        if auth.check_password(SYSTEM, username, password):
            with db.tx() as con:
                db.audit(con, SYSTEM, username, "login")
            return auth.login(RedirectResponse(next or "/portal/invoices", status_code=303), SYSTEM, username)
        return templates.TemplateResponse(request, "login.html", {
            "request": request, "system": SYSTEM, "title": "Supplier Portal", "next": next, "reason": "",
            "error": "Invalid username or password."}, status_code=401)

    @app.get("/portal/logout")
    def logout():
        return auth.logout(RedirectResponse("/portal/login", status_code=303), SYSTEM)

    @app.get("/portal", response_class=HTMLResponse)
    @app.get("/portal/", response_class=HTMLResponse)
    def index(request: Request):
        return RedirectResponse("/portal/invoices", status_code=303)

    @app.get("/portal/invoices", response_class=HTMLResponse)
    def invoices(request: Request, vendor: str = "", status: str = ""):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            vendors = db.rows(con, "SELECT * FROM portal_vendors ORDER BY name")
            sql = ("SELECT i.*, v.name AS vendor_name FROM portal_invoices i JOIN portal_vendors v ON v.id = i.vendor_id "
                   "WHERE 1=1")
            args = []
            if vendor:
                sql += " AND v.name LIKE ?"
                args.append(f"%{vendor}%")
            if status:
                sql += " AND i.status = ?"
                args.append(status)
            sql += " ORDER BY i.issued_on DESC, i.id DESC"
            items = db.rows(con, sql, *args)
        return templates.TemplateResponse(request, "portal_invoices.html", {
            "request": request, "user": user, "vendors": vendors, "items": items, "vendor": vendor, "status": status})

    @app.get("/portal/invoices/{iid}", response_class=HTMLResponse)
    def invoice(request: Request, iid: int):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            inv = db.one(con, "SELECT i.*, v.name AS vendor_name, v.gstin, v.email FROM portal_invoices i "
                              "JOIN portal_vendors v ON v.id = i.vendor_id WHERE i.id = ?", iid)
            if not inv:
                return HTMLResponse("<h1>404 Not found</h1>", status_code=404)
            replacement = db.one(con, "SELECT id, number FROM portal_invoices WHERE supersedes = ?", inv["number"])
            db.audit(con, SYSTEM, user, "view_invoice", invoice=inv["number"])
        return templates.TemplateResponse(request, "portal_invoice.html", {
            "request": request, "user": user, "inv": inv, "replacement": replacement})

    @app.get("/portal/invoices/{iid}/pdf")
    def invoice_pdf(request: Request, iid: int):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            inv = db.one(con, "SELECT * FROM portal_invoices WHERE id = ?", iid)
            if not inv:
                return HTMLResponse("<h1>404 Not found</h1>", status_code=404)
            db.audit(con, SYSTEM, user, "download_pdf", invoice=inv["number"])
        return FileResponse(PDF_DIR / inv["pdf_name"], media_type="application/pdf", filename=inv["pdf_name"])
