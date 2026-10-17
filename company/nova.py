"""NovaBooks: a second ERP the worker has never seen.

Same job as Ledger (record a supplier invoice) with different words, a
three-step wizard instead of one form, dd/mm/yyyy dates, and its own login.
The worker's code is frozen before it meets this app; only its company
knowledge and skills carry over. That is the generalization test.
"""
import re
import time
from datetime import datetime

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from company import auth, chaos, db
from company.ledger import parse_amount

SYSTEM = "nova"


def parse_dmy(text):
    try:
        return datetime.strptime((text or "").strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def register(app, templates):
    @app.get("/nova/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = "/nova/", reason: str = ""):
        return templates.TemplateResponse(request, "login.html", {
            "request": request, "system": SYSTEM, "title": "NovaBooks", "next": next, "reason": reason, "error": ""})

    @app.post("/nova/login")
    def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/nova/")):
        if auth.check_password(SYSTEM, username, password):
            with db.tx() as con:
                db.audit(con, SYSTEM, username, "login")
            return auth.login(RedirectResponse(next or "/nova/", status_code=303), SYSTEM, username)
        return templates.TemplateResponse(request, "login.html", {
            "request": request, "system": SYSTEM, "title": "NovaBooks", "next": next, "reason": "",
            "error": "Sign-in failed. Check your credentials."}, status_code=401)

    @app.get("/nova/logout")
    def logout():
        return auth.logout(RedirectResponse("/nova/login", status_code=303), SYSTEM)

    @app.get("/nova", response_class=HTMLResponse)
    @app.get("/nova/", response_class=HTMLResponse)
    def home(request: Request):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        return templates.TemplateResponse(request, "nova_home.html", {"request": request, "user": user})

    @app.get("/nova/payables", response_class=HTMLResponse)
    def payables(request: Request, search: str = ""):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            sql = "SELECT p.*, s.name AS supplier_name FROM nova_payables p JOIN nova_suppliers s ON s.id = p.supplier_id"
            args = []
            if search:
                sql += " WHERE p.reference LIKE ? OR s.name LIKE ?"
                args += [f"%{search}%"] * 2
            sql += " ORDER BY p.id DESC"
            items = db.rows(con, sql, *args)
        return templates.TemplateResponse(request, "nova_payables.html", {"request": request, "user": user, "items": items, "search": search})

    @app.get("/nova/suppliers", response_class=HTMLResponse)
    def suppliers(request: Request):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            items = db.rows(con, "SELECT * FROM nova_suppliers ORDER BY name")
        return templates.TemplateResponse(request, "nova_suppliers.html", {"request": request, "user": user, "items": items})

    # ---- three-step wizard: supplier -> details -> review -> saved
    @app.get("/nova/payables/record", response_class=HTMLResponse)
    def wizard_step1(request: Request):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            suppliers_ = db.rows(con, "SELECT * FROM nova_suppliers WHERE active = 1 ORDER BY name")
        return templates.TemplateResponse(request, "nova_step1.html", {"request": request, "user": user, "suppliers": suppliers_, "error": ""})

    @app.post("/nova/payables/record/details", response_class=HTMLResponse)
    def wizard_step2(request: Request, supplier_id: str = Form("")):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            supplier = db.one(con, "SELECT * FROM nova_suppliers WHERE id = ?", supplier_id) if supplier_id.isdigit() else None
            suppliers_ = db.rows(con, "SELECT * FROM nova_suppliers WHERE active = 1 ORDER BY name")
        if not supplier:
            return templates.TemplateResponse(request, "nova_step1.html", {
                "request": request, "user": user, "suppliers": suppliers_, "error": "Pick a supplier first."}, status_code=400)
        return templates.TemplateResponse(request, "nova_step2.html", {"request": request, "user": user, "s": supplier, "v": {}, "errors": {}})

    @app.post("/nova/payables/record/review", response_class=HTMLResponse)
    def wizard_step3(request: Request, supplier_id: str = Form(""), reference: str = Form(""), total: str = Form(""),
                     pay_by: str = Form(""), order_ref: str = Form(""), authorised_by: str = Form(""), note: str = Form("")):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            supplier = db.one(con, "SELECT * FROM nova_suppliers WHERE id = ?", supplier_id) if supplier_id.isdigit() else None
        if not supplier:
            return RedirectResponse("/nova/payables/record", status_code=303)
        values = dict(reference=reference.strip(), total=total, pay_by=pay_by, order_ref=order_ref.strip(),
                      authorised_by=authorised_by.strip(), note=note.strip())
        errors = {}
        if not values["reference"]:
            errors["reference"] = "Reference is required."
        paise = parse_amount(total)
        if paise is None:
            errors["total"] = "Enter a positive total."
        iso = parse_dmy(pay_by)
        if iso is None:
            errors["pay_by"] = "Use the format dd/mm/yyyy."
        if errors:
            return templates.TemplateResponse(request, "nova_step2.html", {
                "request": request, "user": user, "s": supplier, "v": values, "errors": errors}, status_code=400)
        return templates.TemplateResponse(request, "nova_step3.html", {
            "request": request, "user": user, "s": supplier, "v": values, "paise": paise, "iso": iso})

    @app.post("/nova/payables/record/confirm")
    def wizard_confirm(request: Request, supplier_id: str = Form(""), reference: str = Form(""), total_paise: str = Form(""),
                       pay_by_iso: str = Form(""), order_ref: str = Form(""), authorised_by: str = Form(""),
                       note: str = Form(""), state: str = Form("recorded")):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        if not (supplier_id.isdigit() and total_paise.isdigit() and reference.strip()):
            return RedirectResponse("/nova/payables/record", status_code=303)
        now = time.time()
        state = "parked" if state == "parked" else "recorded"
        with db.tx() as con:
            supplier = db.one(con, "SELECT * FROM nova_suppliers WHERE id = ?", supplier_id)
            cur = con.execute(
                "INSERT INTO nova_payables (supplier_id, reference, total_paise, pay_by, order_ref, state, "
                "authorised_by, note, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (int(supplier_id), reference.strip(), int(total_paise), pay_by_iso, order_ref.strip() or None,
                 state, authorised_by.strip() or None, note.strip() or None, user, now, now))
            pid = cur.lastrowid
            db.audit(con, SYSTEM, user, "record_payable", payable_id=pid, supplier=supplier["name"],
                     reference=reference.strip(), total_paise=int(total_paise), state=state)
        if chaos.roll("commit_then_502"):
            return HTMLResponse("<h1>502 Bad Gateway</h1>", status_code=502)
        return RedirectResponse(f"/nova/payables/{pid}?flash=saved", status_code=303)

    @app.get("/nova/payables/{pid}", response_class=HTMLResponse)
    def payable(request: Request, pid: int, flash: str = ""):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            item = db.one(con, "SELECT p.*, s.name AS supplier_name, s.tax_id FROM nova_payables p "
                               "JOIN nova_suppliers s ON s.id = p.supplier_id WHERE p.id = ?", pid)
        if not item:
            return HTMLResponse("<h1>404 Not found</h1>", status_code=404)
        return templates.TemplateResponse(request, "nova_payable.html", {"request": request, "user": user, "p": item, "flash": flash})
